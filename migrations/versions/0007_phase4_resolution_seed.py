"""Seed the deterministic strong-identifier normalization rule.

Revision ID: 0007_phase4_resolution_seed
Revises: 0006_phase4_resolution_graph
Create Date: 2026-07-24
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "0007_phase4_resolution_seed"
down_revision: str | None = "0006_phase4_resolution_graph"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RULE_ID = UUID("00000000-0000-4000-8000-000000000601")


def upgrade() -> None:
    rules = sa.table(
        "identifier_normalization_rules",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("version", sa.String()),
        sa.column("status", sa.String()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        rules,
        [
            {
                "id": RULE_ID,
                "code": "strong-identifier",
                "version": "1.0",
                "status": "active",
                "description": (
                    "Exact strong identifiers only; compatible entity type and scope required."
                ),
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM identifier_normalization_rules WHERE id = :id").bindparams(id=RULE_ID)
    )
