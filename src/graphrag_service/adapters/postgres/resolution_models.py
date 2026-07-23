from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from graphrag_service.adapters.postgres.base import Base


class IdentifierNormalizationRuleModel(Base):
    __tablename__ = "identifier_normalization_rules"
    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_identifier_rules_code_version"),
        CheckConstraint("status IN ('active', 'retired')", name="valid_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EntityModel(Base):
    __tablename__ = "entities"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'merged', 'superseded')", name="valid_status"),
        Index("ix_entities_type_normalized", "entity_type_code", "normalized_name"),
        Index("ix_entities_scope_status", "entity_scope", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    vault_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False
    )
    ontology_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ontology_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_from_candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("entity_candidates.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    entity_type_code: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_subtype_code: Mapped[str | None] = mapped_column(String(100))
    entity_scope: Mapped[str] = mapped_column(String(30), nullable=False)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'active'")
    )
    merged_into_entity_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EntityIdentifierModel(Base):
    __tablename__ = "entity_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "vault_id",
            "normalization_rule_id",
            "identifier_kind",
            "normalized_value",
            "entity_type_code",
            "entity_scope",
            name="uq_entity_identifiers_strong_identity",
        ),
        UniqueConstraint(
            "entity_id",
            "identifier_kind",
            "normalized_value",
            name="uq_entity_identifiers_entity_value",
        ),
        Index("ix_entity_identifiers_entity", "entity_id"),
    )

    vault_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    entity_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    source_candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("entity_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_span_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence_spans.id", ondelete="CASCADE"),
        nullable=False,
    )
    normalization_rule_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("identifier_normalization_rules.id", ondelete="RESTRICT"),
        nullable=False,
    )
    identifier_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    identifier_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type_code: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_scope: Mapped[str] = mapped_column(String(30), nullable=False)


class EntityAliasModel(Base):
    __tablename__ = "entity_aliases"
    __table_args__ = (
        UniqueConstraint("entity_id", "source_candidate_id", name="uq_entity_aliases_candidate"),
        Index("ix_entity_aliases_normalized", "normalized_alias"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    entity_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    source_candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("entity_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_span_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence_spans.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_alias: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(20))
    validation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'exact'")
    )


class EntityMentionModel(Base):
    __tablename__ = "entity_mentions"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_entity_mentions_candidate"),
        Index("ix_entity_mentions_entity", "entity_id"),
        Index("ix_entity_mentions_chunk", "chunk_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    entity_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("entity_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    extraction_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    evidence_span_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence_spans.id", ondelete="CASCADE"),
        nullable=False,
    )
    surface_form: Mapped[str] = mapped_column(Text, nullable=False)
    mention_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'active'")
    )


class ResolutionDecisionModel(Base):
    __tablename__ = "resolution_decisions"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_resolution_decisions_candidate"),
        CheckConstraint(
            "decision IN ('create', 'merge', 'keep_separate', 'defer')",
            name="valid_decision",
        ),
        CheckConstraint(
            "method IN ('deterministic_new', 'deterministic_strong_identifier', 'human')",
            name="valid_method",
        ),
        Index("ix_resolution_decisions_run", "extraction_run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    extraction_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("entity_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    matched_entity_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE")
    )
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    rule_version: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[str] = mapped_column(String(100), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResolutionReviewCandidateModel(Base):
    __tablename__ = "resolution_review_candidates"
    __table_args__ = (
        UniqueConstraint(
            "source_candidate_id",
            "target_entity_id",
            "match_method",
            name="uq_resolution_review_candidate_pair",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'deferred')",
            name="valid_status",
        ),
        CheckConstraint("score >= 0 AND score <= 1", name="valid_score"),
        Index("ix_resolution_review_queue", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    source_candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("entity_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_entity_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE")
    )
    target_entity_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    match_method: Mapped[str] = mapped_column(String(30), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'pending'")
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RelationshipAssertionModel(Base):
    __tablename__ = "relationship_assertions"
    __table_args__ = (
        UniqueConstraint("source_candidate_id", name="uq_relationship_assertions_candidate"),
        CheckConstraint("status IN ('active', 'inactive')", name="valid_status"),
        Index("ix_relationship_assertions_subject", "subject_entity_id", "status"),
        Index("ix_relationship_assertions_object", "object_entity_id", "status"),
        Index("ix_relationship_assertions_predicate", "predicate_code", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    source_candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("relationship_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    extraction_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    evidence_span_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence_spans.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject_entity_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    object_entity_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    predicate_code: Mapped[str] = mapped_column(String(50), nullable=False)
    assertion_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False)
    network_layer: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'active'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ClaimModel(Base):
    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("source_candidate_id", name="uq_claims_candidate"),
        CheckConstraint("status IN ('active', 'inactive')", name="valid_status"),
        Index("ix_claims_run_status", "extraction_run_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    source_candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("claim_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    extraction_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    evidence_span_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence_spans.id", ondelete="CASCADE"),
        nullable=False,
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    assertion_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'active'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Neo4jProjectionRunModel(Base):
    __tablename__ = "neo4j_projection_runs"
    __table_args__ = (
        UniqueConstraint("vault_id", "snapshot_sha256", name="uq_neo4j_projection_runs_snapshot"),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="valid_status",
        ),
        Index("ix_neo4j_projection_runs_vault_created", "vault_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    vault_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False
    )
    outbox_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projection_outbox.id", ondelete="SET NULL")
    )
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    generation: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    object_count: Mapped[int] = mapped_column(nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
