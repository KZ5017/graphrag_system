from __future__ import annotations

from datetime import timedelta
from typing import Any, Protocol
from uuid import UUID

from graphrag_service.domain.jobs import ClaimedJob


class JobQueue(Protocol):
    async def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        priority: int = 0,
        max_attempts: int = 3,
    ) -> UUID: ...

    async def claim(self, worker_id: str, lease_for: timedelta) -> ClaimedJob | None: ...

    async def heartbeat(self, job_id: UUID, worker_id: str, lease_for: timedelta) -> bool: ...

    async def succeed(
        self,
        job_id: UUID,
        worker_id: str,
        *,
        checkpoint: dict[str, Any] | None = None,
    ) -> bool: ...

    async def fail(
        self,
        job_id: UUID,
        worker_id: str,
        *,
        error_code: str,
        error_message: str,
        retry_delay: timedelta,
        checkpoint: dict[str, Any] | None = None,
    ) -> bool: ...

    async def request_cancel(self, job_id: UUID) -> bool: ...

    async def recover_expired_leases(self) -> int: ...
