from __future__ import annotations

from fastapi import FastAPI

from graphrag_service.adapters.postgres.projection_store import ProjectionStore
from graphrag_service.adapters.postgres.retrieval_store import RetrievalStore
from graphrag_service.adapters.providers.lmstudio_embeddings import (
    LMStudioEmbeddingProvider,
)
from graphrag_service.adapters.qdrant.client import QdrantVectorIndex
from graphrag_service.application.retrieval import RetrievalService
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
    app.state.embedding_provider = provider
    app.state.vector_index = vectors
    app.state.projection_store = projection_store
    app.state.retrieval_service = RetrievalService(
        store=RetrievalStore(app.state.session_factory),
        projection_store=projection_store,
        vector_index=vectors,
        embedding_provider=provider,
        candidate_limit=settings.retrieval_candidate_limit,
        max_limit=settings.retrieval_max_limit,
        rrf_k=settings.retrieval_rrf_k,
        chunks_alias=settings.qdrant_chunks_alias,
    )
