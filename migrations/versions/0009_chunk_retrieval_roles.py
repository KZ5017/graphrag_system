"""Classify structural anchors and content evidence.

Revision ID: 0009_chunk_retrieval_roles
Revises: 0008_scope_identifiers_by_vault
Create Date: 2026-07-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_chunk_retrieval_roles"
down_revision: str | None = "0008_scope_identifiers_by_vault"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("retrieval_role", sa.String(30), nullable=True))
    op.execute(
        sa.text(
            "UPDATE chunks AS chunk "
            "SET retrieval_role = CASE WHEN EXISTS ("
            "SELECT 1 FROM content_blocks AS block "
            "WHERE block.document_version_id = chunk.document_version_id "
            "AND block.char_start < chunk.char_end "
            "AND block.char_end > chunk.char_start "
            "AND block.block_type NOT IN ('heading', 'thematic_break')"
            ") THEN 'content_evidence' ELSE 'structural_anchor' END"
        )
    )
    op.alter_column("chunks", "retrieval_role", nullable=False)
    op.create_check_constraint(
        op.f("ck_chunks_valid_retrieval_role"),
        "chunks",
        "retrieval_role IN ('structural_anchor', 'content_evidence')",
    )
    op.execute(sa.text("UPDATE chunks SET projection_generation = projection_generation + 1"))


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_chunks_valid_retrieval_role"),
        "chunks",
        type_="check",
    )
    op.drop_column("chunks", "retrieval_role")
