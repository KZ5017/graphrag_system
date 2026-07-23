from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from graphrag_service.adapters.postgres.projection_store import (
    ModelProfile,
    ProjectionStore,
    ProjectionWorkItem,
)
from graphrag_service.domain.embedding import EmbeddingProviderError
from graphrag_service.ports.embedding import EmbeddingProvider
from graphrag_service.ports.vector_index import VectorIndex, VectorPoint


@dataclass(frozen=True, slots=True)
class ProjectionOutcome:
    model_profile_id: UUID
    collection: str
    vector_dimension: int
    enqueued_upserts: int
    enqueued_deletes: int
    projected_upserts: int
    projected_deletes: int


class ChunkProjectionService:
    def __init__(
        self,
        *,
        store: ProjectionStore,
        provider: EmbeddingProvider,
        vectors: VectorIndex,
        alias: str,
        worker_id: str,
        batch_size: int,
        lease_seconds: int,
    ) -> None:
        self._store = store
        self._provider = provider
        self._vectors = vectors
        self._alias = alias
        self._worker_id = worker_id
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds

    async def run(self, *, vault_id: UUID | None) -> ProjectionOutcome:
        await self._provider.healthcheck()
        dimension = await self._provider.probe_dimension()
        info = await self._provider.model_info()
        profile = await self._store.register_embedding_profile(
            provider=info.provider,
            model_name=info.model,
            dimension=dimension,
            capabilities={
                "supports_batch": info.capabilities.supports_batch,
                "max_batch_size": info.capabilities.max_batch_size,
            },
        )
        await self._vectors.ensure_collection(profile.physical_collection, dimension)
        upserts, deletes = await self._store.enqueue_current_chunks(
            profile=profile,
            vault_id=vault_id,
        )

        projected_upserts = 0
        projected_deletes = 0
        while True:
            items = await self._store.claim_batch(
                worker_id=self._worker_id,
                profile_id=profile.id,
                batch_size=self._batch_size,
                lease_seconds=self._lease_seconds,
            )
            if not items:
                break
            current_upserts = [
                item
                for item in items
                if item.operation == "upsert" and item.is_current and item.text is not None
            ]
            delete_items = [item for item in items if item not in current_upserts]
            if current_upserts:
                await self._project_upserts(profile, current_upserts)
                projected_upserts += len(current_upserts)
            if delete_items:
                await self._project_deletes(profile, delete_items)
                projected_deletes += len(delete_items)

        pending, failed = await self._store.outstanding_counts(profile.id)
        if failed:
            raise RuntimeError(f"{failed} Qdrant projection operations exhausted retries")
        if pending:
            raise RuntimeError(f"{pending} Qdrant projection operations are waiting for retry")
        await self._vectors.switch_alias(self._alias, profile.physical_collection)
        await self._store.set_active_profile(profile.id)
        return ProjectionOutcome(
            model_profile_id=profile.id,
            collection=profile.physical_collection,
            vector_dimension=dimension,
            enqueued_upserts=upserts,
            enqueued_deletes=deletes,
            projected_upserts=projected_upserts,
            projected_deletes=projected_deletes,
        )

    async def _project_upserts(
        self,
        profile: ModelProfile,
        items: list[ProjectionWorkItem],
    ) -> None:
        try:
            batch = await self._provider.embed([item.text or "" for item in items])
            if batch.dimension != profile.vector_dimension:
                raise EmbeddingProviderError(
                    "dimension_mismatch",
                    "Embedding batch dimension does not match its model profile.",
                    retryable=False,
                )
            points = [
                VectorPoint(id=item.chunk_id, vector=vector, payload=item.payload)
                for item, vector in zip(items, batch.vectors, strict=True)
            ]
            await self._vectors.upsert(profile.physical_collection, points)
        except Exception as exc:
            for item in items:
                await self._store.mark_failed(
                    item,
                    error_code=type(exc).__name__.lower(),
                    error_message=str(exc),
                )
            raise
        for item in items:
            await self._store.mark_succeeded(item)

    async def _project_deletes(
        self,
        profile: ModelProfile,
        items: list[ProjectionWorkItem],
    ) -> None:
        try:
            await self._vectors.delete(
                profile.physical_collection,
                [item.chunk_id for item in items],
            )
        except Exception as exc:
            for item in items:
                await self._store.mark_failed(
                    item,
                    error_code=type(exc).__name__.lower(),
                    error_message=str(exc),
                )
            raise
        for item in items:
            await self._store.mark_succeeded(item)
