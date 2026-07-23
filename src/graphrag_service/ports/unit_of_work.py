from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self

from graphrag_service.ports.job_queue import JobQueue


class UnitOfWork(Protocol):
    jobs: JobQueue

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
