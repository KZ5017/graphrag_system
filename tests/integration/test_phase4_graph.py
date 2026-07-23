from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from graphrag_service.adapters.neo4j.client import Neo4jGraphAdapter
from graphrag_service.adapters.postgres.extraction_store import ExtractionStore
from graphrag_service.adapters.postgres.graph_store import GraphStore
from graphrag_service.adapters.postgres.ingest_models import DocumentModel
from graphrag_service.adapters.postgres.ingest_store import PostgresIngestStore
from graphrag_service.adapters.postgres.resolution_models import EntityModel
from graphrag_service.adapters.postgres.resolution_store import ResolutionStore
from graphrag_service.adapters.postgres.session import (
    create_engine,
    create_session_factory,
)
from graphrag_service.adapters.postgres.unit_of_work import SqlAlchemyUnitOfWork
from graphrag_service.adapters.vault_fs.factory import build_vault_reader
from graphrag_service.application.extraction import KnowledgeExtractionService
from graphrag_service.application.graph_projection import GraphProjectionService
from graphrag_service.application.ingest import VaultIngestService
from graphrag_service.application.resolution import EntityResolutionService
from graphrag_service.domain.vault import PathCaseMode, ScanType
from graphrag_service.ports.ingest_store import VaultRegistration
from tests.integration.test_phase1_stack import integration_settings, run_alembic
from tests.integration.test_phase4_resolution import ResolutionGenerationProvider

pytestmark = pytest.mark.integration


async def test_neo4j_snapshot_is_rebuildable_and_supports_bounded_queries(
    tmp_path: Path,
) -> None:
    settings = integration_settings()
    run_alembic("downgrade", settings.postgres_dsn)
    run_alembic("upgrade", settings.postgres_dsn)
    settings = settings.model_copy(update={"vault_allowed_roots": [str(tmp_path)]})
    note = tmp_path / "graph.md"
    note.write_text(
        "# Graph\n\n"
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
            name="phase4-graph",
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
    async with sessions() as session:
        serial_entity = await session.scalar(
            select(EntityModel).where(EntityModel.canonical_name == "ONT-ABC-001")
        )
        portal_entity = await session.scalar(
            select(EntityModel)
            .where(EntityModel.canonical_name == "Customer Portal")
            .order_by(EntityModel.created_at)
        )
        assert serial_entity is not None
        assert portal_entity is not None

    graph = Neo4jGraphAdapter(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password.get_secret_value(),
        database=settings.neo4j_database,
    )
    service = GraphProjectionService(
        store=GraphStore(sessions),
        graph=graph,
        max_objects=1000,
    )
    first = await service.rebuild_vault(vault.id)
    assert first.projected is True
    assert first.object_count > 0
    second = await service.rebuild_vault(vault.id)
    assert second.projected is False
    assert second.snapshot_sha256 == first.snapshot_sha256

    neighbors = await graph.neighbors(
        entity_id=serial_entity.id,
        predicate="USES",
        entity_type="APPLICATION",
        max_results=10,
        include_unreviewed=True,
    )
    assert len(neighbors) == 1
    assert neighbors[0]["entity"]["canonical_name"] == "Customer Portal"
    paths = await graph.bounded_paths(
        from_entity_id=serial_entity.id,
        to_entity_id=portal_entity.id,
        max_hops=4,
        max_paths=10,
        predicate_allowlist=("USES",),
        include_unreviewed=True,
    )
    assert paths
    assert paths[0]["hops"] == 1

    note.write_text(
        "# Graph\n\nThe current source no longer supports the graph.\n", encoding="utf-8"
    )
    await ingest.scan(vault.id, ScanType.INCREMENTAL)
    third = await service.rebuild_vault(vault.id)
    assert third.projected is True
    assert third.snapshot_sha256 != first.snapshot_sha256
    assert (
        await graph.neighbors(
            entity_id=serial_entity.id,
            predicate=None,
            entity_type=None,
            max_results=10,
            include_unreviewed=True,
        )
        == []
    )
    await graph.close()
    await engine.dispose()
