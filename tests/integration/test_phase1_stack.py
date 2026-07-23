from __future__ import annotations

import os
import subprocess
import sys
from uuid import UUID

import pytest
from sqlalchemy import select

from graphrag_service.adapters.postgres.models import JobModel
from graphrag_service.adapters.postgres.session import (
    create_engine,
    create_session_factory,
)
from graphrag_service.adapters.postgres.unit_of_work import SqlAlchemyUnitOfWork
from graphrag_service.adapters.readiness import build_readiness_service
from graphrag_service.config import Settings
from graphrag_service.workers.runner import Worker

pytestmark = pytest.mark.integration


def integration_settings() -> Settings:
    dsn = os.environ.get("GKS_TEST_POSTGRES_DSN")
    password = os.environ.get("GKS_TEST_NEO4J_PASSWORD")
    if not dsn or not password:
        pytest.skip("dedicated Phase 1 integration environment is not configured")
    return Settings(
        environment="test",
        service_token="integration-service-token-32-characters",
        postgres_dsn=dsn,
        qdrant_url=os.environ.get("GKS_TEST_QDRANT_URL", "http://127.0.0.1:6333"),
        neo4j_uri=os.environ.get("GKS_TEST_NEO4J_URI", "bolt://127.0.0.1:7687"),
        neo4j_username=os.environ.get("GKS_TEST_NEO4J_USERNAME", "neo4j"),
        neo4j_password=password,
    )


def run_alembic(command: str, dsn: str) -> None:
    environment = {**os.environ, "GKS_POSTGRES_DSN": dsn}
    subprocess.run(
        [sys.executable, "-m", "alembic", command, "head" if command == "upgrade" else "base"],
        check=True,
        env=environment,
    )


async def test_migration_persistent_queue_worker_and_readiness() -> None:
    settings = integration_settings()
    run_alembic("downgrade", settings.postgres_dsn)
    run_alembic("upgrade", settings.postgres_dsn)

    first_engine = create_engine(settings)
    first_sessions = create_session_factory(first_engine)
    async with SqlAlchemyUnitOfWork(first_sessions) as uow:
        job_id: UUID = await uow.jobs.enqueue("dummy.noop", {"durable": True})
    await first_engine.dispose()

    second_engine = create_engine(settings)
    second_sessions = create_session_factory(second_engine)
    async with second_sessions() as session:
        persisted_status = await session.scalar(
            select(JobModel.status).where(JobModel.id == job_id)
        )
    assert persisted_status == "queued"

    worker = Worker(
        worker_id="integration-worker",
        unit_of_work_factory=lambda: SqlAlchemyUnitOfWork(second_sessions),
        lease_seconds=60,
        heartbeat_seconds=20,
    )
    assert await worker.run_once() is True

    async with second_sessions() as session:
        completed_status = await session.scalar(
            select(JobModel.status).where(JobModel.id == job_id)
        )
    assert completed_status == "succeeded"

    readiness_status, components = await build_readiness_service(settings, second_engine).check()
    assert readiness_status == "ready"
    assert all(result.status in {"up", "skipped"} for result in components.values())
    await second_engine.dispose()
