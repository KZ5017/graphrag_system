from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from graphrag_service.ports.vector_index import (
    VectorCollectionState,
    VectorHit,
    VectorPoint,
)


class QdrantError(RuntimeError):
    pass


class QdrantVectorIndex:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"api-key": api_key} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout_seconds,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def ensure_collection(self, name: str, dimension: int) -> None:
        response = await self._client.get(f"/collections/{name}")
        if response.status_code == 404:
            created = await self._client.put(
                f"/collections/{name}",
                json={"vectors": {"size": dimension, "distance": "Cosine"}},
            )
            self._raise(created, "create collection")
            return
        self._raise(response, "inspect collection")
        try:
            vectors = response.json()["result"]["config"]["params"]["vectors"]
            existing_dimension = int(vectors["size"])
            distance = str(vectors["distance"]).lower()
        except (KeyError, TypeError, ValueError) as exc:
            raise QdrantError("Qdrant returned an invalid collection description.") from exc
        if existing_dimension != dimension or distance != "cosine":
            raise QdrantError(f"Collection {name!r} has incompatible vector configuration.")

    async def switch_alias(self, alias: str, collection: str) -> None:
        aliases = await self._client.get("/aliases")
        self._raise(aliases, "inspect aliases")
        current = [
            item
            for item in aliases.json().get("result", {}).get("aliases", [])
            if item.get("alias_name") == alias
        ]
        if any(item.get("collection_name") == collection for item in current):
            return
        actions: list[dict[str, Any]] = [{"delete_alias": {"alias_name": alias}} for _ in current]
        actions.append({"create_alias": {"collection_name": collection, "alias_name": alias}})
        response = await self._client.post(
            "/collections/aliases",
            json={"actions": actions},
        )
        self._raise(response, "switch alias")

    async def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        if not points:
            return
        response = await self._client.put(
            f"/collections/{collection}/points",
            params={"wait": "true"},
            json={
                "points": [
                    {
                        "id": str(point.id),
                        "vector": list(point.vector),
                        "payload": point.payload,
                    }
                    for point in points
                ]
            },
        )
        self._raise(response, "upsert points")

    async def delete(self, collection: str, point_ids: list[UUID]) -> None:
        if not point_ids:
            return
        response = await self._client.post(
            f"/collections/{collection}/points/delete",
            params={"wait": "true"},
            json={"points": [str(point_id) for point_id in point_ids]},
        )
        self._raise(response, "delete points")

    async def delete_collection(self, name: str) -> None:
        response = await self._client.delete(f"/collections/{name}")
        if response.status_code == 404:
            return
        self._raise(response, "delete collection")

    async def collection_state(
        self, *, alias: str, expected_collection: str
    ) -> VectorCollectionState:
        aliases = await self._client.get("/aliases")
        self._raise(aliases, "inspect aliases")
        collection = next(
            (
                str(item.get("collection_name"))
                for item in aliases.json().get("result", {}).get("aliases", [])
                if item.get("alias_name") == alias
            ),
            None,
        )
        target = collection or expected_collection
        description = await self._client.get(f"/collections/{target}")
        if description.status_code == 404:
            return VectorCollectionState(
                alias=alias,
                collection=collection,
                expected_collection=expected_collection,
                exists=False,
                point_count=None,
            )
        self._raise(description, "inspect collection")
        counted = await self._client.post(
            f"/collections/{target}/points/count",
            json={},
        )
        self._raise(counted, "count collection points")
        try:
            point_count = int(counted.json()["result"]["count"])
        except (KeyError, TypeError, ValueError) as exc:
            raise QdrantError("Qdrant returned an invalid point count.") from exc
        return VectorCollectionState(
            alias=alias,
            collection=collection,
            expected_collection=expected_collection,
            exists=True,
            point_count=point_count,
        )

    async def search(
        self,
        collection: str,
        vector: tuple[float, ...],
        *,
        limit: int,
        filters: dict[str, str] | None = None,
    ) -> list[VectorHit]:
        query_filter: dict[str, Any] | None = None
        if filters:
            query_filter = {
                "must": [
                    {"key": key, "match": {"value": value}}
                    for key, value in sorted(filters.items())
                ]
            }
        response = await self._client.post(
            f"/collections/{collection}/points/query",
            json={
                "query": list(vector),
                "limit": limit,
                "with_payload": True,
                "filter": query_filter,
            },
        )
        self._raise(response, "query points")
        try:
            points = response.json()["result"]["points"]
            return [
                VectorHit(
                    id=UUID(str(item["id"])),
                    score=float(item["score"]),
                    payload=dict(item.get("payload") or {}),
                )
                for item in points
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise QdrantError("Qdrant returned an invalid query response.") from exc

    @staticmethod
    def _raise(response: httpx.Response, operation: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise QdrantError(
                f"Qdrant {operation} failed with HTTP {response.status_code}."
            ) from exc
