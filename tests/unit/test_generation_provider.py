from __future__ import annotations

import json

import httpx
import pytest

from graphrag_service.adapters.providers.lmstudio_generation import (
    LMStudioGenerationProvider,
)
from graphrag_service.domain.generation import GenerationProviderError


@pytest.mark.asyncio
async def test_structured_generation_parses_json_and_usage() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "qwen/qwen3.5-9b"
        assert payload["reasoning_effort"] == "none"
        assert payload["response_format"]["type"] == "json_schema"
        return httpx.Response(
            200,
            json={
                "model": "qwen/qwen3.5-9b",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"status":"ok"}'},
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 14,
                },
            },
        )

    provider = LMStudioGenerationProvider(
        base_url="http://lm.test/v1",
        model="qwen/qwen3.5-9b",
        api_key="secret",
        timeout_seconds=5,
        max_tokens=128,
        transport=httpx.MockTransport(handler),
    )
    try:
        result = await provider.generate_structured(
            messages=[{"role": "user", "content": "test"}],
            schema_name="probe",
            schema={"type": "object"},
        )
    finally:
        await provider.close()
    assert result.data == {"status": "ok"}
    assert result.usage.total_tokens == 14
    assert len(result.response_sha256) == 64


@pytest.mark.asyncio
async def test_generation_provider_rejects_invalid_json_without_leaking_body() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "not-json secret-source-text"},
                    }
                ]
            },
        )

    provider = LMStudioGenerationProvider(
        base_url="http://lm.test/v1",
        model="qwen/qwen3.5-9b",
        api_key=None,
        timeout_seconds=5,
        max_tokens=128,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(GenerationProviderError) as raised:
            await provider.generate_structured(
                messages=[{"role": "user", "content": "test"}],
                schema_name="probe",
                schema={"type": "object"},
            )
    finally:
        await provider.close()
    assert raised.value.code == "invalid_response"
    assert "secret-source-text" not in str(raised.value)


@pytest.mark.asyncio
async def test_healthcheck_requires_exact_loaded_model() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "another-model"}]})

    provider = LMStudioGenerationProvider(
        base_url="http://lm.test/v1",
        model="qwen/qwen3.5-9b",
        api_key=None,
        timeout_seconds=5,
        max_tokens=128,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(GenerationProviderError) as raised:
            await provider.healthcheck()
    finally:
        await provider.close()
    assert raised.value.code == "model_not_loaded"
