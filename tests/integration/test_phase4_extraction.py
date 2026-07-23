from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from graphrag_service.adapters.postgres.extraction_models import (
    EntityCandidateModel,
    EvidenceSpanModel,
    ExtractionChunkModel,
    ExtractionRunModel,
)
from graphrag_service.adapters.postgres.extraction_store import ExtractionStore
from graphrag_service.adapters.postgres.ingest_models import DocumentModel
from graphrag_service.adapters.postgres.ingest_store import PostgresIngestStore
from graphrag_service.adapters.postgres.session import (
    create_engine,
    create_session_factory,
)
from graphrag_service.adapters.postgres.unit_of_work import SqlAlchemyUnitOfWork
from graphrag_service.adapters.vault_fs.factory import build_vault_reader
from graphrag_service.application.extraction import KnowledgeExtractionService
from graphrag_service.application.ingest import VaultIngestService
from graphrag_service.domain.generation import (
    GenerationCapabilities,
    GenerationModelInfo,
    GenerationUsage,
    StructuredGeneration,
)
from graphrag_service.domain.vault import PathCaseMode, ScanType
from graphrag_service.ports.ingest_store import VaultRegistration
from tests.integration.test_phase1_stack import integration_settings, run_alembic

pytestmark = pytest.mark.integration


class FixedGenerationProvider:
    async def healthcheck(self) -> str:
        return "available"

    async def model_info(self) -> GenerationModelInfo:
        return GenerationModelInfo(
            provider="deterministic_test",
            model="phase4-test-generation",
            capabilities=GenerationCapabilities(
                structured_output=True,
                reasoning_effort=False,
            ),
        )

    async def generate_structured(self, **_: object) -> StructuredGeneration:
        return StructuredGeneration(
            data={
                "entities": [
                    {
                        "local_id": "e1",
                        "name": "Huawei EG8145V5",
                        "entity_type": "DEVICE_MODEL",
                        "entity_subtype": "ONT",
                        "proposed_subtype": None,
                        "scope": "model",
                        "assertion_kind": "explicit",
                        "evidence": {
                            "quote": "Huawei EG8145V5",
                            "quote_occurrence": 1,
                        },
                    }
                ],
                "relationships": [],
                "claims": [],
            },
            model="phase4-test-generation",
            finish_reason="stop",
            usage=GenerationUsage(20, 10, 30),
            response_sha256="b" * 64,
        )

    async def close(self) -> None:
        return None


async def test_phase4_exact_evidence_and_source_retention_cascade(tmp_path: Path) -> None:
    settings = integration_settings()
    run_alembic("downgrade", settings.postgres_dsn)
    run_alembic("upgrade", settings.postgres_dsn)
    settings = settings.model_copy(update={"vault_allowed_roots": [str(tmp_path)]})
    note = tmp_path / "ont.md"
    note.write_text(
        "# ONT\n\nA támogatott modell Huawei EG8145V5.\n",
        encoding="utf-8",
    )

    engine = create_engine(settings)
    sessions = create_session_factory(engine)
    ingest = VaultIngestService(
        store=PostgresIngestStore(sessions),
        reader_factory=lambda vault: build_vault_reader(settings, vault),
    )
    vault = await ingest.register_vault(
        VaultRegistration(
            name="phase4-test",
            root_path=str(tmp_path),
            path_case_mode=PathCaseMode.SENSITIVE,
            include_globs=("**/*.md",),
            exclude_globs=(),
        )
    )
    await ingest.scan(vault.id, ScanType.INCREMENTAL)
    async with sessions() as session:
        document = await session.scalar(select(DocumentModel))
        assert document is not None

    async with SqlAlchemyUnitOfWork(sessions) as uow:
        job_id = await uow.jobs.enqueue(
            "extract_knowledge_pilot",
            {"vault_id": str(vault.id), "document_ids": [str(document.id)]},
        )
    service = KnowledgeExtractionService(
        store=ExtractionStore(sessions),
        provider=FixedGenerationProvider(),
        max_chunks_per_job=6,
    )
    outcome = await service.run_pilot(
        job_id=job_id,
        vault_id=vault.id,
        document_ids=(document.id,),
        max_chunks=1,
    )
    assert outcome.status == "succeeded"
    assert outcome.valid_candidates == 1

    async with sessions() as session:
        evidence = await session.scalar(select(EvidenceSpanModel))
        assert evidence is not None
        assert evidence.quote_text == "Huawei EG8145V5"
        assert evidence.char_end - evidence.char_start == len(evidence.quote_text)
        assert await session.scalar(select(func.count()).select_from(EntityCandidateModel)) == 1

    note.write_text("# ONT\n\nA modelllista megváltozott.\n", encoding="utf-8")
    await ingest.scan(vault.id, ScanType.INCREMENTAL)
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(EvidenceSpanModel)) == 0
        assert await session.scalar(select(func.count()).select_from(EntityCandidateModel)) == 0
        assert await session.scalar(select(func.count()).select_from(ExtractionChunkModel)) == 0
        assert await session.scalar(select(func.count()).select_from(ExtractionRunModel)) == 1
    await engine.dispose()
