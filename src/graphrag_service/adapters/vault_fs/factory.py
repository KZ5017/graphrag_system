from __future__ import annotations

from graphrag_service.adapters.vault_fs.reader import ReadOnlyVaultFilesystem
from graphrag_service.config import Settings
from graphrag_service.domain.vault import VaultDefinition


def build_vault_reader(settings: Settings, vault: VaultDefinition) -> ReadOnlyVaultFilesystem:
    return ReadOnlyVaultFilesystem(
        root_path=vault.root_path,
        allowed_roots=tuple(settings.vault_allowed_roots),
        include_globs=vault.include_globs,
        exclude_globs=vault.exclude_globs,
        max_note_bytes=settings.max_markdown_note_bytes,
        hash_block_bytes=settings.scan_hash_block_bytes,
    )
