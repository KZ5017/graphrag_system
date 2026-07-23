from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from graphrag_service.adapters.postgres.base import Base


class OntologyVersionModel(Base):
    __tablename__ = "ontology_versions"
    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_ontology_versions_code_version"),
        CheckConstraint("status IN ('draft', 'active', 'retired')", name="valid_status"),
        Index(
            "uq_ontology_versions_one_active",
            "code",
            unique=True,
            postgresql_where=sql_text("status = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EntityTypeDefinitionModel(Base):
    __tablename__ = "entity_type_definitions"
    __table_args__ = (
        UniqueConstraint(
            "ontology_version_id",
            "code",
            name="uq_entity_type_definitions_version_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    ontology_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ontology_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_fallback: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("false")
    )


class EntitySubtypeDefinitionModel(Base):
    __tablename__ = "entity_subtype_definitions"
    __table_args__ = (
        UniqueConstraint(
            "ontology_version_id",
            "entity_type_code",
            "code",
            name="uq_entity_subtype_definitions_version_type_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    ontology_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ontology_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type_code: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class PredicateDefinitionModel(Base):
    __tablename__ = "predicate_definitions"
    __table_args__ = (
        UniqueConstraint(
            "ontology_version_id",
            "code",
            name="uq_predicate_definitions_version_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    ontology_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ontology_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class PredicateInverseMappingModel(Base):
    __tablename__ = "predicate_inverse_mappings"
    __table_args__ = (
        UniqueConstraint(
            "ontology_version_id",
            "predicate_code",
            name="uq_predicate_inverse_mappings_version_predicate",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    ontology_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ontology_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    predicate_code: Mapped[str] = mapped_column(String(50), nullable=False)
    inverse_predicate_code: Mapped[str] = mapped_column(String(50), nullable=False)


class PropertyDefinitionModel(Base):
    __tablename__ = "property_definitions"
    __table_args__ = (
        UniqueConstraint(
            "ontology_version_id",
            "code",
            name="uq_property_definitions_version_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    ontology_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ontology_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    value_type: Mapped[str] = mapped_column(String(30), nullable=False)
    allowed_values_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )


class PromptVersionModel(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_prompt_versions_name_version"),
        CheckConstraint("status IN ('active', 'retired')", name="valid_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    task: Mapped[str] = mapped_column(String(100), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SchemaVersionModel(Base):
    __tablename__ = "schema_versions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_schema_versions_name_version"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    schema_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExtractionRunModel(Base):
    __tablename__ = "extraction_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'partial', 'failed')",
            name="valid_status",
        ),
        CheckConstraint(
            "requested_chunk_count > 0 AND processed_chunk_count >= 0",
            name="valid_counts",
        ),
        UniqueConstraint("job_id", name="uq_extraction_runs_job_id"),
        Index("ix_extraction_runs_created", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL")
    )
    vault_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False
    )
    model_profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("model_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    prompt_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("prompt_versions.id", ondelete="RESTRICT"), nullable=False
    )
    schema_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("schema_versions.id", ondelete="RESTRICT"), nullable=False
    )
    ontology_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ontology_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    requested_chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_chunk_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("0")
    )
    valid_candidate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("0")
    )
    invalid_candidate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("0")
    )
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("0")
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("0")
    )
    warnings_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExtractionChunkModel(Base):
    __tablename__ = "extraction_chunks"
    __table_args__ = (
        UniqueConstraint(
            "extraction_run_id",
            "chunk_id",
            name="uq_extraction_chunks_run_chunk",
        ),
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'schema_invalid', 'provider_failed')",
            name="valid_status",
        ),
        Index("ix_extraction_chunks_run_status", "extraction_run_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    extraction_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    response_sha256: Mapped[str | None] = mapped_column(String(64))
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("0")
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("0")
    )
    error_code: Mapped[str | None] = mapped_column(String(100))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvidenceSpanModel(Base):
    __tablename__ = "evidence_spans"
    __table_args__ = (
        CheckConstraint(
            "char_start >= 0 AND char_end > char_start",
            name="valid_span",
        ),
        CheckConstraint("validation_status = 'exact'", name="exact_only"),
        Index("ix_evidence_spans_chunk", "chunk_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    extraction_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sections.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    quote_text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'exact'")
    )


class EntityCandidateModel(Base):
    __tablename__ = "entity_candidates"
    __table_args__ = (
        CheckConstraint("validation_status IN ('valid', 'invalid')", name="valid_status"),
        UniqueConstraint(
            "extraction_run_id",
            "chunk_id",
            "local_id",
            name="uq_entity_candidates_run_chunk_local",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    extraction_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    evidence_span_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("evidence_spans.id", ondelete="CASCADE")
    )
    local_id: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type_code: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_subtype_code: Mapped[str | None] = mapped_column(String(100))
    proposed_subtype: Mapped[str | None] = mapped_column(String(100))
    entity_scope: Mapped[str] = mapped_column(String(30), nullable=False)
    assertion_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'unreviewed'")
    )
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False)
    validation_errors_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )


class RelationshipCandidateModel(Base):
    __tablename__ = "relationship_candidates"
    __table_args__ = (
        CheckConstraint("validation_status IN ('valid', 'invalid')", name="valid_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    extraction_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    evidence_span_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("evidence_spans.id", ondelete="CASCADE")
    )
    subject_local_id: Mapped[str] = mapped_column(String(20), nullable=False)
    predicate_code: Mapped[str] = mapped_column(String(50), nullable=False)
    object_local_id: Mapped[str] = mapped_column(String(20), nullable=False)
    assertion_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'unreviewed'")
    )
    network_layer: Mapped[str | None] = mapped_column(String(30))
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False)
    validation_errors_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )


class ClaimCandidateModel(Base):
    __tablename__ = "claim_candidates"
    __table_args__ = (
        CheckConstraint("validation_status IN ('valid', 'invalid')", name="valid_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    extraction_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    evidence_span_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("evidence_spans.id", ondelete="CASCADE")
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    assertion_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'unreviewed'")
    )
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False)
    validation_errors_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
