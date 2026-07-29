from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from graphrag_service.adapters.postgres.ingest_models import (
    ChunkModel,
    DocumentModel,
    DocumentVersionModel,
    SectionModel,
    VaultModel,
)
from graphrag_service.adapters.postgres.projection_models import (
    ModelProfileModel,
    ProjectionOutboxModel,
    ProjectionStatusModel,
)


@dataclass(frozen=True, slots=True)
class ModelProfile:
    id: UUID
    provider: str
    model_name: str
    vector_dimension: int
    physical_collection: str


@dataclass(frozen=True, slots=True)
class ProjectionWorkItem:
    outbox_id: UUID
    chunk_id: UUID
    operation: str
    generation: int
    model_profile_id: UUID
    collection: str
    text: str | None
    content_sha256: str | None
    payload: dict[str, Any]
    is_current: bool
    attempt_count: int


def collection_name(model_name: str, dimension: int) -> str:
    slug = "".join(character.lower() if character.isalnum() else "_" for character in model_name)
    slug = "_".join(part for part in slug.split("_") if part)
    return f"gks_chunks__{slug[:40]}_{dimension}__v1"


class ProjectionStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def register_embedding_profile(
        self,
        *,
        provider: str,
        model_name: str,
        dimension: int,
        capabilities: dict[str, Any],
    ) -> ModelProfile:
        async with self._sessions.begin() as session:
            statement = (
                insert(ModelProfileModel)
                .values(
                    kind="embedding",
                    provider=provider,
                    model_name=model_name,
                    vector_dimension=dimension,
                    distance_metric="cosine",
                    capabilities_json=capabilities,
                    is_active=False,
                )
                .on_conflict_do_update(
                    constraint="uq_model_profiles_provider_model_dimension",
                    set_={
                        "capabilities_json": capabilities,
                        "distance_metric": "cosine",
                        "updated_at": func.now(),
                    },
                )
                .returning(ModelProfileModel)
            )
            profile = (await session.scalars(statement)).one()
        return ModelProfile(
            id=profile.id,
            provider=profile.provider,
            model_name=profile.model_name,
            vector_dimension=dimension,
            physical_collection=collection_name(model_name, dimension),
        )

    async def set_active_profile(self, profile_id: UUID) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                update(ModelProfileModel)
                .where(ModelProfileModel.kind == "embedding")
                .values(is_active=False, updated_at=func.now())
            )
            result = await session.execute(
                update(ModelProfileModel)
                .where(
                    ModelProfileModel.id == profile_id,
                    ModelProfileModel.kind == "embedding",
                )
                .values(is_active=True, updated_at=func.now())
            )
            if not result.rowcount:
                raise LookupError("embedding model profile not found")

    async def active_embedding_profile(self) -> ModelProfile | None:
        async with self._sessions() as session:
            profile = await session.scalar(
                select(ModelProfileModel).where(
                    ModelProfileModel.kind == "embedding",
                    ModelProfileModel.is_active.is_(True),
                )
            )
        if profile is None or profile.vector_dimension is None:
            return None
        return ModelProfile(
            id=profile.id,
            provider=profile.provider,
            model_name=profile.model_name,
            vector_dimension=profile.vector_dimension,
            physical_collection=collection_name(profile.model_name, profile.vector_dimension),
        )

    async def enqueue_current_chunks(
        self,
        *,
        profile: ModelProfile,
        vault_id: UUID | None,
        rebuild_token: UUID | None = None,
    ) -> tuple[int, int]:
        """Create idempotent upserts and deletes from one PostgreSQL snapshot."""
        async with self._sessions.begin() as session:
            current_query = (
                select(
                    ChunkModel.id,
                    ChunkModel.projection_generation,
                    ChunkModel.content_sha256,
                )
                .join(
                    DocumentVersionModel,
                    DocumentVersionModel.id == ChunkModel.document_version_id,
                )
                .join(
                    DocumentModel,
                    and_(
                        DocumentModel.id == DocumentVersionModel.document_id,
                        DocumentModel.current_version_id == DocumentVersionModel.id,
                    ),
                )
                .where(DocumentModel.lifecycle_status == "active")
            )
            if vault_id is not None:
                current_query = current_query.where(DocumentModel.vault_id == vault_id)
            current_rows = (await session.execute(current_query)).all()
            current_ids = {row.id for row in current_rows}
            if vault_id is not None:
                all_current_ids_query = (
                    select(ChunkModel.id)
                    .join(
                        DocumentVersionModel,
                        DocumentVersionModel.id == ChunkModel.document_version_id,
                    )
                    .join(
                        DocumentModel,
                        and_(
                            DocumentModel.id == DocumentVersionModel.document_id,
                            DocumentModel.current_version_id == DocumentVersionModel.id,
                        ),
                    )
                    .where(DocumentModel.lifecycle_status == "active")
                )
                current_ids = set(await session.scalars(all_current_ids_query))
            inserted_upserts = 0
            for row in current_rows:
                rebuild_suffix = f":rebuild:{rebuild_token}" if rebuild_token else ""
                key = (
                    f"qdrant:chunk:{row.id}:{row.projection_generation}:upsert:"
                    f"{profile.id}{rebuild_suffix}"
                )
                inserted_id = await session.scalar(
                    insert(ProjectionOutboxModel)
                    .values(
                        target="qdrant",
                        object_type="chunk",
                        object_id=row.id,
                        generation=row.projection_generation,
                        operation="upsert",
                        idempotency_key=key,
                        model_profile_id=profile.id,
                        payload_json={"collection": profile.physical_collection},
                    )
                    .on_conflict_do_nothing(constraint="uq_projection_outbox_idempotency_key")
                    .returning(ProjectionOutboxModel.id)
                )
                inserted_upserts += int(inserted_id is not None)
                if inserted_id is not None:
                    await self._upsert_projection_status(
                        session,
                        chunk_id=row.id,
                        profile=profile,
                        generation=row.projection_generation,
                        status="pending",
                        content_sha256=row.content_sha256,
                    )

            stale_query = select(ProjectionStatusModel).where(
                ProjectionStatusModel.target == "qdrant",
                ProjectionStatusModel.object_type == "chunk",
                ProjectionStatusModel.model_profile_id == profile.id,
                ProjectionStatusModel.status != "deleted",
            )
            if current_ids:
                stale_query = stale_query.where(ProjectionStatusModel.object_id.not_in(current_ids))
            stale_rows = list(await session.scalars(stale_query))
            inserted_deletes = 0
            for stale in stale_rows:
                generation = stale.generation + 1
                key = f"qdrant:chunk:{stale.object_id}:{generation}:delete:{profile.id}"
                inserted_id = await session.scalar(
                    insert(ProjectionOutboxModel)
                    .values(
                        target="qdrant",
                        object_type="chunk",
                        object_id=stale.object_id,
                        generation=generation,
                        operation="delete",
                        idempotency_key=key,
                        model_profile_id=profile.id,
                        payload_json={"collection": stale.physical_target},
                    )
                    .on_conflict_do_nothing(constraint="uq_projection_outbox_idempotency_key")
                    .returning(ProjectionOutboxModel.id)
                )
                inserted_deletes += int(inserted_id is not None)
                if inserted_id is not None:
                    stale.generation = generation
                    stale.status = "pending"
                    stale.updated_at = datetime.now(UTC)
        return inserted_upserts, inserted_deletes

    async def claim_batch(
        self,
        *,
        worker_id: str,
        profile_id: UUID,
        batch_size: int,
        lease_seconds: int,
    ) -> list[ProjectionWorkItem]:
        now = datetime.now(UTC)
        async with self._sessions.begin() as session:
            rows = list(
                await session.scalars(
                    select(ProjectionOutboxModel)
                    .where(
                        ProjectionOutboxModel.target == "qdrant",
                        ProjectionOutboxModel.model_profile_id == profile_id,
                        ProjectionOutboxModel.status.in_(["pending", "processing"]),
                        ProjectionOutboxModel.attempt_count < ProjectionOutboxModel.max_attempts,
                        or_(
                            and_(
                                ProjectionOutboxModel.status == "pending",
                                or_(
                                    ProjectionOutboxModel.next_attempt_at.is_(None),
                                    ProjectionOutboxModel.next_attempt_at <= func.now(),
                                ),
                            ),
                            and_(
                                ProjectionOutboxModel.status == "processing",
                                ProjectionOutboxModel.lease_expires_at < func.now(),
                            ),
                        ),
                    )
                    .order_by(ProjectionOutboxModel.created_at, ProjectionOutboxModel.id)
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
            )
            items: list[ProjectionWorkItem] = []
            for row in rows:
                row.status = "processing"
                row.lease_owner = worker_id
                row.lease_expires_at = now + timedelta(seconds=lease_seconds)
                row.attempt_count += 1
                row.updated_at = now
                chunk_row = (
                    await session.execute(
                        select(
                            ChunkModel,
                            SectionModel,
                            DocumentVersionModel,
                            DocumentModel,
                            VaultModel,
                        )
                        .join(SectionModel, SectionModel.id == ChunkModel.section_id)
                        .join(
                            DocumentVersionModel,
                            DocumentVersionModel.id == ChunkModel.document_version_id,
                        )
                        .join(
                            DocumentModel,
                            DocumentModel.id == DocumentVersionModel.document_id,
                        )
                        .join(VaultModel, VaultModel.id == DocumentModel.vault_id)
                        .where(ChunkModel.id == row.object_id)
                    )
                ).one_or_none()
                is_current = bool(
                    chunk_row
                    and chunk_row[3].current_version_id == chunk_row[2].id
                    and chunk_row[3].lifecycle_status == "active"
                )
                payload: dict[str, Any] = {}
                text: str | None = None
                content_hash: str | None = None
                if chunk_row:
                    chunk, section, version, document, vault = chunk_row
                    text = chunk.text
                    content_hash = chunk.content_sha256
                    payload = {
                        "vault_id": str(vault.id),
                        "document_id": str(document.id),
                        "document_version_id": str(version.id),
                        "section_id": str(section.id),
                        "chunk_id": str(chunk.id),
                        "relative_path": document.current_relative_path,
                        "heading_path": list(section.heading_path_json),
                        "content_sha256": chunk.content_sha256,
                        "parser_version": chunk.parser_version,
                        "chunker_version": chunk.chunker_version,
                        "retrieval_role": chunk.retrieval_role,
                        "projection_generation": row.generation,
                        "is_current": is_current,
                    }
                items.append(
                    ProjectionWorkItem(
                        outbox_id=row.id,
                        chunk_id=row.object_id,
                        operation=row.operation,
                        generation=row.generation,
                        model_profile_id=row.model_profile_id,  # type: ignore[arg-type]
                        collection=str(row.payload_json["collection"]),
                        text=text,
                        content_sha256=content_hash,
                        payload=payload,
                        is_current=is_current,
                        attempt_count=row.attempt_count,
                    )
                )
        return items

    async def outstanding_counts(self, profile_id: UUID) -> tuple[int, int]:
        async with self._sessions() as session:
            pending = await session.scalar(
                select(func.count())
                .select_from(ProjectionOutboxModel)
                .where(
                    ProjectionOutboxModel.model_profile_id == profile_id,
                    ProjectionOutboxModel.status.in_(["pending", "processing"]),
                )
            )
            failed = await session.scalar(
                select(func.count())
                .select_from(ProjectionOutboxModel)
                .where(
                    ProjectionOutboxModel.model_profile_id == profile_id,
                    ProjectionOutboxModel.status == "failed",
                )
            )
        return int(pending or 0), int(failed or 0)

    async def mark_succeeded(self, item: ProjectionWorkItem) -> None:
        status = "deleted" if item.operation == "delete" or not item.is_current else "current"
        async with self._sessions.begin() as session:
            await session.execute(
                update(ProjectionOutboxModel)
                .where(
                    ProjectionOutboxModel.id == item.outbox_id,
                    ProjectionOutboxModel.status == "processing",
                )
                .values(
                    status="succeeded",
                    lease_owner=None,
                    lease_expires_at=None,
                    completed_at=func.now(),
                    updated_at=func.now(),
                    last_error_code=None,
                    last_error_message=None,
                )
            )
            await session.execute(
                update(ProjectionStatusModel)
                .where(
                    ProjectionStatusModel.target == "qdrant",
                    ProjectionStatusModel.object_type == "chunk",
                    ProjectionStatusModel.object_id == item.chunk_id,
                    ProjectionStatusModel.model_profile_id == item.model_profile_id,
                )
                .values(
                    generation=item.generation,
                    status=status,
                    content_sha256=item.content_sha256,
                    last_error_code=None,
                    updated_at=func.now(),
                )
            )

    async def mark_failed(
        self,
        item: ProjectionWorkItem,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        delay = min(300, 2 ** min(item.attempt_count, 8))
        async with self._sessions.begin() as session:
            outbox = await session.get(ProjectionOutboxModel, item.outbox_id)
            if outbox is None:
                return
            retryable = outbox.attempt_count < outbox.max_attempts
            outbox.status = "pending" if retryable else "failed"
            outbox.next_attempt_at = (
                datetime.now(UTC) + timedelta(seconds=delay) if retryable else None
            )
            outbox.lease_owner = None
            outbox.lease_expires_at = None
            outbox.last_error_code = error_code[:100]
            outbox.last_error_message = error_message[:4000]
            outbox.updated_at = datetime.now(UTC)
            await session.execute(
                update(ProjectionStatusModel)
                .where(
                    ProjectionStatusModel.target == "qdrant",
                    ProjectionStatusModel.object_type == "chunk",
                    ProjectionStatusModel.object_id == item.chunk_id,
                    ProjectionStatusModel.model_profile_id == item.model_profile_id,
                )
                .values(
                    status="failed" if not retryable else "pending",
                    last_error_code=error_code[:100],
                    updated_at=func.now(),
                )
            )

    @staticmethod
    async def _upsert_projection_status(
        session: AsyncSession,
        *,
        chunk_id: UUID,
        profile: ModelProfile,
        generation: int,
        status: str,
        content_sha256: str,
    ) -> None:
        await session.execute(
            insert(ProjectionStatusModel)
            .values(
                target="qdrant",
                object_type="chunk",
                object_id=chunk_id,
                model_profile_id=profile.id,
                generation=generation,
                status=status,
                physical_target=profile.physical_collection,
                content_sha256=content_sha256,
            )
            .on_conflict_do_update(
                constraint="uq_projection_status_object_profile",
                set_={
                    "generation": generation,
                    "status": status,
                    "physical_target": profile.physical_collection,
                    "content_sha256": content_sha256,
                    "updated_at": func.now(),
                },
            )
        )
