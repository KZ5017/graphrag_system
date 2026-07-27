from __future__ import annotations

import re
from dataclasses import replace
from hashlib import sha256
from time import perf_counter
from typing import Any
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from graphrag_service.adapters.postgres.ingest_models import (
    ChunkModel,
    DocumentModel,
    DocumentVersionModel,
    SectionModel,
    VaultModel,
)
from graphrag_service.adapters.postgres.projection_models import RetrievalQueryRunModel
from graphrag_service.domain.retrieval import RetrievalChunk, RetrievalWarning

LEXICAL_STOP_WORDS = {
    "a",
    "az",
    "egy",
    "és",
    "vagy",
    "hogy",
    "hogyan",
    "hol",
    "mi",
    "mikor",
    "milyen",
    "lehet",
    "kell",
    "van",
    "vannak",
    "be",
    "ki",
    "fel",
    "le",
    "meg",
    "the",
    "and",
    "or",
    "how",
}


class RetrievalStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def keyword_search(
        self,
        query: str,
        *,
        limit: int,
        vault_id: UUID | None,
    ) -> list[RetrievalChunk]:
        terms = [
            term
            for term in dict.fromkeys(re.findall(r"[a-záéíóöőúüű0-9]+", query.casefold()))
            if len(term) > 1 and term not in LEXICAL_STOP_WORDS
        ]
        expression = " OR ".join(terms) if terms else query
        ts_query = func.websearch_to_tsquery("simple", expression)
        rank = func.ts_rank_cd(ChunkModel.search_vector, ts_query)
        statement = (
            self._current_chunk_query(rank.label("score"))
            .where(ChunkModel.search_vector.op("@@")(ts_query))
            .order_by(rank.desc(), ChunkModel.id)
            .limit(limit)
        )
        if vault_id is not None:
            statement = statement.where(DocumentModel.vault_id == vault_id)
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return [replace(self._to_chunk(row), keyword_score=float(row.score)) for row in rows]

    async def hydrate_current(
        self,
        chunk_ids: list[UUID],
    ) -> dict[UUID, RetrievalChunk]:
        if not chunk_ids:
            return {}
        statement = self._current_chunk_query().where(ChunkModel.id.in_(chunk_ids))
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return {row[0].id: self._to_chunk(row) for row in rows}

    async def section_context(
        self,
        seed_ids: list[UUID],
        *,
        neighbor_window: int = 1,
    ) -> list[RetrievalChunk]:
        if not seed_ids or neighbor_window < 1:
            return []
        async with self._sessions() as session:
            seeds = (
                await session.execute(
                    select(ChunkModel.id, ChunkModel.section_id, ChunkModel.ordinal).where(
                        ChunkModel.id.in_(seed_ids)
                    )
                )
            ).all()
            conditions = [
                and_(
                    ChunkModel.section_id == seed.section_id,
                    ChunkModel.ordinal.between(
                        seed.ordinal - neighbor_window, seed.ordinal + neighbor_window
                    ),
                )
                for seed in seeds
            ]
            if not conditions:
                return []
            rows = (
                await session.execute(
                    self._current_chunk_query()
                    .where(
                        or_(*conditions),
                        ChunkModel.id.not_in(seed_ids),
                        ChunkModel.retrieval_role == "content_evidence",
                    )
                    .order_by(ChunkModel.section_id, ChunkModel.ordinal, ChunkModel.id)
                    .limit(len(seed_ids) * neighbor_window * 2)
                )
            ).all()
        return [self._to_chunk(row) for row in rows]

    async def document_context(
        self,
        seed_ids: list[UUID],
        *,
        max_documents: int,
        max_chunks_per_document: int,
        max_total_chars: int,
        whole_documents: bool = False,
    ) -> tuple[list[RetrievalChunk], bool]:
        """Hydrate bounded content evidence from accepted sections or documents."""
        if not seed_ids or max_documents < 1 or max_chunks_per_document < 1 or max_total_chars < 1:
            return [], False

        async with self._sessions() as session:
            seed_rows = (
                await session.execute(
                    self._current_chunk_query().where(ChunkModel.id.in_(seed_ids))
                )
            ).all()
            seeds_by_id = {row[0].id: row for row in seed_rows}
            document_ranges: dict[UUID, list[tuple[int, int]]] = {}
            version_by_document: dict[UUID, UUID] = {}
            for seed_id in seed_ids:
                row = seeds_by_id.get(seed_id)
                if row is None:
                    continue
                _, section, version, document, _ = row[:5]
                document_ranges.setdefault(document.id, []).append(
                    (section.char_start, section.char_end)
                )
                version_by_document[document.id] = version.id

            selected_documents = list(document_ranges)[:max_documents]
            truncated = len(document_ranges) > max_documents
            result: list[RetrievalChunk] = []
            result_ids: set[UUID] = set(seed_ids)
            total_chars = 0

            for document_id in selected_documents:
                ranges = document_ranges[document_id]
                conditions = [
                    and_(
                        ChunkModel.char_start >= char_start,
                        ChunkModel.char_end <= char_end,
                    )
                    for char_start, char_end in ranges
                ]
                if whole_documents:
                    conditions = [DocumentVersionModel.id == version_by_document[document_id]]
                rows = (
                    await session.execute(
                        self._current_chunk_query()
                        .where(
                            DocumentVersionModel.id == version_by_document[document_id],
                            or_(*conditions),
                            ChunkModel.id.not_in(seed_ids),
                            ChunkModel.retrieval_role == "content_evidence",
                        )
                        .order_by(ChunkModel.ordinal, ChunkModel.id)
                        .limit(max_chunks_per_document + 1)
                    )
                ).all()
                if len(rows) > max_chunks_per_document:
                    truncated = True
                for row in rows[:max_chunks_per_document]:
                    chunk = self._to_chunk(row)
                    if chunk.chunk_id in result_ids:
                        continue
                    chunk_chars = len(chunk.text)
                    if total_chars + chunk_chars > max_total_chars:
                        truncated = True
                        return result, truncated
                    result.append(chunk)
                    result_ids.add(chunk.chunk_id)
                    total_chars += chunk_chars

        return result, truncated

    async def record_query(
        self,
        *,
        query: str,
        strategy: str,
        status: str,
        result_count: int,
        started_at: float,
        model_profile_id: UUID | None,
        request: dict[str, Any],
        warnings: tuple[RetrievalWarning, ...],
    ) -> UUID:
        run = RetrievalQueryRunModel(
            query_sha256=sha256(query.encode("utf-8")).hexdigest(),
            strategy=strategy,
            status=status,
            result_count=result_count,
            latency_ms=max(0, round((perf_counter() - started_at) * 1000)),
            model_profile_id=model_profile_id,
            request_json=request,
            warnings_json=[
                {"code": warning.code, "message": warning.message} for warning in warnings
            ],
        )
        async with self._sessions.begin() as session:
            session.add(run)
            await session.flush()
        return run.id

    @staticmethod
    def _current_chunk_query(*extra_columns: Any):
        return (
            select(
                ChunkModel,
                SectionModel,
                DocumentVersionModel,
                DocumentModel,
                VaultModel,
                *extra_columns,
            )
            .join(SectionModel, SectionModel.id == ChunkModel.section_id)
            .join(
                DocumentVersionModel,
                DocumentVersionModel.id == ChunkModel.document_version_id,
            )
            .join(DocumentModel, DocumentModel.id == DocumentVersionModel.document_id)
            .join(VaultModel, VaultModel.id == DocumentModel.vault_id)
            .where(
                DocumentModel.current_version_id == DocumentVersionModel.id,
                DocumentModel.lifecycle_status == "active",
                DocumentVersionModel.processing_status == "ready",
            )
        )

    @staticmethod
    def _to_chunk(row: Any) -> RetrievalChunk:
        chunk, section, version, document, vault = row[:5]
        source_uri = (
            f"{vault.internal_uri_prefix.rstrip('/')}/"
            f"{quote(document.current_relative_path, safe='/')}"
            f"#chars={chunk.char_start},{chunk.char_end}"
        )
        obsidian_uri = None
        if vault.obsidian_uri_template:
            obsidian_uri = vault.obsidian_uri_template.format(
                path=quote(document.current_relative_path, safe="/"),
                vault=quote(vault.name),
            )
        return RetrievalChunk(
            chunk_id=chunk.id,
            vault_id=vault.id,
            document_id=document.id,
            document_version_id=version.id,
            section_id=section.id,
            relative_path=document.current_relative_path,
            heading_path=tuple(section.heading_path_json),
            text=chunk.text,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            content_sha256=chunk.content_sha256,
            source_uri=source_uri,
            obsidian_uri=obsidian_uri,
            retrieval_role=chunk.retrieval_role,
        )
