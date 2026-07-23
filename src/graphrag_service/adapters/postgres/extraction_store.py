from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from graphrag_service.adapters.postgres.extraction_models import (
    ClaimCandidateModel,
    EntityCandidateModel,
    EvidenceSpanModel,
    ExtractionChunkModel,
    ExtractionRunModel,
    OntologyVersionModel,
    PromptVersionModel,
    RelationshipCandidateModel,
    SchemaVersionModel,
)
from graphrag_service.adapters.postgres.ingest_models import (
    ChunkModel,
    DocumentModel,
    DocumentVersionModel,
    SectionModel,
)
from graphrag_service.adapters.postgres.projection_models import ModelProfileModel
from graphrag_service.domain.extraction import (
    ExactEvidence,
    ExtractedClaim,
    ExtractedEntity,
    ExtractedRelationship,
)


@dataclass(frozen=True, slots=True)
class ExtractionRegistry:
    model_profile_id: UUID
    prompt_version_id: UUID
    schema_version_id: UUID
    ontology_version_id: UUID


@dataclass(frozen=True, slots=True)
class ExtractionSourceChunk:
    id: UUID
    vault_id: UUID
    document_id: UUID
    document_version_id: UUID
    section_id: UUID
    relative_path: str
    heading_path: tuple[str, ...]
    ordinal: int
    char_start: int
    text: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class ValidatedItem:
    value: BaseModel
    evidence: ExactEvidence | None
    errors: tuple[str, ...]


class ExtractionStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def register_runtime(
        self,
        *,
        provider: str,
        model_name: str,
        capabilities: dict[str, Any],
        prompt_name: str,
        prompt_version: str,
        prompt_template: str,
        schema_name: str,
        schema_version: str,
        schema: dict[str, Any],
        ontology_code: str,
        ontology_version: str,
    ) -> ExtractionRegistry:
        prompt_hash = hashlib.sha256(prompt_template.encode("utf-8")).hexdigest()
        canonical_schema = json.dumps(
            schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        schema_hash = hashlib.sha256(canonical_schema.encode("utf-8")).hexdigest()
        async with self._sessions.begin() as session:
            profile = await session.scalar(
                select(ModelProfileModel)
                .where(
                    ModelProfileModel.kind == "generation",
                    ModelProfileModel.provider == provider,
                    ModelProfileModel.model_name == model_name,
                )
                .with_for_update()
            )
            if profile is None:
                profile = ModelProfileModel(
                    kind="generation",
                    provider=provider,
                    model_name=model_name,
                    vector_dimension=None,
                    capabilities_json=capabilities,
                    is_active=False,
                )
                session.add(profile)
                await session.flush()
            else:
                profile.capabilities_json = capabilities
                profile.updated_at = datetime.now(UTC)
            await session.execute(
                update(ModelProfileModel)
                .where(ModelProfileModel.kind == "generation")
                .values(is_active=False, updated_at=func.now())
            )
            profile.is_active = True

            prompt = (
                await session.scalars(
                    insert(PromptVersionModel)
                    .values(
                        name=prompt_name,
                        version=prompt_version,
                        task="knowledge_extraction",
                        content_sha256=prompt_hash,
                        template_text=prompt_template,
                        status="active",
                    )
                    .on_conflict_do_update(
                        constraint="uq_prompt_versions_name_version",
                        set_={
                            "content_sha256": prompt_hash,
                            "template_text": prompt_template,
                            "status": "active",
                        },
                    )
                    .returning(PromptVersionModel)
                )
            ).one()
            schema_row = (
                await session.scalars(
                    insert(SchemaVersionModel)
                    .values(
                        name=schema_name,
                        version=schema_version,
                        schema_sha256=schema_hash,
                        schema_json=schema,
                    )
                    .on_conflict_do_update(
                        constraint="uq_schema_versions_name_version",
                        set_={"schema_sha256": schema_hash, "schema_json": schema},
                    )
                    .returning(SchemaVersionModel)
                )
            ).one()
            ontology = await session.scalar(
                select(OntologyVersionModel).where(
                    OntologyVersionModel.code == ontology_code,
                    OntologyVersionModel.version == ontology_version,
                    OntologyVersionModel.status == "active",
                )
            )
            if ontology is None:
                raise LookupError("active ontology version not found")
            return ExtractionRegistry(
                model_profile_id=profile.id,
                prompt_version_id=prompt.id,
                schema_version_id=schema_row.id,
                ontology_version_id=ontology.id,
            )

    async def select_current_chunks(
        self,
        *,
        vault_id: UUID,
        document_ids: tuple[UUID, ...],
        limit: int,
    ) -> tuple[ExtractionSourceChunk, ...]:
        if not document_ids:
            raise ValueError("the extraction pilot requires explicit document_ids")
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(
                        ChunkModel,
                        SectionModel,
                        DocumentVersionModel,
                        DocumentModel,
                    )
                    .join(SectionModel, SectionModel.id == ChunkModel.section_id)
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
                    .where(
                        DocumentModel.vault_id == vault_id,
                        DocumentModel.id.in_(document_ids),
                        DocumentModel.lifecycle_status == "active",
                        DocumentVersionModel.processing_status == "ready",
                    )
                    .order_by(
                        DocumentModel.current_relative_path,
                        func.length(ChunkModel.text).desc(),
                        ChunkModel.ordinal,
                    )
                    .limit(limit)
                )
            ).all()
        return tuple(
            ExtractionSourceChunk(
                id=chunk.id,
                vault_id=document.vault_id,
                document_id=document.id,
                document_version_id=version.id,
                section_id=section.id,
                relative_path=document.current_relative_path,
                heading_path=tuple(section.heading_path_json),
                ordinal=chunk.ordinal,
                char_start=chunk.char_start,
                text=chunk.text,
                content_sha256=chunk.content_sha256,
            )
            for chunk, section, version, document in rows
        )

    async def prepare_run(
        self,
        *,
        job_id: UUID,
        vault_id: UUID,
        registry: ExtractionRegistry,
        chunks: tuple[ExtractionSourceChunk, ...],
    ) -> UUID:
        if not chunks:
            raise LookupError("no current chunks matched the extraction pilot scope")
        async with self._sessions.begin() as session:
            existing = await session.scalar(
                select(ExtractionRunModel).where(ExtractionRunModel.job_id == job_id)
            )
            if existing is not None:
                return existing.id
            run = ExtractionRunModel(
                id=uuid4(),
                job_id=job_id,
                vault_id=vault_id,
                model_profile_id=registry.model_profile_id,
                prompt_version_id=registry.prompt_version_id,
                schema_version_id=registry.schema_version_id,
                ontology_version_id=registry.ontology_version_id,
                status="running",
                requested_chunk_count=len(chunks),
            )
            session.add(run)
            await session.flush()
            session.add_all(
                [
                    ExtractionChunkModel(
                        extraction_run_id=run.id,
                        chunk_id=chunk.id,
                        status="pending",
                    )
                    for chunk in chunks
                ]
            )
            return run.id

    async def pending_chunks(self, run_id: UUID) -> tuple[ExtractionSourceChunk, ...]:
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(
                        ChunkModel,
                        SectionModel,
                        DocumentVersionModel,
                        DocumentModel,
                    )
                    .join(
                        ExtractionChunkModel,
                        ExtractionChunkModel.chunk_id == ChunkModel.id,
                    )
                    .join(SectionModel, SectionModel.id == ChunkModel.section_id)
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
                    .where(
                        ExtractionChunkModel.extraction_run_id == run_id,
                        ExtractionChunkModel.status.in_(["pending", "provider_failed"]),
                        DocumentModel.lifecycle_status == "active",
                    )
                    .order_by(
                        DocumentModel.current_relative_path,
                        func.length(ChunkModel.text).desc(),
                        ChunkModel.ordinal,
                    )
                )
            ).all()
        return tuple(
            ExtractionSourceChunk(
                id=chunk.id,
                vault_id=document.vault_id,
                document_id=document.id,
                document_version_id=version.id,
                section_id=section.id,
                relative_path=document.current_relative_path,
                heading_path=tuple(section.heading_path_json),
                ordinal=chunk.ordinal,
                char_start=chunk.char_start,
                text=chunk.text,
                content_sha256=chunk.content_sha256,
            )
            for chunk, section, version, document in rows
        )

    async def record_provider_failure(self, run_id: UUID, chunk_id: UUID, code: str) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                update(ExtractionChunkModel)
                .where(
                    ExtractionChunkModel.extraction_run_id == run_id,
                    ExtractionChunkModel.chunk_id == chunk_id,
                )
                .values(status="provider_failed", error_code=code, processed_at=func.now())
            )
            await session.execute(
                update(ExtractionRunModel)
                .where(ExtractionRunModel.id == run_id)
                .values(error_code=code)
            )

    async def record_schema_invalid(
        self,
        *,
        run_id: UUID,
        chunk_id: UUID,
        response_sha256: str,
        prompt_tokens: int,
        completion_tokens: int,
        error_code: str,
    ) -> None:
        await self._record_chunk_status(
            run_id=run_id,
            chunk_id=chunk_id,
            status="schema_invalid",
            response_sha256=response_sha256,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            error_code=error_code,
        )

    async def record_success(
        self,
        *,
        run_id: UUID,
        source: ExtractionSourceChunk,
        response_sha256: str,
        prompt_tokens: int,
        completion_tokens: int,
        entities: tuple[ValidatedItem, ...],
        relationships: tuple[ValidatedItem, ...],
        claims: tuple[ValidatedItem, ...],
    ) -> None:
        async with self._sessions.begin() as session:
            for model in (
                EntityCandidateModel,
                RelationshipCandidateModel,
                ClaimCandidateModel,
            ):
                await session.execute(
                    delete(model).where(
                        model.extraction_run_id == run_id,
                        model.chunk_id == source.id,
                    )
                )
            await session.execute(
                delete(EvidenceSpanModel).where(
                    EvidenceSpanModel.extraction_run_id == run_id,
                    EvidenceSpanModel.chunk_id == source.id,
                )
            )
            for item in entities:
                value = item.value
                if not isinstance(value, ExtractedEntity):
                    raise TypeError("invalid entity candidate value")
                evidence_id = await self._add_evidence(session, run_id, source, item)
                session.add(
                    EntityCandidateModel(
                        extraction_run_id=run_id,
                        chunk_id=source.id,
                        evidence_span_id=evidence_id,
                        local_id=value.local_id,
                        name=value.name,
                        entity_type_code=value.entity_type,
                        entity_subtype_code=value.entity_subtype,
                        proposed_subtype=value.proposed_subtype,
                        entity_scope=value.scope,
                        assertion_kind=value.assertion_kind,
                        review_status="unreviewed",
                        validation_status="invalid" if item.errors else "valid",
                        validation_errors_json=list(item.errors),
                    )
                )
            for item in relationships:
                value = item.value
                if not isinstance(value, ExtractedRelationship):
                    raise TypeError("invalid relationship candidate value")
                evidence_id = await self._add_evidence(session, run_id, source, item)
                session.add(
                    RelationshipCandidateModel(
                        extraction_run_id=run_id,
                        chunk_id=source.id,
                        evidence_span_id=evidence_id,
                        subject_local_id=value.subject_local_id,
                        predicate_code=value.predicate,
                        object_local_id=value.object_local_id,
                        assertion_kind=value.assertion_kind,
                        review_status="unreviewed",
                        network_layer=value.network_layer,
                        validation_status="invalid" if item.errors else "valid",
                        validation_errors_json=list(item.errors),
                    )
                )
            for item in claims:
                value = item.value
                if not isinstance(value, ExtractedClaim):
                    raise TypeError("invalid claim candidate value")
                evidence_id = await self._add_evidence(session, run_id, source, item)
                session.add(
                    ClaimCandidateModel(
                        extraction_run_id=run_id,
                        chunk_id=source.id,
                        evidence_span_id=evidence_id,
                        claim_text=value.text,
                        assertion_kind=value.assertion_kind,
                        review_status="unreviewed",
                        validation_status="invalid" if item.errors else "valid",
                        validation_errors_json=list(item.errors),
                    )
                )
            await session.execute(
                update(ExtractionChunkModel)
                .where(
                    ExtractionChunkModel.extraction_run_id == run_id,
                    ExtractionChunkModel.chunk_id == source.id,
                )
                .values(
                    status="succeeded",
                    response_sha256=response_sha256,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    error_code=None,
                    processed_at=func.now(),
                )
            )

    async def finalize(self, run_id: UUID) -> dict[str, int | str]:
        async with self._sessions.begin() as session:
            processed = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ExtractionChunkModel)
                    .where(
                        ExtractionChunkModel.extraction_run_id == run_id,
                        ExtractionChunkModel.status.in_(["succeeded", "schema_invalid"]),
                    )
                )
                or 0
            )
            invalid_chunks = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ExtractionChunkModel)
                    .where(
                        ExtractionChunkModel.extraction_run_id == run_id,
                        ExtractionChunkModel.status == "schema_invalid",
                    )
                )
                or 0
            )
            prompt_tokens, completion_tokens = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(ExtractionChunkModel.prompt_tokens), 0),
                        func.coalesce(func.sum(ExtractionChunkModel.completion_tokens), 0),
                    ).where(ExtractionChunkModel.extraction_run_id == run_id)
                )
            ).one()
            valid, invalid = 0, 0
            for model in (
                EntityCandidateModel,
                RelationshipCandidateModel,
                ClaimCandidateModel,
            ):
                rows = (
                    await session.execute(
                        select(model.validation_status, func.count())
                        .where(model.extraction_run_id == run_id)
                        .group_by(model.validation_status)
                    )
                ).all()
                for status, count in rows:
                    if status == "valid":
                        valid += int(count)
                    else:
                        invalid += int(count)
            run = await session.get(ExtractionRunModel, run_id, with_for_update=True)
            if run is None:
                raise LookupError("extraction run not found")
            status = "partial" if invalid_chunks or invalid else "succeeded"
            run.status = status
            run.processed_chunk_count = processed
            run.valid_candidate_count = valid
            run.invalid_candidate_count = invalid
            run.prompt_tokens = int(prompt_tokens)
            run.completion_tokens = int(completion_tokens)
            run.finished_at = datetime.now(UTC)
            run.error_code = None
            return {
                "status": status,
                "processed_chunks": processed,
                "valid_candidates": valid,
                "invalid_candidates": invalid,
                "prompt_tokens": int(prompt_tokens),
                "completion_tokens": int(completion_tokens),
            }

    async def _record_chunk_status(
        self,
        *,
        run_id: UUID,
        chunk_id: UUID,
        status: str,
        response_sha256: str,
        prompt_tokens: int,
        completion_tokens: int,
        error_code: str,
    ) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                update(ExtractionChunkModel)
                .where(
                    ExtractionChunkModel.extraction_run_id == run_id,
                    ExtractionChunkModel.chunk_id == chunk_id,
                )
                .values(
                    status=status,
                    response_sha256=response_sha256,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    error_code=error_code,
                    processed_at=func.now(),
                )
            )

    @staticmethod
    async def _add_evidence(
        session: AsyncSession,
        run_id: UUID,
        source: ExtractionSourceChunk,
        item: ValidatedItem,
    ) -> UUID | None:
        if item.errors or item.evidence is None:
            return None
        evidence_id = uuid4()
        session.add(
            EvidenceSpanModel(
                id=evidence_id,
                extraction_run_id=run_id,
                document_version_id=source.document_version_id,
                section_id=source.section_id,
                chunk_id=source.id,
                quote_text=item.evidence.quote,
                char_start=item.evidence.global_char_start,
                char_end=item.evidence.global_char_end,
                quote_sha256=item.evidence.quote_sha256,
                chunk_content_sha256=item.evidence.chunk_content_sha256,
                validation_status="exact",
            )
        )
        await session.flush()
        return evidence_id
