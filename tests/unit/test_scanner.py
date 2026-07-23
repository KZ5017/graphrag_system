from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from graphrag_service.application.scanner import VaultScanner
from graphrag_service.domain.vault import (
    FileSnapshot,
    FileStat,
    PathCaseMode,
    ScanChangeKind,
    VaultDefinition,
)


class FakeReader:
    root_path = "/vault"

    def __init__(self, files: dict[str, tuple[int, int, str]]) -> None:
        self.files = files
        self.hashed: list[str] = []

    def iter_markdown_files(self):
        for path, (size, mtime, _) in sorted(self.files.items()):
            yield FileStat(path, size, mtime)

    def sha256(self, relative_path: str) -> str:
        self.hashed.append(relative_path)
        return self.files[relative_path][2]

    def read_text(self, relative_path: str) -> str:
        raise NotImplementedError


def vault() -> VaultDefinition:
    return VaultDefinition(
        id=uuid4(),
        name="test",
        root_path="/vault",
        path_case_mode=PathCaseMode.SENSITIVE,
        include_globs=("**/*.md",),
        exclude_globs=(),
    )


def test_incremental_scan_reuses_hash_and_hashes_only_changes() -> None:
    document_id = uuid4()
    previous = (
        FileSnapshot("same.md", "same.md", 4, 10, "same-hash", document_id),
        FileSnapshot("changed.md", "changed.md", 4, 10, "old-hash", uuid4()),
    )
    reader = FakeReader(
        {
            "same.md": (4, 10, "same-hash"),
            "changed.md": (5, 11, "new-hash"),
        }
    )
    result = VaultScanner(reader).scan(vault(), previous)

    assert reader.hashed == ["changed.md"]
    assert result.hashed_count == 1
    assert result.unchanged_count == 1
    assert [change.kind for change in result.changes] == [ScanChangeKind.MODIFIED]


def test_unambiguous_hash_rename_keeps_document_id() -> None:
    document_id = uuid4()
    previous = (FileSnapshot("old.md", "old.md", 7, 10, "content-hash", document_id),)
    reader = FakeReader({"new.md": (7, 11, "content-hash")})
    result = VaultScanner(reader).scan(vault(), previous)

    rename = result.changes[0]
    assert rename.kind is ScanChangeKind.RENAMED
    assert rename.document_id == document_id
    assert rename.old_relative_path == "old.md"
    assert rename.new_relative_path == "new.md"


def test_ambiguous_hash_is_not_automatically_renamed() -> None:
    base = FileSnapshot("a.md", "a.md", 1, 1, "same", uuid4())
    previous = (base, replace(base, relative_path="b.md", relative_path_key="b.md"))
    reader = FakeReader({"c.md": (1, 2, "same"), "d.md": (1, 2, "same")})
    result = VaultScanner(reader).scan(vault(), previous)

    assert result.renamed_count == 0
    assert all(change.kind is ScanChangeKind.AMBIGUOUS_RENAME for change in result.changes)
    assert result.warnings[0]["code"] == "ambiguous_rename"
