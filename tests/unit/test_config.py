from __future__ import annotations

import pytest
from pydantic import ValidationError

from graphrag_service.config import Settings


def test_defaults_bind_to_loopback(settings_factory) -> None:
    settings = settings_factory()
    assert settings.api_host == "127.0.0.1"
    assert settings.allow_non_loopback_bind is False


def test_non_loopback_bind_requires_explicit_opt_in(settings_factory) -> None:
    with pytest.raises(ValidationError, match="non-loopback"):
        settings_factory(api_host="0.0.0.0")

    settings = settings_factory(api_host="0.0.0.0", allow_non_loopback_bind=True)
    assert settings.api_host == "0.0.0.0"


def test_secrets_are_required_and_excluded_from_safe_summary() -> None:
    with pytest.raises(ValidationError):
        Settings(neo4j_password="long-enough-password")  # type: ignore[call-arg]

    settings = Settings(
        service_token="a-service-token-that-is-long-enough",
        neo4j_password="a-neo4j-password",
    )
    summary = str(settings.safe_summary())
    assert settings.service_token.get_secret_value() not in summary
    assert settings.neo4j_password.get_secret_value() not in summary


def test_worker_heartbeat_must_be_shorter_than_lease(settings_factory) -> None:
    with pytest.raises(ValidationError, match="heartbeat"):
        settings_factory(worker_lease_seconds=20, worker_heartbeat_seconds=20)


@pytest.mark.parametrize(
    "field,value",
    [
        ("postgres_dsn", "postgresql://localhost/db"),
        ("qdrant_url", "ftp://localhost"),
        ("neo4j_uri", "http://localhost:7687"),
    ],
)
def test_endpoint_scheme_validation(settings_factory, field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        settings_factory(**{field: value})
