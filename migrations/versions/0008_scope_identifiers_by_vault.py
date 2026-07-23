"""Scope strong identifier uniqueness by vault.

Revision ID: 0008_scope_identifiers_by_vault
Revises: 0007_phase4_resolution_seed
Create Date: 2026-07-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_scope_identifiers_by_vault"
down_revision: str | None = "0007_phase4_resolution_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("entity_identifiers", sa.Column("vault_id", sa.Uuid(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE entity_identifiers AS identifier "
            "SET vault_id = entity.vault_id "
            "FROM entities AS entity "
            "WHERE entity.id = identifier.entity_id"
        )
    )
    op.alter_column("entity_identifiers", "vault_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_entity_identifiers_vault_id_vaults"),
        "entity_identifiers",
        "vaults",
        ["vault_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "uq_entity_identifiers_strong_identity",
        "entity_identifiers",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_entity_identifiers_strong_identity",
        "entity_identifiers",
        [
            "vault_id",
            "normalization_rule_id",
            "identifier_kind",
            "normalized_value",
            "entity_type_code",
            "entity_scope",
        ],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_entity_identifiers_strong_identity",
        "entity_identifiers",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_entity_identifiers_strong_identity",
        "entity_identifiers",
        [
            "normalization_rule_id",
            "identifier_kind",
            "normalized_value",
            "entity_type_code",
            "entity_scope",
        ],
    )
    op.drop_constraint(
        op.f("fk_entity_identifiers_vault_id_vaults"),
        "entity_identifiers",
        type_="foreignkey",
    )
    op.drop_column("entity_identifiers", "vault_id")
