from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import func, select

from graphrag_service.adapters.postgres.ingest_models import (
    ChunkModel,
    DocumentModel,
    DocumentVersionModel,
)
from graphrag_service.adapters.postgres.ingest_store import PostgresIngestStore
from graphrag_service.adapters.postgres.retrieval_store import RetrievalStore
from graphrag_service.adapters.postgres.session import (
    create_engine,
    create_session_factory,
)
from graphrag_service.adapters.vault_fs.factory import build_vault_reader
from graphrag_service.application.ingest import VaultIngestService
from graphrag_service.domain.vault import PathCaseMode, ScanType
from graphrag_service.ports.ingest_store import VaultRegistration
from tests.integration.test_phase1_stack import integration_settings, run_alembic

pytestmark = pytest.mark.integration


def snapshot(path: Path) -> dict[str, tuple[int, int, str]]:
    return {
        item.relative_to(path).as_posix(): (
            item.stat().st_size,
            item.stat().st_mtime_ns,
            hashlib.sha256(item.read_bytes()).hexdigest(),
        )
        for item in path.rglob("*")
        if item.is_file()
    }


async def test_phase2_incremental_lifecycle_and_read_only_acceptance(
    tmp_path: Path,
) -> None:
    settings = integration_settings()
    run_alembic("downgrade", settings.postgres_dsn)
    run_alembic("upgrade", settings.postgres_dsn)
    note = tmp_path / "knowledge.md"
    note.write_text(
        "# Hálózat\n\nÁttekintés az eljárásról.\n\n"
        "## Eljárás\n\n"
        "### Előkészítés\n\nAz ONT előkészítése.\n\n"
        "### Beállítás\n\nA CMTS [[ONT]] eszközt szolgál ki.\n",
        encoding="utf-8",
    )
    before = snapshot(tmp_path)

    settings = settings.model_copy(update={"vault_allowed_roots": [str(tmp_path)]})
    engine = create_engine(settings)
    sessions = create_session_factory(engine)
    store = PostgresIngestStore(sessions)
    service = VaultIngestService(
        store=store,
        reader_factory=lambda vault: build_vault_reader(settings, vault),
    )
    vault = await service.register_vault(
        VaultRegistration(
            name="phase2-test",
            root_path=str(tmp_path),
            path_case_mode=PathCaseMode.SENSITIVE,
            include_globs=("**/*.md",),
            exclude_globs=(),
        )
    )

    first = await service.scan(vault.id, ScanType.INCREMENTAL)
    assert first.result.new_count == 1
    assert first.parsed_documents == 1
    assert snapshot(tmp_path) == before

    async with sessions() as session:
        document = await session.scalar(select(DocumentModel))
        assert document is not None
        stable_document_id = document.id
        first_version_id = document.current_version_id
        chunk_count = await session.scalar(select(func.count()).select_from(ChunkModel))
        assert chunk_count and chunk_count > 0
        chunks = (await session.scalars(select(ChunkModel))).all()
        assert all(chunk.text for chunk in chunks)
        roles = {chunk.retrieval_role for chunk in chunks}
        assert roles == {"structural_anchor", "content_evidence"}
        assert (
            next(
                chunk for chunk in chunks if chunk.retrieval_role == "structural_anchor"
            ).text.strip()
            == "## Eljárás"
        )

        retrieval_store = RetrievalStore(sessions)
        hydrated = await retrieval_store.hydrate_current([chunk.id for chunk in chunks])
        root_chunk = next(item for item in hydrated.values() if len(item.heading_path) == 1)
        document_context, context_truncated = await retrieval_store.document_context(
            [root_chunk.chunk_id],
            max_documents=1,
            max_chunks_per_document=10,
            max_total_chars=10000,
        )
        assert [item.heading_path[-1] for item in document_context] == [
            "Előkészítés",
            "Beállítás",
        ]
        assert context_truncated is False

    unchanged = await service.scan(vault.id, ScanType.INCREMENTAL)
    assert unchanged.result.hashed_count == 0
    assert unchanged.parsed_documents == 0

    renamed = tmp_path / "renamed.md"
    note.rename(renamed)
    rename_scan = await service.scan(vault.id, ScanType.INCREMENTAL)
    assert rename_scan.result.renamed_count == 1
    assert rename_scan.parsed_documents == 0
    async with sessions() as session:
        document = await session.get(DocumentModel, stable_document_id)
        assert document and document.current_relative_path == "renamed.md"

    renamed.write_text("# Hálózat\n\nMódosított CMTS tartalom.\n", encoding="utf-8")
    modified = await service.scan(vault.id, ScanType.INCREMENTAL)
    assert modified.result.modified_count == 1
    assert modified.parsed_documents == 1
    async with sessions() as session:
        document = await session.get(DocumentModel, stable_document_id)
        assert document and document.current_version_id != first_version_id
        versions = (
            await session.scalars(
                select(DocumentVersionModel).where(
                    DocumentVersionModel.document_id == stable_document_id
                )
            )
        ).all()
        assert len(versions) == 2
        old_version = next(item for item in versions if item.id == first_version_id)
        assert old_version.processing_status == "superseded"
        old_chunks = await session.scalar(
            select(func.count())
            .select_from(ChunkModel)
            .where(ChunkModel.document_version_id == first_version_id)
        )
        assert old_chunks == 0

    renamed.unlink()
    deleted = await service.scan(vault.id, ScanType.INCREMENTAL)
    assert deleted.result.deleted_count == 1
    async with sessions() as session:
        document = await session.get(DocumentModel, stable_document_id)
        assert document and document.lifecycle_status == "deleted"
        assert document.current_version_id is None
        assert await session.scalar(select(func.count()).select_from(ChunkModel)) == 0
    await engine.dispose()
