from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    id: UUID
    job_type: str
    payload: dict[str, Any]
    checkpoint: dict[str, Any]
    attempt_count: int
    max_attempts: int
    lease_owner: str
    lease_expires_at: datetime
    warnings: list[str] = field(default_factory=list)
