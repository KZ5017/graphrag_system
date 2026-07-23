from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from graphrag_service.adapters.postgres.extraction_store import ExtractionStore
from graphrag_service.adapters.providers.lmstudio_generation import (
    LMStudioGenerationProvider,
)
from graphrag_service.application.extraction import KnowledgeExtractionService
from graphrag_service.config import Settings
from graphrag_service.domain.jobs import ClaimedJob
from graphrag_service.workers.runner import JobHandler


def build_extraction_handlers(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[dict[str, JobHandler], LMStudioGenerationProvider | None]:
    if not settings.generation_provider_enabled:
        return {}, None
    provider = LMStudioGenerationProvider(
        base_url=settings.generation_provider_url,
        model=settings.generation_model,
        api_key=(
            settings.generation_provider_api_key.get_secret_value()
            if settings.generation_provider_api_key
            else None
        ),
        timeout_seconds=settings.generation_timeout_seconds,
        max_tokens=settings.generation_max_tokens,
        reasoning_effort=settings.generation_reasoning_effort,
    )
    service = KnowledgeExtractionService(
        store=ExtractionStore(session_factory),
        provider=provider,
        max_chunks_per_job=settings.extraction_max_chunks_per_job,
    )

    async def extract_knowledge_pilot(job: ClaimedJob) -> dict[str, object]:
        raw_document_ids = job.payload.get("document_ids")
        if not isinstance(raw_document_ids, list) or not raw_document_ids:
            raise ValueError("extraction pilot requires explicit document_ids")
        outcome = await service.run_pilot(
            job_id=job.id,
            vault_id=UUID(str(job.payload["vault_id"])),
            document_ids=tuple(UUID(str(value)) for value in raw_document_ids),
            max_chunks=int(job.payload.get("max_chunks", 6)),
        )
        return {
            "extraction_run_id": str(outcome.run_id),
            "status": outcome.status,
            "processed_chunks": outcome.processed_chunks,
            "valid_candidates": outcome.valid_candidates,
            "invalid_candidates": outcome.invalid_candidates,
            "prompt_tokens": outcome.prompt_tokens,
            "completion_tokens": outcome.completion_tokens,
        }

    return {"extract_knowledge_pilot": extract_knowledge_pilot}, provider
