from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import TracebackType
from uuid import UUID, uuid4

from graphrag_service.domain.jobs import ClaimedJob
from graphrag_service.workers.runner import Worker


class FakeQueue:
    def __init__(self, claimed_job: ClaimedJob | None) -> None:
        self.claimed_job = claimed_job
        self.succeeded: list[UUID] = []
        self.failed: list[UUID] = []

    async def claim(self, worker_id: str, lease_for: timedelta) -> ClaimedJob | None:
        job, self.claimed_job = self.claimed_job, None
        return job

    async def succeed(
        self,
        job_id: UUID,
        worker_id: str,
        *,
        checkpoint: dict[str, object] | None = None,
    ) -> bool:
        self.succeeded.append(job_id)
        return True

    async def fail(
        self,
        job_id: UUID,
        worker_id: str,
        **_: object,
    ) -> bool:
        self.failed.append(job_id)
        return True

    async def recover_expired_leases(self) -> int:
        return 0

    async def heartbeat(self, job_id: UUID, worker_id: str, lease_for: timedelta) -> bool:
        return True


class FakeUnitOfWork:
    def __init__(self, queue: FakeQueue) -> None:
        self.jobs = queue

    async def __aenter__(self) -> FakeUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


def make_job(job_type: str = "dummy.noop") -> ClaimedJob:
    return ClaimedJob(
        id=uuid4(),
        job_type=job_type,
        payload={},
        checkpoint={},
        attempt_count=1,
        max_attempts=3,
        lease_owner="worker-1",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )


async def test_worker_claims_and_completes_dummy_job() -> None:
    job = make_job()
    queue = FakeQueue(job)
    worker = Worker(
        worker_id="worker-1",
        unit_of_work_factory=lambda: FakeUnitOfWork(queue),
        lease_seconds=60,
        heartbeat_seconds=20,
    )

    assert await worker.run_once() is True
    assert queue.succeeded == [job.id]
    assert queue.failed == []


async def test_worker_retries_unknown_job_type() -> None:
    job = make_job("unknown")
    queue = FakeQueue(job)
    worker = Worker(
        worker_id="worker-1",
        unit_of_work_factory=lambda: FakeUnitOfWork(queue),
        lease_seconds=60,
        heartbeat_seconds=20,
    )

    assert await worker.run_once() is True
    assert queue.failed == [job.id]
    assert queue.succeeded == []
