from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from graphrag_service.api.schemas.graph import (
    EntityDetailResponse,
    EvidenceResponse,
    GraphPathRequest,
    GraphPathResponse,
    NeighborListResponse,
    NeighborResponse,
)
from graphrag_service.domain.ontology import ENTITY_TYPES, PREDICATES

router = APIRouter(tags=["graph"])


@router.get("/entities/{entity_id}", response_model=EntityDetailResponse)
async def entity_detail(entity_id: UUID, request: Request) -> EntityDetailResponse:
    detail = await request.app.state.graph_store.entity_detail(entity_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="entity not found")
    return EntityDetailResponse(
        id=detail.id,
        vault_id=detail.vault_id,
        canonical_name=detail.canonical_name,
        entity_type=detail.entity_type,
        entity_subtype=detail.entity_subtype,
        scope=detail.scope,
        status=detail.status,
        aliases=list(detail.aliases),
        identifiers=list(detail.identifiers),
        evidence=[
            EvidenceResponse(
                evidence_id=item.evidence_id,
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                relative_path=item.relative_path,
                quote=item.quote,
                char_start=item.char_start,
                char_end=item.char_end,
            )
            for item in detail.evidence
        ],
    )


@router.get(
    "/entities/{entity_id}/neighbors",
    response_model=NeighborListResponse,
)
async def entity_neighbors(
    entity_id: UUID,
    request: Request,
    predicate: str | None = None,
    entity_type: str | None = None,
    max_results: int = Query(default=20, ge=1, le=50),
    include_unreviewed: bool = True,
) -> NeighborListResponse:
    if predicate is not None and predicate not in PREDICATES:
        raise HTTPException(status_code=422, detail="predicate is not in the active ontology")
    if entity_type is not None and entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=422, detail="entity_type is not in the active ontology")
    rows = await request.app.state.graph_adapter.neighbors(
        entity_id=entity_id,
        predicate=predicate,
        entity_type=entity_type,
        max_results=max_results + 1,
        include_unreviewed=include_unreviewed,
    )
    return NeighborListResponse(
        entity_id=entity_id,
        neighbors=[NeighborResponse(**row) for row in rows[:max_results]],
        truncated=len(rows) > max_results,
    )


@router.post("/graph/path", response_model=GraphPathResponse)
async def graph_path(payload: GraphPathRequest, request: Request) -> GraphPathResponse:
    unknown = sorted(set(payload.predicate_allowlist) - set(PREDICATES))
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"predicate_allowlist contains unknown values: {', '.join(unknown)}",
        )
    rows = await request.app.state.graph_adapter.bounded_paths(
        from_entity_id=payload.from_entity_id,
        to_entity_id=payload.to_entity_id,
        max_hops=payload.max_hops,
        max_paths=payload.max_paths + 1,
        predicate_allowlist=tuple(payload.predicate_allowlist),
        include_unreviewed=payload.include_unreviewed,
    )
    return GraphPathResponse(
        paths=rows[: payload.max_paths],
        truncated=len(rows) > payload.max_paths,
    )
