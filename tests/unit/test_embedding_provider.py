from __future__ import annotations

import httpx
import pytest

from graphrag_service.adapters.providers.lmstudio_embeddings import (
    LMStudioEmbeddingProvider,
)
from graphrag_service.domain.embedding import EmbeddingProviderError


async def test_lmstudio_embedding_provider_probes_dimension_and_preserves_order() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-provider-token"
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "bge-test"}]})
        assert request.url.path.endswith("/embeddings")
        return httpx.Response(
            200,
            json={
                "model": "bge-test",
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0, 0.0]},
                    {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                ],
            },
        )

    provider = LMStudioEmbeddingProvider(
        base_url="http://lm.test/v1",
        model="bge-test",
        api_key="test-provider-token",
        timeout_seconds=1,
        max_batch_size=8,
        transport=httpx.MockTransport(handler),
    )
    try:
        assert await provider.healthcheck() == "available"
        batch = await provider.embed(["first", "second"])
        assert batch.vectors == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        assert batch.dimension == 3
        assert (await provider.model_info()).vector_dimension == 3
    finally:
        await provider.close()


async def test_lmstudio_provider_returns_structured_secret_free_auth_error() -> None:
    provider = LMStudioEmbeddingProvider(
        base_url="http://lm.test/v1",
        model="bge-test",
        api_key="super-secret-provider-token",
        timeout_seconds=1,
        max_batch_size=8,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(401, json={"error": {"message": "bad token"}})
        ),
    )
    try:
        with pytest.raises(EmbeddingProviderError) as caught:
            await provider.healthcheck()
    finally:
        await provider.close()
    assert caught.value.code == "authentication_failed"
    assert caught.value.retryable is False
    assert "super-secret-provider-token" not in str(caught.value)


async def test_lmstudio_provider_rejects_inconsistent_dimensions() -> None:
    provider = LMStudioEmbeddingProvider(
        base_url="http://lm.test/v1",
        model="bge-test",
        api_key=None,
        timeout_seconds=1,
        max_batch_size=8,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "data": [
                        {"index": 0, "embedding": [1.0, 0.0]},
                        {"index": 1, "embedding": [0.0, 1.0, 0.0]},
                    ]
                },
            )
        ),
    )
    try:
        with pytest.raises(EmbeddingProviderError) as caught:
            await provider.embed(["first", "second"])
    finally:
        await provider.close()
    assert caught.value.code == "dimension_mismatch"
