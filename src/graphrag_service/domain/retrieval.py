from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

RetrievalStrategy = Literal["keyword", "semantic", "hybrid"]


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
    fusion_score: float | None = None


@dataclass(frozen=True, slots=True)
class RetrievalWarning:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    query_id: UUID
    strategy: RetrievalStrategy
    chunks: tuple[RetrievalChunk, ...]
    context_chunks: tuple[RetrievalChunk, ...]
    warnings: tuple[RetrievalWarning, ...]
    truncated: bool
