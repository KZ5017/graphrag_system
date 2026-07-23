from __future__ import annotations

from fastapi import Depends
from fastapi.testclient import TestClient

from graphrag_service.api.app import create_app
from graphrag_service.api.auth import require_service_token
from graphrag_service.application.readiness import ComponentCheck, ReadinessService


def test_health_is_liveness_only_and_returns_request_id(settings_factory) -> None:
    async def unreachable() -> str:
        raise AssertionError("health must not invoke readiness checks")

    readiness = ReadinessService(
        [ComponentCheck(name="unused", required=True, check=unreachable)],
        timeout_seconds=0.1,
    )
    app = create_app(settings_factory(), readiness_service=readiness)

    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "known-request"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "graphrag-knowledge-service",
        "version": "0.1.0",
    }
    assert response.headers["X-Request-ID"] == "known-request"


def test_ready_returns_component_status_and_503(settings_factory) -> None:
    async def down() -> str:
        raise ConnectionError

    readiness = ReadinessService(
        [ComponentCheck(name="postgresql", required=True, check=down)],
        timeout_seconds=0.1,
    )
    app = create_app(settings_factory(), readiness_service=readiness)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["components"]["postgresql"]["status"] == "down"


def test_v1_service_token_dependency_does_not_echo_secret(settings_factory) -> None:
    settings = settings_factory()
    app = create_app(
        settings,
        readiness_service=ReadinessService([], timeout_seconds=0.1),
    )

    @app.get("/v1/test-auth", dependencies=[Depends(require_service_token)])
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        missing = client.get("/v1/test-auth")
        invalid = client.get(
            "/v1/test-auth",
            headers={"Authorization": "Bearer definitely-wrong-secret"},
        )
        valid = client.get(
            "/v1/test-auth",
            headers={"Authorization": f"Bearer {settings.service_token.get_secret_value()}"},
        )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert "definitely-wrong-secret" not in invalid.text
    assert valid.status_code == 200
