from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class VectorPoint:
    id: UUID
    vector: tuple[float, ...]
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VectorHit:
    id: UUID
    score: float
    payload: dict[str, Any]


class VectorIndex(Protocol):
    async def ensure_collection(self, name: str, dimension: int) -> None: ...

    async def switch_alias(self, alias: str, collection: str) -> None: ...

    async def upsert(self, collection: str, points: list[VectorPoint]) -> None: ...

    async def delete(self, collection: str, point_ids: list[UUID]) -> None: ...

    async def search(
        self,
        collection: str,
        vector: tuple[float, ...],
        *,
        limit: int,
        filters: dict[str, str] | None = None,
    ) -> list[VectorHit]: ...
