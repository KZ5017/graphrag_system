from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError

from graphrag_service.adapters.postgres.job_queries import get_job
from graphrag_service.adapters.postgres.unit_of_work import SqlAlchemyUnitOfWork
from graphrag_service.api.schemas.vaults import (
    JobResponse,
    ScanAcceptedResponse,
    ScanRequest,
    VaultCreateRequest,
    VaultResponse,
)
from graphrag_service.domain.vault import PathCaseMode
from graphrag_service.ports.ingest_store import VaultRegistration

router = APIRouter()


def _vault_response(vault) -> VaultResponse:
    return VaultResponse(
        id=vault.id,
        name=vault.name,
        root_path=vault.root_path,
        path_case_mode=vault.path_case_mode.value,
        include_globs=list(vault.include_globs),
        exclude_globs=list(vault.exclude_globs),
    )


@router.post(
    "/vaults",
    response_model=VaultResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["vaults"],
)
async def create_vault(payload: VaultCreateRequest, request: Request) -> VaultResponse:
    registration = VaultRegistration(
        name=payload.name,
        root_path=payload.root_path,
        path_case_mode=PathCaseMode(payload.path_case_mode),
        include_globs=tuple(payload.include_globs),
        exclude_globs=tuple(payload.exclude_globs),
        obsidian_uri_template=payload.obsidian_uri_template,
    )
    try:
        vault = await request.app.state.ingest_service.register_vault(registration)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Vault already registered.") from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _vault_response(vault)


@router.get("/vaults", response_model=list[VaultResponse], tags=["vaults"])
async def list_vaults(request: Request) -> list[VaultResponse]:
    vaults = await request.app.state.ingest_store.list_vaults()
    return [_vault_response(vault) for vault in vaults]


@router.get("/vaults/{vault_id}", response_model=VaultResponse, tags=["vaults"])
async def get_vault(vault_id: UUID, request: Request) -> VaultResponse:
    vault = await request.app.state.ingest_store.get_vault(vault_id)
    if vault is None:
        raise HTTPException(status_code=404, detail="Vault not found.")
    return _vault_response(vault)


@router.post(
    "/vaults/{vault_id}/scans",
    response_model=ScanAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["vaults", "jobs"],
)
async def start_scan(
    vault_id: UUID, payload: ScanRequest, request: Request
) -> ScanAcceptedResponse:
    vault = await request.app.state.ingest_store.get_vault(vault_id)
    if vault is None:
        raise HTTPException(status_code=404, detail="Vault not found.")
    async with SqlAlchemyUnitOfWork(request.app.state.session_factory) as uow:
        job_id = await uow.jobs.enqueue(
            "scan_vault",
            {"vault_id": str(vault_id), "scan_type": payload.scan_type},
            max_attempts=3,
        )
    return ScanAcceptedResponse(job_id=job_id)


@router.get("/jobs/{job_id}", response_model=JobResponse, tags=["jobs"])
async def job_status(job_id: UUID, request: Request) -> JobResponse:
    job = await get_job(request.app.state.session_factory, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JobResponse(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        progress_current=job.progress_current,
        progress_total=job.progress_total,
        checkpoint=job.checkpoint,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
