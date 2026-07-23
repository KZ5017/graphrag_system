from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from graphrag_service.adapters.postgres.unit_of_work import SqlAlchemyUnitOfWork
from graphrag_service.api.schemas.extraction import (
    ExtractionJobAcceptedResponse,
    ExtractionJobRequest,
)

router = APIRouter()


@router.post(
    "/extraction-jobs",
    response_model=ExtractionJobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["jobs", "extraction"],
)
async def start_extraction_job(
    payload: ExtractionJobRequest,
    request: Request,
) -> ExtractionJobAcceptedResponse:
    settings = request.app.state.settings
    if not settings.generation_provider_enabled:
        raise HTTPException(status_code=503, detail="Generation provider is disabled.")
    if payload.max_chunks > settings.extraction_max_chunks_per_job:
        raise HTTPException(
            status_code=400,
            detail=(
                "max_chunks exceeds the configured extraction pilot limit "
                f"{settings.extraction_max_chunks_per_job}."
            ),
        )
    vault = await request.app.state.ingest_store.get_vault(payload.vault_id)
    if vault is None:
        raise HTTPException(status_code=404, detail="Vault not found.")
    document_ids = tuple(dict.fromkeys(payload.document_ids))
    async with SqlAlchemyUnitOfWork(request.app.state.session_factory) as uow:
        job_id = await uow.jobs.enqueue(
            "extract_knowledge_pilot",
            {
                "vault_id": str(payload.vault_id),
                "document_ids": [str(value) for value in document_ids],
                "max_chunks": payload.max_chunks,
            },
            max_attempts=3,
        )
    return ExtractionJobAcceptedResponse(job_id=job_id)
