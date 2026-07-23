from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from sqlalchemy import func, select

from graphrag_service.adapters.postgres.extraction_models import (
    ClaimCandidateModel,
    EntityCandidateModel,
    EvidenceSpanModel,
    ExtractionChunkModel,
    RelationshipCandidateModel,
)
from graphrag_service.adapters.postgres.extraction_store import ExtractionStore
from graphrag_service.adapters.postgres.ingest_models import DocumentModel
from graphrag_service.adapters.postgres.ingest_store import PostgresIngestStore
from graphrag_service.adapters.postgres.session import create_engine, create_session_factory
from graphrag_service.adapters.postgres.unit_of_work import SqlAlchemyUnitOfWork
from graphrag_service.adapters.providers.lmstudio_generation import (
    LMStudioGenerationProvider,
)
from graphrag_service.adapters.vault_fs.factory import build_vault_reader
from graphrag_service.application.extraction import KnowledgeExtractionService
from graphrag_service.application.ingest import VaultIngestService
from graphrag_service.config import get_settings
from graphrag_service.domain.vault import PathCaseMode, ScanType
from graphrag_service.ports.ingest_store import VaultRegistration

DEFAULT_DOCUMENTS = (
    "Belső_tudásbázis/NOC/Folyamatok/SMTP-tiltott-ügyfelek-kezelése.md",
    "Belső_tudásbázis/Saját_fejlesztésű_rendszerek/Helyi_AI_Asszisztens/Módok_és_eszközök.md",
    "Eszközök/Szolgáltatói_eszközök/Végponti_eszközök/Optikai_hálózat/"
    "huawei-ont-k-kezelési-utmutato.md",
)


