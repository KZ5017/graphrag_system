from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from graphrag_service.api.schemas.health import (
    ComponentReadiness,
    HealthResponse,
    ReadinessResponse,
)

router = APIRouter(tags=["service"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.service_version,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def ready(request: Request, response: Response) -> ReadinessResponse:
    readiness_status, results = await request.app.state.readiness_service.check()
    if readiness_status == "not_ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    settings = request.app.state.settings
    return ReadinessResponse(
        status=readiness_status,
        service=settings.service_name,
        version=settings.service_version,
        components={
            name: ComponentReadiness(
                status=result.status,
                required=result.required,
                latency_ms=result.latency_ms,
                detail=result.detail,
            )
            for name, result in results.items()
        },
    )
