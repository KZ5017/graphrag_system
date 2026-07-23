from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID


class PathCaseMode(StrEnum):
    SENSITIVE = "sensitive"
    INSENSITIVE = "insensitive"


class ScanType(StrEnum):
    INCREMENTAL = "incremental"
    FULL_REHASH = "full_rehash"
    MEASURE = "measure"


class ScanChangeKind(StrEnum):
    CREATED = "created"
    MODIFIED = "modified"
    RENAMED = "renamed"
    DELETED = "deleted"
    AMBIGUOUS_RENAME = "ambiguous_rename"
    READ_FAILED = "read_failed"


@dataclass(frozen=True, slots=True)
class VaultDefinition:
    id: UUID
    name: str
    root_path: str
    path_case_mode: PathCaseMode
    include_globs: tuple[str, ...]
    exclude_globs: tuple[str, ...]

    def path_key(self, relative_path: str) -> str:
        normalized = relative_path.replace("\\", "/")
        if self.path_case_mode is PathCaseMode.INSENSITIVE:
            return normalized.casefold()
        return normalized


@dataclass(frozen=True, slots=True)
class FileStat:
    relative_path: str
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class FileSnapshot:
    relative_path: str
    relative_path_key: str
    size_bytes: int
    mtime_ns: int
    content_sha256: str
    document_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ScanChange:
    kind: ScanChangeKind
    old_relative_path: str | None
    new_relative_path: str | None
    content_sha256: str | None
    document_id: UUID | None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScanResult:
    files: tuple[FileSnapshot, ...]
    changes: tuple[ScanChange, ...]
    discovered_count: int
    hashed_count: int
    new_count: int
    modified_count: int
    renamed_count: int
    deleted_count: int
    unchanged_count: int
    failed_count: int
    markdown_bytes: int
    warnings: tuple[dict[str, Any], ...]
