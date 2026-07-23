from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class IndexJobRequest(BaseModel):
    vault_id: UUID | None = None


class IndexJobAcceptedResponse(BaseModel):
    job_id: UUID
    status: Literal["queued"] = "queued"


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    strategy: Literal["keyword", "semantic", "hybrid"] = "hybrid"
    limit: int = Field(default=10, ge=1, le=50)
    vault_id: UUID | None = None


class RetrievalScores(BaseModel):
    keyword: float | None
    semantic: float | None
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


class RetrievalWarningResponse(BaseModel):
    code: str
    message: str


class RetrieveResponse(BaseModel):
    query_id: UUID
    query_type: Literal["retrieval"] = "retrieval"
    retrieval_plan: list[str]
    strategy: Literal["keyword", "semantic", "hybrid"]
    chunks: list[RetrievalChunkResponse]
    context_chunks: list[RetrievalChunkResponse]
    entities: list[object] = Field(default_factory=list)
    relationships: list[object] = Field(default_factory=list)
    claims: list[object] = Field(default_factory=list)
    retrieval_paths: list[object] = Field(default_factory=list)
    sources: list[RetrievalSource]
    warnings: list[RetrievalWarningResponse]
    truncated: bool
    confidence: None = None
