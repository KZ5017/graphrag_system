from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import func, select

from graphrag_service.adapters.neo4j.client import Neo4jGraphAdapter
from graphrag_service.adapters.postgres.extraction_models import ExtractionRunModel
from graphrag_service.adapters.postgres.extraction_store import ExtractionStore
from graphrag_service.adapters.postgres.graph_store import GraphStore
from graphrag_service.adapters.postgres.ingest_models import DocumentModel
from graphrag_service.adapters.postgres.ingest_store import PostgresIngestStore
from graphrag_service.adapters.postgres.resolution_models import (
    ClaimModel,
    EntityModel,
    RelationshipAssertionModel,
    ResolutionReviewCandidateModel,
)
from graphrag_service.adapters.postgres.resolution_store import ResolutionStore
from graphrag_service.adapters.postgres.session import create_engine, create_session_factory
from graphrag_service.adapters.postgres.unit_of_work import SqlAlchemyUnitOfWork
from graphrag_service.adapters.providers.lmstudio_generation import (
    LMStudioGenerationProvider,
)
from graphrag_service.adapters.vault_fs.factory import build_vault_reader
from graphrag_service.application.extraction import KnowledgeExtractionService
from graphrag_service.application.graph_projection import GraphProjectionService
from graphrag_service.application.ingest import VaultIngestService
from graphrag_service.application.resolution import EntityResolutionService
from graphrag_service.config import get_settings
from graphrag_service.domain.vault import PathCaseMode, ScanType
from graphrag_service.ports.ingest_store import VaultRegistration

DEFAULT_DOCUMENTS = (
    "Belső_tudásbázis/NOC/Folyamatok/SMTP-tiltott-ügyfelek-kezelése.md",
    "Belső_tudásbázis/Saját_fejlesztésű_rendszerek/Helyi_AI_Asszisztens/Módok_és_eszközök.md",
    "Eszközök/Szolgáltatói_eszközök/Végponti_eszközök/Optikai_hálózat/"
    "huawei-ont-k-kezelési-utmutato.md",
)


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    if not settings.generation_provider_enabled:
        raise RuntimeError("GKS_GENERATION_PROVIDER_ENABLED must be true")
    root = str(Path(args.vault_root))
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
    graph = Neo4jGraphAdapter(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password.get_secret_value(),
        database=settings.neo4j_database,
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

        extraction = KnowledgeExtractionService(
            store=ExtractionStore(sessions),
            provider=provider,
            max_chunks_per_job=settings.extraction_max_chunks_per_job,
        )
        resolver = EntityResolutionService(ResolutionStore(sessions))
        runs: list[dict[str, object]] = []
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
            extracted = await extraction.run_pilot(
                job_id=job_id,
                vault_id=vault.id,
                document_ids=(document.id,),
                max_chunks=args.chunks_per_document,
            )
            resolved = await resolver.resolve_run(extracted.run_id)
            runs.append(
                {
                    "relative_path": path,
                    "run_id": str(extracted.run_id),
                    "extraction": {
                        "status": extracted.status,
                        "processed_chunks": extracted.processed_chunks,
                        "valid_candidates": extracted.valid_candidates,
                        "invalid_candidates": extracted.invalid_candidates,
                        "prompt_tokens": extracted.prompt_tokens,
                        "completion_tokens": extracted.completion_tokens,
                    },
                    "resolution": {
                        "created_entities": resolved.created_entities,
                        "merged_mentions": resolved.merged_mentions,
                        "deferred_candidates": resolved.deferred_candidates,
                        "review_candidates": resolved.review_candidates,
                        "relationship_assertions": resolved.relationship_assertions,
                        "claims": resolved.claims,
                    },
                }
            )
        projected = await GraphProjectionService(
            store=GraphStore(sessions),
            graph=graph,
            max_objects=settings.graph_projection_max_objects,
        ).rebuild_vault(vault.id)
        async with sessions() as session:
            canonical_counts = {
                "entities": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(EntityModel)
                        .where(EntityModel.vault_id == vault.id)
                    )
                    or 0
                ),
                "relationship_assertions": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(RelationshipAssertionModel)
                        .join(
                            EntityModel,
                            EntityModel.id == RelationshipAssertionModel.subject_entity_id,
                        )
                        .where(EntityModel.vault_id == vault.id)
                    )
                    or 0
                ),
                "claims": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(ClaimModel)
                        .join(
                            ExtractionRunModel,
                            ExtractionRunModel.id == ClaimModel.extraction_run_id,
                        )
                        .where(ExtractionRunModel.vault_id == vault.id)
                    )
                    or 0
                ),
                "pending_resolution_review": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(ResolutionReviewCandidateModel)
                        .where(ResolutionReviewCandidateModel.status == "pending")
                    )
                    or 0
                ),
            }
        print(
            json.dumps(
                {
                    "vault_id": str(vault.id),
                    "vault_read_only": True,
                    "scan": {
                        "discovered": scan.result.discovered_count,
                        "hashed": scan.result.hashed_count,
                        "parsed_documents": scan.parsed_documents,
                        "failed_documents": scan.failed_documents,
                    },
                    "generation_model": settings.generation_model,
                    "ontology": "telecom-core@0.1",
                    "runs": runs,
                    "canonical_counts": canonical_counts,
                    "neo4j_projection": {
                        "generation": projected.generation,
                        "snapshot_sha256": projected.snapshot_sha256,
                        "object_count": projected.object_count,
                        "projected": projected.projected,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await graph.close()
        await provider.close()
        await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run bounded extraction, deterministic resolution, and Neo4j projection."
    )
    parser.add_argument(
        "--vault-root",
        default="/mnt/d/hack/MCP_Test_ObsidianVault",
    )
    parser.add_argument("--vault-name", default="phase4-graph-pilot")
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
