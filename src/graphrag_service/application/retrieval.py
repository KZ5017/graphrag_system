from __future__ import annotations

from dataclasses import replace
from time import perf_counter
from uuid import UUID

from graphrag_service.adapters.postgres.projection_store import ProjectionStore
from graphrag_service.adapters.postgres.retrieval_store import RetrievalStore
from graphrag_service.domain.embedding import EmbeddingProviderError
from graphrag_service.domain.retrieval import (
    RetrievalChunk,
    RetrievalResult,
    RetrievalStrategy,
    RetrievalWarning,
)
from graphrag_service.ports.embedding import EmbeddingProvider
from graphrag_service.ports.vector_index import VectorIndex


def reciprocal_rank_fusion(
    channels: dict[str, list[UUID]],
    *,
    k: int,
) -> dict[UUID, float]:
    scores: dict[UUID, float] = {}
    for channel_name in sorted(channels):
        for rank, object_id in enumerate(channels[channel_name], start=1):
            scores[object_id] = scores.get(object_id, 0.0) + 1.0 / (k + rank)
    return scores


class RetrievalService:
    def __init__(
        self,
        *,
        store: RetrievalStore,
        projection_store: ProjectionStore,
        vector_index: VectorIndex,
        embedding_provider: EmbeddingProvider | None,
        candidate_limit: int,
        max_limit: int,
        rrf_k: int,
        chunks_alias: str,
    ) -> None:
        self._store = store
        self._projection_store = projection_store
        self._vectors = vector_index
        self._embeddings = embedding_provider
        self._candidate_limit = candidate_limit
        self._max_limit = max_limit
        self._rrf_k = rrf_k
        self._chunks_alias = chunks_alias

    async def retrieve(
        self,
        query: str,
        *,
        strategy: RetrievalStrategy,
        limit: int,
        vault_id: UUID | None,
    ) -> RetrievalResult:
        if not query.strip():
            raise ValueError("query must not be blank")
        if limit < 1 or limit > self._max_limit:
            raise ValueError(f"limit must be between 1 and {self._max_limit}")
        started_at = perf_counter()
        warnings: list[RetrievalWarning] = []
        keyword: list[RetrievalChunk] = []
        semantic: list[RetrievalChunk] = []
        profile = await self._projection_store.active_embedding_profile()

        if strategy in {"keyword", "hybrid"}:
            keyword = await self._store.keyword_search(
                query,
                limit=max(limit, self._candidate_limit),
                vault_id=vault_id,
            )
        if strategy in {"semantic", "hybrid"}:
            if self._embeddings is None or profile is None:
                warnings.append(
                    RetrievalWarning(
                        code="semantic_unavailable",
                        message="Semantic retrieval is not configured; keyword results were used.",
                    )
                )
            else:
                try:
                    embedded = await self._embeddings.embed([query])
                    if embedded.dimension != profile.vector_dimension:
                        raise EmbeddingProviderError(
                            "dimension_mismatch",
                            "Query embedding dimension does not match the active index.",
                            retryable=False,
                        )
                    vector_hits = await self._vectors.search(
                        self._chunks_alias,
                        embedded.vectors[0],
                        limit=max(limit, self._candidate_limit),
                        filters={"vault_id": str(vault_id)} if vault_id else None,
                    )
                    hydrated = await self._store.hydrate_current([item.id for item in vector_hits])
                    stale_count = 0
                    for hit in vector_hits:
                        chunk = hydrated.get(hit.id)
                        if chunk is None:
                            stale_count += 1
                            continue
                        semantic.append(replace(chunk, semantic_score=hit.score))
                    if stale_count:
                        warnings.append(
                            RetrievalWarning(
                                code="stale_projection_filtered",
                                message=f"{stale_count} stale vector hits were discarded.",
                            )
                        )
                except (EmbeddingProviderError, RuntimeError) as exc:
                    if strategy == "semantic":
                        warnings.append(
                            RetrievalWarning(
                                code="semantic_unavailable",
                                message=str(exc),
                            )
                        )
                    else:
                        warnings.append(
                            RetrievalWarning(
                                code="semantic_degraded",
                                message="Semantic retrieval failed; keyword results were retained.",
                            )
                        )

        if strategy == "keyword" or (strategy == "hybrid" and not semantic):
            ranked = keyword
        elif strategy == "semantic":
            ranked = semantic
        else:
            fusion = reciprocal_rank_fusion(
                {
                    "keyword": [item.chunk_id for item in keyword],
                    "semantic": [item.chunk_id for item in semantic],
                },
                k=self._rrf_k,
            )
            all_chunks = {item.chunk_id: item for item in [*keyword, *semantic]}
            keyword_scores = {item.chunk_id: item.keyword_score for item in keyword}
            semantic_scores = {item.chunk_id: item.semantic_score for item in semantic}
            ranked = [
                replace(
                    all_chunks[chunk_id],
                    keyword_score=keyword_scores.get(chunk_id),
                    semantic_score=semantic_scores.get(chunk_id),
                    fusion_score=score,
                )
                for chunk_id, score in sorted(
                    fusion.items(),
                    key=lambda item: (-item[1], str(item[0])),
                )
            ]

        truncated = len(ranked) > limit
        ranked = ranked[:limit]
        context_chunks = await self._store.section_context(
            [item.chunk_id for item in ranked], neighbor_window=1
        )
        warning_tuple = tuple(warnings)
        status = "degraded" if warnings else "succeeded"
        query_id = await self._store.record_query(
            query=query,
            strategy=strategy,
            status=status,
            result_count=len(ranked),
            started_at=started_at,
            model_profile_id=profile.id if profile else None,
            request={"limit": limit, "vault_id": str(vault_id) if vault_id else None},
            warnings=warning_tuple,
        )
        return RetrievalResult(
            query_id=query_id,
            query_type=strategy,
            retrieval_plan=(strategy,),
            planner_reason_code="legacy_strategy",
            strategy=strategy,
            chunks=tuple(ranked),
            context_chunks=tuple(context_chunks),
            entities=(),
            relationships=(),
            retrieval_paths=(),
            claims=(),
            warnings=warning_tuple,
            truncated=truncated,
        )
