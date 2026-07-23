from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from graphrag_service.adapters.postgres.extraction_models import (
    ClaimCandidateModel,
    EntityCandidateModel,
    EvidenceSpanModel,
    ExtractionRunModel,
    RelationshipCandidateModel,
)
from graphrag_service.adapters.postgres.resolution_models import (
    ClaimModel,
    EntityAliasModel,
    EntityIdentifierModel,
    EntityMentionModel,
    EntityModel,
    IdentifierNormalizationRuleModel,
    RelationshipAssertionModel,
    ResolutionDecisionModel,
    ResolutionReviewCandidateModel,
)
from graphrag_service.domain.resolution import (
    NORMALIZATION_RULE_CODE,
    NORMALIZATION_RULE_VERSION,
    ResolutionCandidate,
    StrongIdentifier,
    normalize_entity_name,
)


@dataclass(frozen=True, slots=True)
class CandidateResolutionResult:
    decision: str
    entity_id: UUID | None
    review_candidates: int


class ResolutionStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def load_unresolved_candidates(self, run_id: UUID) -> tuple[ResolutionCandidate, ...]:
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(
                        EntityCandidateModel,
                        EvidenceSpanModel,
                        ExtractionRunModel,
                    )
                    .join(
                        EvidenceSpanModel,
                        EvidenceSpanModel.id == EntityCandidateModel.evidence_span_id,
                    )
                    .join(
                        ExtractionRunModel,
                        ExtractionRunModel.id == EntityCandidateModel.extraction_run_id,
                    )
                    .outerjoin(
                        ResolutionDecisionModel,
                        ResolutionDecisionModel.candidate_id == EntityCandidateModel.id,
                    )
                    .where(
                        EntityCandidateModel.extraction_run_id == run_id,
                        EntityCandidateModel.validation_status == "valid",
                        ResolutionDecisionModel.id.is_(None),
                    )
                    .order_by(
                        EntityCandidateModel.chunk_id,
                        EntityCandidateModel.local_id,
                        EntityCandidateModel.id,
                    )
                )
            ).all()
        return tuple(
            ResolutionCandidate(
                candidate_id=candidate.id,
                extraction_run_id=candidate.extraction_run_id,
                vault_id=run.vault_id,
                ontology_version_id=run.ontology_version_id,
                chunk_id=candidate.chunk_id,
                evidence_span_id=evidence.id,
                name=candidate.name,
                entity_type=candidate.entity_type_code,
                entity_subtype=candidate.entity_subtype_code,
                scope=candidate.entity_scope,
                assertion_kind=candidate.assertion_kind,
                evidence_quote=evidence.quote_text,
            )
            for candidate, evidence, run in rows
        )

    async def resolve_candidate(
        self,
        candidate: ResolutionCandidate,
        identifiers: tuple[StrongIdentifier, ...],
    ) -> CandidateResolutionResult:
        async with self._sessions.begin() as session:
            existing_decision = await session.scalar(
                select(ResolutionDecisionModel)
                .where(ResolutionDecisionModel.candidate_id == candidate.candidate_id)
                .with_for_update()
            )
            if existing_decision is not None:
                return CandidateResolutionResult(
                    decision=existing_decision.decision,
                    entity_id=existing_decision.matched_entity_id,
                    review_candidates=0,
                )
            rule = await session.scalar(
                select(IdentifierNormalizationRuleModel).where(
                    IdentifierNormalizationRuleModel.code == NORMALIZATION_RULE_CODE,
                    IdentifierNormalizationRuleModel.version == NORMALIZATION_RULE_VERSION,
                    IdentifierNormalizationRuleModel.status == "active",
                )
            )
            if rule is None:
                raise LookupError("active identifier normalization rule not found")

            matched_ids: set[UUID] = set()
            for identifier in identifiers:
                matched_ids.update(
                    await session.scalars(
                        select(EntityIdentifierModel.entity_id)
                        .join(EntityModel, EntityModel.id == EntityIdentifierModel.entity_id)
                        .where(
                            EntityIdentifierModel.vault_id == candidate.vault_id,
                            EntityIdentifierModel.normalization_rule_id == rule.id,
                            EntityIdentifierModel.identifier_kind == identifier.kind,
                            EntityIdentifierModel.normalized_value == identifier.normalized_value,
                            EntityIdentifierModel.entity_type_code == candidate.entity_type,
                            EntityIdentifierModel.entity_scope == candidate.scope,
                            EntityModel.vault_id == candidate.vault_id,
                            EntityModel.status == "active",
                        )
                    )
                )

            entity: EntityModel | None
            if len(matched_ids) > 1:
                session.add(
                    ResolutionDecisionModel(
                        extraction_run_id=candidate.extraction_run_id,
                        candidate_id=candidate.candidate_id,
                        matched_entity_id=None,
                        decision="defer",
                        method="deterministic_strong_identifier",
                        score=None,
                        rule_version=NORMALIZATION_RULE_VERSION,
                        reason="strong identifiers resolve to conflicting canonical entities",
                        decided_by="entity-resolution-service",
                    )
                )
                return CandidateResolutionResult("defer", None, 0)
            if matched_ids:
                entity = await session.get(EntityModel, next(iter(matched_ids)))
                if entity is None:
                    raise LookupError("matched canonical entity not found")
                decision_code = "merge"
                method = "deterministic_strong_identifier"
                reason = "compatible type/scope and normalized strong identifier match"
                score: Decimal | None = Decimal("1.0000")
            else:
                entity = EntityModel(
                    vault_id=candidate.vault_id,
                    ontology_version_id=candidate.ontology_version_id,
                    created_from_candidate_id=candidate.candidate_id,
                    entity_type_code=candidate.entity_type,
                    entity_subtype_code=candidate.entity_subtype,
                    entity_scope=candidate.scope,
                    canonical_name=candidate.name,
                    normalized_name=normalize_entity_name(candidate.name),
                    status="active",
                )
                session.add(entity)
                await session.flush()
                decision_code = "create"
                method = "deterministic_new"
                reason = (
                    "no compatible canonical entity had the same normalized strong identifier"
                    if identifiers
                    else "no strong identifier was present; a separate entity was created"
                )
                score = None

            existing_identifier_keys = {
                (kind, normalized)
                for kind, normalized in (
                    await session.execute(
                        select(
                            EntityIdentifierModel.identifier_kind,
                            EntityIdentifierModel.normalized_value,
                        ).where(EntityIdentifierModel.entity_id == entity.id)
                    )
                ).all()
            }
            for identifier in identifiers:
                if (identifier.kind, identifier.normalized_value) in existing_identifier_keys:
                    continue
                session.add(
                    EntityIdentifierModel(
                        vault_id=candidate.vault_id,
                        entity_id=entity.id,
                        source_candidate_id=candidate.candidate_id,
                        evidence_span_id=candidate.evidence_span_id,
                        normalization_rule_id=rule.id,
                        identifier_kind=identifier.kind,
                        identifier_value=identifier.value,
                        normalized_value=identifier.normalized_value,
                        entity_type_code=candidate.entity_type,
                        entity_scope=candidate.scope,
                    )
                )
            session.add(
                EntityAliasModel(
                    entity_id=entity.id,
                    source_candidate_id=candidate.candidate_id,
                    evidence_span_id=candidate.evidence_span_id,
                    alias=candidate.name,
                    normalized_alias=normalize_entity_name(candidate.name),
                    validation_status="exact",
                )
            )
            session.add(
                EntityMentionModel(
                    entity_id=entity.id,
                    candidate_id=candidate.candidate_id,
                    extraction_run_id=candidate.extraction_run_id,
                    chunk_id=candidate.chunk_id,
                    evidence_span_id=candidate.evidence_span_id,
                    surface_form=candidate.name,
                    mention_status="active",
                )
            )
            session.add(
                ResolutionDecisionModel(
                    extraction_run_id=candidate.extraction_run_id,
                    candidate_id=candidate.candidate_id,
                    matched_entity_id=entity.id,
                    decision=decision_code,
                    method=method,
                    score=score,
                    rule_version=NORMALIZATION_RULE_VERSION,
                    reason=reason,
                    decided_by="entity-resolution-service",
                )
            )
            await session.flush()

            exact_name_targets = list(
                await session.scalars(
                    select(EntityModel)
                    .where(
                        EntityModel.vault_id == candidate.vault_id,
                        EntityModel.entity_type_code == candidate.entity_type,
                        EntityModel.entity_scope == candidate.scope,
                        EntityModel.normalized_name == normalize_entity_name(candidate.name),
                        EntityModel.status == "active",
                        EntityModel.id != entity.id,
                    )
                    .order_by(EntityModel.created_at, EntityModel.id)
                    .limit(20)
                )
            )
            review_count = 0
            for target in exact_name_targets:
                inserted = await session.scalar(
                    insert(ResolutionReviewCandidateModel)
                    .values(
                        source_candidate_id=candidate.candidate_id,
                        source_entity_id=entity.id,
                        target_entity_id=target.id,
                        match_method="exact_name",
                        score=Decimal("1.0000"),
                        status="pending",
                        reason="exact normalized name is review-only and never auto-merges",
                    )
                    .on_conflict_do_nothing(constraint="uq_resolution_review_candidate_pair")
                    .returning(ResolutionReviewCandidateModel.id)
                )
                review_count += int(inserted is not None)
            return CandidateResolutionResult(decision_code, entity.id, review_count)

    async def materialize_assertions(self, run_id: UUID) -> tuple[int, int]:
        async with self._sessions.begin() as session:
            resolved_rows = (
                await session.execute(
                    select(
                        EntityCandidateModel.chunk_id,
                        EntityCandidateModel.local_id,
                        ResolutionDecisionModel.matched_entity_id,
                    )
                    .join(
                        ResolutionDecisionModel,
                        ResolutionDecisionModel.candidate_id == EntityCandidateModel.id,
                    )
                    .where(
                        EntityCandidateModel.extraction_run_id == run_id,
                        ResolutionDecisionModel.matched_entity_id.is_not(None),
                    )
                )
            ).all()
            resolved = {
                (chunk_id, local_id): entity_id for chunk_id, local_id, entity_id in resolved_rows
            }
            relationships = list(
                await session.scalars(
                    select(RelationshipCandidateModel).where(
                        RelationshipCandidateModel.extraction_run_id == run_id,
                        RelationshipCandidateModel.validation_status == "valid",
                        RelationshipCandidateModel.evidence_span_id.is_not(None),
                    )
                )
            )
            inserted_relationships = 0
            for relationship in relationships:
                subject_id = resolved.get((relationship.chunk_id, relationship.subject_local_id))
                object_id = resolved.get((relationship.chunk_id, relationship.object_local_id))
                if subject_id is None or object_id is None:
                    continue
                inserted = await session.scalar(
                    insert(RelationshipAssertionModel)
                    .values(
                        source_candidate_id=relationship.id,
                        extraction_run_id=run_id,
                        evidence_span_id=relationship.evidence_span_id,
                        subject_entity_id=subject_id,
                        object_entity_id=object_id,
                        predicate_code=relationship.predicate_code,
                        assertion_kind=relationship.assertion_kind,
                        review_status=relationship.review_status,
                        network_layer=relationship.network_layer,
                        status="active",
                    )
                    .on_conflict_do_nothing(constraint="uq_relationship_assertions_candidate")
                    .returning(RelationshipAssertionModel.id)
                )
                inserted_relationships += int(inserted is not None)

            claims = list(
                await session.scalars(
                    select(ClaimCandidateModel).where(
                        ClaimCandidateModel.extraction_run_id == run_id,
                        ClaimCandidateModel.validation_status == "valid",
                        ClaimCandidateModel.evidence_span_id.is_not(None),
                    )
                )
            )
            inserted_claims = 0
            for claim in claims:
                inserted = await session.scalar(
                    insert(ClaimModel)
                    .values(
                        source_candidate_id=claim.id,
                        extraction_run_id=run_id,
                        evidence_span_id=claim.evidence_span_id,
                        claim_text=claim.claim_text,
                        assertion_kind=claim.assertion_kind,
                        review_status=claim.review_status,
                        status="active",
                    )
                    .on_conflict_do_nothing(constraint="uq_claims_candidate")
                    .returning(ClaimModel.id)
                )
                inserted_claims += int(inserted is not None)
        return inserted_relationships, inserted_claims
