from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from graphrag_service.adapters.postgres.unit_of_work import SqlAlchemyUnitOfWork
from graphrag_service.api.schemas.operator import (
    OperatorChangeResponse,
    OperatorDocumentResponse,
    OperatorJobAcceptedResponse,
    OperatorJobResponse,
    OperatorOverviewResponse,
    OperatorPendingDocumentResponse,
    OperatorPendingRefreshResponse,
    OperatorPreviewResponse,
    OperatorVaultResponse,
    OperatorVectorProjectionResponse,
)

page_router = APIRouter(tags=["operator"])
api_router = APIRouter(prefix="/operator", tags=["operator"])
_DASHBOARD = Path(__file__).resolve().parents[1] / "static" / "operator.html"


@page_router.get("/operator", response_class=HTMLResponse, include_in_schema=False)
async def operator_page() -> HTMLResponse:
    return HTMLResponse(
        _DASHBOARD.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store"},
    )


@api_router.get("/overview", response_model=OperatorOverviewResponse)
async def operator_overview(request: Request) -> OperatorOverviewResponse:
    readiness, components = await request.app.state.readiness_service.check()
    vaults = await request.app.state.operator_store.vault_states()
    jobs = await request.app.state.operator_store.recent_jobs()
    expected_points = sum(item.chunk_count for item in vaults)
    try:
        profile = await request.app.state.projection_store.active_embedding_profile()
    except Exception:
        profile = None
    if profile is None:
        vector_projection = OperatorVectorProjectionResponse(
            status="rebuild_required",
            detail="Nincs aktív embedding-profil vagy vektorprojekció.",
            expected_collection=None,
            active_collection=None,
            expected_points=expected_points,
            actual_points=None,
            recovery_action="rebuild_vector_projection",
        )
    elif not request.app.state.settings.embedding_provider_enabled:
        vector_projection = OperatorVectorProjectionResponse(
            status="disabled",
            detail="Az embedding provider le van tiltva.",
            expected_collection=profile.physical_collection,
            active_collection=None,
            expected_points=expected_points,
            actual_points=None,
            recovery_action=None,
        )
    else:
        try:
            state = await request.app.state.vector_index.collection_state(
                alias=request.app.state.settings.qdrant_chunks_alias,
                expected_collection=profile.physical_collection,
            )
            healthy = (
                state.exists
                and state.collection == profile.physical_collection
                and state.point_count == expected_points
            )
            vector_projection = OperatorVectorProjectionResponse(
                status="ready" if healthy else "rebuild_required",
                detail=(
                    "A vektorprojekció egyezik a kanonikus PostgreSQL chunk-állománnyal."
                    if healthy
                    else "A Qdrant vektorprojekció hiányzik vagy eltér a PostgreSQL "
                    "aktuális chunk-állományától; a semantic retrieval nem megbízható."
                ),
                expected_collection=profile.physical_collection,
                active_collection=state.collection,
                expected_points=expected_points,
                actual_points=state.point_count,
                recovery_action=None if healthy else "rebuild_vector_projection",
            )
        except Exception:
            vector_projection = OperatorVectorProjectionResponse(
                status="unavailable",
                detail="A Qdrant vektorprojekció állapota nem ellenőrizhető.",
                expected_collection=profile.physical_collection,
                active_collection=None,
                expected_points=expected_points,
                actual_points=None,
                recovery_action=None,
            )
    return OperatorOverviewResponse(
        readiness=readiness,
        vector_projection=vector_projection,
        components={
            name: {
                "status": item.status,
                "required": item.required,
                "latency_ms": item.latency_ms,
                "detail": item.detail,
            }
            for name, item in components.items()
        },
        vaults=[
            OperatorVaultResponse.model_validate(item, from_attributes=True) for item in vaults
        ],
        recent_jobs=[
            OperatorJobResponse.model_validate(item, from_attributes=True) for item in jobs
        ],
    )


@api_router.post(
    "/vector-rebuild",
    response_model=OperatorJobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def operator_vector_rebuild(request: Request) -> OperatorJobAcceptedResponse:
    if not request.app.state.settings.embedding_provider_enabled:
        raise HTTPException(status_code=503, detail="Embedding provider is disabled.")
    async with SqlAlchemyUnitOfWork(request.app.state.session_factory) as uow:
        job_id = await uow.jobs.enqueue(
            "rebuild_vector_projection",
            {},
            max_attempts=3,
        )
    return OperatorJobAcceptedResponse(
        job_id=job_id,
        job_type="rebuild_vector_projection",
    )


@api_router.post(
    "/vaults/{vault_id}/graph-rebuild",
    response_model=OperatorJobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def operator_graph_rebuild(vault_id: UUID, request: Request) -> OperatorJobAcceptedResponse:
    if await request.app.state.ingest_store.get_vault(vault_id) is None:
        raise HTTPException(status_code=404, detail="Vault not found.")
    async with SqlAlchemyUnitOfWork(request.app.state.session_factory) as uow:
        job_id = await uow.jobs.enqueue(
            "rebuild_graph_projection",
            {"vault_id": str(vault_id)},
            max_attempts=3,
        )
    return OperatorJobAcceptedResponse(
        job_id=job_id,
        job_type="rebuild_graph_projection",
    )


@api_router.get(
    "/vaults/{vault_id}/pending-refresh",
    response_model=OperatorPendingRefreshResponse,
)
async def operator_pending_refresh(
    vault_id: UUID, request: Request
) -> OperatorPendingRefreshResponse:
    if await request.app.state.ingest_store.get_vault(vault_id) is None:
        raise HTTPException(status_code=404, detail="Vault not found.")
    pending = await request.app.state.operator_store.pending_refresh(vault_id)
    return OperatorPendingRefreshResponse(
        scan_id=pending.scan_id,
        scan_finished_at=pending.scan_finished_at,
        graph_refresh_required=pending.graph_refresh_required,
        documents=[
            OperatorPendingDocumentResponse.model_validate(item, from_attributes=True)
            for item in pending.documents
        ],
    )


@api_router.get(
    "/vaults/{vault_id}/preview",
    response_model=OperatorPreviewResponse,
)
async def operator_preview(vault_id: UUID, request: Request) -> OperatorPreviewResponse:
    try:
        result = await request.app.state.operator_preview.preview(vault_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Vault not found.") from exc
    return OperatorPreviewResponse(
        vault_id=vault_id,
        discovered=result.discovered_count,
        hashed=result.hashed_count,
        created=result.new_count,
        modified=result.modified_count,
        renamed=result.renamed_count,
        deleted=result.deleted_count,
        failed=result.failed_count,
        needs_refresh=bool(result.changes),
        changes=[
            OperatorChangeResponse(
                kind=item.kind.value,
                old_relative_path=item.old_relative_path,
                new_relative_path=item.new_relative_path,
                document_id=item.document_id,
                detail=item.detail,
            )
            for item in result.changes
        ],
        warnings=list(result.warnings),
    )


@api_router.get(
    "/vaults/{vault_id}/documents",
    response_model=list[OperatorDocumentResponse],
)
async def operator_documents(vault_id: UUID, request: Request) -> list[OperatorDocumentResponse]:
    if await request.app.state.ingest_store.get_vault(vault_id) is None:
        raise HTTPException(status_code=404, detail="Vault not found.")
    documents = await request.app.state.operator_store.documents(vault_id)
    return [
        OperatorDocumentResponse.model_validate(item, from_attributes=True) for item in documents
    ]
