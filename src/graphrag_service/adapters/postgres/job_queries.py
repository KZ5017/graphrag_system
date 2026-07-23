from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from graphrag_service.adapters.postgres.models import JobModel


@dataclass(frozen=True, slots=True)
class JobView:
    id: UUID
    job_type: str
    status: str
    progress_current: int
    progress_total: int | None
    checkpoint: dict[str, Any]
    attempt_count: int
    max_attempts: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


async def get_job(
    session_factory: async_sessionmaker[AsyncSession], job_id: UUID
) -> JobView | None:
    async with session_factory() as session:
        model = await session.get(JobModel, job_id)
    if model is None:
        return None
    return JobView(
        id=model.id,
        job_type=model.job_type,
        status=model.status,
        progress_current=model.progress_current,
        progress_total=model.progress_total,
        checkpoint=dict(model.checkpoint_json),
        attempt_count=model.attempt_count,
        max_attempts=model.max_attempts,
        error_code=model.error_code,
        error_message=model.error_message,
        created_at=model.created_at,
        started_at=model.started_at,
        finished_at=model.finished_at,
    )
