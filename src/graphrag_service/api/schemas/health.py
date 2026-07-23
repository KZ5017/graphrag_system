from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class ComponentReadiness(BaseModel):
    status: Literal["up", "down", "skipped"]
    required: bool
    latency_ms: float
    detail: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "degraded", "not_ready"]
    service: str
    version: str
    components: dict[str, ComponentReadiness]
