from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from graphrag_service.adapters.postgres.document_queries import (
    get_document,
    get_sections,
    get_source,
)
from graphrag_service.api.schemas.documents import (
    DocumentResponse,
    SectionResponse,
    SourceResponse,
)

router = APIRouter()


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    tags=["documents"],
)
async def document_detail(document_id: UUID, request: Request) -> DocumentResponse:
    document = await get_document(request.app.state.session_factory, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentResponse(**asdict(document))


@router.get(
    "/documents/{document_id}/sections",
    response_model=list[SectionResponse],
    tags=["documents"],
)
async def document_sections(document_id: UUID, request: Request) -> list[SectionResponse]:
    sections = await get_sections(request.app.state.session_factory, document_id)
    if sections is None:
        raise HTTPException(status_code=404, detail="Current document not found.")
    return [
        SectionResponse(
            id=item.id,
            parent_section_id=item.parent_section_id,
            heading_level=item.heading_level,
            heading_text=item.heading_text,
            heading_path=item.heading_path,
            heading_occurrence=item.heading_occurrence,
            char_start=item.char_start,
            char_end=item.char_end,
            ordinal=item.ordinal,
        )
        for item in sections
    ]


@router.get("/sources/{source_id}", response_model=SourceResponse, tags=["sources"])
async def source_detail(source_id: UUID, request: Request) -> SourceResponse:
    source = await get_source(request.app.state.session_factory, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Current source not found.")
    return SourceResponse(
        source_id=source.source_id,
        vault_id=source.vault_id,
        document_id=source.document_id,
        document_version_id=source.document_version_id,
        section_id=source.section_id,
        relative_path=source.relative_path,
        heading_path=source.heading_path,
        quote=source.quote,
        char_start=source.char_start,
        char_end=source.char_end,
        content_hash=source.content_hash,
        source_uri=source.source_uri,
        obsidian_uri=source.obsidian_uri,
    )
