"""Create Phase 3 model, projection outbox, and retrieval audit structures.

Revision ID: 0003_phase3_retrieval
Revises: 0002_phase2_ingest
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_phase3_retrieval"
down_revision: str | None = "0002_phase2_ingest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("vector_dimension", sa.Integer()),
        sa.Column("distance_metric", sa.String(30)),
        sa.Column(
            "capabilities_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('embedding', 'generation')", name="ck_model_profiles_valid_kind"
        ),
        sa.CheckConstraint(
            "vector_dimension IS NULL OR vector_dimension > 0",
            name="ck_model_profiles_valid_dimension",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_profiles")),
        sa.UniqueConstraint(
            "provider",
            "model_name",
            "vector_dimension",
            name="uq_model_profiles_provider_model_dimension",
        ),
    )
    op.create_index(
        "uq_model_profiles_one_active_embedding",
        "model_profiles",
        ["kind"],
        unique=True,
        postgresql_where=sa.text("kind = 'embedding' AND is_active"),
    )
    op.create_table(
        "projection_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target", sa.String(20), nullable=False),
        sa.Column("object_type", sa.String(50), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("model_profile_id", sa.Uuid()),
        sa.Column(
            "payload_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("lease_owner", sa.String(255)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(100)),
        sa.Column("last_error_message", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "target IN ('qdrant', 'neo4j')",
            name="ck_projection_outbox_valid_target",
        ),
        sa.CheckConstraint(
            "operation IN ('upsert', 'delete')",
            name="ck_projection_outbox_valid_operation",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'succeeded', 'failed')",
            name="ck_projection_outbox_valid_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0",
            name="ck_projection_outbox_valid_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["model_profile_id"],
            ["model_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projection_outbox")),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_projection_outbox_idempotency_key",
        ),
    )
    op.create_index(
        "ix_projection_outbox_claim",
        "projection_outbox",
        ["target", "status", "next_attempt_at"],
    )
    op.create_index(
        "ix_projection_outbox_object",
        "projection_outbox",
        ["target", "object_type", "object_id"],
    )
    op.create_table(
        "projection_status",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target", sa.String(20), nullable=False),
        sa.Column("object_type", sa.String(50), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("model_profile_id", sa.Uuid(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("physical_target", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64)),
        sa.Column("last_error_code", sa.String(100)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'current', 'failed', 'deleted')",
            name="ck_projection_status_valid_status",
        ),
        sa.ForeignKeyConstraint(
            ["model_profile_id"],
            ["model_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projection_status")),
        sa.UniqueConstraint(
            "target",
            "object_type",
            "object_id",
            "model_profile_id",
            name="uq_projection_status_object_profile",
        ),
    )
    op.create_index(
        "ix_projection_status_state",
        "projection_status",
        ["target", "status"],
    )
    op.create_table(
        "retrieval_query_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("query_sha256", sa.String(64), nullable=False),
        sa.Column("strategy", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("model_profile_id", sa.Uuid()),
        sa.Column(
            "request_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "warnings_json",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "strategy IN ('keyword', 'semantic', 'hybrid')",
            name="ck_retrieval_query_runs_valid_strategy",
        ),
        sa.CheckConstraint(
            "status IN ('succeeded', 'degraded', 'failed')",
            name="ck_retrieval_query_runs_valid_status",
        ),
        sa.ForeignKeyConstraint(
            ["model_profile_id"],
            ["model_profiles.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retrieval_query_runs")),
    )
    op.create_index(
        "ix_retrieval_query_runs_created",
        "retrieval_query_runs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_retrieval_query_runs_created", table_name="retrieval_query_runs")
    op.drop_table("retrieval_query_runs")
    op.drop_index("ix_projection_status_state", table_name="projection_status")
    op.drop_table("projection_status")
    op.drop_index("ix_projection_outbox_object", table_name="projection_outbox")
    op.drop_index("ix_projection_outbox_claim", table_name="projection_outbox")
    op.drop_table("projection_outbox")
    op.execute("DROP INDEX IF EXISTS uq_model_profiles_one_active_embedding")
    op.drop_table("model_profiles")
