from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from graphrag_service.api.app import create_app
from graphrag_service.application.readiness import ReadinessService


def test_extraction_job_is_fail_closed_when_generation_is_disabled(
    settings_factory,
) -> None:
    settings = settings_factory(generation_provider_enabled=False)
    app = create_app(
        settings,
        readiness_service=ReadinessService([], timeout_seconds=0.1),
    )
    headers = {"Authorization": f"Bearer {settings.service_token.get_secret_value()}"}
    with TestClient(app) as client:
        response = client.post(
            "/v1/extraction-jobs",
            headers=headers,
            json={
                "vault_id": str(uuid4()),
                "document_ids": [str(uuid4())],
                "max_chunks": 2,
            },
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "Generation provider is disabled."


def test_extraction_job_requires_explicit_document_scope(settings_factory) -> None:
    settings = settings_factory(generation_provider_enabled=True)
    app = create_app(
        settings,
        readiness_service=ReadinessService([], timeout_seconds=0.1),
    )
    headers = {"Authorization": f"Bearer {settings.service_token.get_secret_value()}"}
    with TestClient(app) as client:
        response = client.post(
            "/v1/extraction-jobs",
            headers=headers,
            json={"vault_id": str(uuid4()), "document_ids": [], "max_chunks": 2},
        )
    assert response.status_code == 422
