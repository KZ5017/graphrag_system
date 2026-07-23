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


class ModelProfileModel(Base):
    __tablename__ = "model_profiles"
    __table_args__ = (
        CheckConstraint("kind IN ('embedding', 'generation')", name="valid_kind"),
        CheckConstraint("vector_dimension IS NULL OR vector_dimension > 0", name="valid_dimension"),
        UniqueConstraint(
            "provider",
            "model_name",
            "vector_dimension",
            name="uq_model_profiles_provider_model_dimension",
        ),
        Index(
            "uq_model_profiles_one_active_embedding",
            "kind",
            unique=True,
            postgresql_where=sql_text("kind = 'embedding' AND is_active"),
        ),
        Index(
            "uq_model_profiles_generation_provider_model",
            "provider",
            "model_name",
            unique=True,
            postgresql_where=sql_text("kind = 'generation'"),
        ),
        Index(
            "uq_model_profiles_one_active_generation",
            "kind",
            unique=True,
            postgresql_where=sql_text("kind = 'generation' AND is_active"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    vector_dimension: Mapped[int | None] = mapped_column(Integer)
    distance_metric: Mapped[str | None] = mapped_column(String(30))
    capabilities_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProjectionOutboxModel(Base):
    __tablename__ = "projection_outbox"
    __table_args__ = (
        CheckConstraint("target IN ('qdrant', 'neo4j')", name="valid_target"),
        CheckConstraint("operation IN ('upsert', 'delete')", name="valid_operation"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'succeeded', 'failed')",
            name="valid_status",
        ),
        CheckConstraint("attempt_count >= 0 AND max_attempts > 0", name="valid_attempts"),
        UniqueConstraint("idempotency_key", name="uq_projection_outbox_idempotency_key"),
        Index("ix_projection_outbox_claim", "target", "status", "next_attempt_at"),
        Index("ix_projection_outbox_object", "target", "object_type", "object_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    target: Mapped[str] = mapped_column(String(20), nullable=False)
    object_type: Mapped[str] = mapped_column(String(50), nullable=False)
    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    model_profile_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("model_profiles.id", ondelete="CASCADE"),
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'pending'")
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("0")
    )
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("5"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectionStatusModel(Base):
    __tablename__ = "projection_status"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'current', 'failed', 'deleted')",
            name="valid_status",
        ),
        UniqueConstraint(
            "target",
            "object_type",
            "object_id",
            "model_profile_id",
            name="uq_projection_status_object_profile",
        ),
        Index("ix_projection_status_state", "target", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    target: Mapped[str] = mapped_column(String(20), nullable=False)
    object_type: Mapped[str] = mapped_column(String(50), nullable=False)
    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    model_profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("model_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    physical_target: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RetrievalQueryRunModel(Base):
    __tablename__ = "retrieval_query_runs"
    __table_args__ = (
        CheckConstraint("strategy IN ('keyword', 'semantic', 'hybrid')", name="valid_strategy"),
        CheckConstraint("status IN ('succeeded', 'degraded', 'failed')", name="valid_status"),
        Index("ix_retrieval_query_runs_created", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    query_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    model_profile_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("model_profiles.id", ondelete="SET NULL")
    )
    request_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )
    warnings_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
