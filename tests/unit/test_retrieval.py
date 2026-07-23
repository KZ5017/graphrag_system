from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

from graphrag_service.adapters.postgres.projection_store import ModelProfile
from graphrag_service.application.retrieval import RetrievalService, reciprocal_rank_fusion
from graphrag_service.domain.embedding import (
    EmbeddingBatch,
    EmbeddingModelInfo,
    ProviderCapabilities,
)
from graphrag_service.domain.retrieval import RetrievalChunk
from graphrag_service.ports.vector_index import VectorHit


def make_chunk(chunk_id: UUID, *, keyword: float | None = None) -> RetrievalChunk:
    return RetrievalChunk(
        chunk_id=chunk_id,
        vault_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        section_id=uuid4(),
        relative_path="note.md",
        heading_path=("Heading",),
        text="modem provisioning",
        char_start=10,
        char_end=28,
        content_sha256="a" * 64,
        source_uri="vault://test/note.md#chars=10,28",
        obsidian_uri=None,
        keyword_score=keyword,
    )


def test_reciprocal_rank_fusion_is_deterministic() -> None:
    first, second, third = uuid4(), uuid4(), uuid4()
    scores = reciprocal_rank_fusion(
        {"semantic": [second, third], "keyword": [first, second]},
        k=60,
    )
    assert scores[second] > scores[first]
    assert scores[second] > scores[third]


class FakeRetrievalStore:
    def __init__(self, keyword: list[RetrievalChunk], hydrated: dict[UUID, RetrievalChunk]):
        self.keyword = keyword
        self.hydrated = hydrated
        self.audit: dict[str, object] | None = None

    async def keyword_search(self, *_: object, **__: object) -> list[RetrievalChunk]:
        return self.keyword

    async def hydrate_current(self, _: list[UUID]) -> dict[UUID, RetrievalChunk]:
        return self.hydrated

    async def section_context(self, *_: object, **__: object) -> list[RetrievalChunk]:
        return []

    async def record_query(self, **values: object) -> UUID:
        self.audit = values
        return uuid4()


class FakeProjectionStore:
    def __init__(self, profile: ModelProfile | None) -> None:
        self.profile = profile

    async def active_embedding_profile(self) -> ModelProfile | None:
        return self.profile


class FakeEmbeddingProvider:
    async def healthcheck(self) -> str:
        return "available"

    async def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            provider="fake",
            model="fake-3",
            vector_dimension=3,
            capabilities=ProviderCapabilities(supports_batch=True),
        )

    async def probe_dimension(self) -> int:
        return 3

    async def embed(self, texts: list[str]) -> EmbeddingBatch:
        return EmbeddingBatch(
            vectors=tuple((1.0, 0.0, 0.0) for _ in texts),
            model="fake-3",
            dimension=3,
        )


class FakeVectorIndex:
    def __init__(self, hits: list[VectorHit]) -> None:
        self.hits = hits

    async def search(self, *_: object, **__: object) -> list[VectorHit]:
        return self.hits


async def test_hybrid_retrieval_filters_stale_vectors_and_keeps_provenance() -> None:
    keyword_id, shared_id, stale_id = uuid4(), uuid4(), uuid4()
    keyword_chunk = make_chunk(keyword_id, keyword=0.6)
    shared_chunk = make_chunk(shared_id, keyword=0.5)
    store = FakeRetrievalStore(
        [keyword_chunk, shared_chunk],
        {shared_id: replace(shared_chunk, keyword_score=None)},
    )
    profile = ModelProfile(
        id=uuid4(),
        provider="fake",
        model_name="fake-3",
        vector_dimension=3,
        physical_collection="fake",
    )
    service = RetrievalService(
        store=store,  # type: ignore[arg-type]
        projection_store=FakeProjectionStore(profile),  # type: ignore[arg-type]
        vector_index=FakeVectorIndex(  # type: ignore[arg-type]
            [
                VectorHit(id=shared_id, score=0.95, payload={}),
                VectorHit(id=stale_id, score=0.94, payload={}),
            ]
        ),
        embedding_provider=FakeEmbeddingProvider(),
        candidate_limit=10,
        max_limit=20,
        rrf_k=60,
        chunks_alias="active",
    )

    result = await service.retrieve("modem", strategy="hybrid", limit=10, vault_id=None)

    assert result.chunks[0].chunk_id == shared_id
    assert result.chunks[0].fusion_score is not None
    assert result.chunks[0].source_uri.startswith("vault://")
    assert [warning.code for warning in result.warnings] == ["stale_projection_filtered"]
    assert store.audit is not None
    assert store.audit["status"] == "degraded"


async def test_hybrid_degrades_to_keyword_when_embedding_is_disabled() -> None:
    chunk = make_chunk(uuid4(), keyword=0.5)
    store = FakeRetrievalStore([chunk], {})
    service = RetrievalService(
        store=store,  # type: ignore[arg-type]
        projection_store=FakeProjectionStore(None),  # type: ignore[arg-type]
        vector_index=FakeVectorIndex([]),  # type: ignore[arg-type]
        embedding_provider=None,
        candidate_limit=10,
        max_limit=20,
        rrf_k=60,
        chunks_alias="active",
    )

    result = await service.retrieve("modem", strategy="hybrid", limit=5, vault_id=None)

    assert result.chunks == (chunk,)
    assert result.warnings[0].code == "semantic_unavailable"
