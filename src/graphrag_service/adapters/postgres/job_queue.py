from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from graphrag_service.adapters.postgres.models import JobModel
from graphrag_service.domain.jobs import ClaimedJob, JobStatus


class SqlAlchemyJobQueue:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        priority: int = 0,
        max_attempts: int = 3,
    ) -> UUID:
        job = JobModel(
            job_type=job_type,
            payload_json=payload,
            priority=priority,
            max_attempts=max_attempts,
        )
        self._session.add(job)
        await self._session.flush()
        return job.id

    async def claim(self, worker_id: str, lease_for: timedelta) -> ClaimedJob | None:
        now = datetime.now(UTC)
        statement = (
            select(JobModel)
            .where(
                JobModel.status == JobStatus.QUEUED.value,
                or_(JobModel.next_attempt_at.is_(None), JobModel.next_attempt_at <= func.now()),
                JobModel.attempt_count < JobModel.max_attempts,
            )
            .order_by(
                JobModel.priority.desc(),
                JobModel.next_attempt_at.asc().nullsfirst(),
                JobModel.created_at.asc(),
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = await self._session.scalar(statement)
        if job is None:
            return None

        job.status = JobStatus.RUNNING.value
        job.lease_owner = worker_id
        job.lease_expires_at = now + lease_for
        job.heartbeat_at = now
        job.attempt_count += 1
        job.started_at = job.started_at or now
        job.updated_at = now
        await self._session.flush()
        return ClaimedJob(
            id=job.id,
            job_type=job.job_type,
            payload=dict(job.payload_json),
            checkpoint=dict(job.checkpoint_json),
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            lease_owner=worker_id,
            lease_expires_at=job.lease_expires_at,
        )

    async def heartbeat(self, job_id: UUID, worker_id: str, lease_for: timedelta) -> bool:
        now = datetime.now(UTC)
        result = await self._session.execute(
            update(JobModel)
            .where(
                JobModel.id == job_id,
                JobModel.status == JobStatus.RUNNING.value,
                JobModel.lease_owner == worker_id,
                JobModel.lease_expires_at > func.now(),
            )
            .values(
                heartbeat_at=now,
                lease_expires_at=now + lease_for,
                updated_at=now,
            )
        )
        return bool(result.rowcount)

    async def succeed(
        self,
        job_id: UUID,
        worker_id: str,
        *,
        checkpoint: dict[str, Any] | None = None,
    ) -> bool:
        now = datetime.now(UTC)
        values: dict[str, Any] = {
            "status": JobStatus.SUCCEEDED.value,
            "finished_at": now,
            "updated_at": now,
            "lease_owner": None,
            "lease_expires_at": None,
            "heartbeat_at": None,
            "error_code": None,
            "error_message": None,
        }
        if checkpoint is not None:
            values["checkpoint_json"] = checkpoint
        result = await self._session.execute(
            update(JobModel)
            .where(
                JobModel.id == job_id,
                JobModel.status == JobStatus.RUNNING.value,
                JobModel.lease_owner == worker_id,
            )
            .values(**values)
        )
        return bool(result.rowcount)

    async def fail(
        self,
        job_id: UUID,
        worker_id: str,
        *,
        error_code: str,
        error_message: str,
        retry_delay: timedelta,
        checkpoint: dict[str, Any] | None = None,
    ) -> bool:
        statement = (
            select(JobModel)
            .where(
                JobModel.id == job_id,
                JobModel.status == JobStatus.RUNNING.value,
                JobModel.lease_owner == worker_id,
            )
            .with_for_update()
        )
        job = await self._session.scalar(statement)
        if job is None:
            return False

        now = datetime.now(UTC)
        can_retry = job.attempt_count < job.max_attempts
        job.status = JobStatus.QUEUED.value if can_retry else JobStatus.FAILED.value
        job.next_attempt_at = now + retry_delay if can_retry else None
        job.finished_at = None if can_retry else now
        job.lease_owner = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        job.error_code = error_code
        job.error_message = error_message[:4000]
        job.updated_at = now
        if checkpoint is not None:
            job.checkpoint_json = checkpoint
        await self._session.flush()
        return True

    async def request_cancel(self, job_id: UUID) -> bool:
        now = datetime.now(UTC)
        queued_result = await self._session.execute(
            update(JobModel)
            .where(
                JobModel.id == job_id,
                JobModel.status == JobStatus.QUEUED.value,
            )
            .values(
                status=JobStatus.CANCELLED.value,
                cancel_requested_at=now,
                finished_at=now,
                updated_at=now,
            )
        )
        if queued_result.rowcount:
            return True
        running_result = await self._session.execute(
            update(JobModel)
            .where(
                JobModel.id == job_id,
                JobModel.status == JobStatus.RUNNING.value,
            )
            .values(cancel_requested_at=now, updated_at=now)
        )
        return bool(running_result.rowcount)

    async def recover_expired_leases(self) -> int:
        now = datetime.now(UTC)
        retryable = await self._session.execute(
            update(JobModel)
            .where(
                JobModel.status == JobStatus.RUNNING.value,
                JobModel.lease_expires_at < func.now(),
                JobModel.attempt_count < JobModel.max_attempts,
            )
            .values(
                status=JobStatus.QUEUED.value,
                next_attempt_at=now,
                lease_owner=None,
                lease_expires_at=None,
                heartbeat_at=None,
                error_code="lease_expired",
                error_message="Worker lease expired; job returned to the queue.",
                updated_at=now,
            )
        )
        exhausted = await self._session.execute(
            update(JobModel)
            .where(
                JobModel.status == JobStatus.RUNNING.value,
                JobModel.lease_expires_at < func.now(),
                JobModel.attempt_count >= JobModel.max_attempts,
            )
            .values(
                status=JobStatus.FAILED.value,
                lease_owner=None,
                lease_expires_at=None,
                heartbeat_at=None,
                error_code="lease_expired",
                error_message="Worker lease expired and retry limit was reached.",
                finished_at=now,
                updated_at=now,
            )
        )
        return int(retryable.rowcount or 0) + int(exhausted.rowcount or 0)

    async def cancellation_requested(self, job_id: UUID, worker_id: str) -> bool:
        value = await self._session.scalar(
            select(JobModel.cancel_requested_at).where(
                and_(
                    JobModel.id == job_id,
                    JobModel.status == JobStatus.RUNNING.value,
                    JobModel.lease_owner == worker_id,
                )
            )
        )
        return value is not None
