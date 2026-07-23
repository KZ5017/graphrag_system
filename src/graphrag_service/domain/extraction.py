from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from graphrag_service.domain.ontology import OntologySnapshot


class EvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote: str = Field(min_length=1, max_length=2000)
    quote_occurrence: int = Field(default=1, ge=1, le=100)


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=500)
    entity_type: str = Field(min_length=1, max_length=50)
    entity_subtype: str | None = Field(default=None, max_length=100)
    proposed_subtype: str | None = Field(default=None, max_length=100)
    scope: str
    assertion_kind: str
    evidence: EvidenceInput


class ExtractedRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_local_id: str = Field(min_length=1, max_length=40)
    predicate: str = Field(min_length=1, max_length=50)
    object_local_id: str = Field(min_length=1, max_length=40)
    assertion_kind: str
    network_layer: str | None = None
    evidence: EvidenceInput


class ExtractedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    assertion_kind: str
    evidence: EvidenceInput


class ExtractionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: list[ExtractedEntity] = Field(default_factory=list, max_length=40)
    relationships: list[ExtractedRelationship] = Field(default_factory=list, max_length=40)
    claims: list[ExtractedClaim] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def references_known_entities(self) -> ExtractionEnvelope:
        ids = [entity.local_id for entity in self.entities]
        if len(ids) != len(set(ids)):
            raise ValueError("entity local_id values must be unique")
        known = set(ids)
        for relationship in self.relationships:
            if relationship.subject_local_id not in known:
                raise ValueError("relationship subject_local_id is unknown")
            if relationship.object_local_id not in known:
                raise ValueError("relationship object_local_id is unknown")
        return self


@dataclass(frozen=True, slots=True)
class ExactEvidence:
    quote: str
    local_char_start: int
    local_char_end: int
    global_char_start: int
    global_char_end: int
    quote_sha256: str
    chunk_content_sha256: str


@dataclass(frozen=True, slots=True)
class EvidenceError:
    code: Literal["missing_quote", "quote_occurrence_missing"]
    detail: str


def locate_exact_evidence(
    *,
    chunk_text: str,
    chunk_char_start: int,
    chunk_content_sha256: str,
    evidence: EvidenceInput,
) -> ExactEvidence | EvidenceError:
    offsets: list[int] = []
    cursor = 0
    while True:
        offset = chunk_text.find(evidence.quote, cursor)
        if offset < 0:
            break
        offsets.append(offset)
        cursor = offset + 1
    if not offsets:
        return EvidenceError("missing_quote", "The quote is not present verbatim in the chunk.")
    occurrence_index = 0 if len(offsets) == 1 else evidence.quote_occurrence - 1
    if occurrence_index >= len(offsets):
        return EvidenceError(
            "quote_occurrence_missing",
            "The requested exact quote occurrence is not present in the chunk.",
        )
    local_start = offsets[occurrence_index]
    local_end = local_start + len(evidence.quote)
    return ExactEvidence(
        quote=evidence.quote,
        local_char_start=local_start,
        local_char_end=local_end,
        global_char_start=chunk_char_start + local_start,
        global_char_end=chunk_char_start + local_end,
        quote_sha256=hashlib.sha256(evidence.quote.encode("utf-8")).hexdigest(),
        chunk_content_sha256=chunk_content_sha256,
    )


def validate_ontology(
    envelope: ExtractionEnvelope,
    ontology: OntologySnapshot,
) -> list[tuple[str, int, str]]:
    errors: list[tuple[str, int, str]] = []
    for index, entity in enumerate(envelope.entities):
        if entity.entity_type not in ontology.entity_types:
            errors.append(("entity", index, "unknown_entity_type"))
        elif not ontology.valid_subtype(entity.entity_type, entity.entity_subtype):
            errors.append(("entity", index, "unknown_entity_subtype"))
        if entity.scope not in ontology.entity_scopes:
            errors.append(("entity", index, "unknown_entity_scope"))
        if entity.assertion_kind not in ontology.assertion_kinds:
            errors.append(("entity", index, "unknown_assertion_kind"))
    for index, relationship in enumerate(envelope.relationships):
        if relationship.predicate not in ontology.predicates:
            errors.append(("relationship", index, "unknown_predicate"))
        if relationship.assertion_kind not in ontology.assertion_kinds:
            errors.append(("relationship", index, "unknown_assertion_kind"))
        if (
            relationship.network_layer is not None
            and relationship.network_layer not in ontology.network_layers
        ):
            errors.append(("relationship", index, "unknown_network_layer"))
    for index, claim in enumerate(envelope.claims):
        if claim.assertion_kind not in ontology.assertion_kinds:
            errors.append(("claim", index, "unknown_assertion_kind"))
    return errors
