from __future__ import annotations


def test_local_model_defaults_match_validated_lm_studio_identifiers(settings_factory) -> None:
    settings = settings_factory()

    assert settings.embedding_model == "text-embedding-bge-m3"
    assert settings.generation_model == "qwen/qwen3.5-9b"
    assert settings.generation_reasoning_effort == "none"


def test_blank_optional_provider_tokens_are_normalized(settings_factory) -> None:
    settings = settings_factory(
        generation_provider_api_key="",
        embedding_provider_api_key="",
    )

    assert settings.generation_provider_api_key is None
    assert settings.embedding_provider_api_key is None
