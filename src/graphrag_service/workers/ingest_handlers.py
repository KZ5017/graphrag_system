from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from graphrag_service.adapters.postgres.ingest_store import PostgresIngestStore
from graphrag_service.adapters.postgres.projection_store import ProjectionStore
from graphrag_service.adapters.providers.lmstudio_embeddings import LMStudioEmbeddingProvider
from graphrag_service.adapters.qdrant.client import QdrantVectorIndex
from graphrag_service.adapters.vault_fs.factory import build_vault_reader
from graphrag_service.application.ingest import VaultIngestService
from graphrag_service.application.projection import ChunkProjectionService
from graphrag_service.config import Settings
from graphrag_service.domain.jobs import ClaimedJob
from graphrag_service.domain.vault import ScanType
from graphrag_service.workers.runner import JobHandler, dummy_job_handler


def build_ingest_handlers(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    worker_id: str = "projection-worker",
) -> dict[str, JobHandler]:
    store = PostgresIngestStore(session_factory)
    service = VaultIngestService(
        store=store,
        reader_factory=lambda vault: build_vault_reader(settings, vault),
    )

    projection_service = None
    if settings.embedding_provider_enabled:
        provider = LMStudioEmbeddingProvider(
            base_url=settings.embedding_provider_url,
            model=settings.embedding_model,
            api_key=(
                settings.embedding_provider_api_key.get_secret_value()
                if settings.embedding_provider_api_key
                else None
            ),
            timeout_seconds=settings.embedding_timeout_seconds,
            max_batch_size=settings.embedding_batch_size,
        )
        vectors = QdrantVectorIndex(
            base_url=settings.qdrant_url,
            api_key=(
                settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
            ),
            timeout_seconds=settings.embedding_timeout_seconds,
        )
        projection_service = ChunkProjectionService(
            store=ProjectionStore(session_factory),
            provider=provider,
            vectors=vectors,
            alias=settings.qdrant_chunks_alias,
            worker_id=worker_id,
            batch_size=settings.projection_batch_size,
            lease_seconds=settings.worker_lease_seconds,
        )

    async def scan_vault(job: ClaimedJob) -> dict[str, object]:
        vault_id = UUID(str(job.payload["vault_id"]))
        scan_type = ScanType(str(job.payload.get("scan_type", "incremental")))
        outcome = await service.scan(vault_id, scan_type)
        return {
            "scan_id": str(outcome.scan_id),
            "discovered": outcome.result.discovered_count,
            "hashed": outcome.result.hashed_count,
            "created": outcome.result.new_count,
            "modified": outcome.result.modified_count,
            "renamed": outcome.result.renamed_count,
            "deleted": outcome.result.deleted_count,
            "parsed_documents": outcome.parsed_documents,
            "failed_documents": outcome.failed_documents,
        }

    async def project_chunks(job: ClaimedJob) -> dict[str, object]:
        if projection_service is None:
            raise RuntimeError("embedding provider is disabled")
        raw_vault_id = job.payload.get("vault_id")
        outcome = await projection_service.run(
            vault_id=UUID(str(raw_vault_id)) if raw_vault_id else None
        )
        return {
            "model_profile_id": str(outcome.model_profile_id),
            "collection": outcome.collection,
            "vector_dimension": outcome.vector_dimension,
            "enqueued_upserts": outcome.enqueued_upserts,
            "enqueued_deletes": outcome.enqueued_deletes,
            "projected_upserts": outcome.projected_upserts,
            "projected_deletes": outcome.projected_deletes,
        }

    async def rebuild_vector_projection(job: ClaimedJob) -> dict[str, object]:
        if projection_service is None:
            raise RuntimeError("embedding provider is disabled")
        outcome = await projection_service.run(vault_id=None, rebuild=True)
        return {
            "model_profile_id": str(outcome.model_profile_id),
            "collection": outcome.collection,
            "vector_dimension": outcome.vector_dimension,
            "projected_upserts": outcome.projected_upserts,
            "rebuild": True,
        }

    return {
        "dummy.noop": dummy_job_handler,
        "scan_vault": scan_vault,
        "project_chunks": project_chunks,
        "rebuild_vector_projection": rebuild_vector_projection,
    }
