from __future__ import annotations

from collections.abc import Callable

import pytest

from graphrag_service.config import Settings


@pytest.fixture
def settings_factory() -> Callable[..., Settings]:
    def factory(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "environment": "test",
            "service_token": "unit-test-service-token-32-characters",
            "neo4j_password": "unit-test-neo4j-password",
            "generation_provider_enabled": False,
            "embedding_provider_enabled": False,
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)  # type: ignore[arg-type]

    return factory
