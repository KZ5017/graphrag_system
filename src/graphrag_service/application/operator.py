from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from graphrag_service.application.scanner import VaultScanner
from graphrag_service.domain.vault import ScanResult, VaultDefinition
from graphrag_service.ports.ingest_store import IngestStore
from graphrag_service.ports.vault import VaultReader


class OperatorPreviewService:
    def __init__(
        self,
        *,
        store: IngestStore,
        reader_factory: Callable[[VaultDefinition], VaultReader],
    ) -> None:
        self._store = store
        self._reader_factory = reader_factory

    async def preview(self, vault_id: UUID) -> ScanResult:
        vault = await self._store.get_vault(vault_id)
        if vault is None:
            raise LookupError("vault not found")
        previous = await self._store.load_file_states(vault_id)
        return VaultScanner(self._reader_factory(vault)).scan(vault, previous, full_rehash=False)
