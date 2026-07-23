from __future__ import annotations

from graphrag_service.domain.extraction_schema import (
    grammar_compatible_extraction_schema,
)
from graphrag_service.domain.ontology import ENTITY_TYPES, PREDICATES


def test_grammar_schema_uses_flat_llama_cpp_compatible_subset() -> None:
    schema = grammar_compatible_extraction_schema()
    assert "$defs" not in schema
    entity = schema["properties"]["entities"]["items"]
    relationship = schema["properties"]["relationships"]["items"]
    assert entity["properties"]["entity_type"]["enum"] == list(ENTITY_TYPES)
    assert relationship["properties"]["predicate"]["enum"] == list(PREDICATES)
    assert entity["additionalProperties"] is False
    assert schema["required"] == ["entities", "relationships", "claims"]
