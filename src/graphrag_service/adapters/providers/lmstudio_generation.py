from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx

from graphrag_service.domain.generation import (
    GenerationCapabilities,
    GenerationModelInfo,
    GenerationProviderError,
    GenerationUsage,
    StructuredGeneration,
)


class LMStudioGenerationProvider:
    """Bounded OpenAI-compatible structured generation client."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_seconds: float,
        max_tokens: int,
        reasoning_effort: str = "none",
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
        self._max_tokens = max_tokens
        self._reasoning_effort = reasoning_effort

    async def __aenter__(self) -> LMStudioGenerationProvider:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def healthcheck(self) -> str:
        try:
            response = await self._client.get("/models")
            response.raise_for_status()
            body = response.json()
            loaded = {
                str(item.get("id"))
                for item in body.get("data", [])
                if isinstance(item, dict) and item.get("id")
            }
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise self._provider_error(exc, operation="healthcheck") from exc
        if self._model not in loaded:
            raise GenerationProviderError(
                "model_not_loaded",
                "Configured generation model is not loaded.",
                retryable=True,
            )
        return "available"

    async def model_info(self) -> GenerationModelInfo:
        return GenerationModelInfo(
            provider="lm_studio",
            model=self._model,
            capabilities=GenerationCapabilities(
                structured_output=True,
                reasoning_effort=True,
            ),
        )

    async def generate_structured(
        self,
        *,
        messages: list[dict[str, str]],
        schema_name: str,
        schema: dict[str, Any],
    ) -> StructuredGeneration:
        if not messages:
            raise ValueError("generation messages must not be empty")
        request = {
            "model": self._model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
            "reasoning_effort": self._reasoning_effort,
            "temperature": 0,
            "max_tokens": self._max_tokens,
            "stream": False,
        }
        try:
            response = await self._client.post("/chat/completions", json=request)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise self._provider_error(exc, operation="structured_generation") from exc
        try:
            choice = body["choices"][0]
            finish_reason = str(choice.get("finish_reason") or "unknown")
            if finish_reason != "stop":
                code = "output_truncated" if finish_reason == "length" else "incomplete_response"
                raise GenerationProviderError(
                    code,
                    "Generation provider did not complete the structured response.",
                    retryable=False,
                )
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content:
                raise TypeError("empty content")
            data = json.loads(content)
            if not isinstance(data, dict):
                raise TypeError("top-level response is not an object")
            usage = body.get("usage") or {}
            canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            return StructuredGeneration(
                data=data,
                model=str(body.get("model") or self._model),
                finish_reason=finish_reason,
                usage=GenerationUsage(
                    prompt_tokens=int(usage.get("prompt_tokens") or 0),
                    completion_tokens=int(usage.get("completion_tokens") or 0),
                    total_tokens=int(usage.get("total_tokens") or 0),
                ),
                response_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GenerationProviderError(
                "invalid_response",
                "Generation provider returned a response that was not valid structured JSON.",
                retryable=False,
            ) from exc

    @staticmethod
    def _provider_error(
        exc: Exception,
        *,
        operation: str,
    ) -> GenerationProviderError:
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            return GenerationProviderError(
                "authentication_failed" if status in {401, 403} else "http_error",
                f"Generation provider {operation} failed with HTTP {status}.",
                retryable=status == 429 or status >= 500,
                status_code=status,
            )
        if isinstance(exc, httpx.HTTPError):
            return GenerationProviderError(
                "provider_unavailable",
                f"Generation provider {operation} failed.",
                retryable=True,
            )
        return GenerationProviderError(
            "invalid_response",
            "Generation provider returned invalid JSON.",
            retryable=False,
        )
