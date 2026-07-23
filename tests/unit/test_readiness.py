from __future__ import annotations

from graphrag_service.application.readiness import ComponentCheck, ReadinessService


async def test_readiness_is_not_ready_when_required_component_fails() -> None:
    async def up() -> str:
        return "available"

    async def down() -> str:
        raise ConnectionError("not exposed")

    service = ReadinessService(
        [
            ComponentCheck(name="postgresql", required=True, check=down),
            ComponentCheck(name="provider", required=False, check=up),
        ],
        timeout_seconds=0.1,
    )
    status, components = await service.check()

    assert status == "not_ready"
    assert components["postgresql"].status == "down"
    assert components["postgresql"].detail == "check_failed:ConnectionError"


async def test_readiness_is_degraded_for_optional_failure_and_skips_disabled() -> None:
    async def down() -> str:
        raise ConnectionError

    async def disabled() -> str:
        return "disabled"

    service = ReadinessService(
        [
            ComponentCheck(name="provider", required=False, check=down),
            ComponentCheck(name="other_provider", required=False, check=disabled),
        ],
        timeout_seconds=0.1,
    )
    status, components = await service.check()

    assert status == "degraded"
    assert components["other_provider"].status == "skipped"
