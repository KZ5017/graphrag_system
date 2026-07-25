from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RetrievalScores(BaseModel):
    keyword: float | None
    semantic: float | None
    graph: float | None
    claim: float | None
    fusion: float | None


class RetrievalSource(BaseModel):
    source_id: UUID
    vault_id: UUID
    document_id: UUID
    document_version_id: UUID
    section_id: UUID
    relative_path: str
    heading_path: list[str]
    quote: str
    char_start: int
    char_end: int
    content_sha256: str
    source_uri: str
    obsidian_uri: str | None


class RetrievalChunkResponse(BaseModel):
    chunk_id: UUID
    text: str
    scores: RetrievalScores
    source: RetrievalSource


class RetrievalEntityResponse(BaseModel):
    entity_id: UUID
    vault_id: UUID
    canonical_name: str
    entity_type: str
    entity_subtype: str | None
    scope: str
    score: float
    seed_channels: list[str]
    source_chunk_ids: list[UUID]


class RetrievalRelationshipResponse(BaseModel):
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


class RetrievalClaimResponse(BaseModel):
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
    seed_channels: list[str]


class RetrievalPathResponse(BaseModel):
    entity_ids: list[UUID]
    assertion_ids: list[UUID]
    source_chunk_ids: list[UUID]
    hops: int


class RetrievalWarningResponse(BaseModel):
    code: str
    message: str


class RetrieveResponse(BaseModel):
    query_id: UUID
    query_type: Literal["keyword", "semantic", "hybrid", "entity", "graph"]
    retrieval_plan: list[str]
    planner_reason_code: str
    strategy: Literal["keyword", "semantic", "hybrid"]
    chunks: list[RetrievalChunkResponse]
    context_chunks: list[RetrievalChunkResponse]
    entities: list[RetrievalEntityResponse] = Field(default_factory=list)
    relationships: list[RetrievalRelationshipResponse] = Field(default_factory=list)
    claims: list[RetrievalClaimResponse] = Field(default_factory=list)
    retrieval_paths: list[RetrievalPathResponse] = Field(default_factory=list)
    sources: list[RetrievalSource]
    warnings: list[RetrievalWarningResponse]
    truncated: bool
    confidence: None = None
