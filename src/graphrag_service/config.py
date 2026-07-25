from __future__ import annotations

from functools import lru_cache
from ipaddress import ip_address
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded exclusively from explicit values and GKS_* variables."""

    model_config = SettingsConfigDict(
        env_prefix="GKS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    service_name: str = "graphrag-knowledge-service"
    service_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8080, ge=1, le=65535)
    allow_non_loopback_bind: bool = False
    service_token: SecretStr = Field(min_length=16)
    vault_allowed_roots: list[str] = Field(
        default_factory=lambda: ["/mnt/d/hack/MCP_Test_ObsidianVault"]
    )
    max_markdown_note_bytes: int = Field(default=20 * 1024 * 1024, ge=1024)
    scan_hash_block_bytes: int = Field(default=1024 * 1024, ge=4096, le=8 * 1024 * 1024)

    postgres_dsn: str = "postgresql+psycopg://graphrag:graphrag@127.0.0.1:5432/graphrag"
    database_pool_size: int = Field(default=5, ge=1, le=100)
    database_max_overflow: int = Field(default=5, ge=0, le=100)

    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_chunks_alias: str = "gks_chunks_active"

    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: SecretStr
    neo4j_database: str = "neo4j"

    generation_provider_enabled: bool = False
    generation_provider_url: str = "http://127.0.0.1:1234/v1"
    generation_provider_api_key: SecretStr | None = None
    generation_model: str = "qwen/qwen3.5-9b"
    generation_reasoning_effort: Literal["none", "low", "medium", "high"] = "none"
    generation_timeout_seconds: float = Field(default=180, gt=0, le=600)
    generation_max_tokens: int = Field(default=4096, ge=128, le=16384)
    extraction_max_chunks_per_job: int = Field(default=20, ge=1, le=100)
    embedding_provider_enabled: bool = False
    embedding_provider_url: str = "http://127.0.0.1:1234/v1"
    embedding_provider_api_key: SecretStr | None = None
    embedding_model: str = "text-embedding-bge-m3"
    embedding_timeout_seconds: float = Field(default=60, gt=0, le=600)
    embedding_batch_size: int = Field(default=16, ge=1, le=256)
    projection_batch_size: int = Field(default=16, ge=1, le=256)
    graph_projection_max_objects: int = Field(default=20000, ge=100, le=1000000)
    retrieval_candidate_limit: int = Field(default=40, ge=1, le=500)
    retrieval_max_limit: int = Field(default=50, ge=1, le=200)
    retrieval_rrf_k: int = Field(default=60, ge=1, le=1000)
    retrieval_entity_limit: int = Field(default=10, ge=1, le=50)
    retrieval_claim_limit: int = Field(default=20, ge=1, le=100)
    retrieval_graph_max_hops: int = Field(default=2, ge=1, le=4)
    retrieval_graph_max_paths: int = Field(default=20, ge=1, le=50)
    retrieval_document_context_max_documents: int = Field(default=1, ge=1, le=10)
    retrieval_document_context_max_chunks_per_document: int = Field(default=32, ge=1, le=100)
    retrieval_document_context_max_chars: int = Field(default=30000, ge=1000, le=200000)

    readiness_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    worker_id: str | None = None
    worker_poll_interval_seconds: float = Field(default=2.0, gt=0, le=60)
    worker_lease_seconds: int = Field(default=60, ge=10, le=3600)
    worker_heartbeat_seconds: int = Field(default=20, ge=1, le=1200)

    @field_validator("postgres_dsn")
    @classmethod
    def validate_postgres_dsn(cls, value: str) -> str:
        if not value.startswith(("postgresql+psycopg://", "postgresql+psycopg_async://")):
            raise ValueError("postgres_dsn must use the async psycopg SQLAlchemy driver")
        return value

    @field_validator(
        "qdrant_api_key",
        "generation_provider_api_key",
        "embedding_provider_api_key",
        mode="before",
    )
    @classmethod
    def blank_secret_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("qdrant_url", "generation_provider_url", "embedding_provider_url")
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("URL must use http or https")
        return value.rstrip("/")

    @field_validator("neo4j_uri")
    @classmethod
    def validate_neo4j_uri(cls, value: str) -> str:
        if not value.startswith(("bolt://", "neo4j://", "bolt+s://", "neo4j+s://")):
            raise ValueError("neo4j_uri must use a supported Neo4j driver scheme")
        return value

    @model_validator(mode="after")
    def validate_network_and_worker_timing(self) -> Settings:
        try:
            is_loopback = ip_address(self.api_host).is_loopback
        except ValueError:
            is_loopback = self.api_host == "localhost"
        if not is_loopback and not self.allow_non_loopback_bind:
            raise ValueError("non-loopback API binding requires GKS_ALLOW_NON_LOOPBACK_BIND=true")
        if self.worker_heartbeat_seconds >= self.worker_lease_seconds:
            raise ValueError("worker heartbeat interval must be shorter than the lease")
        return self

    def safe_summary(self) -> dict[str, str | int | bool]:
        """Return a deliberately small, secret-free summary for startup logs."""
        return {
            "service": self.service_name,
            "version": self.service_version,
            "environment": self.environment,
            "api_host": self.api_host,
            "api_port": self.api_port,
            "generation_provider_enabled": self.generation_provider_enabled,
            "generation_model": self.generation_model,
            "embedding_model": self.embedding_model,
            "embedding_provider_enabled": self.embedding_provider_enabled,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
