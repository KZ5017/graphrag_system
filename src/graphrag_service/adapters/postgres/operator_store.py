from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from graphrag_service.adapters.postgres.extraction_models import (
    ExtractionChunkModel,
    ExtractionRunModel,
)
from graphrag_service.adapters.postgres.ingest_models import (
    ChunkModel,
    DocumentModel,
    DocumentVersionModel,
    ScanChangeModel,
    ScanRunModel,
    VaultModel,
)
from graphrag_service.adapters.postgres.models import JobModel
from graphrag_service.adapters.postgres.projection_models import ProjectionOutboxModel
from graphrag_service.adapters.postgres.resolution_models import (
    ClaimModel,
    EntityModel,
    Neo4jProjectionRunModel,
    RelationshipAssertionModel,
)


@dataclass(frozen=True, slots=True)
class OperatorVaultState:
    id: UUID
    name: str
    document_count: int
    chunk_count: int
    entity_count: int
    relationship_count: int
    claim_count: int
    latest_scan_status: str | None
    latest_scan_finished_at: datetime | None
    latest_graph_status: str | None
    latest_graph_finished_at: datetime | None
    qdrant_pending: int
    qdrant_failed: int


@dataclass(frozen=True, slots=True)
class OperatorDocument:
    id: UUID
    relative_path: str
    lifecycle_status: str
    processing_status: str | None


@dataclass(frozen=True, slots=True)
class OperatorPendingDocument:
    id: UUID
    relative_path: str
    extraction_run_id: UUID | None


@dataclass(frozen=True, slots=True)
class OperatorPendingRefresh:
    scan_id: UUID | None
    scan_finished_at: datetime | None
    graph_refresh_required: bool
    documents: tuple[OperatorPendingDocument, ...]


