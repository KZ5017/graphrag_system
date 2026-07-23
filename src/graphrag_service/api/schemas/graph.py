from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: UUID
    chunk_id: UUID
    document_id: UUID
    relative_path: str
    quote: str
    char_start: int
    char_end: int


class EntityDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    vault_id: UUID
    canonical_name: str
    entity_type: str
    entity_subtype: str | None
    scope: str
    status: str
    aliases: list[str]
    identifiers: list[dict[str, str]]
    evidence: list[EvidenceResponse]


class NeighborResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity: dict[str, Any]
    assertion: dict[str, Any]
    direction: str


class NeighborListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: UUID
    neighbors: list[NeighborResponse]
    truncated: bool


class GraphPathRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_entity_id: UUID
    to_entity_id: UUID
    max_hops: int = Field(default=3, ge=1, le=4)
    max_paths: int = Field(default=10, ge=1, le=50)
    predicate_allowlist: list[str] = Field(default_factory=list, max_length=30)
    include_unreviewed: bool = True


class GraphPathResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: list[dict[str, Any]]
    truncated: bool