async def candidate_summary(sessions, run_id: UUID) -> dict[str, object]:
    async with sessions() as session:
        candidate_counts: dict[str, dict[str, int]] = {}
        for name, model in (
            ("entity", EntityCandidateModel),
            ("relationship", RelationshipCandidateModel),
            ("claim", ClaimCandidateModel),
        ):
            rows = (
                await session.execute(
                    select(model.validation_status, func.count())
                    .where(model.extraction_run_id == run_id)
                    .group_by(model.validation_status)
                )
            ).all()
            candidate_counts[name] = {status: int(count) for status, count in rows}
        error_rows = (
            await session.execute(
                select(
                    EntityCandidateModel.validation_errors_json,
                    func.count(),
                )
                .where(
                    EntityCandidateModel.extraction_run_id == run_id,
                    EntityCandidateModel.validation_status == "invalid",
                )
                .group_by(EntityCandidateModel.validation_errors_json)
            )
        ).all()
        evidence_count = int(
            await session.scalar(
                select(func.count())
                .select_from(EvidenceSpanModel)
                .where(EvidenceSpanModel.extraction_run_id == run_id)
            )
            or 0
        )
        chunk_rows = (
            await session.execute(
                select(
                    ExtractionChunkModel.status,
                    ExtractionChunkModel.error_code,
                    func.count(),
                )
                .where(ExtractionChunkModel.extraction_run_id == run_id)
                .group_by(ExtractionChunkModel.status, ExtractionChunkModel.error_code)
            )
        ).all()
    return {
        "candidate_counts": candidate_counts,
        "entity_validation_errors": [
            {"errors": errors, "count": int(count)} for errors, count in error_rows
        ],
        "exact_evidence_spans": evidence_count,
        "chunk_statuses": [
            {"status": status, "error_code": error_code, "count": int(count)}
            for status, error_code, count in chunk_rows
        ],
    }


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    if not settings.generation_provider_enabled:
        raise RuntimeError("GKS_GENERATION_PROVIDER_ENABLED must be true")
    root = args.vault_root.rstrip("/") or "/"
    if root not in settings.vault_allowed_roots:
        raise RuntimeError("pilot vault root must be present in GKS_VAULT_ALLOWED_ROOTS")

    engine = create_engine(settings)
    sessions = create_session_factory(engine)
    ingest_store = PostgresIngestStore(sessions)
    ingest = VaultIngestService(
        store=ingest_store,
        reader_factory=lambda vault: build_vault_reader(settings, vault),
    )
    provider = LMStudioGenerationProvider(
        base_url=settings.generation_provider_url,
        model=settings.generation_model,
        api_key=(
            settings.generation_provider_api_key.get_secret_value()
            if settings.generation_provider_api_key
            else None
        ),
        timeout_seconds=settings.generation_timeout_seconds,
        max_tokens=settings.generation_max_tokens,
        reasoning_effort=settings.generation_reasoning_effort,
    )
    try:
        vault = next(
            (item for item in await ingest_store.list_vaults() if item.root_path == root),
            None,
        )
        if vault is None:
            vault = await ingest.register_vault(
                VaultRegistration(
                    name=args.vault_name,
                    root_path=root,
                    path_case_mode=PathCaseMode.SENSITIVE,
                    include_globs=("**/*.md",),
                    exclude_globs=(".obsidian/**", ".trash/**"),
                )
            )
        scan = await ingest.scan(vault.id, ScanType.INCREMENTAL)
        async with sessions() as session:
            documents = (
                await session.scalars(
                    select(DocumentModel).where(
                        DocumentModel.vault_id == vault.id,
                        DocumentModel.current_relative_path.in_(args.document),
                        DocumentModel.lifecycle_status == "active",
                    )
                )
            ).all()
        by_path = {item.current_relative_path: item for item in documents}
        missing = [path for path in args.document if path not in by_path]
        if missing:
            raise LookupError(f"pilot documents not found: {missing}")

        service = KnowledgeExtractionService(
            store=ExtractionStore(sessions),
            provider=provider,
            max_chunks_per_job=settings.extraction_max_chunks_per_job,
        )
        runs = []
        for path in args.document:
            document = by_path[path]
            async with SqlAlchemyUnitOfWork(sessions) as uow:
                job_id = await uow.jobs.enqueue(
                    "extract_knowledge_pilot",
                    {
                        "vault_id": str(vault.id),
                        "document_ids": [str(document.id)],
                        "max_chunks": args.chunks_per_document,
                    },
                )
            outcome = await service.run_pilot(
                job_id=job_id,
                vault_id=vault.id,
                document_ids=(document.id,),
                max_chunks=args.chunks_per_document,
            )
            runs.append(
                {
                    "relative_path": path,
                    "run_id": str(outcome.run_id),
                    "status": outcome.status,
                    "processed_chunks": outcome.processed_chunks,
                    "valid_candidates": outcome.valid_candidates,
                    "invalid_candidates": outcome.invalid_candidates,
                    "prompt_tokens": outcome.prompt_tokens,
                    "completion_tokens": outcome.completion_tokens,
                    "audit": await candidate_summary(sessions, outcome.run_id),
                }
            )
        print(
            json.dumps(
                {
                    "vault_id": str(vault.id),
                    "scan": {
                        "discovered": scan.result.discovered_count,
                        "hashed": scan.result.hashed_count,
                        "parsed_documents": scan.parsed_documents,
                        "failed_documents": scan.failed_documents,
                    },
                    "model": settings.generation_model,
                    "ontology": "telecom-core@0.1",
                    "runs": runs,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await provider.close()
        await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the bounded Phase 4 extraction pilot.")
    parser.add_argument(
        "--vault-root",
        default="/mnt/d/hack/MCP_Test_ObsidianVault",
    )
    parser.add_argument("--vault-name", default="phase4-extraction-pilot")
    parser.add_argument(
        "--document",
        action="append",
        default=None,
        help="Vault-relative Markdown path; repeat for multiple representative documents.",
    )
    parser.add_argument("--chunks-per-document", type=int, default=2)
    args = parser.parse_args()
    args.document = tuple(args.document or DEFAULT_DOCUMENTS)
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
