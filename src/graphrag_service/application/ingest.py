from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid5

from graphrag_service.adapters.markdown.parser import SourceMappedMarkdownParser
from graphrag_service.application.chunker import StructuralChunker
from graphrag_service.application.scanner import VaultScanner
from graphrag_service.domain.vault import ScanResult, ScanType, VaultDefinition
from graphrag_service.ports.ingest_store import (
    IngestStore,
    VaultRegistration,
)
from graphrag_service.ports.vault import VaultReader

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IngestOutcome:
    scan_id: UUID
    result: ScanResult
    parsed_documents: int
    failed_documents: int


VaultReaderFactory = Callable[[VaultDefinition], VaultReader]


class VaultIngestService:
    def __init__(
        self,
        *,
        store: IngestStore,
        reader_factory: VaultReaderFactory,
        parser: SourceMappedMarkdownParser | None = None,
        chunker: StructuralChunker | None = None,
    ) -> None:
        self._store = store
        self._reader_factory = reader_factory
        self._parser = parser or SourceMappedMarkdownParser()
        self._chunker = chunker or StructuralChunker()

    async def register_vault(self, registration: VaultRegistration) -> VaultDefinition:
        candidate = VaultDefinition(
            id=UUID(int=0),
            name=registration.name,
            root_path=registration.root_path,
            path_case_mode=registration.path_case_mode,
            include_globs=registration.include_globs,
            exclude_globs=registration.exclude_globs,
        )
        self._reader_factory(candidate)
        return await self._store.register_vault(registration)

    async def scan(self, vault_id: UUID, scan_type: ScanType) -> IngestOutcome:
        vault = await self._store.get_vault(vault_id)
        if vault is None:
            raise LookupError("vault not found")
        reader = self._reader_factory(vault)
        previous = await self._store.load_file_states(vault_id)
        scan_id = await self._store.begin_scan(vault_id, scan_type)
        try:
            result = VaultScanner(reader).scan(
                vault,
                previous,
                full_rehash=scan_type in {ScanType.FULL_REHASH, ScanType.MEASURE},
            )
            stored = await self._store.apply_scan(scan_id, vault, scan_type, result)
            parsed_count = 0
            failed_count = 0
            document_warnings: list[dict[str, object]] = []
            for source in stored.documents_to_parse:
                try:
                    markdown = reader.read_text(source.relative_path)
                    version_id = uuid5(source.document_id, source.content_sha256)
                    parsed = self._parser.parse(markdown, version_id)
                    chunks = self._chunker.chunk(
                        markdown,
                        version_id,
                        parsed.sections,
                        parsed.blocks,
                    )
                    await self._store.store_document(source, parsed, chunks)
                    parsed_count += 1
                except Exception as exc:
                    failed_count += 1
                    error_type = type(exc).__name__
                    document_warnings.append(
                        {
                            "code": "document_processing_failed",
                            "relative_path": source.relative_path,
                            "error_type": error_type,
                        }
                    )
                    await self._store.mark_document_failed(
                        source.document_id,
                        source.content_sha256,
                        error_type,
                    )
                    logger.exception(
                        "document_processing_failed",
                        extra={
                            "document_id": str(source.document_id),
                            "relative_path": source.relative_path,
                        },
                    )
            await self._store.finish_scan(
                scan_id,
                failed_documents=failed_count,
                warnings=tuple(document_warnings),
            )
            return IngestOutcome(
                scan_id=scan_id,
                result=result,
                parsed_documents=parsed_count,
                failed_documents=failed_count,
            )
        except Exception as exc:
            await self._store.fail_scan(scan_id, type(exc).__name__)
            raise
