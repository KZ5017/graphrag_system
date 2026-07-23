from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from graphrag_service.domain.vault import FileStat


class VaultReader(Protocol):
    @property
    def root_path(self) -> str: ...

    def iter_markdown_files(self) -> Iterator[FileStat]: ...

    def sha256(self, relative_path: str) -> str: ...

    def read_text(self, relative_path: str) -> str: ...
