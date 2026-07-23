from __future__ import annotations

from collections.abc import Iterable

import httpx

from graphrag_service.domain.embedding import (
    EmbeddingBatch,
    EmbeddingModelInfo,
    EmbeddingProviderError,
    ProviderCapabilities,
)


class LMStudioEmbeddingProvider:
    """OpenAI-compatible embedding client with runtime dimension discovery."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_seconds: float,
        max_batch_size: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout_seconds,
            transport=transport,
        )
        self._model = model
        self._max_batch_size = max_batch_size
        self._dimension: int | None = None

    async def __aenter__(self) -> LMStudioEmbeddingProvider:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def healthcheck(self) -> str:
        try:
            response = await self._client.get("/models")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise self._provider_error(exc, operation="healthcheck") from exc
        return "available"

    async def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            provider="lm_studio",
            model=self._model,
            vector_dimension=self._dimension,
            capabilities=ProviderCapabilities(
                supports_batch=True,
                max_batch_size=self._max_batch_size,
            ),
        )

    async def probe_dimension(self) -> int:
        result = await self.embed(["dimension probe"])
        return result.dimension

    async def embed(self, texts: list[str]) -> EmbeddingBatch:
        if not texts:
            raise ValueError("embedding input must not be empty")
        if len(texts) > self._max_batch_size:
            raise ValueError(f"embedding batch exceeds configured limit {self._max_batch_size}")
        try:
            response = await self._client.post(
                "/embeddings",
                json={"model": self._model, "input": texts, "encoding_format": "float"},
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            if isinstance(exc, httpx.HTTPError):
                error = self._provider_error(exc, operation="embed")
            else:
                error = EmbeddingProviderError(
                    "invalid_response",
                    "Embedding provider returned invalid JSON.",
                    retryable=False,
                )
            raise error from exc

        try:
            rows = sorted(body["data"], key=lambda item: int(item["index"]))
            indices = [int(item["index"]) for item in rows]
            vectors = tuple(tuple(float(value) for value in item["embedding"]) for item in rows)
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingProviderError(
                "invalid_response",
                "Embedding provider response did not match the expected schema.",
                retryable=False,
            ) from exc
        if indices != list(range(len(texts))) or len(vectors) != len(texts):
            raise EmbeddingProviderError(
                "invalid_response",
                "Embedding provider returned incomplete or duplicate indices.",
                retryable=False,
            )
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1 or not dimensions or 0 in dimensions:
            raise EmbeddingProviderError(
                "dimension_mismatch",
                "Embedding provider returned inconsistent vector dimensions.",
                retryable=False,
            )
        dimension = dimensions.pop()
        if self._dimension is not None and dimension != self._dimension:
            raise EmbeddingProviderError(
                "dimension_changed",
                "Embedding vector dimension changed during the provider session.",
                retryable=False,
            )
        self._dimension = dimension
        response_model = str(body.get("model") or self._model)
        return EmbeddingBatch(vectors=vectors, model=response_model, dimension=dimension)

    @staticmethod
    def _provider_error(
        exc: httpx.HTTPError,
        *,
        operation: str,
    ) -> EmbeddingProviderError:
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            retryable = status == 429 or status >= 500
            code = "authentication_failed" if status in {401, 403} else "http_error"
            return EmbeddingProviderError(
                code,
                f"Embedding provider {operation} failed with HTTP {status}.",
                retryable=retryable,
                status_code=status,
            )
        return EmbeddingProviderError(
            "provider_unavailable",
            f"Embedding provider {operation} failed.",
            retryable=True,
        )


def iter_batches(items: list[str], size: int) -> Iterable[list[str]]:
    if size < 1:
        raise ValueError("batch size must be positive")
    for offset in range(0, len(items), size):
        yield items[offset : offset + size]
