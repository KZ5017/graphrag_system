from __future__ import annotations

import httpx
from neo4j import AsyncGraphDatabase
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from graphrag_service.adapters.postgres.migrations import ALEMBIC_HEAD_REVISION
from graphrag_service.application.readiness import ComponentCheck, ReadinessService
from graphrag_service.config import Settings


def build_readiness_service(settings: Settings, engine: AsyncEngine) -> ReadinessService:
    async def check_postgres() -> str:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        if revision != ALEMBIC_HEAD_REVISION:
            raise RuntimeError("database migration is not at application head")
        return f"migration:{revision}"

    async def check_job_queue() -> str:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT id FROM jobs LIMIT 1"))
        return "available"

    async def check_qdrant() -> str:
        headers: dict[str, str] = {}
        if settings.qdrant_api_key is not None:
            headers["api-key"] = settings.qdrant_api_key.get_secret_value()
        async with httpx.AsyncClient(
            base_url=settings.qdrant_url,
            headers=headers,
            timeout=settings.readiness_timeout_seconds,
        ) as client:
            response = await client.get("/collections")
            response.raise_for_status()
        return "available"

    async def check_neo4j() -> str:
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(
                settings.neo4j_username,
                settings.neo4j_password.get_secret_value(),
            ),
        )
        try:
            await driver.verify_connectivity()
            async with driver.session(database=settings.neo4j_database) as session:
                result = await session.run(
                    "SHOW CONSTRAINTS YIELD name RETURN collect(name) AS names"
                )
                record = await result.single()
                names = set(record["names"] if record is not None else [])
                required = {
                    "gks_vault_id",
                    "gks_document_id",
                    "gks_documentversion_id",
                    "gks_section_id",
                    "gks_chunk_id",
                    "gks_entity_id",
                    "gks_relationshipassertion_id",
                    "gks_claim_id",
                    "gks_evidence_id",
                }
                if required - names:
                    raise RuntimeError("Neo4j graph constraints are missing")
        finally:
            await driver.close()
        return "available:schema"

    async def check_generation_provider() -> str:
        if not settings.generation_provider_enabled:
            return "disabled"
        headers: dict[str, str] = {}
        if settings.generation_provider_api_key is not None:
            headers["Authorization"] = (
                f"Bearer {settings.generation_provider_api_key.get_secret_value()}"
            )
        async with httpx.AsyncClient(
            base_url=settings.generation_provider_url,
            headers=headers,
            timeout=settings.readiness_timeout_seconds,
        ) as client:
            response = await client.get("/models")
            response.raise_for_status()
        models = {str(item.get("id")) for item in response.json().get("data", [])}
        if settings.generation_model not in models:
            raise RuntimeError("configured generation model is not loaded")
        return f"available:{settings.generation_model}"

    async def check_embedding_provider() -> str:
        if not settings.embedding_provider_enabled:
            return "disabled"
        headers: dict[str, str] = {}
        if settings.embedding_provider_api_key is not None:
            headers["Authorization"] = (
                f"Bearer {settings.embedding_provider_api_key.get_secret_value()}"
            )
        async with httpx.AsyncClient(
            base_url=settings.embedding_provider_url,
            headers=headers,
            timeout=settings.readiness_timeout_seconds,
        ) as client:
            response = await client.get("/models")
            response.raise_for_status()
        models = {str(item.get("id")) for item in response.json().get("data", [])}
        if settings.embedding_model not in models:
            raise RuntimeError("configured embedding model is not loaded")
        return f"available:{settings.embedding_model}"

    return ReadinessService(
        checks=[
            ComponentCheck(name="postgresql", required=True, check=check_postgres),
            ComponentCheck(name="job_queue", required=True, check=check_job_queue),
            ComponentCheck(name="qdrant", required=True, check=check_qdrant),
            ComponentCheck(name="neo4j", required=True, check=check_neo4j),
            ComponentCheck(
                name="generation_provider",
                required=False,
                check=check_generation_provider,
            ),
            ComponentCheck(
                name="embedding_provider",
                required=False,
                check=check_embedding_provider,
            ),
        ],
        timeout_seconds=settings.readiness_timeout_seconds,
    )
