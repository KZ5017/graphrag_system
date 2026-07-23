from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

ComponentState = Literal["up", "down", "skipped"]


@dataclass(frozen=True, slots=True)
class ComponentCheck:
    name: str
    required: bool
    check: Callable[[], Awaitable[str]]


@dataclass(frozen=True, slots=True)
class ComponentResult:
    status: ComponentState
    required: bool
    latency_ms: float
    detail: str


class ReadinessService:
    def __init__(self, checks: list[ComponentCheck], timeout_seconds: float) -> None:
        self._checks = checks
        self._timeout_seconds = timeout_seconds

    async def check(self) -> tuple[str, dict[str, ComponentResult]]:
        pairs = await asyncio.gather(*(self._run(component) for component in self._checks))
        results = dict(pairs)
        required_down = any(
            result.required and result.status == "down" for result in results.values()
        )
        optional_down = any(
            not result.required and result.status == "down" for result in results.values()
        )
        status = "not_ready" if required_down else "degraded" if optional_down else "ready"
        return status, results

    async def _run(self, component: ComponentCheck) -> tuple[str, ComponentResult]:
        started = perf_counter()
        try:
            detail = await asyncio.wait_for(component.check(), timeout=self._timeout_seconds)
        except TimeoutError:
            result = ComponentResult(
                status="down",
                required=component.required,
                latency_ms=round((perf_counter() - started) * 1000, 2),
                detail="timeout",
            )
        except Exception as exc:
            result = ComponentResult(
                status="down",
                required=component.required,
                latency_ms=round((perf_counter() - started) * 1000, 2),
                detail=f"check_failed:{type(exc).__name__}",
            )
        else:
            state: ComponentState = "skipped" if detail == "disabled" else "up"
            result = ComponentResult(
                status=state,
                required=component.required,
                latency_ms=round((perf_counter() - started) * 1000, 2),
                detail=detail,
            )
        return component.name, result
