from __future__ import annotations

from typing import Any

from graphrag_service.domain.ontology import (
    ASSERTION_KINDS,
    ENTITY_SCOPES,
    ENTITY_TYPES,
    NETWORK_LAYERS,
    PREDICATES,
)


def grammar_compatible_extraction_schema() -> dict[str, Any]:
    """A deliberately small JSON Schema subset accepted by llama.cpp grammars.

    Pydantic remains the authoritative validation gate after generation.
    """
    evidence = {
        "type": "object",
        "properties": {
            "quote": {"type": "string"},
            "quote_occurrence": {"type": "integer"},
        },
        "required": ["quote", "quote_occurrence"],
        "additionalProperties": False,
    }
    entity = {
        "type": "object",
        "properties": {
            "local_id": {"type": "string"},
            "name": {"type": "string"},
            "entity_type": {"type": "string", "enum": list(ENTITY_TYPES)},
            "entity_subtype": {"type": ["string", "null"]},
            "proposed_subtype": {"type": ["string", "null"]},
            "scope": {"type": "string", "enum": list(ENTITY_SCOPES)},
            "assertion_kind": {"type": "string", "enum": list(ASSERTION_KINDS)},
            "evidence": evidence,
        },
        "required": [
            "local_id",
            "name",
            "entity_type",
            "entity_subtype",
            "proposed_subtype",
            "scope",
            "assertion_kind",
            "evidence",
        ],
        "additionalProperties": False,
    }
    relationship = {
        "type": "object",
        "properties": {
            "subject_local_id": {"type": "string"},
            "predicate": {"type": "string", "enum": list(PREDICATES)},
            "object_local_id": {"type": "string"},
            "assertion_kind": {"type": "string", "enum": list(ASSERTION_KINDS)},
            "network_layer": {"enum": [*NETWORK_LAYERS, None]},
            "evidence": evidence,
        },
        "required": [
            "subject_local_id",
            "predicate",
            "object_local_id",
            "assertion_kind",
            "network_layer",
            "evidence",
        ],
        "additionalProperties": False,
    }
    claim = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "assertion_kind": {"type": "string", "enum": list(ASSERTION_KINDS)},
            "evidence": evidence,
        },
        "required": ["text", "assertion_kind", "evidence"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "entities": {"type": "array", "items": entity, "maxItems": 12},
            "relationships": {"type": "array", "items": relationship, "maxItems": 12},
            "claims": {"type": "array", "items": claim, "maxItems": 8},
        },
        "required": ["entities", "relationships", "claims"],
        "additionalProperties": False,
    }
