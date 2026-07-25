from __future__ import annotations

import re
from collections import defaultdict
from uuid import UUID

from sqlalchemy import and_, exists, false, or_, select
from sqlalchemy.orm import aliased

from graphrag_service.adapters.postgres.extraction_models import EvidenceSpanModel
from graphrag_service.adapters.postgres.ingest_models import (
    ChunkModel,
    DocumentModel,
    DocumentVersionModel,
    SectionModel,
    VaultModel,
)
from graphrag_service.adapters.postgres.resolution_models import (
    ClaimModel,
    EntityAliasModel,
    EntityMentionModel,
    EntityModel,
    RelationshipAssertionModel,
)
from graphrag_service.adapters.postgres.retrieval_store import (
    LEXICAL_STOP_WORDS,
    RetrievalStore,
)
from graphrag_service.domain.retrieval import (
    RetrievalChunk,
    RetrievalClaim,
    RetrievalEntity,
    RetrievalRelationship,
)


class GraphRetrievalStore(RetrievalStore):
    """Current-source PostgreSQL gates for entity and graph retrieval."""

    async def entity_seeds(
        self,
        query: str,
        *,
        chunk_ids: list[UUID],
        limit: int,
        vault_id: UUID | None,
    ) -> list[RetrievalEntity]:
        terms = [
            term
            for term in dict.fromkeys(re.findall(r"[a-záéíóöőúüű0-9_.:-]+", query.casefold()))
            if len(term) > 1 and term not in LEXICAL_STOP_WORDS
        ]
        patterns = [f"%{term}%" for term in terms]
        name_match = (
            or_(*(EntityModel.normalized_name.ilike(pattern) for pattern in patterns))
            if patterns
            else false()
        )
        alias_match = (
            exists(
                select(EntityAliasModel.id).where(
                    EntityAliasModel.entity_id == EntityModel.id,
                    or_(
                        *(EntityAliasModel.normalized_alias.ilike(pattern) for pattern in patterns)
                    ),
                )
            )
            if patterns
            else false()
        )
        chunk_match = EntityMentionModel.chunk_id.in_(chunk_ids) if chunk_ids else false()
        if not patterns and not chunk_ids:
            return []

        statement = (
            select(
                EntityModel,
                EntityMentionModel.chunk_id,
                name_match.label("name_match"),
                alias_match.label("alias_match"),
            )
            .join(EntityMentionModel, EntityMentionModel.entity_id == EntityModel.id)
            .join(ChunkModel, ChunkModel.id == EntityMentionModel.chunk_id)
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
                EntityModel.status == "active",
                EntityMentionModel.mention_status == "active",
                DocumentModel.lifecycle_status == "active",
                DocumentVersionModel.processing_status == "ready",
                or_(name_match, alias_match, chunk_match),
            )
            .order_by(EntityModel.canonical_name, EntityModel.id, EntityMentionModel.chunk_id)
            .limit(min(1000, max(limit * 20, limit)))
        )
        if vault_id is not None:
            statement = statement.where(
                EntityModel.vault_id == vault_id,
                DocumentModel.vault_id == vault_id,
            )

        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()

        chunk_ranks = {chunk_id: rank for rank, chunk_id in enumerate(chunk_ids, start=1)}
        records: dict[UUID, EntityModel] = {}
        scores: dict[UUID, float] = {}
        channels: dict[UUID, set[str]] = defaultdict(set)
        sources: dict[UUID, set[UUID]] = defaultdict(set)
        query_terms = set(terms)
        for entity, source_chunk_id, matched_name, _matched_alias in rows:
            score = 0.0
            normalized_terms = {
                term
                for term in re.findall(
                    r"[a-záéíóöőúüű0-9_.:-]+",
                    entity.normalized_name.casefold(),
                )
                if len(term) > 1 and term not in LEXICAL_STOP_WORDS
            }
            explicit_name_match = bool(
                matched_name and normalized_terms and normalized_terms.issubset(query_terms)
            )
            if explicit_name_match:
                channels[entity.id].add("entity")
                score = 1.0
            if source_chunk_id in chunk_ranks:
                channels[entity.id].add("chunk")
                score = max(score, 1.0 / chunk_ranks[source_chunk_id])
            if not channels[entity.id]:
                continue
            records[entity.id] = entity
            sources[entity.id].add(source_chunk_id)
            scores[entity.id] = max(scores.get(entity.id, 0.0), score)

        entities = [
            RetrievalEntity(
                entity_id=entity.id,
                vault_id=entity.vault_id,
                canonical_name=entity.canonical_name,
                entity_type=entity.entity_type_code,
                entity_subtype=entity.entity_subtype_code,
                scope=entity.entity_scope,
                score=scores[entity.id],
                seed_channels=tuple(sorted(channels[entity.id])),
                source_chunk_ids=tuple(sorted(sources[entity.id], key=str)),
            )
            for entity in records.values()
        ]
        return sorted(
            entities,
            key=lambda item: (-item.score, item.canonical_name.casefold(), str(item.entity_id)),
        )[:limit]

    async def hydrate_assertions(
        self,
        assertion_ids: list[UUID],
    ) -> dict[UUID, tuple[RetrievalRelationship, RetrievalChunk]]:
        if not assertion_ids:
            return {}
        subject = aliased(EntityModel)
        object_ = aliased(EntityModel)
        statement = (
            select(
                RelationshipAssertionModel,
                EvidenceSpanModel,
                ChunkModel,
                SectionModel,
                DocumentVersionModel,
                DocumentModel,
                VaultModel,
            )
            .join(subject, subject.id == RelationshipAssertionModel.subject_entity_id)
            .join(object_, object_.id == RelationshipAssertionModel.object_entity_id)
            .join(
                EvidenceSpanModel,
                EvidenceSpanModel.id == RelationshipAssertionModel.evidence_span_id,
            )
            .join(ChunkModel, ChunkModel.id == EvidenceSpanModel.chunk_id)
            .join(SectionModel, SectionModel.id == ChunkModel.section_id)
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
            .join(VaultModel, VaultModel.id == DocumentModel.vault_id)
            .where(
                RelationshipAssertionModel.id.in_(assertion_ids),
                RelationshipAssertionModel.status == "active",
                subject.status == "active",
                object_.status == "active",
                DocumentModel.lifecycle_status == "active",
                DocumentVersionModel.processing_status == "ready",
                EvidenceSpanModel.validation_status == "exact",
                EvidenceSpanModel.chunk_content_sha256 == ChunkModel.content_sha256,
            )
            .order_by(RelationshipAssertionModel.id)
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()

        result: dict[UUID, tuple[RetrievalRelationship, RetrievalChunk]] = {}
        for assertion, evidence, chunk, section, version, document, vault in rows:
            result[assertion.id] = (
                RetrievalRelationship(
                    assertion_id=assertion.id,
                    subject_entity_id=assertion.subject_entity_id,
                    object_entity_id=assertion.object_entity_id,
                    predicate=assertion.predicate_code,
                    assertion_kind=assertion.assertion_kind,
                    review_status=assertion.review_status,
                    evidence_id=evidence.id,
                    source_chunk_id=chunk.id,
                    quote=evidence.quote_text,
                    char_start=evidence.char_start,
                    char_end=evidence.char_end,
                ),
                self._to_chunk((chunk, section, version, document, vault)),
            )
        return result

    async def claim_candidates(
        self,
        query: str,
        *,
        chunk_ids: list[UUID],
        limit: int,
        vault_id: UUID | None,
    ) -> list[tuple[RetrievalClaim, RetrievalChunk]]:
        terms = [
            term
            for term in dict.fromkeys(re.findall(r"[a-záéíóöőúüű0-9_.:-]+", query.casefold()))
            if len(term) > 1 and term not in LEXICAL_STOP_WORDS
        ]
        patterns = [f"%{term}%" for term in terms]
        text_match = (
            or_(*(ClaimModel.claim_text.ilike(pattern) for pattern in patterns))
            if patterns
            else false()
        )
        chunk_match = EvidenceSpanModel.chunk_id.in_(chunk_ids) if chunk_ids else false()
        if not patterns and not chunk_ids:
            return []

        statement = self._current_claim_statement().where(or_(text_match, chunk_match))
        if vault_id is not None:
            statement = statement.where(DocumentModel.vault_id == vault_id)
        statement = statement.order_by(ClaimModel.id).limit(min(2000, max(limit * 20, limit)))
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()

        chunk_ranks = {chunk_id: rank for rank, chunk_id in enumerate(chunk_ids, start=1)}
        minimum_text_overlap = 1 if len(terms) <= 2 else 2
        candidates: list[tuple[RetrievalClaim, RetrievalChunk]] = []
        for claim, evidence, chunk, section, version, document, vault in rows:
            channels: set[str] = set()
            score = 0.0
            folded = claim.claim_text.casefold()
            overlap = sum(term in folded for term in terms)
            if overlap >= minimum_text_overlap:
                channels.add("claim_text")
                score = overlap / max(1, len(terms))
            if chunk.id in chunk_ranks:
                channels.add("chunk")
                score = max(score, 1.0 / chunk_ranks[chunk.id])
            if not channels:
                continue
            candidates.append(
                (
                    self._to_claim(
                        claim,
                        evidence,
                        chunk,
                        score=score,
                        seed_channels=tuple(sorted(channels)),
                    ),
                    self._to_chunk((chunk, section, version, document, vault)),
                )
            )
        return sorted(
            candidates,
            key=lambda item: (
                -item[0].score,
                item[0].text.casefold(),
                str(item[0].claim_id),
            ),
        )[:limit]

    async def hydrate_claims(
        self,
        claim_ids: list[UUID],
    ) -> dict[UUID, tuple[RetrievalClaim, RetrievalChunk]]:
        if not claim_ids:
            return {}
        statement = (
            self._current_claim_statement()
            .where(ClaimModel.id.in_(claim_ids))
            .order_by(ClaimModel.id)
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return {
            claim.id: (
                self._to_claim(
                    claim,
                    evidence,
                    chunk,
                    score=1.0,
                    seed_channels=("claim_id",),
                ),
                self._to_chunk((chunk, section, version, document, vault)),
            )
            for claim, evidence, chunk, section, version, document, vault in rows
        }

    @staticmethod
    def _current_claim_statement():
        return (
            select(
                ClaimModel,
                EvidenceSpanModel,
                ChunkModel,
                SectionModel,
                DocumentVersionModel,
                DocumentModel,
                VaultModel,
            )
            .join(
                EvidenceSpanModel,
                EvidenceSpanModel.id == ClaimModel.evidence_span_id,
            )
            .join(ChunkModel, ChunkModel.id == EvidenceSpanModel.chunk_id)
            .join(SectionModel, SectionModel.id == ChunkModel.section_id)
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
            .join(VaultModel, VaultModel.id == DocumentModel.vault_id)
            .where(
                ClaimModel.status == "active",
                DocumentModel.lifecycle_status == "active",
                DocumentVersionModel.processing_status == "ready",
                EvidenceSpanModel.validation_status == "exact",
                EvidenceSpanModel.chunk_content_sha256 == ChunkModel.content_sha256,
            )
        )

    @staticmethod
    def _to_claim(
        claim: ClaimModel,
        evidence: EvidenceSpanModel,
        chunk: ChunkModel,
        *,
        score: float,
        seed_channels: tuple[str, ...],
    ) -> RetrievalClaim:
        return RetrievalClaim(
            claim_id=claim.id,
            text=claim.claim_text,
            assertion_kind=claim.assertion_kind,
            review_status=claim.review_status,
            evidence_id=evidence.id,
            source_chunk_id=chunk.id,
            quote=evidence.quote_text,
            char_start=evidence.char_start,
            char_end=evidence.char_end,
            score=score,
            seed_channels=seed_channels,
        )
