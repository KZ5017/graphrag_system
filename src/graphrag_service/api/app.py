from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from graphrag_service.adapters.postgres.session import (
    create_engine,
    create_session_factory,
)
from graphrag_service.adapters.readiness import build_readiness_service
from graphrag_service.api.auth import require_service_token
from graphrag_service.api.graph_bootstrap import configure_graph
from graphrag_service.api.ingest_bootstrap import configure_ingest
from graphrag_service.api.middleware import RequestContextMiddleware
from graphrag_service.api.retrieval_bootstrap import configure_retrieval
from graphrag_service.api.routes.documents import router as document_router
from graphrag_service.api.routes.extraction import router as extraction_router
from graphrag_service.api.routes.graph import router as graph_router
from graphrag_service.api.routes.health import router as health_router
from graphrag_service.api.routes.resolution import router as resolution_router
from graphrag_service.api.routes.retrieval import router as retrieval_router
from graphrag_service.api.routes.vaults import router as vault_router
from graphrag_service.application.readiness import ReadinessService
from graphrag_service.config import Settings, get_settings
from graphrag_service.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    engine: AsyncEngine | None = None,
    readiness_service: ReadinessService | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    owns_engine = engine is None
    resolved_engine = engine or create_engine(resolved_settings)
    resolved_readiness = readiness_service or build_readiness_service(
        resolved_settings, resolved_engine
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        app.state.engine = resolved_engine
        app.state.session_factory = create_session_factory(resolved_engine)
        app.state.readiness_service = resolved_readiness
        configure_ingest(app, resolved_settings)
        configure_retrieval(app, resolved_settings)
        configure_graph(app, resolved_settings)
        logger.info("service_started", extra=resolved_settings.safe_summary())
        try:
            yield
        finally:
            await app.state.graph_adapter.close()
            if app.state.embedding_provider is not None:
                await app.state.embedding_provider.close()
            await app.state.vector_index.close()
            if owns_engine:
                await resolved_engine.dispose()
            logger.info("service_stopped")

    app = FastAPI(
        title="GraphRAG Knowledge Service",
        version=resolved_settings.service_version,
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router)
    v1_router = APIRouter(
        prefix="/v1",
        dependencies=[Depends(require_service_token)],
    )
    v1_router.include_router(vault_router)
    v1_router.include_router(document_router)
    v1_router.include_router(extraction_router)
    v1_router.include_router(retrieval_router)
    v1_router.include_router(graph_router)
    v1_router.include_router(resolution_router)
    app.include_router(v1_router)
    return app
