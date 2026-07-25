from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

RetrievalStrategy = Literal["keyword", "semantic", "hybrid"]
RetrievalQueryType = Literal["keyword", "semantic", "hybrid", "entity", "graph"]


@dataclass(frozen=True, slots=True)
class RetrievalChunk:
    chunk_id: UUID
    vault_id: UUID
    document_id: UUID
    document_version_id: UUID
    section_id: UUID
    relative_path: str
    heading_path: tuple[str, ...]
    text: str
    char_start: int
    char_end: int
    content_sha256: str
    source_uri: str
    obsidian_uri: str | None
    keyword_score: float | None = None
    semantic_score: float | None = None
    graph_score: float | None = None
    claim_score: float | None = None
    fusion_score: float | None = None


@dataclass(frozen=True, slots=True)
class RetrievalEntity:
    entity_id: UUID
    vault_id: UUID
    canonical_name: str
    entity_type: str
    entity_subtype: str | None
    scope: str
    score: float
    seed_channels: tuple[str, ...]
    source_chunk_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class RetrievalRelationship:
    assertion_id: UUID
    subject_entity_id: UUID
    object_entity_id: UUID
    predicate: str
    assertion_kind: str
    review_status: str
    evidence_id: UUID
    source_chunk_id: UUID
    quote: str
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class RetrievalClaim:
    claim_id: UUID
    text: str
    assertion_kind: str
    review_status: str
    evidence_id: UUID
    source_chunk_id: UUID
    quote: str
    char_start: int
    char_end: int
    score: float
    seed_channels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalPath:
    entity_ids: tuple[UUID, ...]
    assertion_ids: tuple[UUID, ...]
    source_chunk_ids: tuple[UUID, ...]
    hops: int


@dataclass(frozen=True, slots=True)
class RetrievalWarning:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    query_id: UUID
    query_type: RetrievalQueryType
    retrieval_plan: tuple[str, ...]
    planner_reason_code: str
    strategy: RetrievalStrategy
    chunks: tuple[RetrievalChunk, ...]
    context_chunks: tuple[RetrievalChunk, ...]
    entities: tuple[RetrievalEntity, ...]
    relationships: tuple[RetrievalRelationship, ...]
    claims: tuple[RetrievalClaim, ...]
    retrieval_paths: tuple[RetrievalPath, ...]
    warnings: tuple[RetrievalWarning, ...]
    truncated: bool
