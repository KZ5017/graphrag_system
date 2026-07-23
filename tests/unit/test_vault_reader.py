from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from graphrag_service.adapters.vault_fs.reader import (
    ReadOnlyVaultFilesystem,
    VaultSecurityError,
)


def build_reader(root: Path) -> ReadOnlyVaultFilesystem:
    return ReadOnlyVaultFilesystem(
        root_path=str(root),
        allowed_roots=(str(root),),
        include_globs=("**/*.md",),
        exclude_globs=(".obsidian/**", ".trash/**"),
        max_note_bytes=20 * 1024 * 1024,
    )


def snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    result = {}
    for path in root.rglob("*"):
        if path.is_file():
            stat = path.stat()
            result[path.relative_to(root).as_posix()] = (
                stat.st_size,
                stat.st_mtime_ns,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
    return result


def test_reader_lists_only_included_markdown_and_preserves_vault(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / "root.md").write_text("# Root\n", encoding="utf-8")
    (tmp_path / "nested" / "note.md").write_text("Text\n", encoding="utf-8")
    (tmp_path / "asset.png").write_bytes(b"not processed")
    (tmp_path / ".obsidian" / "workspace.md").write_text("hidden", encoding="utf-8")
    before = snapshot(tmp_path)

    reader = build_reader(tmp_path)
    files = list(reader.iter_markdown_files())
    assert [item.relative_path for item in files] == ["root.md", "nested/note.md"]
    assert reader.read_text("root.md") == "# Root\n"
    assert reader.sha256("nested/note.md") == hashlib.sha256(b"Text\n").hexdigest()
    assert not hasattr(reader, "write")
    assert snapshot(tmp_path) == before


def test_reader_rejects_root_escape_and_non_allowlisted_root(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text("safe", encoding="utf-8")
    reader = build_reader(tmp_path)

    with pytest.raises(VaultSecurityError):
        reader.read_text("../outside.md")
    with pytest.raises(VaultSecurityError):
        ReadOnlyVaultFilesystem(
            root_path=str(tmp_path),
            allowed_roots=(str(tmp_path / "other"),),
            include_globs=("**/*.md",),
            exclude_globs=(),
            max_note_bytes=1024,
        )


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
def test_reader_rejects_symlink_that_escapes_root(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    (vault / "escape.md").symlink_to(outside)

    reader = build_reader(vault)
    with pytest.raises(VaultSecurityError):
        list(reader.iter_markdown_files())
