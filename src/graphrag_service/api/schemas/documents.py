from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: UUID
    vault_id: UUID
    relative_path: str
    title: str | None
    lifecycle_status: Literal["active", "deleted", "error"]
    current_version_id: UUID | None
    content_sha256: str | None
    frontmatter: dict[str, Any]
    quality_flags: list[dict[str, Any]]


class SectionResponse(BaseModel):
    id: UUID
    parent_section_id: UUID | None
    heading_level: int
    heading_text: str
    heading_path: list[str]
    heading_occurrence: int
    char_start: int
    char_end: int
    ordinal: int


class SourceResponse(BaseModel):
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
    content_hash: str
    source_uri: str
    obsidian_uri: str | None
