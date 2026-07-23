from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class ParsedSection:
    id: UUID
    parent_id: UUID | None
    heading_level: int
    heading_text: str
    heading_path: list[str]
    heading_occurrence: int
    char_start: int
    char_end: int
    content_sha256: str
    ordinal: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    id: UUID
    section_id: UUID
    block_type: str
    ordinal: int
    char_start: int
    char_end: int
    content_sha256: str
    code_language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParsedChunk:
    id: UUID
    section_id: UUID
    ordinal: int
    char_start: int
    char_end: int
    text: str
    content_sha256: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParsedLink:
    id: UUID
    link_kind: str
    raw_target: str
    target_path: str | None
    target_heading: str | None
    target_block_id: str | None
    alias: str | None
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class ParsedTag:
    value: str
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    title: str | None
    frontmatter: dict[str, Any]
    sections: tuple[ParsedSection, ...]
    blocks: tuple[ParsedBlock, ...]
    links: tuple[ParsedLink, ...]
    tags: tuple[ParsedTag, ...]
    quality_flags: tuple[dict[str, Any], ...]
