from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from graphrag_service.adapters.postgres.ingest_store import PostgresIngestStore
from graphrag_service.adapters.postgres.projection_models import (
    ModelProfileModel,
    ProjectionOutboxModel,
    ProjectionStatusModel,
)
from graphrag_service.adapters.postgres.projection_store import ProjectionStore
from graphrag_service.adapters.postgres.retrieval_store import RetrievalStore
from graphrag_service.adapters.postgres.session import (
    create_engine,
    create_session_factory,
)
from graphrag_service.adapters.qdrant.client import QdrantVectorIndex
from graphrag_service.adapters.vault_fs.factory import build_vault_reader
from graphrag_service.application.ingest import VaultIngestService
from graphrag_service.application.projection import ChunkProjectionService
from graphrag_service.application.retrieval import RetrievalService
from graphrag_service.domain.embedding import (
    EmbeddingBatch,
    EmbeddingModelInfo,
    ProviderCapabilities,
)
from graphrag_service.domain.vault import PathCaseMode, ScanType
from graphrag_service.ports.ingest_store import VaultRegistration
from tests.integration.test_phase1_stack import integration_settings, run_alembic

pytestmark = pytest.mark.integration


class DeterministicEmbeddingProvider:
    async def healthcheck(self) -> str:
        return "available"

    async def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            provider="deterministic_test",
            model="phase3-test-embedding",
            vector_dimension=4,
            capabilities=ProviderCapabilities(supports_batch=True, max_batch_size=16),
        )

    async def probe_dimension(self) -> int:
        return 4

    async def embed(self, texts: list[str]) -> EmbeddingBatch:
        vectors = []
        for text in texts:
            folded = text.casefold()
            vector = (
                float(folded.count("cmts") + 1),
                float(folded.count("modem") + 1),
                float(folded.count("provision") + 1),
                1.0,
            )
            vectors.append(vector)
        return EmbeddingBatch(
            vectors=tuple(vectors),
            model="phase3-test-embedding",
            dimension=4,
        )


async def test_phase3_outbox_qdrant_hybrid_and_delete_reconciliation(
    tmp_path: Path,
) -> None:
    settings = integration_settings()
    run_alembic("downgrade", settings.postgres_dsn)
    run_alembic("upgrade", settings.postgres_dsn)
    settings = settings.model_copy(
        update={
            "vault_allowed_roots": [str(tmp_path)],
            "qdrant_url": settings.qdrant_url,
        }
    )
    note = tmp_path / "network.md"
    note.write_text(
        "# Access network\n\nThe CMTS provisions cable modems for subscribers.\n",
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
            name="phase3-test",
            root_path=str(tmp_path),
            path_case_mode=PathCaseMode.SENSITIVE,
            include_globs=("**/*.md",),
            exclude_globs=(),
        )
    )
    await ingest.scan(vault.id, ScanType.INCREMENTAL)

    provider = DeterministicEmbeddingProvider()
    vectors = QdrantVectorIndex(
        base_url=settings.qdrant_url,
        api_key=None,
        timeout_seconds=10,
    )
    projection_store = ProjectionStore(sessions)
    projection = ChunkProjectionService(
        store=projection_store,
        provider=provider,
        vectors=vectors,
        alias="gks_chunks_active",
        worker_id="phase3-integration",
        batch_size=8,
        lease_seconds=60,
    )
    outcome = None
    try:
        await vectors.ensure_collection("phase3_old_collection", 4)
        await vectors.switch_alias("gks_chunks_active", "phase3_old_collection")
        outcome = await projection.run(vault_id=vault.id)
        assert outcome.vector_dimension == 4
        assert outcome.projected_upserts > 0
        async with httpx.AsyncClient(base_url=settings.qdrant_url) as client:
            aliases = (await client.get("/aliases")).json()["result"]["aliases"]
        assert {item["alias_name"]: item["collection_name"] for item in aliases}[
            "gks_chunks_active"
        ] == outcome.collection

        retrieval = RetrievalService(
            store=RetrievalStore(sessions),
            projection_store=projection_store,
            vector_index=vectors,
            embedding_provider=provider,
            candidate_limit=10,
            max_limit=20,
            rrf_k=60,
            chunks_alias="gks_chunks_active",
        )
        result = await retrieval.retrieve(
            "CMTS modem provisioning",
            strategy="hybrid",
            limit=5,
            vault_id=vault.id,
        )
        assert result.chunks
        assert "CMTS" in result.chunks[0].text
        assert result.chunks[0].source_uri.startswith("vault://")
        assert result.chunks[0].fusion_score is not None

        async with sessions() as session:
            assert await session.scalar(
                select(func.count())
                .select_from(ProjectionOutboxModel)
                .where(ProjectionOutboxModel.status == "succeeded")
            )
            assert await session.scalar(
                select(func.count())
                .select_from(ProjectionStatusModel)
                .where(ProjectionStatusModel.status == "current")
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ModelProfileModel)
                    .where(ModelProfileModel.is_active.is_(True))
                )
                == 1
            )

        note.unlink()
        await ingest.scan(vault.id, ScanType.INCREMENTAL)
        deleted = await projection.run(vault_id=vault.id)
        assert deleted.projected_deletes > 0
        after_delete = await retrieval.retrieve(
            "CMTS modem provisioning",
            strategy="hybrid",
            limit=5,
            vault_id=vault.id,
        )
        assert after_delete.chunks == ()
    finally:
        await vectors.close()
        if outcome is not None:
            async with httpx.AsyncClient(base_url=settings.qdrant_url) as client:
                await client.delete("/collections/phase3_old_collection")
                await client.delete(f"/collections/{outcome.collection}")
        await engine.dispose()
