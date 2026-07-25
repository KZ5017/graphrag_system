from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from graphrag_service.adapters.neo4j.client import Neo4jGraphAdapter
from graphrag_service.adapters.postgres.extraction_store import ExtractionStore
from graphrag_service.adapters.postgres.graph_store import GraphStore
from graphrag_service.adapters.postgres.graphrag_retrieval_store import (
    GraphRetrievalStore,
)
from graphrag_service.adapters.postgres.ingest_models import DocumentModel
from graphrag_service.adapters.postgres.ingest_store import PostgresIngestStore
from graphrag_service.adapters.postgres.projection_store import ProjectionStore
from graphrag_service.adapters.postgres.resolution_store import ResolutionStore
from graphrag_service.adapters.postgres.session import (
    create_engine,
    create_session_factory,
)
from graphrag_service.adapters.postgres.unit_of_work import SqlAlchemyUnitOfWork
from graphrag_service.adapters.vault_fs.factory import build_vault_reader
from graphrag_service.application.extraction import KnowledgeExtractionService
from graphrag_service.application.graph_projection import GraphProjectionService
from graphrag_service.application.graph_retrieval import GraphRetrievalEnricher
from graphrag_service.application.ingest import VaultIngestService
from graphrag_service.application.phase5_retrieval import Phase5RetrievalService
from graphrag_service.application.query_planner import DeterministicQueryPlanner
from graphrag_service.application.resolution import EntityResolutionService
from graphrag_service.domain.vault import PathCaseMode, ScanType
from graphrag_service.ports.ingest_store import VaultRegistration
from tests.integration.test_phase1_stack import integration_settings, run_alembic
from tests.integration.test_phase4_resolution import ResolutionGenerationProvider

pytestmark = pytest.mark.integration


class UnusedVectorIndex:
    async def search(self, *_: object, **__: object) -> list[object]:
        raise AssertionError("semantic search must not run without an active profile")


async def test_phase5_graph_expansion_hydrates_only_current_sources(tmp_path: Path) -> None:
    settings = integration_settings()
    run_alembic("downgrade", settings.postgres_dsn)
    run_alembic("upgrade", settings.postgres_dsn)
    settings = settings.model_copy(update={"vault_allowed_roots": [str(tmp_path)]})
    note = tmp_path / "phase5.md"
    note.write_text(
        "# GraphRAG\n\n"
        "Device serial number: ONT-ABC-001. "
        "ONT-ABC-001 uses Customer Portal. "
        "The device is registered.\n\n"
        "Backup serial number: ONT-ABC-001. "
        "Customer Portal remains available.\n",
        encoding="utf-8",
    )

    engine = create_engine(settings)
    sessions = create_session_factory(engine)
    ingest = VaultIngestService(
        store=PostgresIngestStore(sessions),
        reader_factory=lambda vault: build_vault_reader(settings, vault),
    )
    vault = await ingest.register_vault(
        VaultRegistration(
            name="phase5-graphrag",
            root_path=str(tmp_path),
            path_case_mode=PathCaseMode.SENSITIVE,
            include_globs=("**/*.md",),
            exclude_globs=(),
        )
    )
    await ingest.scan(vault.id, ScanType.INCREMENTAL)
    async with sessions() as session:
        document = await session.scalar(select(DocumentModel))
        assert document is not None
    async with SqlAlchemyUnitOfWork(sessions) as uow:
        job_id = await uow.jobs.enqueue(
            "extract_knowledge_pilot",
            {"vault_id": str(vault.id), "document_ids": [str(document.id)]},
        )
    extraction = await KnowledgeExtractionService(
        store=ExtractionStore(sessions),
        provider=ResolutionGenerationProvider(),
        max_chunks_per_job=2,
    ).run_pilot(
        job_id=job_id,
        vault_id=vault.id,
        document_ids=(document.id,),
        max_chunks=1,
    )
    await EntityResolutionService(ResolutionStore(sessions)).resolve_run(extraction.run_id)

    graph = Neo4jGraphAdapter(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password.get_secret_value(),
        database=settings.neo4j_database,
    )
    projection = GraphProjectionService(
        store=GraphStore(sessions),
        graph=graph,
        max_objects=1000,
    )
    await projection.rebuild_vault(vault.id)

    store = GraphRetrievalStore(sessions)
    retrieval = Phase5RetrievalService(
        store=store,
        projection_store=ProjectionStore(sessions),
        vector_index=UnusedVectorIndex(),  # type: ignore[arg-type]
        embedding_provider=None,
        query_planner=DeterministicQueryPlanner(),
        graph_enricher=GraphRetrievalEnricher(
            store=store,
            graph=graph,
            entity_limit=10,
            max_hops=2,
            max_paths=20,
        ),
        candidate_limit=10,
        claim_limit=20,
        max_limit=20,
        rrf_k=60,
        chunks_alias="unused",
    )
    result = await retrieval.retrieve(
        "Mivel kommunikál az ONT-ABC-001 a Customer Portal szolgáltatással?",
        strategy="hybrid",
        limit=5,
        vault_id=vault.id,
    )

    assert result.query_type == "graph"
    assert result.retrieval_paths
    assert result.relationships[0].predicate == "USES"
    assert result.claims[0].text == "The device is registered."
    active_source_ids = {item.chunk_id for item in [*result.chunks, *result.context_chunks]}
    assert all(
        relationship.source_chunk_id in active_source_ids for relationship in result.relationships
    )
    assert all(claim.source_chunk_id in active_source_ids for claim in result.claims)

    old_assertion_ids = [item.assertion_id for item in result.relationships]
    old_claim_ids = [item.claim_id for item in result.claims]
    note.write_text(
        "# GraphRAG\n\nThe source no longer supports the assertion.\n", encoding="utf-8"
    )
    await ingest.scan(vault.id, ScanType.INCREMENTAL)
    await projection.rebuild_vault(vault.id)
    assert await store.hydrate_assertions(old_assertion_ids) == {}
    assert await store.hydrate_claims(old_claim_ids) == {}

    await graph.close()
    await engine.dispose()
