from __future__ import annotations

from uuid import UUID

from graphrag_service.adapters.neo4j.client import Neo4jGraphAdapter
from graphrag_service.adapters.postgres.graph_store import GraphStore
from graphrag_service.domain.graph import GraphProjectionOutcome


class GraphProjectionService:
    def __init__(
        self,
        *,
        store: GraphStore,
        graph: Neo4jGraphAdapter,
        max_objects: int,
    ) -> None:
        self._store = store
        self._graph = graph
        self._max_objects = max_objects

    async def rebuild_vault(self, vault_id: UUID) -> GraphProjectionOutcome:
        snapshot = await self._store.build_snapshot(vault_id)
        if snapshot.object_count > self._max_objects:
            raise ValueError(
                f"graph snapshot has {snapshot.object_count} objects; "
                f"configured limit is {self._max_objects}"
            )
        work = await self._store.prepare_projection(snapshot)
        if not work.should_project:
            return GraphProjectionOutcome(
                vault_id=vault_id,
                snapshot_sha256=snapshot.sha256,
                generation=work.generation,
                object_count=snapshot.object_count,
                projected=False,
            )
        await self._store.mark_projection_running(work)
        try:
            await self._graph.ensure_schema()
            await self._graph.replace_vault_snapshot(snapshot)
        except Exception as exc:
            await self._store.mark_projection_failed(
                work,
                error_code=type(exc).__name__.lower(),
                error_message=str(exc),
            )
            raise
        await self._store.mark_projection_succeeded(work)
        return GraphProjectionOutcome(
            vault_id=vault_id,
            snapshot_sha256=snapshot.sha256,
            generation=work.generation,
            object_count=snapshot.object_count,
            projected=True,
        )
