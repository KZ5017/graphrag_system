from __future__ import annotations

from uuid import uuid4

import httpx

from graphrag_service.adapters.qdrant.client import QdrantVectorIndex
from graphrag_service.ports.vector_index import VectorPoint


async def test_qdrant_collection_upsert_alias_and_query_contract() -> None:
    requests: list[httpx.Request] = []
    point_id = uuid4()

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if request.method == "GET" and path == "/collections/test_collection":
            return httpx.Response(404, json={"status": "not found"})
        if request.method == "PUT" and path == "/collections/test_collection":
            return httpx.Response(200, json={"result": True})
        if request.method == "GET" and path == "/aliases":
            return httpx.Response(200, json={"result": {"aliases": []}})
        if request.method == "POST" and path == "/collections/aliases":
            return httpx.Response(200, json={"result": True})
        if request.method == "PUT" and path.endswith("/points"):
            return httpx.Response(200, json={"result": {"status": "completed"}})
        if request.method == "POST" and path.endswith("/points/query"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "points": [
                            {
                                "id": str(point_id),
                                "score": 0.9,
                                "payload": {"vault_id": "vault-a"},
                            }
                        ]
                    }
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {path}")

    index = QdrantVectorIndex(
        base_url="http://qdrant.test",
        api_key="qdrant-secret",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    try:
        await index.ensure_collection("test_collection", 3)
        await index.upsert(
            "test_collection",
            [
                VectorPoint(
                    id=point_id,
                    vector=(1.0, 0.0, 0.0),
                    payload={"vault_id": "vault-a"},
                )
            ],
        )
        await index.switch_alias("test_alias", "test_collection")
        hits = await index.search(
            "test_alias",
            (1.0, 0.0, 0.0),
            limit=5,
            filters={"vault_id": "vault-a"},
        )
    finally:
        await index.close()

    assert hits[0].id == point_id
    assert hits[0].score == 0.9
    assert all(request.headers["api-key"] == "qdrant-secret" for request in requests)
