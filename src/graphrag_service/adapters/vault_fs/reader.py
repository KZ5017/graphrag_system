from __future__ import annotations

import fnmatch
import hashlib
import os
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from graphrag_service.domain.vault import FileStat


class VaultAccessError(RuntimeError):
    pass


class VaultSecurityError(VaultAccessError):
    pass


class SourceChangedDuringRead(VaultAccessError):
    pass


class NoteTooLarge(VaultAccessError):
    pass


def _matches(path: str, pattern: str) -> bool:
    pure = PurePosixPath(path)
    if pure.match(pattern) or fnmatch.fnmatchcase(path, pattern):
        return True
    if pattern.startswith("**/"):
        shortened = pattern[3:]
        return pure.match(shortened) or fnmatch.fnmatchcase(path, shortened)
    return False


class ReadOnlyVaultFilesystem:
    """Filesystem adapter intentionally exposing no write operation."""

    def __init__(
        self,
        *,
        root_path: str,
        allowed_roots: tuple[str, ...],
        include_globs: tuple[str, ...],
        exclude_globs: tuple[str, ...],
        max_note_bytes: int,
        hash_block_bytes: int = 1024 * 1024,
    ) -> None:
        requested_root = Path(root_path)
        if not requested_root.is_absolute():
            raise VaultSecurityError("vault root must be absolute")
        try:
            resolved_root = requested_root.resolve(strict=True)
        except OSError as exc:
            raise VaultAccessError("vault root is not accessible") from exc
        if not resolved_root.is_dir():
            raise VaultAccessError("vault root is not a directory")

        allowed = set()
        for value in allowed_roots:
            try:
                allowed.add(Path(value).resolve(strict=True))
            except OSError:
                continue
        if resolved_root not in allowed:
            raise VaultSecurityError("vault root is not on the configured allowlist")

        self._root = resolved_root
        self._include_globs = include_globs
        self._exclude_globs = exclude_globs
        self._max_note_bytes = max_note_bytes
        self._hash_block_bytes = hash_block_bytes

    @property
    def root_path(self) -> str:
        return str(self._root)

    def iter_markdown_files(self) -> Iterator[FileStat]:
        for directory, directory_names, file_names in os.walk(self._root, followlinks=False):
            directory_path = Path(directory)
            directory_names[:] = sorted(
                name
                for name in directory_names
                if not self._is_excluded(
                    (directory_path / name).relative_to(self._root).as_posix() + "/"
                )
            )
            for file_name in sorted(file_names):
                candidate = directory_path / file_name
                relative_path = candidate.relative_to(self._root).as_posix()
                if not self._is_included(relative_path) or self._is_excluded(relative_path):
                    continue
                resolved = self._resolve_relative(relative_path)
                try:
                    stat = resolved.stat()
                except OSError as exc:
                    raise VaultAccessError(f"cannot stat source: {relative_path}") from exc
                if not resolved.is_file():
                    continue
                yield FileStat(
                    relative_path=relative_path,
                    size_bytes=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                )

    def sha256(self, relative_path: str) -> str:
        path = self._resolve_relative(relative_path)
        before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while block := source.read(self._hash_block_bytes):
                digest.update(block)
        after = path.stat()
        self._verify_stable(before, after)
        return digest.hexdigest()

    def read_text(self, relative_path: str) -> str:
        path = self._resolve_relative(relative_path)
        before = path.stat()
        if before.st_size > self._max_note_bytes:
            raise NoteTooLarge(f"Markdown note exceeds configured limit: {before.st_size} bytes")
        with path.open("rb") as source:
            raw = source.read(self._max_note_bytes + 1)
        after = path.stat()
        self._verify_stable(before, after)
        if len(raw) > self._max_note_bytes:
            raise NoteTooLarge("Markdown note grew beyond the configured limit")
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise VaultAccessError("Markdown note is not valid UTF-8") from exc

    def _resolve_relative(self, relative_path: str) -> Path:
        pure = PurePosixPath(relative_path)
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            raise VaultSecurityError("invalid vault-relative path")
        candidate = self._root.joinpath(*pure.parts)
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(self._root)
        except (OSError, ValueError) as exc:
            raise VaultSecurityError("source path escapes the configured vault root") from exc
        return resolved

    def _is_included(self, relative_path: str) -> bool:
        return any(_matches(relative_path, pattern) for pattern in self._include_globs)

    def _is_excluded(self, relative_path: str) -> bool:
        normalized = relative_path.rstrip("/")
        return any(
            _matches(normalized, pattern)
            or _matches(normalized + "/", pattern)
            or _matches(normalized + "/placeholder", pattern)
            for pattern in self._exclude_globs
        )

    @staticmethod
    def _verify_stable(before: os.stat_result, after: os.stat_result) -> None:
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            raise SourceChangedDuringRead("source changed while it was being read")