@dataclass(frozen=True, slots=True)
class OperatorJob:
    id: UUID
    job_type: str
    status: str
    checkpoint: dict[str, Any]
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class PostgresOperatorStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def vault_states(self) -> list[OperatorVaultState]:
        async with self._sessions() as session:
            vaults = list(
                await session.scalars(
                    select(VaultModel)
                    .where(VaultModel.status == "active")
                    .order_by(VaultModel.name)
                )
            )
            return [await self._vault_state(session, vault) for vault in vaults]

    async def documents(self, vault_id: UUID) -> list[OperatorDocument]:
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(
                        DocumentModel.id,
                        DocumentModel.current_relative_path,
                        DocumentModel.lifecycle_status,
                        DocumentVersionModel.processing_status,
                    )
                    .outerjoin(
                        DocumentVersionModel,
                        DocumentVersionModel.id == DocumentModel.current_version_id,
                    )
                    .where(DocumentModel.vault_id == vault_id)
                    .order_by(DocumentModel.current_relative_path)
                )
            ).all()
        return [
            OperatorDocument(
                id=row.id,
                relative_path=row.current_relative_path,
                lifecycle_status=row.lifecycle_status,
                processing_status=row.processing_status,
            )
            for row in rows
        ]

    async def pending_refresh(self, vault_id: UUID) -> OperatorPendingRefresh:
        async with self._sessions() as session:
            latest_scan = await session.scalar(
                select(ScanRunModel)
                .where(
                    ScanRunModel.vault_id == vault_id,
                    ScanRunModel.status == "succeeded",
                    ScanRunModel.scan_type != "measure",
                    (
                        ScanRunModel.new_count
                        + ScanRunModel.modified_count
                        + ScanRunModel.renamed_count
                        + ScanRunModel.deleted_count
                    )
                    > 0,
                )
                .order_by(ScanRunModel.finished_at.desc())
                .limit(1)
            )
            if latest_scan is None:
                return OperatorPendingRefresh(None, None, False, ())
            latest_graph = await session.scalar(
                select(Neo4jProjectionRunModel)
                .where(
                    Neo4jProjectionRunModel.vault_id == vault_id,
                    Neo4jProjectionRunModel.status == "succeeded",
                )
                .order_by(Neo4jProjectionRunModel.finished_at.desc())
                .limit(1)
            )
            if (
                latest_graph is not None
                and latest_graph.finished_at is not None
                and latest_scan.finished_at is not None
                and latest_graph.finished_at >= latest_scan.finished_at
            ):
                return OperatorPendingRefresh(latest_scan.id, latest_scan.finished_at, False, ())
            changed_rows = (
                await session.execute(
                    select(
                        ScanChangeModel.document_id,
                        ScanChangeModel.new_relative_path,
                    )
                    .where(
                        ScanChangeModel.scan_id == latest_scan.id,
                        ScanChangeModel.change_kind.in_(["created", "modified"]),
                        ScanChangeModel.document_id.is_not(None),
                        ScanChangeModel.new_relative_path.is_not(None),
                    )
                    .order_by(ScanChangeModel.new_relative_path)
                )
            ).all()
            document_ids = [row.document_id for row in changed_rows]
            extracted: dict[UUID, UUID] = {}
            if document_ids:
                extraction_rows = (
                    await session.execute(
                        select(
                            DocumentModel.id,
                            ExtractionRunModel.id,
                            ExtractionRunModel.created_at,
                        )
                        .join(
                            DocumentVersionModel,
                            DocumentVersionModel.id == DocumentModel.current_version_id,
                        )
                        .join(
                            ChunkModel,
                            ChunkModel.document_version_id == DocumentVersionModel.id,
                        )
                        .join(
                            ExtractionChunkModel,
                            ExtractionChunkModel.chunk_id == ChunkModel.id,
                        )
                        .join(
                            ExtractionRunModel,
                            ExtractionRunModel.id == ExtractionChunkModel.extraction_run_id,
                        )
                        .where(
                            DocumentModel.id.in_(document_ids),
                            ExtractionRunModel.created_at >= latest_scan.started_at,
                            ExtractionRunModel.status.in_(["succeeded", "partial"]),
                        )
                        .order_by(ExtractionRunModel.created_at.desc())
                    )
                ).all()
                for document_id, run_id, _ in extraction_rows:
                    extracted.setdefault(document_id, run_id)
            return OperatorPendingRefresh(
                scan_id=latest_scan.id,
                scan_finished_at=latest_scan.finished_at,
                graph_refresh_required=True,
                documents=tuple(
                    OperatorPendingDocument(
                        id=row.document_id,
                        relative_path=row.new_relative_path,
                        extraction_run_id=extracted.get(row.document_id),
                    )
                    for row in changed_rows
                ),
            )

    async def recent_jobs(self, limit: int = 24) -> list[OperatorJob]:
        async with self._sessions() as session:
            rows = list(
                await session.scalars(
                    select(JobModel).order_by(JobModel.created_at.desc()).limit(limit)
                )
            )
        return [
            OperatorJob(
                id=row.id,
                job_type=row.job_type,
                status=row.status,
                checkpoint=dict(row.checkpoint_json),
                error_code=row.error_code,
                error_message=row.error_message,
                created_at=row.created_at,
                started_at=row.started_at,
                finished_at=row.finished_at,
            )
            for row in rows
        ]

    async def _vault_state(self, session: AsyncSession, vault: VaultModel) -> OperatorVaultState:
        document_count = await session.scalar(
            select(func.count())
            .select_from(DocumentModel)
            .where(
                DocumentModel.vault_id == vault.id,
                DocumentModel.lifecycle_status == "active",
            )
        )
        chunk_count = await session.scalar(
            select(func.count())
            .select_from(ChunkModel)
            .join(
                DocumentVersionModel,
                DocumentVersionModel.id == ChunkModel.document_version_id,
            )
            .join(
                DocumentModel,
                DocumentModel.current_version_id == DocumentVersionModel.id,
            )
            .where(
                DocumentModel.vault_id == vault.id,
                DocumentModel.lifecycle_status == "active",
            )
        )
        entity_count = await session.scalar(
            select(func.count())
            .select_from(EntityModel)
            .where(EntityModel.vault_id == vault.id, EntityModel.status == "active")
        )
        relationship_count = await session.scalar(
            select(func.count())
            .select_from(RelationshipAssertionModel)
            .join(
                ExtractionRunModel,
                ExtractionRunModel.id == RelationshipAssertionModel.extraction_run_id,
            )
            .where(
                ExtractionRunModel.vault_id == vault.id,
                RelationshipAssertionModel.status == "active",
            )
        )
        claim_count = await session.scalar(
            select(func.count())
            .select_from(ClaimModel)
            .join(
                ExtractionRunModel,
                ExtractionRunModel.id == ClaimModel.extraction_run_id,
            )
            .where(
                ExtractionRunModel.vault_id == vault.id,
                ClaimModel.status == "active",
            )
        )
        latest_scan = await session.scalar(
            select(ScanRunModel)
            .where(ScanRunModel.vault_id == vault.id)
            .order_by(ScanRunModel.started_at.desc())
            .limit(1)
        )
        latest_graph = await session.scalar(
            select(Neo4jProjectionRunModel)
            .where(Neo4jProjectionRunModel.vault_id == vault.id)
            .order_by(Neo4jProjectionRunModel.created_at.desc())
            .limit(1)
        )
        qdrant_counts = dict(
            (
                await session.execute(
                    select(ProjectionOutboxModel.status, func.count())
                    .join(
                        ChunkModel,
                        ChunkModel.id == ProjectionOutboxModel.object_id,
                    )
                    .join(
                        DocumentVersionModel,
                        DocumentVersionModel.id == ChunkModel.document_version_id,
                    )
                    .join(
                        DocumentModel,
                        DocumentModel.current_version_id == DocumentVersionModel.id,
                    )
                    .where(
                        ProjectionOutboxModel.target == "qdrant",
                        DocumentModel.vault_id == vault.id,
                        ProjectionOutboxModel.status.in_(["pending", "processing", "failed"]),
                    )
                    .group_by(ProjectionOutboxModel.status)
                )
            ).all()
        )
        return OperatorVaultState(
            id=vault.id,
            name=vault.name,
            document_count=int(document_count or 0),
            chunk_count=int(chunk_count or 0),
            entity_count=int(entity_count or 0),
            relationship_count=int(relationship_count or 0),
            claim_count=int(claim_count or 0),
            latest_scan_status=latest_scan.status if latest_scan else None,
            latest_scan_finished_at=latest_scan.finished_at if latest_scan else None,
            latest_graph_status=latest_graph.status if latest_graph else None,
            latest_graph_finished_at=(latest_graph.finished_at if latest_graph else None),
            qdrant_pending=int(qdrant_counts.get("pending", 0))
            + int(qdrant_counts.get("processing", 0)),
            qdrant_failed=int(qdrant_counts.get("failed", 0)),
        )
