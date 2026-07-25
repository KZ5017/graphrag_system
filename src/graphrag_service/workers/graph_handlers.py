from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from graphrag_service.adapters.neo4j.client import Neo4jGraphAdapter
from graphrag_service.adapters.postgres.extraction_models import ExtractionRunModel
from graphrag_service.adapters.postgres.graph_store import GraphStore
from graphrag_service.adapters.postgres.resolution_store import ResolutionStore
from graphrag_service.application.graph_projection import GraphProjectionService
from graphrag_service.application.resolution import EntityResolutionService
from graphrag_service.config import Settings
from graphrag_service.domain.jobs import ClaimedJob
from graphrag_service.workers.runner import JobHandler


def build_graph_handlers(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[dict[str, JobHandler], Neo4jGraphAdapter]:
    graph = Neo4jGraphAdapter(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password.get_secret_value(),
        database=settings.neo4j_database,
    )
    resolver = EntityResolutionService(ResolutionStore(session_factory))
    projection = GraphProjectionService(
        store=GraphStore(session_factory),
        graph=graph,
        max_objects=settings.graph_projection_max_objects,
    )

    async def resolve_and_project_graph(job: ClaimedJob) -> dict[str, object]:
        vault_id = UUID(str(job.payload["vault_id"]))
        raw_run_ids = job.payload.get("extraction_run_ids")
        if not isinstance(raw_run_ids, list) or not raw_run_ids:
            raise ValueError("resolution job requires explicit extraction_run_ids")
        run_ids = tuple(UUID(str(value)) for value in raw_run_ids)
        async with session_factory() as session:
            rows = (
                await session.execute(
                    select(ExtractionRunModel.id, ExtractionRunModel.vault_id).where(
                        ExtractionRunModel.id.in_(run_ids)
                    )
                )
            ).all()
        found = {run_id: run_vault_id for run_id, run_vault_id in rows}
        if set(found) != set(run_ids):
            raise LookupError("one or more extraction runs were not found")
        if any(run_vault_id != vault_id for run_vault_id in found.values()):
            raise ValueError("all extraction runs must belong to the requested vault")

        outcomes = [await resolver.resolve_run(run_id) for run_id in run_ids]
        projected = await projection.rebuild_vault(vault_id)
        return {
            "vault_id": str(vault_id),
            "resolved_runs": [
                {
                    "run_id": str(outcome.run_id),
                    "created_entities": outcome.created_entities,
                    "merged_mentions": outcome.merged_mentions,
                    "deferred_candidates": outcome.deferred_candidates,
                    "review_candidates": outcome.review_candidates,
                    "relationship_assertions": outcome.relationship_assertions,
                    "claims": outcome.claims,
                }
                for outcome in outcomes
            ],
            "projection": {
                "generation": projected.generation,
                "snapshot_sha256": projected.snapshot_sha256,
                "object_count": projected.object_count,
                "projected": projected.projected,
            },
        }

    async def rebuild_graph_projection(job: ClaimedJob) -> dict[str, object]:
        vault_id = UUID(str(job.payload["vault_id"]))
        projected = await projection.rebuild_vault(vault_id)
        return {
            "vault_id": str(vault_id),
            "projection": {
                "generation": projected.generation,
                "snapshot_sha256": projected.snapshot_sha256,
                "object_count": projected.object_count,
                "projected": projected.projected,
            },
        }

    return {
        "resolve_and_project_graph": resolve_and_project_graph,
        "rebuild_graph_projection": rebuild_graph_projection,
    }, graph
