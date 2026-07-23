from __future__ import annotations

from uuid import uuid4

import pytest

from graphrag_service.adapters.postgres.projection_store import (
    ModelProfile,
    ProjectionWorkItem,
)
from graphrag_service.application.projection import ChunkProjectionService
from graphrag_service.domain.embedding import (
    EmbeddingBatch,
    EmbeddingModelInfo,
    ProviderCapabilities,
)


class FakeProvider:
    async def healthcheck(self) -> str:
        return "available"

    async def probe_dimension(self) -> int:
        return 3

    async def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            provider="fake",
            model="fake-model",
            vector_dimension=3,
            capabilities=ProviderCapabilities(supports_batch=True, max_batch_size=8),
        )

    async def embed(self, texts: list[str]) -> EmbeddingBatch:
        return EmbeddingBatch(
            vectors=tuple((1.0, 0.0, 0.0) for _ in texts),
            model="fake-model",
            dimension=3,
        )


class FakeProjectionStore:
    def __init__(self) -> None:
        self.profile = ModelProfile(
            id=uuid4(),
            provider="fake",
            model_name="fake-model",
            vector_dimension=3,
            physical_collection="test_collection",
        )
        self.item = ProjectionWorkItem(
            outbox_id=uuid4(),
            chunk_id=uuid4(),
            operation="upsert",
            generation=1,
            model_profile_id=self.profile.id,
            collection="test_collection",
            text="test chunk",
            content_sha256="a" * 64,
            payload={"is_current": True},
            is_current=True,
            attempt_count=1,
        )
        self.claimed = False
        self.failed: list[ProjectionWorkItem] = []
        self.activated = False

    async def register_embedding_profile(self, **_: object) -> ModelProfile:
        return self.profile

    async def enqueue_current_chunks(self, **_: object) -> tuple[int, int]:
        return 1, 0

    async def claim_batch(self, **_: object) -> list[ProjectionWorkItem]:
        if self.claimed:
            return []
        self.claimed = True
        return [self.item]

    async def mark_failed(self, item: ProjectionWorkItem, **_: object) -> None:
        self.failed.append(item)

    async def mark_succeeded(self, _: ProjectionWorkItem) -> None:
        raise AssertionError("failed external write must not be marked succeeded")

    async def outstanding_counts(self, _: object) -> tuple[int, int]:
        return 1, 0

    async def set_active_profile(self, _: object) -> None:
        self.activated = True


class FailingVectorIndex:
    def __init__(self) -> None:
        self.alias_switched = False

    async def ensure_collection(self, _: str, __: int) -> None:
        return None

    async def upsert(self, *_: object) -> None:
        raise RuntimeError("injected qdrant outage")

    async def delete(self, *_: object) -> None:
        return None

    async def switch_alias(self, *_: object) -> None:
        self.alias_switched = True


async def test_projection_failure_remains_retryable_and_does_not_switch_alias() -> None:
    store = FakeProjectionStore()
    vectors = FailingVectorIndex()
    service = ChunkProjectionService(
        store=store,  # type: ignore[arg-type]
        provider=FakeProvider(),
        vectors=vectors,  # type: ignore[arg-type]
        alias="active",
        worker_id="test-worker",
        batch_size=8,
        lease_seconds=60,
    )

    with pytest.raises(RuntimeError, match="injected qdrant outage"):
        await service.run(vault_id=None)

    assert store.failed == [store.item]
    assert store.activated is False
    assert vectors.alias_switched is False
