from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from graphrag_service.adapters.postgres.unit_of_work import SqlAlchemyUnitOfWork
from graphrag_service.api.schemas.resolution import (
    ResolutionJobAcceptedResponse,
    ResolutionJobRequest,
)

router = APIRouter()


@router.post(
    "/resolution-jobs",
    response_model=ResolutionJobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["jobs", "graph"],
)
async def start_resolution_job(
    payload: ResolutionJobRequest,
    request: Request,
) -> ResolutionJobAcceptedResponse:
    vault = await request.app.state.ingest_store.get_vault(payload.vault_id)
    if vault is None:
        raise HTTPException(status_code=404, detail="Vault not found.")
    run_ids = tuple(dict.fromkeys(payload.extraction_run_ids))
    async with SqlAlchemyUnitOfWork(request.app.state.session_factory) as uow:
        job_id = await uow.jobs.enqueue(
            "resolve_and_project_graph",
            {
                "vault_id": str(payload.vault_id),
                "extraction_run_ids": [str(value) for value in run_ids],
            },
            max_attempts=3,
        )
    return ResolutionJobAcceptedResponse(job_id=job_id)
