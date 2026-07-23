from __future__ import annotations

from typing import Protocol

from graphrag_service.domain.embedding import EmbeddingBatch, EmbeddingModelInfo


class EmbeddingProvider(Protocol):
    async def healthcheck(self) -> str: ...

    async def model_info(self) -> EmbeddingModelInfo: ...

    async def probe_dimension(self) -> int: ...

    async def embed(self, texts: list[str]) -> EmbeddingBatch: ...
