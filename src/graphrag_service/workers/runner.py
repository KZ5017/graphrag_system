from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import timedelta
from typing import Protocol

from graphrag_service.domain.jobs import ClaimedJob
from graphrag_service.ports.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)

JobHandler = Callable[[ClaimedJob], Awaitable[dict[str, object] | None]]


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


async def dummy_job_handler(job: ClaimedJob) -> dict[str, object]:
    """Phase 1 acceptance handler; proves durable claim and completion."""
    await asyncio.sleep(0)
    return {"phase": 1, "dummy": True, "job_id": str(job.id)}


class Worker:
    def __init__(
        self,
        *,
        worker_id: str,
        unit_of_work_factory: UnitOfWorkFactory,
        lease_seconds: int,
        heartbeat_seconds: int,
        handlers: dict[str, JobHandler] | None = None,
    ) -> None:
        self._worker_id = worker_id
        self._uow_factory = unit_of_work_factory
        self._lease_for = timedelta(seconds=lease_seconds)
        self._heartbeat_seconds = heartbeat_seconds
        self._handlers = handlers or {"dummy.noop": dummy_job_handler}

    async def recover_expired_leases(self) -> int:
        async with self._uow_factory() as uow:
            recovered = await uow.jobs.recover_expired_leases()
        if recovered:
            logger.warning("expired_job_leases_recovered", extra={"count": recovered})
        return recovered

    async def run_once(self) -> bool:
        async with self._uow_factory() as uow:
            job = await uow.jobs.claim(self._worker_id, self._lease_for)
        if job is None:
            return False

        logger.info(
            "job_claimed",
            extra={
                "job_id": str(job.id),
                "job_type": job.job_type,
                "attempt": job.attempt_count,
            },
        )
        heartbeat = asyncio.create_task(self._heartbeat(job.id))
        try:
            handler = self._handlers.get(job.job_type)
            if handler is None:
                raise LookupError(f"unsupported job type: {job.job_type}")
            checkpoint = await handler(job)
        except Exception as exc:
            retry_delay = timedelta(seconds=min(300, 2 ** min(job.attempt_count, 8)))
            async with self._uow_factory() as uow:
                await uow.jobs.fail(
                    job.id,
                    self._worker_id,
                    error_code=type(exc).__name__.lower(),
                    error_message=str(exc),
                    retry_delay=retry_delay,
                )
            logger.exception(
                "job_failed",
                extra={"job_id": str(job.id), "job_type": job.job_type},
            )
        else:
            async with self._uow_factory() as uow:
                completed = await uow.jobs.succeed(
                    job.id,
                    self._worker_id,
                    checkpoint=checkpoint,
                )
            if not completed:
                logger.error(
                    "job_completion_rejected",
                    extra={"job_id": str(job.id), "reason": "lease_not_owned"},
                )
            else:
                logger.info(
                    "job_succeeded",
                    extra={"job_id": str(job.id), "job_type": job.job_type},
                )
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
        return True

    async def run(self, stop_event: asyncio.Event, poll_interval_seconds: float) -> None:
        await self.recover_expired_leases()
        logger.info("worker_started", extra={"worker_id": self._worker_id})
        while not stop_event.is_set():
            processed = await self.run_once()
            if not processed:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=poll_interval_seconds)
                except TimeoutError:
                    pass
        logger.info("worker_stopped", extra={"worker_id": self._worker_id})

    async def _heartbeat(self, job_id: object) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_seconds)
            async with self._uow_factory() as uow:
                renewed = await uow.jobs.heartbeat(
                    job_id,  # type: ignore[arg-type]
                    self._worker_id,
                    self._lease_for,
                )
            if not renewed:
                logger.error(
                    "job_heartbeat_rejected",
                    extra={"job_id": str(job_id), "reason": "lease_not_owned_or_expired"},
                )
                return
