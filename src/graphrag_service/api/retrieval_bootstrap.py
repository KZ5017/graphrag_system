from __future__ import annotations

from fastapi import FastAPI

from graphrag_service.adapters.postgres.graphrag_retrieval_store import (
    GraphRetrievalStore,
)
from graphrag_service.adapters.postgres.projection_store import ProjectionStore
from graphrag_service.adapters.providers.lmstudio_embeddings import (
    LMStudioEmbeddingProvider,
)
from graphrag_service.adapters.qdrant.client import QdrantVectorIndex
from graphrag_service.application.graph_retrieval import GraphRetrievalEnricher
from graphrag_service.application.phase5_retrieval import Phase5RetrievalService
from graphrag_service.application.query_planner import DeterministicQueryPlanner
from graphrag_service.config import Settings


def configure_retrieval(app: FastAPI, settings: Settings) -> None:
    provider = None
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
        api_key=(settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None),
        timeout_seconds=settings.readiness_timeout_seconds,
    )
    projection_store = ProjectionStore(app.state.session_factory)
    store = GraphRetrievalStore(app.state.session_factory)
    app.state.embedding_provider = provider
    app.state.vector_index = vectors
    app.state.projection_store = projection_store
    app.state.retrieval_service = Phase5RetrievalService(
        store=store,
        projection_store=projection_store,
        vector_index=vectors,
        embedding_provider=provider,
        query_planner=DeterministicQueryPlanner(),
        graph_enricher=GraphRetrievalEnricher(
            store=store,
            graph=app.state.graph_adapter,
            entity_limit=settings.retrieval_entity_limit,
            max_hops=settings.retrieval_graph_max_hops,
            max_paths=settings.retrieval_graph_max_paths,
        ),
        candidate_limit=settings.retrieval_candidate_limit,
        claim_limit=settings.retrieval_claim_limit,
        max_limit=settings.retrieval_max_limit,
        rrf_k=settings.retrieval_rrf_k,
        chunks_alias=settings.qdrant_chunks_alias,
        document_context_max_documents=settings.retrieval_document_context_max_documents,
        document_context_max_chunks_per_document=(
            settings.retrieval_document_context_max_chunks_per_document
        ),
        document_context_max_chars=settings.retrieval_document_context_max_chars,
    )
