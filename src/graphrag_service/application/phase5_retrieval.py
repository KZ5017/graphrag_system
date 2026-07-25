from __future__ import annotations

from dataclasses import replace
from time import perf_counter
from uuid import UUID

from graphrag_service.adapters.postgres.projection_store import (
    ModelProfile,
    ProjectionStore,
)
from graphrag_service.adapters.postgres.retrieval_store import RetrievalStore
from graphrag_service.application.graph_retrieval import (
    GraphRetrievalEnricher,
    GraphRetrievalExpansion,
)
from graphrag_service.application.query_planner import DeterministicQueryPlanner
from graphrag_service.application.retrieval import reciprocal_rank_fusion
from graphrag_service.domain.embedding import EmbeddingProviderError
from graphrag_service.domain.retrieval import (
    RetrievalChunk,
    RetrievalClaim,
    RetrievalResult,
    RetrievalStrategy,
    RetrievalWarning,
)
from graphrag_service.ports.embedding import EmbeddingProvider
from graphrag_service.ports.vector_index import VectorIndex


class Phase5RetrievalService:
    """Deterministic chunk/entity/graph retrieval with current-source gates."""

    def __init__(
        self,
        *,
        store: RetrievalStore,
        projection_store: ProjectionStore,
        vector_index: VectorIndex,
        embedding_provider: EmbeddingProvider | None,
        query_planner: DeterministicQueryPlanner,
        graph_enricher: GraphRetrievalEnricher,
        candidate_limit: int,
        claim_limit: int,
        max_limit: int,
        rrf_k: int,
        chunks_alias: str,
    ) -> None:
        self._store = store
        self._projection_store = projection_store
        self._vectors = vector_index
        self._embeddings = embedding_provider
        self._planner = query_planner
        self._graph = graph_enricher
        self._candidate_limit = candidate_limit
        self._claim_limit = claim_limit
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
        plan = self._planner.plan(query, strategy=strategy)
        warnings: list[RetrievalWarning] = []
        keyword: list[RetrievalChunk] = []
        semantic: list[RetrievalChunk] = []
        profile = await self._projection_store.active_embedding_profile()
        candidate_limit = max(limit, self._candidate_limit)

        if "keyword" in plan.channels:
            keyword = await self._store.keyword_search(
                query,
                limit=candidate_limit,
                vault_id=vault_id,
            )
        if "semantic" in plan.channels:
            semantic, semantic_warnings = await self._semantic_search(
                query,
                limit=candidate_limit,
                vault_id=vault_id,
                profile=profile,
                strategy=strategy,
            )
            warnings.extend(semantic_warnings)

        graph = GraphRetrievalExpansion((), (), (), (), (), False)
        seed_chunks: list[RetrievalChunk] = []
        claims: list[RetrievalClaim] = []
        claim_chunks: list[RetrievalChunk] = []
        claim_truncated = False
        channels: dict[str, list[UUID]] = {}
        all_chunks: dict[UUID, RetrievalChunk] = {}
        if keyword:
            channels["keyword"] = [item.chunk_id for item in keyword]
            all_chunks.update((item.chunk_id, item) for item in keyword)
        if semantic:
            channels["semantic"] = [item.chunk_id for item in semantic]
            all_chunks.update((item.chunk_id, item) for item in semantic)

        if plan.graph_expansion:
            seed_chunks = self._rank_seed_chunks(keyword, semantic)[:candidate_limit]
            graph = await self._graph.expand(
                query,
                seed_chunks=seed_chunks,
                vault_id=vault_id,
            )
            warnings.extend(graph.warnings)
            graph_chunks = {item.chunk_id: item for item in graph.source_chunks}
            entity_ids = list(
                dict.fromkeys(
                    chunk_id
                    for entity in graph.entities
                    if any(channel != "graph" for channel in entity.seed_channels)
                    for chunk_id in entity.source_chunk_ids
                    if chunk_id in graph_chunks
                )
            )
            if entity_ids:
                channels["entity"] = entity_ids
                all_chunks.update((chunk_id, graph_chunks[chunk_id]) for chunk_id in entity_ids)
            if graph.source_chunks:
                graph_ids = [item.chunk_id for item in graph.source_chunks]
                channels["graph"] = graph_ids
                for rank, item in enumerate(graph.source_chunks, start=1):
                    all_chunks[item.chunk_id] = replace(
                        all_chunks.get(item.chunk_id, item),
                        graph_score=1.0 / (self._rrf_k + rank),
                    )

        if plan.claim_retrieval:
            claim_seed_ids = list(
                dict.fromkeys(
                    [item.chunk_id for item in seed_chunks]
                    + [item.chunk_id for item in graph.source_chunks]
                )
            )
            claim_rows = await self._store.claim_candidates(
                query,
                chunk_ids=claim_seed_ids,
                limit=self._claim_limit + 1,
                vault_id=vault_id,
            )
            claim_truncated = len(claim_rows) > self._claim_limit
            claim_rows = claim_rows[: self._claim_limit]
            claims = [claim for claim, _ in claim_rows]
            claim_chunks = list({chunk.chunk_id: chunk for _, chunk in claim_rows}.values())
            if claim_chunks:
                channels["claim"] = [item.chunk_id for item in claim_chunks]
                for rank, item in enumerate(claim_chunks, start=1):
                    all_chunks[item.chunk_id] = replace(
                        all_chunks.get(item.chunk_id, item),
                        claim_score=1.0 / (self._rrf_k + rank),
                    )

        consensus_ids = _primary_consensus_ids(keyword, semantic)
        precision_filtered = False
        if consensus_ids:
            allowed_ids = set(consensus_ids)
            if _has_explicit_entity_anchor(graph):
                allowed_ids.update(item.chunk_id for item in graph.source_chunks)
                allowed_ids.update(item.chunk_id for item in claim_chunks)
            precision_filtered = any(chunk_id not in allowed_ids for chunk_id in all_chunks)
            channels = {
                name: [chunk_id for chunk_id in chunk_ids if chunk_id in allowed_ids]
                for name, chunk_ids in channels.items()
                if any(chunk_id in allowed_ids for chunk_id in chunk_ids)
            }
            all_chunks = {
                chunk_id: chunk for chunk_id, chunk in all_chunks.items() if chunk_id in allowed_ids
            }

        ranked = self._rank(strategy, keyword, semantic, channels, all_chunks)
        truncated = len(ranked) > limit or graph.truncated or claim_truncated or precision_filtered
        ranked = ranked[:limit]
        section_context = await self._store.section_context(
            [item.chunk_id for item in ranked],
            neighbor_window=1,
        )
        ranked_ids = {item.chunk_id for item in ranked}
        context_by_id = {
            item.chunk_id: item for item in section_context if item.chunk_id not in ranked_ids
        }
        context_chunks = list(context_by_id.values())
        active_source_ids = ranked_ids | set(context_by_id)
        relationships = tuple(
            item for item in graph.relationships if item.source_chunk_id in active_source_ids
        )
        visible_claims = tuple(item for item in claims if item.source_chunk_id in active_source_ids)
        retrieval_paths = tuple(
            item
            for item in graph.paths
            if item.source_chunk_ids
            and all(chunk_id in active_source_ids for chunk_id in item.source_chunk_ids)
        )
        visible_entity_ids = {
            entity_id
            for relationship in relationships
            for entity_id in (
                relationship.subject_entity_id,
                relationship.object_entity_id,
            )
        } | {entity_id for path in retrieval_paths for entity_id in path.entity_ids}
        entities = tuple(
            item
            for item in graph.entities
            if item.entity_id in visible_entity_ids
            or any(chunk_id in active_source_ids for chunk_id in item.source_chunk_ids)
        )
        query_type = plan.query_type
        retrieval_plan = plan.channels
        warning_tuple = tuple(warnings)
        status = "degraded" if warnings else "succeeded"
        query_id = await self._store.record_query(
            query=query,
            strategy=strategy,
            status=status,
            result_count=len(ranked),
            started_at=started_at,
            model_profile_id=profile.id if profile else None,
            request={
                "limit": limit,
                "vault_id": str(vault_id) if vault_id else None,
                "query_type": query_type,
                "channels": list(retrieval_plan),
                "planner_reason_code": plan.reason_code,
            },
            warnings=warning_tuple,
        )
        return RetrievalResult(
            query_id=query_id,
            query_type=query_type,
            retrieval_plan=retrieval_plan,
            planner_reason_code=plan.reason_code,
            strategy=strategy,
            chunks=tuple(ranked),
            context_chunks=tuple(context_chunks),
            entities=entities,
            relationships=relationships,
            claims=visible_claims,
            retrieval_paths=retrieval_paths,
            warnings=warning_tuple,
            truncated=truncated,
        )

    async def _semantic_search(
        self,
        query: str,
        *,
        limit: int,
        vault_id: UUID | None,
        profile: ModelProfile | None,
        strategy: RetrievalStrategy,
    ) -> tuple[list[RetrievalChunk], list[RetrievalWarning]]:
        if self._embeddings is None or profile is None:
            return [], [
                RetrievalWarning(
                    code="semantic_unavailable",
                    message="Semantic retrieval is not configured; available channels were used.",
                )
            ]
        try:
            embedded = await self._embeddings.embed([query])
            vector_dimension = int(profile.vector_dimension)
            if embedded.dimension != vector_dimension:
                raise EmbeddingProviderError(
                    "dimension_mismatch",
                    "Query embedding dimension does not match the active index.",
                    retryable=False,
                )
            vector_hits = await self._vectors.search(
                self._chunks_alias,
                embedded.vectors[0],
                limit=limit,
                filters={"vault_id": str(vault_id)} if vault_id else None,
            )
            hydrated = await self._store.hydrate_current([item.id for item in vector_hits])
            semantic: list[RetrievalChunk] = []
            stale_count = 0
            for hit in vector_hits:
                chunk = hydrated.get(hit.id)
                if chunk is None:
                    stale_count += 1
                    continue
                semantic.append(replace(chunk, semantic_score=hit.score))
            warnings = (
                [
                    RetrievalWarning(
                        code="stale_projection_filtered",
                        message=f"{stale_count} stale vector hits were discarded.",
                    )
                ]
                if stale_count
                else []
            )
            return semantic, warnings
        except (EmbeddingProviderError, RuntimeError) as exc:
            return [], [
                RetrievalWarning(
                    code=(
                        "semantic_unavailable" if strategy == "semantic" else "semantic_degraded"
                    ),
                    message=(
                        str(exc)
                        if strategy == "semantic"
                        else "Semantic retrieval failed; available channels were retained."
                    ),
                )
            ]

    def _rank_seed_chunks(
        self,
        keyword: list[RetrievalChunk],
        semantic: list[RetrievalChunk],
    ) -> list[RetrievalChunk]:
        channels = {
            name: [item.chunk_id for item in values]
            for name, values in (("keyword", keyword), ("semantic", semantic))
            if values
        }
        if not channels:
            return []
        scores = reciprocal_rank_fusion(channels, k=self._rrf_k)
        chunks = {item.chunk_id: item for item in [*keyword, *semantic]}
        return [
            chunks[chunk_id]
            for chunk_id, _ in sorted(
                scores.items(),
                key=lambda item: (-item[1], str(item[0])),
            )
        ]

    def _rank(
        self,
        strategy: RetrievalStrategy,
        keyword: list[RetrievalChunk],
        semantic: list[RetrievalChunk],
        channels: dict[str, list[UUID]],
        all_chunks: dict[UUID, RetrievalChunk],
    ) -> list[RetrievalChunk]:
        if strategy == "keyword":
            return keyword
        if strategy == "semantic":
            return semantic
        if not channels:
            return []
        if len(channels) == 1:
            return [all_chunks[chunk_id] for chunk_id in next(iter(channels.values()))]

        fusion = reciprocal_rank_fusion(channels, k=self._rrf_k)
        keyword_scores = {item.chunk_id: item.keyword_score for item in keyword}
        semantic_scores = {item.chunk_id: item.semantic_score for item in semantic}
        return [
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


def _primary_consensus_ids(
    keyword: list[RetrievalChunk],
    semantic: list[RetrievalChunk],
) -> set[UUID]:
    if not keyword or not semantic:
        return set()
    semantic_scores = [item.semantic_score for item in semantic if item.semantic_score is not None]
    if not semantic_scores:
        return set()
    semantic_floor = max(semantic_scores) * 0.85
    strong_semantic_ids = {
        item.chunk_id
        for item in semantic
        if item.semantic_score is not None and item.semantic_score >= semantic_floor
    }
    return {item.chunk_id for item in keyword} & strong_semantic_ids


def _has_explicit_entity_anchor(expansion: GraphRetrievalExpansion) -> bool:
    return any("entity" in item.seed_channels and item.score >= 1.0 for item in expansion.entities)
