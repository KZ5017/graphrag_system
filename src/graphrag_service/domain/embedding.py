from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    supports_batch: bool
    max_batch_size: int | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingModelInfo:
    provider: str
    model: str
    vector_dimension: int | None
    capabilities: ProviderCapabilities


class EmbeddingProviderError(RuntimeError):
    """Structured, secret-free embedding provider failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    vectors: tuple[tuple[float, ...], ...]
    model: str
    dimension: int
