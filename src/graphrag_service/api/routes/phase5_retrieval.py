from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from graphrag_service.adapters.postgres.unit_of_work import SqlAlchemyUnitOfWork
from graphrag_service.api.schemas.phase5_retrieval import (
    RetrievalChunkResponse,
    RetrievalClaimResponse,
    RetrievalEntityResponse,
    RetrievalPathResponse,
    RetrievalRelationshipResponse,
    RetrievalScores,
    RetrievalSource,
    RetrievalWarningResponse,
    RetrieveResponse,
)
from graphrag_service.api.schemas.retrieval import (
    IndexJobAcceptedResponse,
    IndexJobRequest,
    RetrieveRequest,
)
from graphrag_service.domain.retrieval import RetrievalChunk

router = APIRouter()


@router.post(
    "/index-jobs",
    response_model=IndexJobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["jobs", "retrieval"],
)
async def start_index_job(
    payload: IndexJobRequest,
    request: Request,
) -> IndexJobAcceptedResponse:
    if not request.app.state.settings.embedding_provider_enabled:
        raise HTTPException(
            status_code=503,
            detail="Embedding provider is disabled.",
        )
    if payload.vault_id is not None:
        vault = await request.app.state.ingest_store.get_vault(payload.vault_id)
        if vault is None:
            raise HTTPException(status_code=404, detail="Vault not found.")
    async with SqlAlchemyUnitOfWork(request.app.state.session_factory) as uow:
        job_id = await uow.jobs.enqueue(
            "project_chunks",
            {"vault_id": str(payload.vault_id) if payload.vault_id else None},
            max_attempts=10,
        )
    return IndexJobAcceptedResponse(job_id=job_id)


@router.post(
    "/retrieve",
    response_model=RetrieveResponse,
    tags=["retrieval"],
)
async def retrieve(payload: RetrieveRequest, request: Request) -> RetrieveResponse:
    try:
        result = await request.app.state.retrieval_service.retrieve(
            payload.query,
            strategy=payload.strategy,
            limit=payload.limit,
            vault_id=payload.vault_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    chunks = [_chunk_response(item) for item in result.chunks]
    context_chunks = [_chunk_response(item, include_scores=False) for item in result.context_chunks]
    source_map = {item.source.source_id: item.source for item in [*chunks, *context_chunks]}
    return RetrieveResponse(
        query_id=result.query_id,
        query_type=result.query_type,
        retrieval_plan=list(result.retrieval_plan),
        planner_reason_code=result.planner_reason_code,
        strategy=result.strategy,
        chunks=chunks,
        context_chunks=context_chunks,
        entities=[
            RetrievalEntityResponse(
                entity_id=item.entity_id,
                vault_id=item.vault_id,
                canonical_name=item.canonical_name,
                entity_type=item.entity_type,
                entity_subtype=item.entity_subtype,
                scope=item.scope,
                score=item.score,
                seed_channels=list(item.seed_channels),
                source_chunk_ids=list(item.source_chunk_ids),
            )
            for item in result.entities
        ],
        relationships=[
            RetrievalRelationshipResponse(
                assertion_id=item.assertion_id,
                subject_entity_id=item.subject_entity_id,
                object_entity_id=item.object_entity_id,
                predicate=item.predicate,
                assertion_kind=item.assertion_kind,
                review_status=item.review_status,
                evidence_id=item.evidence_id,
                source_chunk_id=item.source_chunk_id,
                quote=item.quote,
                char_start=item.char_start,
                char_end=item.char_end,
            )
            for item in result.relationships
        ],
        claims=[
            RetrievalClaimResponse(
                claim_id=item.claim_id,
                text=item.text,
                assertion_kind=item.assertion_kind,
                review_status=item.review_status,
                evidence_id=item.evidence_id,
                source_chunk_id=item.source_chunk_id,
                quote=item.quote,
                char_start=item.char_start,
                char_end=item.char_end,
                score=item.score,
                seed_channels=list(item.seed_channels),
            )
            for item in result.claims
        ],
        retrieval_paths=[
            RetrievalPathResponse(
                entity_ids=list(item.entity_ids),
                assertion_ids=list(item.assertion_ids),
                source_chunk_ids=list(item.source_chunk_ids),
                hops=item.hops,
            )
            for item in result.retrieval_paths
        ],
        sources=list(source_map.values()),
        warnings=[
            RetrievalWarningResponse(code=item.code, message=item.message)
            for item in result.warnings
        ],
        truncated=result.truncated,
    )


def _chunk_response(
    item: RetrievalChunk,
    *,
    include_scores: bool = True,
) -> RetrievalChunkResponse:
    source = RetrievalSource(
        source_id=item.chunk_id,
        vault_id=item.vault_id,
        document_id=item.document_id,
        document_version_id=item.document_version_id,
        section_id=item.section_id,
        relative_path=item.relative_path,
        heading_path=list(item.heading_path),
        quote=item.text,
        char_start=item.char_start,
        char_end=item.char_end,
        content_sha256=item.content_sha256,
        source_uri=item.source_uri,
        obsidian_uri=item.obsidian_uri,
    )
    return RetrievalChunkResponse(
        chunk_id=item.chunk_id,
        text=item.text,
        scores=RetrievalScores(
            keyword=item.keyword_score if include_scores else None,
            semantic=item.semantic_score if include_scores else None,
            graph=item.graph_score if include_scores else None,
            claim=item.claim_score if include_scores else None,
            fusion=item.fusion_score if include_scores else None,
        ),
        source=source,
    )
