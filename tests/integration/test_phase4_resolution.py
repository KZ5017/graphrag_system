from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from graphrag_service.adapters.postgres.extraction_models import (
    EntityCandidateModel,
    EvidenceSpanModel,
)
from graphrag_service.adapters.postgres.extraction_store import ExtractionStore
from graphrag_service.adapters.postgres.ingest_models import DocumentModel
from graphrag_service.adapters.postgres.ingest_store import PostgresIngestStore
from graphrag_service.adapters.postgres.resolution_models import (
    ClaimModel,
    EntityMentionModel,
    EntityModel,
    RelationshipAssertionModel,
    ResolutionDecisionModel,
    ResolutionReviewCandidateModel,
)
from graphrag_service.adapters.postgres.resolution_store import ResolutionStore
from graphrag_service.adapters.postgres.session import (
    create_engine,
    create_session_factory,
)
from graphrag_service.adapters.postgres.unit_of_work import SqlAlchemyUnitOfWork
from graphrag_service.adapters.vault_fs.factory import build_vault_reader
from graphrag_service.application.extraction import KnowledgeExtractionService
from graphrag_service.application.ingest import VaultIngestService
from graphrag_service.application.resolution import EntityResolutionService
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


class ResolutionGenerationProvider:
    async def healthcheck(self) -> str:
        return "available"

    async def model_info(self) -> GenerationModelInfo:
        return GenerationModelInfo(
            provider="deterministic_test",
            model="phase4-resolution-test",
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
                        "name": "ONT-ABC-001",
                        "entity_type": "DEVICE_INSTANCE",
                        "entity_subtype": "ONT",
                        "proposed_subtype": None,
                        "scope": "instance",
                        "assertion_kind": "explicit",
                        "evidence": {
                            "quote": "serial number: ONT-ABC-001",
                            "quote_occurrence": 1,
                        },
                    },
                    {
                        "local_id": "e2",
                        "name": "ONT-ABC-001",
                        "entity_type": "DEVICE_INSTANCE",
                        "entity_subtype": "ONT",
                        "proposed_subtype": None,
                        "scope": "instance",
                        "assertion_kind": "explicit",
                        "evidence": {
                            "quote": "serial number: ONT-ABC-001",
                            "quote_occurrence": 2,
                        },
                    },
                    {
                        "local_id": "e3",
                        "name": "Customer Portal",
                        "entity_type": "APPLICATION",
                        "entity_subtype": None,
                        "proposed_subtype": None,
                        "scope": "logical",
                        "assertion_kind": "explicit",
                        "evidence": {
                            "quote": "Customer Portal",
                            "quote_occurrence": 1,
                        },
                    },
                    {
                        "local_id": "e4",
                        "name": "Customer Portal",
                        "entity_type": "APPLICATION",
                        "entity_subtype": None,
                        "proposed_subtype": None,
                        "scope": "logical",
                        "assertion_kind": "explicit",
                        "evidence": {
                            "quote": "Customer Portal",
                            "quote_occurrence": 2,
                        },
                    },
                ],
                "relationships": [
                    {
                        "subject_local_id": "e1",
                        "predicate": "USES",
                        "object_local_id": "e3",
                        "assertion_kind": "explicit",
                        "network_layer": "service",
                        "evidence": {
                            "quote": "ONT-ABC-001 uses Customer Portal",
                            "quote_occurrence": 1,
                        },
                    }
                ],
                "claims": [
                    {
                        "text": "The device is registered.",
                        "assertion_kind": "explicit",
                        "evidence": {
                            "quote": "The device is registered.",
                            "quote_occurrence": 1,
                        },
                    }
                ],
            },
            model="phase4-resolution-test",
            finish_reason="stop",
            usage=GenerationUsage(40, 20, 60),
            response_sha256="c" * 64,
        )

    async def close(self) -> None:
        return None


async def test_resolution_merges_only_strong_ids_and_cascades_with_source(
    tmp_path: Path,
) -> None:
    settings = integration_settings()
    run_alembic("downgrade", settings.postgres_dsn)
    run_alembic("upgrade", settings.postgres_dsn)
    settings = settings.model_copy(update={"vault_allowed_roots": [str(tmp_path)]})
    note = tmp_path / "resolution.md"
    note.write_text(
        "# Resolution\n\n"
        "Device serial number: ONT-ABC-001. "
        "ONT-ABC-001 uses Customer Portal. "
        "The device is registered.\n\n"
        "Backup serial number: ONT-ABC-001. "
        "Customer Portal remains available.\n",
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
            name="phase4-resolution",
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
    extraction = await KnowledgeExtractionService(
        store=ExtractionStore(sessions),
        provider=ResolutionGenerationProvider(),
        max_chunks_per_job=2,
    ).run_pilot(
        job_id=job_id,
        vault_id=vault.id,
        document_ids=(document.id,),
        max_chunks=1,
    )
    resolution = await EntityResolutionService(ResolutionStore(sessions)).resolve_run(
        extraction.run_id
    )
    assert resolution.created_entities == 3
    assert resolution.merged_mentions == 1
    assert resolution.deferred_candidates == 0
    assert resolution.review_candidates == 1
    assert resolution.relationship_assertions == 1
    assert resolution.claims == 1

    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(EntityModel)) == 3
        assert await session.scalar(select(func.count()).select_from(EntityMentionModel)) == 4
        assert await session.scalar(select(func.count()).select_from(ResolutionDecisionModel)) == 4
        assert (
            await session.scalar(select(func.count()).select_from(ResolutionReviewCandidateModel))
            == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(RelationshipAssertionModel)) == 1
        )
        assert await session.scalar(select(func.count()).select_from(ClaimModel)) == 1

    second = await EntityResolutionService(ResolutionStore(sessions)).resolve_run(extraction.run_id)
    assert second.created_entities == 0
    assert second.merged_mentions == 0
    assert second.relationship_assertions == 0
    assert second.claims == 0

    note.write_text("# Resolution\n\nCurrent source changed.\n", encoding="utf-8")
    await ingest.scan(vault.id, ScanType.INCREMENTAL)
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(EvidenceSpanModel)) == 0
        assert await session.scalar(select(func.count()).select_from(EntityCandidateModel)) == 0
        assert await session.scalar(select(func.count()).select_from(EntityModel)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(RelationshipAssertionModel)) == 0
        )
        assert await session.scalar(select(func.count()).select_from(ClaimModel)) == 0
    await engine.dispose()
