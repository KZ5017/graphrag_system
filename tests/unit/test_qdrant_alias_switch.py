from __future__ import annotations

import json

import httpx

from graphrag_service.adapters.qdrant.client import QdrantVectorIndex


async def test_alias_switch_deletes_old_mapping_before_creating_new_one() -> None:
    actions: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/aliases":
            return httpx.Response(
                200,
                json={
                    "result": {
                        "aliases": [
                            {
                                "alias_name": "active",
                                "collection_name": "old_collection",
                            }
                        ]
                    }
                },
            )
        if request.method == "POST" and request.url.path == "/collections/aliases":
            actions.extend(json.loads(request.content)["actions"])
            return httpx.Response(200, json={"result": True})
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    index = QdrantVectorIndex(
        base_url="http://qdrant.test",
        api_key=None,
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    try:
        await index.switch_alias("active", "new_collection")
    finally:
        await index.close()

    assert actions == [
        {"delete_alias": {"alias_name": "active"}},
        {
            "create_alias": {
                "collection_name": "new_collection",
                "alias_name": "active",
            }
        },
    ]
