from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from graphrag_service.adapters.postgres.graph_store import Neo4jProjectionWork
from graphrag_service.api.app import create_app
from graphrag_service.application.graph_projection import GraphProjectionService
from graphrag_service.application.readiness import ReadinessService
from graphrag_service.domain.graph import (
    EntityDetail,
    EntityEvidence,
    GraphSnapshot,
)


class FakeGraph:
    def __init__(self) -> None:
        self.replaced = 0

    async def close(self) -> None:
        return None

    async def ensure_schema(self) -> None:
        return None

    async def replace_vault_snapshot(self, _: GraphSnapshot) -> None:
        self.replaced += 1

    async def neighbors(self, **_: object) -> list[dict[str, object]]:
        return [
            {
                "entity": {"id": str(uuid4()), "canonical_name": f"neighbor-{index}"},
                "assertion": {"id": str(uuid4()), "predicate": "USES"},
                "direction": "outgoing",
            }
            for index in range(3)
        ]

    async def bounded_paths(self, **_: object) -> list[dict[str, object]]:
        return [{"entities": [], "assertions": [], "hops": 1}]


class FakeProjectionStore:
    def __init__(self, snapshot: GraphSnapshot) -> None:
        self.snapshot = snapshot
        self.succeeded = 0

    async def build_snapshot(self, _: object) -> GraphSnapshot:
        return self.snapshot

    async def prepare_projection(self, _: object) -> Neo4jProjectionWork:
        return Neo4jProjectionWork(uuid4(), uuid4(), 1, True)

    async def mark_projection_running(self, _: object) -> None:
        return None

    async def mark_projection_succeeded(self, _: object) -> None:
        self.succeeded += 1

    async def mark_projection_failed(self, *_: object, **__: object) -> None:
        raise AssertionError("projection should not fail")


class FakeEntityStore:
    async def entity_detail(self, entity_id: object) -> EntityDetail:
        return EntityDetail(
            id=entity_id,  # type: ignore[arg-type]
            vault_id=uuid4(),
            canonical_name="ONT-ABC-001",
            entity_type="DEVICE_INSTANCE",
            entity_subtype="ONT",
            scope="instance",
            status="active",
            aliases=("ONT-ABC-001",),
            identifiers=(
                {
                    "kind": "serial_number",
                    "value": "ONT-ABC-001",
                    "normalized_value": "ONT-ABC-001",
                },
            ),
            evidence=(
                EntityEvidence(
                    evidence_id=uuid4(),
                    chunk_id=uuid4(),
                    document_id=uuid4(),
                    relative_path="ont.md",
                    quote="serial number: ONT-ABC-001",
                    char_start=10,
                    char_end=36,
                ),
            ),
        )


def test_graph_snapshot_hash_is_order_sensitive_but_repeatable() -> None:
    vault_id = uuid4()
    snapshot = GraphSnapshot(
        vault_id=vault_id,
        nodes={"Vault": ({"id": str(vault_id)},)},
        relationships={},
    )
    assert snapshot.sha256 == snapshot.sha256
    assert snapshot.object_count == 1


@pytest.mark.asyncio
async def test_graph_projection_is_outbox_backed_and_idempotent() -> None:
    vault_id = uuid4()
    snapshot = GraphSnapshot(
        vault_id=vault_id,
        nodes={"Vault": ({"id": str(vault_id)},)},
        relationships={},
    )
    store = FakeProjectionStore(snapshot)
    graph = FakeGraph()
    outcome = await GraphProjectionService(
        store=store,  # type: ignore[arg-type]
        graph=graph,  # type: ignore[arg-type]
        max_objects=100,
    ).rebuild_vault(vault_id)
    assert outcome.projected is True
    assert graph.replaced == 1
    assert store.succeeded == 1


def test_entity_and_bounded_graph_api(settings_factory) -> None:
    settings = settings_factory()
    app = create_app(
        settings,
        readiness_service=ReadinessService([], timeout_seconds=0.1),
    )
    headers = {"Authorization": f"Bearer {settings.service_token.get_secret_value()}"}
    entity_id = uuid4()
    with TestClient(app) as client:
        app.state.graph_store = FakeEntityStore()
        app.state.graph_adapter = FakeGraph()
        detail = client.get(f"/v1/entities/{entity_id}", headers=headers)
        neighbors = client.get(
            f"/v1/entities/{entity_id}/neighbors?max_results=2",
            headers=headers,
        )
        invalid_path = client.post(
            "/v1/graph/path",
            headers=headers,
            json={
                "from_entity_id": str(entity_id),
                "to_entity_id": str(uuid4()),
                "max_hops": 5,
                "max_paths": 10,
            },
        )
        valid_path = client.post(
            "/v1/graph/path",
            headers=headers,
            json={
                "from_entity_id": str(entity_id),
                "to_entity_id": str(uuid4()),
                "max_hops": 4,
                "max_paths": 10,
                "predicate_allowlist": ["USES"],
            },
        )
    assert detail.status_code == 200
    assert detail.json()["evidence"][0]["relative_path"] == "ont.md"
    assert neighbors.status_code == 200
    assert len(neighbors.json()["neighbors"]) == 2
    assert neighbors.json()["truncated"] is True
    assert invalid_path.status_code == 422
    assert valid_path.status_code == 200
    assert valid_path.json()["paths"][0]["hops"] == 1
