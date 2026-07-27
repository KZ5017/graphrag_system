from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from graphrag_service.adapters.markdown.parser import PARSER_NAME, PARSER_VERSION
from graphrag_service.adapters.postgres.ingest_models import (
    ChunkModel,
    ContentBlockModel,
    DocumentLinkModel,
    DocumentModel,
    DocumentVersionModel,
    ScanChangeModel,
    ScanRunModel,
    SectionModel,
    VaultFileStateModel,
    VaultModel,
)
from graphrag_service.application.chunker import CHUNKER_NAME, CHUNKER_VERSION
from graphrag_service.application.scanner import VaultScanner
from graphrag_service.domain.markdown import ParsedChunk, ParsedDocument
from graphrag_service.domain.vault import (
    FileSnapshot,
    PathCaseMode,
    ScanChangeKind,
    ScanResult,
    ScanType,
    VaultDefinition,
)
from graphrag_service.ports.ingest_store import (
    DocumentToParse,
    StoredScan,
    VaultRegistration,
)


class PostgresIngestStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def register_vault(self, registration: VaultRegistration) -> VaultDefinition:
        vault_id = uuid4()
        model = VaultModel(
            id=vault_id,
            name=registration.name,
            root_path=registration.root_path,
            path_case_mode=registration.path_case_mode.value,
            include_globs=list(registration.include_globs),
            exclude_globs=list(registration.exclude_globs),
            internal_uri_prefix=f"vault://{vault_id}/",
            obsidian_uri_template=registration.obsidian_uri_template,
            status="active",
        )
        async with self._session_factory.begin() as session:
            session.add(model)
        return self._definition(model)

    async def list_vaults(self) -> tuple[VaultDefinition, ...]:
        async with self._session_factory() as session:
            models = (
                await session.scalars(
                    select(VaultModel)
                    .where(VaultModel.status == "active")
                    .order_by(VaultModel.name)
                )
            ).all()
        return tuple(self._definition(model) for model in models)

    async def get_vault(self, vault_id: UUID) -> VaultDefinition | None:
        async with self._session_factory() as session:
            model = await session.get(VaultModel, vault_id)
        return self._definition(model) if model else None

    async def load_file_states(self, vault_id: UUID) -> tuple[FileSnapshot, ...]:
        async with self._session_factory() as session:
            models = (
                await session.scalars(
                    select(VaultFileStateModel).where(VaultFileStateModel.vault_id == vault_id)
                )
            ).all()
        return tuple(
            FileSnapshot(
                relative_path=model.relative_path,
                relative_path_key=model.relative_path_key,
                size_bytes=model.size_bytes,
                mtime_ns=model.mtime_ns,
                content_sha256=model.content_sha256,
                document_id=model.document_id,
            )
            for model in models
        )

    async def begin_scan(self, vault_id: UUID, scan_type: ScanType) -> UUID:
        scan_id = uuid4()
        async with self._session_factory.begin() as session:
            session.add(
                ScanRunModel(
                    id=scan_id,
                    vault_id=vault_id,
                    status="running",
                    scan_type=scan_type.value,
                    scanner_version=VaultScanner.VERSION,
                )
            )
        return scan_id

    async def apply_scan(
        self,
        scan_id: UUID,
        vault: VaultDefinition,
        scan_type: ScanType,
        result: ScanResult,
    ) -> StoredScan:
        async with self._session_factory.begin() as session:
            scan = await session.get(ScanRunModel, scan_id, with_for_update=True)
            if scan is None:
                raise LookupError("scan not found")
            self._set_scan_counts(scan, result)
            if scan_type is ScanType.MEASURE:
                return StoredScan(scan_id=scan_id, documents_to_parse=())

            state_models = (
                await session.scalars(
                    select(VaultFileStateModel)
                    .where(VaultFileStateModel.vault_id == vault.id)
                    .with_for_update()
                )
            ).all()
            states_by_path = {item.relative_path: item for item in state_models}
            states_by_key = {item.relative_path_key: item for item in state_models}
            parse_sources: list[DocumentToParse] = []
            assigned_documents: dict[str, UUID] = {}

            for change in result.changes:
                if change.kind is ScanChangeKind.RENAMED:
                    old_state = states_by_path.get(change.old_relative_path or "")
                    if old_state is None or change.new_relative_path is None:
                        continue
                    document = await session.get(
                        DocumentModel, old_state.document_id, with_for_update=True
                    )
                    if document is None:
                        continue
                    await session.delete(old_state)
                    new_key = vault.path_key(change.new_relative_path)
                    snapshot = next(
                        item
                        for item in result.files
                        if item.relative_path == change.new_relative_path
                    )
                    document.current_relative_path = change.new_relative_path
                    document.path_key = new_key
                    document.last_seen_at = datetime.now(UTC)
                    session.add(self._file_state(vault.id, new_key, snapshot, document.id, scan_id))
                    assigned_documents[new_key] = document.id
                    self._add_change(session, scan_id, vault.id, change, document.id)

            for change in result.changes:
                if change.kind is ScanChangeKind.RENAMED:
                    continue
                if change.kind is ScanChangeKind.READ_FAILED:
                    self._add_change(session, scan_id, vault.id, change, change.document_id)
                    continue
                if change.old_relative_path and not change.new_relative_path:
                    old_state = states_by_path.get(change.old_relative_path)
                    if old_state is not None:
                        await session.delete(old_state)
                        await self._delete_document_source(session, old_state.document_id)
                    self._add_change(
                        session,
                        scan_id,
                        vault.id,
                        change,
                        old_state.document_id if old_state else change.document_id,
                    )
                    continue
                if change.new_relative_path is None:
                    self._add_change(session, scan_id, vault.id, change, change.document_id)
                    continue
                snapshot = next(
                    item for item in result.files if item.relative_path == change.new_relative_path
                )
                path_key = snapshot.relative_path_key
                existing = states_by_key.get(path_key)
                document_id = existing.document_id if existing else assigned_documents.get(path_key)
                if document_id is None:
                    document_id = uuid4()
                    session.add(
                        DocumentModel(
                            id=document_id,
                            vault_id=vault.id,
                            current_relative_path=snapshot.relative_path,
                            path_key=path_key,
                            lifecycle_status="active",
                        )
                    )
                else:
                    document = await session.get(DocumentModel, document_id, with_for_update=True)
                    if document is not None:
                        document.lifecycle_status = "active"
                        document.deleted_at = None
                        document.current_relative_path = snapshot.relative_path
                        document.path_key = path_key
                        document.last_seen_at = datetime.now(UTC)
                if existing:
                    existing.relative_path = snapshot.relative_path
                    existing.size_bytes = snapshot.size_bytes
                    existing.mtime_ns = snapshot.mtime_ns
                    existing.content_sha256 = snapshot.content_sha256
                    existing.last_seen_scan_id = scan_id
                    existing.updated_at = datetime.now(UTC)
                else:
                    session.add(
                        self._file_state(vault.id, path_key, snapshot, document_id, scan_id)
                    )
                parse_sources.append(
                    DocumentToParse(
                        document_id=document_id,
                        relative_path=snapshot.relative_path,
                        content_sha256=snapshot.content_sha256,
                        size_bytes=snapshot.size_bytes,
                        mtime_ns=snapshot.mtime_ns,
                    )
                )
                self._add_change(session, scan_id, vault.id, change, document_id)

            changed_keys = {
                vault.path_key(change.new_relative_path)
                for change in result.changes
                if change.new_relative_path
            }
            for snapshot in result.files:
                if snapshot.relative_path_key in changed_keys:
                    continue
                state = states_by_key.get(snapshot.relative_path_key)
                if state is not None:
                    state.last_seen_scan_id = scan_id
                    state.updated_at = datetime.now(UTC)
            pending_document_ids = set(
                (
                    await session.scalars(
                        select(DocumentModel.id).where(
                            DocumentModel.vault_id == vault.id,
                            or_(
                                DocumentModel.lifecycle_status == "error",
                                DocumentModel.current_version_id.is_(None),
                            ),
                        )
                    )
                ).all()
            )
            scheduled_ids = {item.document_id for item in parse_sources}
            for state in state_models:
                if (
                    state.document_id in pending_document_ids
                    and state.document_id not in scheduled_ids
                ):
                    parse_sources.append(
                        DocumentToParse(
                            document_id=state.document_id,
                            relative_path=state.relative_path,
                            content_sha256=state.content_sha256,
                            size_bytes=state.size_bytes,
                            mtime_ns=state.mtime_ns,
                        )
                    )
        return StoredScan(scan_id=scan_id, documents_to_parse=tuple(parse_sources))

    async def store_document(
        self,
        source: DocumentToParse,
        parsed: ParsedDocument,
        chunks: tuple[ParsedChunk, ...],
    ) -> UUID:
        version_id = uuid5(source.document_id, source.content_sha256)
        async with self._session_factory.begin() as session:
            document = await session.get(DocumentModel, source.document_id, with_for_update=True)
            if document is None:
                raise LookupError("document not found")
            existing = await session.get(DocumentVersionModel, version_id)
            if existing is not None:
                await self._delete_derived(session, version_id)
                version = existing
                version.processing_status = "parsing"
                version.superseded_at = None
            else:
                version = DocumentVersionModel(
                    id=version_id,
                    document_id=source.document_id,
                    content_sha256=source.content_sha256,
                    size_bytes=source.size_bytes,
                    mtime_ns=source.mtime_ns,
                    parser_name=PARSER_NAME,
                    parser_version=PARSER_VERSION,
                    chunker_name=CHUNKER_NAME,
                    chunker_version=CHUNKER_VERSION,
                    processing_status="parsing",
                )
                session.add(version)
            version.frontmatter_json = parsed.frontmatter
            version.quality_flags_json = list(parsed.quality_flags)
            await session.flush()
            session.add_all(
                [
                    SectionModel(
                        id=item.id,
                        document_version_id=version_id,
                        parent_section_id=item.parent_id,
                        heading_level=item.heading_level,
                        heading_text=item.heading_text,
                        heading_path_json=item.heading_path,
                        heading_occurrence=item.heading_occurrence,
                        char_start=item.char_start,
                        char_end=item.char_end,
                        content_sha256=item.content_sha256,
                        ordinal=item.ordinal,
                        metadata_json=item.metadata,
                    )
                    for item in parsed.sections
                ]
            )
            await session.flush()
            session.add_all(
                [
                    ContentBlockModel(
                        id=item.id,
                        document_version_id=version_id,
                        section_id=item.section_id,
                        block_type=item.block_type,
                        ordinal=item.ordinal,
                        char_start=item.char_start,
                        char_end=item.char_end,
                        content_sha256=item.content_sha256,
                        code_language=item.code_language,
                        metadata_json=item.metadata,
                    )
                    for item in parsed.blocks
                ]
            )
            chunk_models = []
            for item in chunks:
                tags = [
                    tag.value
                    for tag in parsed.tags
                    if item.char_start <= tag.char_start < item.char_end
                ]
                metadata = {**item.metadata, "tags": tags}
                chunk_models.append(
                    ChunkModel(
                        id=item.id,
                        document_version_id=version_id,
                        section_id=item.section_id,
                        ordinal=item.ordinal,
                        char_start=item.char_start,
                        char_end=item.char_end,
                        text=item.text,
                        content_sha256=item.content_sha256,
                        parser_version=PARSER_VERSION,
                        chunker_version=CHUNKER_VERSION,
                        retrieval_role=str(item.metadata["retrieval_role"]),
                        metadata_json=metadata,
                    )
                )
            session.add_all(chunk_models)
            await session.flush()
            session.add_all(
                [
                    DocumentLinkModel(
                        id=item.id,
                        source_document_version_id=version_id,
                        source_chunk_id=next(
                            (
                                chunk.id
                                for chunk in chunks
                                if chunk.char_start <= item.char_start < chunk.char_end
                            ),
                            None,
                        ),
                        link_kind=item.link_kind,
                        raw_target=item.raw_target,
                        target_path=item.target_path,
                        target_heading=item.target_heading,
                        target_block_id=item.target_block_id,
                        alias=item.alias,
                        resolution_status=(
                            "external"
                            if re.match(
                                r"^[a-zA-Z][a-zA-Z0-9+.-]*:",
                                item.raw_target,
                            )
                            else "unresolved"
                        ),
                        char_start=item.char_start,
                        char_end=item.char_end,
                    )
                    for item in parsed.links
                ]
            )
            old_version_id = document.current_version_id
            if old_version_id and old_version_id != version_id:
                old_version = await session.get(
                    DocumentVersionModel, old_version_id, with_for_update=True
                )
                if old_version:
                    old_version.processing_status = "superseded"
                    old_version.superseded_at = datetime.now(UTC)
                    await self._delete_derived(session, old_version_id)
            document.current_version_id = version_id
            document.title = parsed.title
            document.lifecycle_status = "active"
            document.last_seen_at = datetime.now(UTC)
            version.processing_status = "ready"
        return version_id

    async def mark_document_failed(
        self, document_id: UUID, content_sha256: str, error_type: str
    ) -> None:
        version_id = uuid5(document_id, content_sha256)
        async with self._session_factory.begin() as session:
            document = await session.get(DocumentModel, document_id)
            if document:
                document.lifecycle_status = "error"
            version = await session.get(DocumentVersionModel, version_id)
            if version:
                version.processing_status = "failed"
                flags = list(version.quality_flags_json)
                flags.append({"code": "document_processing_failed", "error_type": error_type})
                version.quality_flags_json = flags

    async def finish_scan(
        self,
        scan_id: UUID,
        *,
        failed_documents: int = 0,
        warnings: tuple[dict[str, object], ...] = (),
    ) -> None:
        async with self._session_factory.begin() as session:
            scan = await session.get(ScanRunModel, scan_id, with_for_update=True)
            if scan:
                scan.status = "succeeded"
                scan.failed_count += failed_documents
                scan.warnings_json = [*scan.warnings_json, *warnings]
                scan.finished_at = datetime.now(UTC)

    async def fail_scan(self, scan_id: UUID, error_type: str) -> None:
        async with self._session_factory.begin() as session:
            scan = await session.get(ScanRunModel, scan_id, with_for_update=True)
            if scan:
                scan.status = "failed"
                scan.error_summary = error_type
                scan.finished_at = datetime.now(UTC)

    @staticmethod
    def _definition(model: VaultModel) -> VaultDefinition:
        return VaultDefinition(
            id=model.id,
            name=model.name,
            root_path=model.root_path,
            path_case_mode=PathCaseMode(model.path_case_mode),
            include_globs=tuple(model.include_globs),
            exclude_globs=tuple(model.exclude_globs),
        )

    @staticmethod
    def _file_state(
        vault_id: UUID,
        path_key: str,
        snapshot: FileSnapshot,
        document_id: UUID,
        scan_id: UUID,
    ) -> VaultFileStateModel:
        return VaultFileStateModel(
            vault_id=vault_id,
            relative_path_key=path_key,
            relative_path=snapshot.relative_path,
            size_bytes=snapshot.size_bytes,
            mtime_ns=snapshot.mtime_ns,
            content_sha256=snapshot.content_sha256,
            document_id=document_id,
            last_seen_scan_id=scan_id,
        )

    @staticmethod
    def _set_scan_counts(scan: ScanRunModel, result: ScanResult) -> None:
        scan.discovered_count = result.discovered_count
        scan.hashed_count = result.hashed_count
        scan.new_count = result.new_count
        scan.modified_count = result.modified_count
        scan.renamed_count = result.renamed_count
        scan.deleted_count = result.deleted_count
        scan.unchanged_count = result.unchanged_count
        scan.failed_count = result.failed_count
        scan.markdown_bytes = result.markdown_bytes
        scan.warnings_json = list(result.warnings)

    @staticmethod
    def _add_change(
        session: AsyncSession,
        scan_id: UUID,
        vault_id: UUID,
        change,
        document_id: UUID | None,
    ) -> None:
        session.add(
            ScanChangeModel(
                scan_id=scan_id,
                vault_id=vault_id,
                document_id=document_id,
                change_kind=change.kind.value,
                old_relative_path=change.old_relative_path,
                new_relative_path=change.new_relative_path,
                content_sha256=change.content_sha256,
                detail_json=change.detail,
            )
        )

    async def _delete_document_source(self, session: AsyncSession, document_id: UUID) -> None:
        document = await session.get(DocumentModel, document_id, with_for_update=True)
        if document is None:
            return
        if document.current_version_id:
            version = await session.get(
                DocumentVersionModel,
                document.current_version_id,
                with_for_update=True,
            )
            await self._delete_derived(session, document.current_version_id)
            if version:
                version.processing_status = "superseded"
                version.superseded_at = datetime.now(UTC)
        document.current_version_id = None
        document.lifecycle_status = "deleted"
        document.deleted_at = datetime.now(UTC)

    @staticmethod
    async def _delete_derived(session: AsyncSession, document_version_id: UUID) -> None:
        await session.execute(
            delete(DocumentLinkModel).where(
                DocumentLinkModel.source_document_version_id == document_version_id
            )
        )
        await session.execute(
            delete(ChunkModel).where(ChunkModel.document_version_id == document_version_id)
        )
        await session.execute(
            delete(ContentBlockModel).where(
                ContentBlockModel.document_version_id == document_version_id
            )
        )
        await session.execute(
            delete(SectionModel).where(SectionModel.document_version_id == document_version_id)
        )
