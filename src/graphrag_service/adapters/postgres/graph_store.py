from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from graphrag_service.adapters.postgres.extraction_models import (
    EvidenceSpanModel,
    ExtractionRunModel,
)
from graphrag_service.adapters.postgres.ingest_models import (
    ChunkModel,
    DocumentLinkModel,
    DocumentModel,
    DocumentVersionModel,
    SectionModel,
    VaultModel,
)
from graphrag_service.adapters.postgres.projection_models import ProjectionOutboxModel
from graphrag_service.adapters.postgres.resolution_models import (
    ClaimModel,
    EntityAliasModel,
    EntityIdentifierModel,
    EntityMentionModel,
    EntityModel,
    Neo4jProjectionRunModel,
    RelationshipAssertionModel,
)
from graphrag_service.domain.graph import (
    EntityDetail,
    EntityEvidence,
    GraphSnapshot,
)


@dataclass(frozen=True, slots=True)
class Neo4jProjectionWork:
    run_id: UUID
    outbox_id: UUID
    generation: int
    should_project: bool


class GraphStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def build_snapshot(self, vault_id: UUID) -> GraphSnapshot:
        async with self._sessions() as session:
            vault = await session.get(VaultModel, vault_id)
            if vault is None:
                raise LookupError("vault not found")
            document_rows = (
                await session.execute(
                    select(DocumentModel, DocumentVersionModel)
                    .join(
                        DocumentVersionModel,
                        DocumentVersionModel.id == DocumentModel.current_version_id,
                    )
                    .where(
                        DocumentModel.vault_id == vault_id,
                        DocumentModel.lifecycle_status == "active",
                        DocumentVersionModel.processing_status == "ready",
                    )
                    .order_by(DocumentModel.id)
                )
            ).all()
            document_ids = {document.id for document, _ in document_rows}
            version_ids = {version.id for _, version in document_rows}
            sections = (
                list(
                    await session.scalars(
                        select(SectionModel)
                        .where(SectionModel.document_version_id.in_(version_ids))
                        .order_by(SectionModel.id)
                    )
                )
                if version_ids
                else []
            )
            chunks = (
                list(
                    await session.scalars(
                        select(ChunkModel)
                        .where(ChunkModel.document_version_id.in_(version_ids))
                        .order_by(ChunkModel.id)
                    )
                )
                if version_ids
                else []
            )
            chunk_ids = {chunk.id for chunk in chunks}
            links = (
                list(
                    await session.scalars(
                        select(DocumentLinkModel)
                        .where(
                            DocumentLinkModel.source_document_version_id.in_(version_ids),
                            DocumentLinkModel.resolution_status == "resolved",
                            DocumentLinkModel.resolved_document_id.in_(document_ids),
                        )
                        .order_by(DocumentLinkModel.id)
                    )
                )
                if version_ids and document_ids
                else []
            )
            entities = list(
                await session.scalars(
                    select(EntityModel)
                    .where(EntityModel.vault_id == vault_id, EntityModel.status == "active")
                    .order_by(EntityModel.id)
                )
            )
            entity_ids = {entity.id for entity in entities}
            mentions = (
                list(
                    await session.scalars(
                        select(EntityMentionModel)
                        .where(
                            EntityMentionModel.entity_id.in_(entity_ids),
                            EntityMentionModel.chunk_id.in_(chunk_ids),
                            EntityMentionModel.mention_status == "active",
                        )
                        .order_by(EntityMentionModel.id)
                    )
                )
                if entity_ids and chunk_ids
                else []
            )
            assertions = (
                list(
                    await session.scalars(
                        select(RelationshipAssertionModel)
                        .where(
                            RelationshipAssertionModel.subject_entity_id.in_(entity_ids),
                            RelationshipAssertionModel.object_entity_id.in_(entity_ids),
                            RelationshipAssertionModel.status == "active",
                        )
                        .order_by(RelationshipAssertionModel.id)
                    )
                )
                if entity_ids
                else []
            )
            claims = list(
                await session.scalars(
                    select(ClaimModel)
                    .join(
                        ExtractionRunModel,
                        ExtractionRunModel.id == ClaimModel.extraction_run_id,
                    )
                    .where(
                        ExtractionRunModel.vault_id == vault_id,
                        ClaimModel.status == "active",
                    )
                    .order_by(ClaimModel.id)
                )
            )
            evidence_ids = {item.evidence_span_id for item in assertions} | {
                item.evidence_span_id for item in claims
            }
            evidence = (
                list(
                    await session.scalars(
                        select(EvidenceSpanModel)
                        .where(
                            EvidenceSpanModel.id.in_(evidence_ids),
                            EvidenceSpanModel.chunk_id.in_(chunk_ids),
                        )
                        .order_by(EvidenceSpanModel.id)
                    )
                )
                if evidence_ids and chunk_ids
                else []
            )

        common = {"gks_managed": True, "vault_id": str(vault_id)}
        nodes: dict[str, tuple[dict[str, Any], ...]] = {
            "Vault": (
                {
                    **common,
                    "id": str(vault.id),
                    "name": vault.name,
                },
            ),
            "Document": tuple(
                {
                    **common,
                    "id": str(document.id),
                    "relative_path": document.current_relative_path,
                    "title": document.title,
                    "status": document.lifecycle_status,
                }
                for document, _ in document_rows
            ),
            "DocumentVersion": tuple(
                {
                    **common,
                    "id": str(version.id),
                    "document_id": str(document.id),
                    "content_sha256": version.content_sha256,
                    "parser_version": version.parser_version,
                    "chunker_version": version.chunker_version,
                }
                for document, version in document_rows
            ),
            "Section": tuple(
                {
                    **common,
                    "id": str(section.id),
                    "heading": section.heading_text,
                    "heading_path": section.heading_path_json,
                    "heading_level": section.heading_level,
                    "ordinal": section.ordinal,
                }
                for section in sections
            ),
            "Chunk": tuple(
                {
                    **common,
                    "id": str(chunk.id),
                    "section_id": str(chunk.section_id),
                    "content_sha256": chunk.content_sha256,
                    "ordinal": chunk.ordinal,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                }
                for chunk in chunks
            ),
            "Entity": tuple(
                {
                    **common,
                    "id": str(entity.id),
                    "canonical_name": entity.canonical_name,
                    "normalized_name": entity.normalized_name,
                    "entity_type": entity.entity_type_code,
                    "entity_subtype": entity.entity_subtype_code,
                    "scope": entity.entity_scope,
                    "status": entity.status,
                }
                for entity in entities
            ),
            "RelationshipAssertion": tuple(
                {
                    **common,
                    "id": str(assertion.id),
                    "predicate": assertion.predicate_code,
                    "assertion_kind": assertion.assertion_kind,
                    "review_status": assertion.review_status,
                    "network_layer": assertion.network_layer,
                    "status": assertion.status,
                }
                for assertion in assertions
            ),
            "Claim": tuple(
                {
                    **common,
                    "id": str(claim.id),
                    "text": claim.claim_text,
                    "assertion_kind": claim.assertion_kind,
                    "review_status": claim.review_status,
                    "status": claim.status,
                }
                for claim in claims
            ),
            "Evidence": tuple(
                {
                    **common,
                    "id": str(item.id),
                    "chunk_id": str(item.chunk_id),
                    "quote": item.quote_text,
                    "quote_sha256": item.quote_sha256,
                    "char_start": item.char_start,
                    "char_end": item.char_end,
                }
                for item in evidence
            ),
        }

        def edge(
            source_id: UUID,
            target_id: UUID,
            properties: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            return {
                "source_id": str(source_id),
                "target_id": str(target_id),
                "properties": properties or {},
            }

        relationships: dict[str, tuple[dict[str, Any], ...]] = {
            "CONTAINS": tuple(edge(vault_id, document.id) for document, _ in document_rows),
            "HAS_VERSION": tuple(
                edge(document.id, version.id) for document, version in document_rows
            ),
            "HAS_SECTION": tuple(
                edge(section.document_version_id, section.id) for section in sections
            ),
            "HAS_CHILD": tuple(
                edge(section.parent_section_id, section.id)
                for section in sections
                if section.parent_section_id is not None
            ),
            "HAS_CHUNK": tuple(edge(chunk.section_id, chunk.id) for chunk in chunks),
            "LINKS_TO": tuple(
                edge(
                    next(
                        document.id
                        for document, version in document_rows
                        if version.id == link.source_document_version_id
                    ),
                    link.resolved_document_id,
                    {"link_id": str(link.id), "link_kind": link.link_kind},
                )
                for link in links
                if link.resolved_document_id is not None
            ),
            "MENTIONS": tuple(
                edge(
                    mention.chunk_id,
                    mention.entity_id,
                    {
                        "mention_id": str(mention.id),
                        "surface_form": mention.surface_form,
                    },
                )
                for mention in mentions
            ),
            "SUBJECT": tuple(
                edge(assertion.id, assertion.subject_entity_id) for assertion in assertions
            ),
            "OBJECT": tuple(
                edge(assertion.id, assertion.object_entity_id) for assertion in assertions
            ),
            "ENTITY_LINK": tuple(
                edge(
                    assertion.subject_entity_id,
                    assertion.object_entity_id,
                    {
                        "assertion_id": str(assertion.id),
                        "predicate": assertion.predicate_code,
                        "review_status": assertion.review_status,
                        "assertion_kind": assertion.assertion_kind,
                    },
                )
                for assertion in assertions
            ),
            "ASSERTION_SUPPORTED_BY": tuple(
                edge(assertion.id, assertion.evidence_span_id) for assertion in assertions
            ),
            "CLAIM_SUPPORTED_BY": tuple(edge(claim.id, claim.evidence_span_id) for claim in claims),
            "LOCATED_IN": tuple(edge(item.id, item.chunk_id) for item in evidence),
        }
        return GraphSnapshot(vault_id=vault_id, nodes=nodes, relationships=relationships)

    async def prepare_projection(self, snapshot: GraphSnapshot) -> Neo4jProjectionWork:
        async with self._sessions.begin() as session:
            existing = await session.scalar(
                select(Neo4jProjectionRunModel).where(
                    Neo4jProjectionRunModel.vault_id == snapshot.vault_id,
                    Neo4jProjectionRunModel.snapshot_sha256 == snapshot.sha256,
                )
            )
            if existing is not None and existing.outbox_id is not None:
                return Neo4jProjectionWork(
                    run_id=existing.id,
                    outbox_id=existing.outbox_id,
                    generation=existing.generation,
                    should_project=existing.status != "succeeded",
                )
            generation = (
                int(
                    await session.scalar(
                        select(
                            func.coalesce(func.max(Neo4jProjectionRunModel.generation), 0)
                        ).where(Neo4jProjectionRunModel.vault_id == snapshot.vault_id)
                    )
                    or 0
                )
                + 1
            )
            outbox = (
                await session.scalars(
                    insert(ProjectionOutboxModel)
                    .values(
                        target="neo4j",
                        object_type="vault_snapshot",
                        object_id=snapshot.vault_id,
                        generation=generation,
                        operation="upsert",
                        idempotency_key=(
                            f"neo4j:vault:{snapshot.vault_id}:snapshot:{snapshot.sha256}"
                        ),
                        model_profile_id=None,
                        payload_json={"snapshot_sha256": snapshot.sha256},
                        status="pending",
                    )
                    .on_conflict_do_nothing(constraint="uq_projection_outbox_idempotency_key")
                    .returning(ProjectionOutboxModel)
                )
            ).one()
            run = Neo4jProjectionRunModel(
                vault_id=snapshot.vault_id,
                outbox_id=outbox.id,
                snapshot_sha256=snapshot.sha256,
                generation=generation,
                status="pending",
                object_count=snapshot.object_count,
            )
            session.add(run)
            await session.flush()
            return Neo4jProjectionWork(run.id, outbox.id, generation, True)

    async def mark_projection_running(self, work: Neo4jProjectionWork) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                update(ProjectionOutboxModel)
                .where(ProjectionOutboxModel.id == work.outbox_id)
                .values(
                    status="processing",
                    attempt_count=ProjectionOutboxModel.attempt_count + 1,
                    updated_at=func.now(),
                )
            )
            await session.execute(
                update(Neo4jProjectionRunModel)
                .where(Neo4jProjectionRunModel.id == work.run_id)
                .values(status="running", last_error_code=None, last_error_message=None)
            )

    async def mark_projection_succeeded(self, work: Neo4jProjectionWork) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                update(ProjectionOutboxModel)
                .where(ProjectionOutboxModel.id == work.outbox_id)
                .values(
                    status="succeeded",
                    completed_at=func.now(),
                    updated_at=func.now(),
                    last_error_code=None,
                    last_error_message=None,
                )
            )
            await session.execute(
                update(Neo4jProjectionRunModel)
                .where(Neo4jProjectionRunModel.id == work.run_id)
                .values(status="succeeded", finished_at=func.now())
            )

    async def mark_projection_failed(
        self,
        work: Neo4jProjectionWork,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        async with self._sessions.begin() as session:
            outbox = await session.get(ProjectionOutboxModel, work.outbox_id)
            if outbox is not None:
                outbox.status = (
                    "pending" if outbox.attempt_count < outbox.max_attempts else "failed"
                )
                outbox.last_error_code = error_code[:100]
                outbox.last_error_message = error_message[:4000]
                outbox.updated_at = datetime.now(UTC)
            await session.execute(
                update(Neo4jProjectionRunModel)
                .where(Neo4jProjectionRunModel.id == work.run_id)
                .values(
                    status="failed",
                    last_error_code=error_code[:100],
                    last_error_message=error_message[:4000],
                    finished_at=func.now(),
                )
            )

    async def entity_detail(self, entity_id: UUID) -> EntityDetail | None:
        async with self._sessions() as session:
            entity = await session.get(EntityModel, entity_id)
            if entity is None:
                return None
            aliases = tuple(
                await session.scalars(
                    select(EntityAliasModel.alias)
                    .where(EntityAliasModel.entity_id == entity_id)
                    .distinct()
                    .order_by(EntityAliasModel.alias)
                )
            )
            identifier_rows = (
                await session.execute(
                    select(
                        EntityIdentifierModel.identifier_kind,
                        EntityIdentifierModel.identifier_value,
                        EntityIdentifierModel.normalized_value,
                    )
                    .where(EntityIdentifierModel.entity_id == entity_id)
                    .order_by(
                        EntityIdentifierModel.identifier_kind,
                        EntityIdentifierModel.normalized_value,
                    )
                )
            ).all()
            evidence_rows = (
                await session.execute(
                    select(
                        EvidenceSpanModel,
                        ChunkModel,
                        DocumentVersionModel,
                        DocumentModel,
                    )
                    .join(
                        EntityMentionModel,
                        EntityMentionModel.evidence_span_id == EvidenceSpanModel.id,
                    )
                    .join(ChunkModel, ChunkModel.id == EvidenceSpanModel.chunk_id)
                    .join(
                        DocumentVersionModel,
                        DocumentVersionModel.id == EvidenceSpanModel.document_version_id,
                    )
                    .join(
                        DocumentModel,
                        and_(
                            DocumentModel.id == DocumentVersionModel.document_id,
                            DocumentModel.current_version_id == DocumentVersionModel.id,
                        ),
                    )
                    .where(
                        EntityMentionModel.entity_id == entity_id,
                        DocumentModel.lifecycle_status == "active",
                    )
                    .order_by(DocumentModel.current_relative_path, EvidenceSpanModel.char_start)
                )
            ).all()
        return EntityDetail(
            id=entity.id,
            vault_id=entity.vault_id,
            canonical_name=entity.canonical_name,
            entity_type=entity.entity_type_code,
            entity_subtype=entity.entity_subtype_code,
            scope=entity.entity_scope,
            status=entity.status,
            aliases=aliases,
            identifiers=tuple(
                {"kind": kind, "value": value, "normalized_value": normalized}
                for kind, value, normalized in identifier_rows
            ),
            evidence=tuple(
                EntityEvidence(
                    evidence_id=evidence.id,
                    chunk_id=chunk.id,
                    document_id=document.id,
                    relative_path=document.current_relative_path,
                    quote=evidence.quote_text,
                    char_start=evidence.char_start,
                    char_end=evidence.char_end,
                )
                for evidence, chunk, _, document in evidence_rows
            ),
        )
