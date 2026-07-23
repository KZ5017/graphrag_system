from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from graphrag_service.adapters.postgres.unit_of_work import SqlAlchemyUnitOfWork
from graphrag_service.api.schemas.retrieval import (
    IndexJobAcceptedResponse,
    IndexJobRequest,
    RetrievalChunkResponse,
    RetrievalScores,
    RetrievalSource,
    RetrievalWarningResponse,
    RetrieveRequest,
    RetrieveResponse,
)

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

    chunks: list[RetrievalChunkResponse] = []
    sources: list[RetrievalSource] = []
    for item in result.chunks:
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
        sources.append(source)
        chunks.append(
            RetrievalChunkResponse(
                chunk_id=item.chunk_id,
                text=item.text,
                scores=RetrievalScores(
                    keyword=item.keyword_score,
                    semantic=item.semantic_score,
                    fusion=item.fusion_score,
                ),
                source=source,
            )
        )
    context_chunks: list[RetrievalChunkResponse] = []
    for item in result.context_chunks:
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
        sources.append(source)
        context_chunks.append(
            RetrievalChunkResponse(
                chunk_id=item.chunk_id,
                text=item.text,
                scores=RetrievalScores(keyword=None, semantic=None, fusion=None),
                source=source,
            )
        )
    return RetrieveResponse(
        query_id=result.query_id,
        retrieval_plan=[result.strategy],
        strategy=result.strategy,
        chunks=chunks,
        context_chunks=context_chunks,
        sources=sources,
        warnings=[
            RetrievalWarningResponse(code=item.code, message=item.message)
            for item in result.warnings
        ],
        truncated=result.truncated,
    )
