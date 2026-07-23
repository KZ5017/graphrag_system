from __future__ import annotations

from typing import Any, Protocol

from graphrag_service.domain.generation import GenerationModelInfo, StructuredGeneration


class GenerationProvider(Protocol):
    async def healthcheck(self) -> str: ...

    async def model_info(self) -> GenerationModelInfo: ...

    async def generate_structured(
        self,
        *,
        messages: list[dict[str, str]],
        schema_name: str,
        schema: dict[str, Any],
    ) -> StructuredGeneration: ...

    async def close(self) -> None: ...
