from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from graphrag_service.adapters.postgres.ingest_models import (
    ChunkModel,
    DocumentModel,
    DocumentVersionModel,
    SectionModel,
    VaultModel,
)


@dataclass(frozen=True, slots=True)
class DocumentView:
    id: UUID
    vault_id: UUID
    relative_path: str
    title: str | None
    lifecycle_status: str
    current_version_id: UUID | None
    content_sha256: str | None
    frontmatter: dict[str, Any]
    quality_flags: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class SectionView:
    id: UUID
    parent_section_id: UUID | None
    heading_level: int
    heading_text: str
    heading_path: list[str]
    heading_occurrence: int
    char_start: int
    char_end: int
    ordinal: int


@dataclass(frozen=True, slots=True)
class SourceView:
    source_id: UUID
    vault_id: UUID
    document_id: UUID
    document_version_id: UUID
    section_id: UUID
    relative_path: str
    heading_path: list[str]
    quote: str
    char_start: int
    char_end: int
    content_hash: str
    source_uri: str
    obsidian_uri: str | None


async def get_document(
    sessions: async_sessionmaker[AsyncSession], document_id: UUID
) -> DocumentView | None:
    async with sessions() as session:
        row = (
            await session.execute(
                select(DocumentModel, DocumentVersionModel)
                .outerjoin(
                    DocumentVersionModel,
                    DocumentVersionModel.id == DocumentModel.current_version_id,
                )
                .where(DocumentModel.id == document_id)
            )
        ).one_or_none()
    if row is None:
        return None
    document, version = row
    return DocumentView(
        id=document.id,
        vault_id=document.vault_id,
        relative_path=document.current_relative_path,
        title=document.title,
        lifecycle_status=document.lifecycle_status,
        current_version_id=document.current_version_id,
        content_sha256=version.content_sha256 if version else None,
        frontmatter=dict(version.frontmatter_json) if version else {},
        quality_flags=list(version.quality_flags_json) if version else [],
    )


async def get_sections(
    sessions: async_sessionmaker[AsyncSession], document_id: UUID
) -> tuple[SectionView, ...] | None:
    async with sessions() as session:
        current_version_id = await session.scalar(
            select(DocumentModel.current_version_id).where(
                DocumentModel.id == document_id,
                DocumentModel.lifecycle_status == "active",
            )
        )
        if current_version_id is None:
            return None
        models = (
            await session.scalars(
                select(SectionModel)
                .where(SectionModel.document_version_id == current_version_id)
                .order_by(SectionModel.ordinal)
            )
        ).all()
    return tuple(
        SectionView(
            id=item.id,
            parent_section_id=item.parent_section_id,
            heading_level=item.heading_level,
            heading_text=item.heading_text,
            heading_path=list(item.heading_path_json),
            heading_occurrence=item.heading_occurrence,
            char_start=item.char_start,
            char_end=item.char_end,
            ordinal=item.ordinal,
        )
        for item in models
    )


async def get_source(
    sessions: async_sessionmaker[AsyncSession], source_id: UUID
) -> SourceView | None:
    async with sessions() as session:
        row = (
            await session.execute(
                select(
                    ChunkModel,
                    SectionModel,
                    DocumentVersionModel,
                    DocumentModel,
                    VaultModel,
                )
                .join(SectionModel, SectionModel.id == ChunkModel.section_id)
                .join(
                    DocumentVersionModel,
                    DocumentVersionModel.id == ChunkModel.document_version_id,
                )
                .join(
                    DocumentModel,
                    DocumentModel.id == DocumentVersionModel.document_id,
                )
                .join(VaultModel, VaultModel.id == DocumentModel.vault_id)
                .where(
                    ChunkModel.id == source_id,
                    DocumentModel.current_version_id == ChunkModel.document_version_id,
                    DocumentModel.lifecycle_status == "active",
                )
            )
        ).one_or_none()
    if row is None:
        return None
    chunk, section, version, document, vault = row
    obsidian_uri = None
    if vault.obsidian_uri_template:
        obsidian_uri = vault.obsidian_uri_template.format(
            relative_path=document.current_relative_path
        )
    return SourceView(
        source_id=chunk.id,
        vault_id=vault.id,
        document_id=document.id,
        document_version_id=version.id,
        section_id=section.id,
        relative_path=document.current_relative_path,
        heading_path=list(section.heading_path_json),
        quote=chunk.text,
        char_start=chunk.char_start,
        char_end=chunk.char_end,
        content_hash=chunk.content_sha256,
        source_uri=f"{vault.internal_uri_prefix}{document.current_relative_path}",
        obsidian_uri=obsidian_uri,
    )
