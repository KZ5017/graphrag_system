from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from graphrag_service.domain.markdown import ParsedChunk, ParsedDocument
from graphrag_service.domain.vault import (
    FileSnapshot,
    PathCaseMode,
    ScanResult,
    ScanType,
    VaultDefinition,
)


@dataclass(frozen=True, slots=True)
class VaultRegistration:
    name: str
    root_path: str
    path_case_mode: PathCaseMode
    include_globs: tuple[str, ...]
    exclude_globs: tuple[str, ...]
    obsidian_uri_template: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentToParse:
    document_id: UUID
    relative_path: str
    content_sha256: str
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class StoredScan:
    scan_id: UUID
    documents_to_parse: tuple[DocumentToParse, ...]


class IngestStore(Protocol):
    async def register_vault(self, registration: VaultRegistration) -> VaultDefinition: ...

    async def list_vaults(self) -> tuple[VaultDefinition, ...]: ...

    async def get_vault(self, vault_id: UUID) -> VaultDefinition | None: ...

    async def load_file_states(self, vault_id: UUID) -> tuple[FileSnapshot, ...]: ...

    async def begin_scan(self, vault_id: UUID, scan_type: ScanType) -> UUID: ...

    async def apply_scan(
        self,
        scan_id: UUID,
        vault: VaultDefinition,
        scan_type: ScanType,
        result: ScanResult,
    ) -> StoredScan: ...

    async def store_document(
        self,
        source: DocumentToParse,
        parsed: ParsedDocument,
        chunks: tuple[ParsedChunk, ...],
    ) -> UUID: ...

    async def mark_document_failed(
        self, document_id: UUID, content_sha256: str, error_type: str
    ) -> None: ...

    async def finish_scan(
        self,
        scan_id: UUID,
        *,
        failed_documents: int = 0,
        warnings: tuple[dict[str, object], ...] = (),
    ) -> None: ...

    async def fail_scan(self, scan_id: UUID, error_type: str) -> None: ...
