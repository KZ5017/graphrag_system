"""Seed the immutable telecom ontology v0.1 and generation profile constraints.

Revision ID: 0005_phase4_registry_seed
Revises: 0004_phase4_extraction
Create Date: 2026-07-23
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_phase4_registry_seed"
down_revision: str | None = "0004_phase4_extraction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ONTOLOGY_ID = UUID("00000000-0000-4000-8000-000000000401")

ENTITY_TYPES = {
    "ORGANIZATION": "company or organization",
    "ORG_UNIT": "directorate, department, or team",
    "PERSON": "person named in the document",
    "ROLE": "job or functional role",
    "PROCESS": "business or technical process",
    "CAPABILITY": "enterprise capability",
    "POLICY": "rule, policy, or principle",
    "PRODUCT": "sellable product",
    "SERVICE": "customer-facing or internal service",
    "CUSTOMER_SEGMENT": "customer segment",
    "EXTERNAL_PARTY": "partner, supplier, authority, or external party",
    "SYSTEM": "IT or network system",
    "APPLICATION": "application or software",
    "COMPONENT": "system component or subsystem",
    "NETWORK_ELEMENT": "logical or physical network element",
    "DEVICE_MODEL": "device model",
    "DEVICE_INSTANCE": "specific device instance",
    "NETWORK_SEGMENT": "network segment or domain",
    "INTERFACE": "physical or logical interface",
    "PROTOCOL": "network or application protocol",
    "TECHNOLOGY": "technology or standard",
    "SITE": "site, node location, or POP",
    "LOCATION": "geographic or organizational location",
    "INFRASTRUCTURE_ASSET": "cable, route, rack, or infrastructure asset",
    "DOCUMENT": "object referenced as a document",
    "CONCEPT": "concept, method, or abstract category",
    "OTHER": "controlled fallback",
}

ENTITY_SUBTYPES = {
    "NETWORK_ELEMENT": (
        "CMTS",
        "CBR",
        "ASR_ROUTER",
        "OLT",
        "HFC_NODE",
        "ACCESS_NODE",
        "AGGREGATION_ROUTER",
    ),
    "DEVICE_MODEL": ("ONT", "CABLE_MODEM", "SMART_DEVICE", "ROUTER", "SWITCH", "SET_TOP_BOX"),
    "DEVICE_INSTANCE": (
        "ONT",
        "CABLE_MODEM",
        "SMART_DEVICE",
        "ROUTER",
        "SWITCH",
        "SET_TOP_BOX",
    ),
}

PREDICATES = (
    "PART_OF",
    "INSTANCE_OF",
    "HAS_COMPONENT",
    "DEPENDS_ON",
    "USES",
    "SUPPORTS",
    "IMPLEMENTS",
    "OWNS",
    "RESPONSIBLE_FOR",
    "OPERATES",
    "MAINTAINS",
    "INPUT_TO",
    "OUTPUT_OF",
    "PRECEDES",
    "TRIGGERS",
    "PROVIDES",
    "SERVES",
    "SUPPLIED_BY",
    "CONNECTS_TO",
    "TERMINATES_AT",
    "ROUTES_VIA",
    "LOCATED_AT",
    "DESCRIBES",
    "APPLIES_TO",
    "REFERENCES",
    "RELATED_TO",
)

NETWORK_LAYERS = (
    "physical",
    "access",
    "layer_2",
    "layer_3",
    "transport",
    "service",
    "business",
)


def upgrade() -> None:
    op.create_index(
        "uq_model_profiles_generation_provider_model",
        "model_profiles",
        ["provider", "model_name"],
        unique=True,
        postgresql_where=sa.text("kind = 'generation'"),
    )
    op.create_index(
        "uq_model_profiles_one_active_generation",
        "model_profiles",
        ["kind"],
        unique=True,
        postgresql_where=sa.text("kind = 'generation' AND is_active"),
    )

    ontology_versions = sa.table(
        "ontology_versions",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("version", sa.String()),
        sa.column("content_sha256", sa.String()),
        sa.column("status", sa.String()),
    )
    entity_types = sa.table(
        "entity_type_definitions",
        sa.column("id", sa.Uuid()),
        sa.column("ontology_version_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("is_fallback", sa.Boolean()),
    )
    entity_subtypes = sa.table(
        "entity_subtype_definitions",
        sa.column("id", sa.Uuid()),
        sa.column("ontology_version_id", sa.Uuid()),
        sa.column("entity_type_code", sa.String()),
        sa.column("code", sa.String()),
        sa.column("description", sa.Text()),
    )
    predicates = sa.table(
        "predicate_definitions",
        sa.column("id", sa.Uuid()),
        sa.column("ontology_version_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.Text()),
    )
    properties = sa.table(
        "property_definitions",
        sa.column("id", sa.Uuid()),
        sa.column("ontology_version_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("value_type", sa.String()),
        sa.column("allowed_values_json", postgresql.JSONB()),
    )

    canonical = json.dumps(
        {
            "entity_types": ENTITY_TYPES,
            "entity_subtypes": ENTITY_SUBTYPES,
            "predicates": PREDICATES,
            "network_layers": NETWORK_LAYERS,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    op.bulk_insert(
        ontology_versions,
        [
            {
                "id": ONTOLOGY_ID,
                "code": "telecom-core",
                "version": "0.1",
                "content_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                "status": "active",
            }
        ],
    )
    op.bulk_insert(
        entity_types,
        [
            {
                "id": uuid5(ONTOLOGY_ID, f"entity-type:{code}"),
                "ontology_version_id": ONTOLOGY_ID,
                "code": code,
                "description": description,
                "is_fallback": code == "OTHER",
            }
            for code, description in ENTITY_TYPES.items()
        ],
    )
    op.bulk_insert(
        entity_subtypes,
        [
            {
                "id": uuid5(ONTOLOGY_ID, f"entity-subtype:{entity_type}:{code}"),
                "ontology_version_id": ONTOLOGY_ID,
                "entity_type_code": entity_type,
                "code": code,
                "description": None,
            }
            for entity_type, codes in ENTITY_SUBTYPES.items()
            for code in codes
        ],
    )
    op.bulk_insert(
        predicates,
        [
            {
                "id": uuid5(ONTOLOGY_ID, f"predicate:{code}"),
                "ontology_version_id": ONTOLOGY_ID,
                "code": code,
                "description": None,
            }
            for code in PREDICATES
        ],
    )
    op.bulk_insert(
        properties,
        [
            {
                "id": uuid5(ONTOLOGY_ID, "property:network_layer"),
                "ontology_version_id": ONTOLOGY_ID,
                "code": "network_layer",
                "value_type": "enum",
                "allowed_values_json": list(NETWORK_LAYERS),
            }
        ],
    )


def downgrade() -> None:
    # Runs pin the ontology with RESTRICT; registry downgrade discards Phase 4 runs.
    op.execute(sa.text("DELETE FROM extraction_runs"))
    op.execute(sa.text("DELETE FROM ontology_versions WHERE id = :id").bindparams(id=ONTOLOGY_ID))
    op.drop_index(
        "uq_model_profiles_one_active_generation",
        table_name="model_profiles",
        postgresql_where=sa.text("kind = 'generation' AND is_active"),
    )
    op.drop_index(
        "uq_model_profiles_generation_provider_model",
        table_name="model_profiles",
        postgresql_where=sa.text("kind = 'generation'"),
    )
