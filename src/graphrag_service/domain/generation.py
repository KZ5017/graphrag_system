from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GenerationCapabilities:
    structured_output: bool
    reasoning_effort: bool


@dataclass(frozen=True, slots=True)
class GenerationModelInfo:
    provider: str
    model: str
    capabilities: GenerationCapabilities


@dataclass(frozen=True, slots=True)
class GenerationUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class StructuredGeneration:
    data: dict[str, Any]
    model: str
    finish_reason: str
    usage: GenerationUsage
    response_sha256: str


class GenerationProviderError(RuntimeError):
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
