from __future__ import annotations

from collections import defaultdict

from graphrag_service.domain.vault import (
    FileSnapshot,
    ScanChange,
    ScanChangeKind,
    ScanResult,
    VaultDefinition,
)
from graphrag_service.ports.vault import VaultReader


class VaultScanner:
    VERSION = "1.0.0"

    def __init__(self, reader: VaultReader) -> None:
        self._reader = reader

    def scan(
        self,
        vault: VaultDefinition,
        previous: tuple[FileSnapshot, ...],
        *,
        full_rehash: bool = False,
    ) -> ScanResult:
        previous_by_key = {item.relative_path_key: item for item in previous}
        current: list[FileSnapshot] = []
        changes: list[ScanChange] = []
        warnings: list[dict[str, object]] = []
        hashed_count = 0
        unchanged_count = 0
        failed_count = 0

        for stat in self._reader.iter_markdown_files():
            path_key = vault.path_key(stat.relative_path)
            old = previous_by_key.get(path_key)
            should_hash = (
                full_rehash
                or old is None
                or old.size_bytes != stat.size_bytes
                or old.mtime_ns != stat.mtime_ns
            )
            try:
                content_hash = (
                    self._reader.sha256(stat.relative_path) if should_hash else old.content_sha256
                )
            except Exception as exc:
                failed_count += 1
                warnings.append(
                    {
                        "code": "source_read_failed",
                        "relative_path": stat.relative_path,
                        "error_type": type(exc).__name__,
                    }
                )
                changes.append(
                    ScanChange(
                        kind=ScanChangeKind.READ_FAILED,
                        old_relative_path=old.relative_path if old else None,
                        new_relative_path=stat.relative_path,
                        content_sha256=None,
                        document_id=old.document_id if old else None,
                        detail={"error_type": type(exc).__name__},
                    )
                )
                continue
            if should_hash:
                hashed_count += 1
            else:
                unchanged_count += 1
            current.append(
                FileSnapshot(
                    relative_path=stat.relative_path,
                    relative_path_key=path_key,
                    size_bytes=stat.size_bytes,
                    mtime_ns=stat.mtime_ns,
                    content_sha256=content_hash,
                    document_id=old.document_id if old else None,
                )
            )

        current_by_key = {item.relative_path_key: item for item in current}
        deleted = [item for key, item in previous_by_key.items() if key not in current_by_key]
        created = [item for key, item in current_by_key.items() if key not in previous_by_key]

        deleted_by_hash: dict[str, list[FileSnapshot]] = defaultdict(list)
        created_by_hash: dict[str, list[FileSnapshot]] = defaultdict(list)
        for item in deleted:
            deleted_by_hash[item.content_sha256].append(item)
        for item in created:
            created_by_hash[item.content_sha256].append(item)

        renamed_old_keys: set[str] = set()
        renamed_new_keys: set[str] = set()
        ambiguous_hashes: set[str] = set()
        for content_hash in deleted_by_hash.keys() & created_by_hash.keys():
            old_candidates = deleted_by_hash[content_hash]
            new_candidates = created_by_hash[content_hash]
            if len(old_candidates) == len(new_candidates) == 1:
                old_item = old_candidates[0]
                new_item = new_candidates[0]
                renamed_old_keys.add(old_item.relative_path_key)
                renamed_new_keys.add(new_item.relative_path_key)
                changes.append(
                    ScanChange(
                        kind=ScanChangeKind.RENAMED,
                        old_relative_path=old_item.relative_path,
                        new_relative_path=new_item.relative_path,
                        content_sha256=content_hash,
                        document_id=old_item.document_id,
                    )
                )
            else:
                ambiguous_hashes.add(content_hash)
                warnings.append(
                    {
                        "code": "ambiguous_rename",
                        "content_sha256": content_hash,
                        "deleted_count": len(old_candidates),
                        "created_count": len(new_candidates),
                    }
                )

        for item in deleted:
            if item.relative_path_key in renamed_old_keys:
                continue
            kind = (
                ScanChangeKind.AMBIGUOUS_RENAME
                if item.content_sha256 in ambiguous_hashes
                else ScanChangeKind.DELETED
            )
            changes.append(
                ScanChange(
                    kind=kind,
                    old_relative_path=item.relative_path,
                    new_relative_path=None,
                    content_sha256=item.content_sha256,
                    document_id=item.document_id,
                )
            )
        for item in created:
            if item.relative_path_key in renamed_new_keys:
                continue
            kind = (
                ScanChangeKind.AMBIGUOUS_RENAME
                if item.content_sha256 in ambiguous_hashes
                else ScanChangeKind.CREATED
            )
            changes.append(
                ScanChange(
                    kind=kind,
                    old_relative_path=None,
                    new_relative_path=item.relative_path,
                    content_sha256=item.content_sha256,
                    document_id=None,
                )
            )

        for key in previous_by_key.keys() & current_by_key.keys():
            old = previous_by_key[key]
            new = current_by_key[key]
            if old.content_sha256 != new.content_sha256:
                changes.append(
                    ScanChange(
                        kind=ScanChangeKind.MODIFIED,
                        old_relative_path=old.relative_path,
                        new_relative_path=new.relative_path,
                        content_sha256=new.content_sha256,
                        document_id=old.document_id,
                    )
                )

        counts = {kind: 0 for kind in ScanChangeKind}
        for change in changes:
            counts[change.kind] += 1
        return ScanResult(
            files=tuple(current),
            changes=tuple(changes),
            discovered_count=len(current),
            hashed_count=hashed_count,
            new_count=counts[ScanChangeKind.CREATED] + counts[ScanChangeKind.AMBIGUOUS_RENAME],
            modified_count=counts[ScanChangeKind.MODIFIED],
            renamed_count=counts[ScanChangeKind.RENAMED],
            deleted_count=counts[ScanChangeKind.DELETED] + counts[ScanChangeKind.AMBIGUOUS_RENAME],
            unchanged_count=unchanged_count,
            failed_count=failed_count,
            markdown_bytes=sum(item.size_bytes for item in current),
            warnings=tuple(warnings),
        )
