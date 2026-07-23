from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
from uuid import uuid4

from graphrag_service.adapters.postgres.session import (
    create_engine,
    create_session_factory,
)
from graphrag_service.adapters.postgres.unit_of_work import SqlAlchemyUnitOfWork
from graphrag_service.config import get_settings
from graphrag_service.logging import configure_logging
from graphrag_service.workers.extraction_handlers import build_extraction_handlers
from graphrag_service.workers.graph_handlers import build_graph_handlers
from graphrag_service.workers.ingest_handlers import build_ingest_handlers
from graphrag_service.workers.runner import Worker

logger = logging.getLogger(__name__)


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    worker_id = settings.worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
    handlers = build_ingest_handlers(settings, session_factory, worker_id)
    extraction_handlers, generation_provider = build_extraction_handlers(settings, session_factory)
    handlers.update(extraction_handlers)
    graph_handlers, graph_adapter = build_graph_handlers(settings, session_factory)
    handlers.update(graph_handlers)
    worker = Worker(
        worker_id=worker_id,
        unit_of_work_factory=lambda: SqlAlchemyUnitOfWork(session_factory),
        lease_seconds=settings.worker_lease_seconds,
        handlers=handlers,
        heartbeat_seconds=settings.worker_heartbeat_seconds,
    )
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    try:
        await worker.run(stop_event, settings.worker_poll_interval_seconds)
    finally:
        await graph_adapter.close()
        if generation_provider is not None:
            await generation_provider.close()
        await engine.dispose()


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("worker_interrupted")


if __name__ == "__main__":
    main()
