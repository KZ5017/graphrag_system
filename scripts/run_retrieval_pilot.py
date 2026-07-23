from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from pathlib import Path
from time import perf_counter
from typing import Any

from graphrag_service.adapters.postgres.ingest_store import PostgresIngestStore
from graphrag_service.adapters.postgres.projection_store import ProjectionStore
from graphrag_service.adapters.postgres.retrieval_store import RetrievalStore
from graphrag_service.adapters.postgres.session import (
    create_engine,
    create_session_factory,
)
from graphrag_service.adapters.providers.lmstudio_embeddings import (
    LMStudioEmbeddingProvider,
)
from graphrag_service.adapters.qdrant.client import QdrantVectorIndex
from graphrag_service.adapters.vault_fs.factory import build_vault_reader
from graphrag_service.application.ingest import VaultIngestService
from graphrag_service.application.projection import ChunkProjectionService
from graphrag_service.application.retrieval import RetrievalService
from graphrag_service.config import Settings
from graphrag_service.domain.vault import PathCaseMode, ScanType
from graphrag_service.ports.ingest_store import VaultRegistration


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 3 retrieval pilot.")
    parser.add_argument("vault", type=Path)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("docs/evaluation/retrieval-pilot-v0.json"),
    )
    parser.add_argument("--limit", type=int, default=5)
    return parser.parse_args()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


async def ensure_vault(
    service: VaultIngestService,
    store: PostgresIngestStore,
    path: Path,
):
    resolved = str(await asyncio.to_thread(path.resolve))
    for vault in await store.list_vaults():
        if vault.root_path == resolved:
            return vault
    return await service.register_vault(
        VaultRegistration(
            name="retrieval-pilot-v0",
            root_path=resolved,
            path_case_mode=PathCaseMode.SENSITIVE,
            include_globs=("**/*.md",),
            exclude_globs=(".obsidian/**", ".trash/**"),
        )
    )


def document_rank(paths: list[str], expected_path: str) -> int | None:
    seen: set[str] = set()
    rank = 0
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        rank += 1
        if path == expected_path:
            return rank
    return None


async def run() -> dict[str, Any]:
    args = parse_args()
    settings = Settings()  # type: ignore[call-arg]
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    engine = create_engine(settings)
    sessions = create_session_factory(engine)
    ingest_store = PostgresIngestStore(sessions)
    ingest = VaultIngestService(
        store=ingest_store,
        reader_factory=lambda vault: build_vault_reader(settings, vault),
    )
    provider = LMStudioEmbeddingProvider(
        base_url=settings.embedding_provider_url,
        model=settings.embedding_model,
        api_key=(
            settings.embedding_provider_api_key.get_secret_value()
            if settings.embedding_provider_api_key
            else None
        ),
        timeout_seconds=settings.embedding_timeout_seconds,
        max_batch_size=settings.embedding_batch_size,
    )
    vectors = QdrantVectorIndex(
        base_url=settings.qdrant_url,
        api_key=(settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None),
        timeout_seconds=settings.embedding_timeout_seconds,
    )
    try:
        vault = await ensure_vault(ingest, ingest_store, args.vault)
        scan = await ingest.scan(vault.id, ScanType.INCREMENTAL)
        projection_store = ProjectionStore(sessions)
        projection = await ChunkProjectionService(
            store=projection_store,
            provider=provider,
            vectors=vectors,
            alias=settings.qdrant_chunks_alias,
            worker_id="retrieval-pilot-v0",
            batch_size=settings.projection_batch_size,
            lease_seconds=settings.worker_lease_seconds,
        ).run(vault_id=vault.id)
        retrieval = RetrievalService(
            store=RetrievalStore(sessions),
            projection_store=projection_store,
            vector_index=vectors,
            embedding_provider=provider,
            candidate_limit=settings.retrieval_candidate_limit,
            max_limit=settings.retrieval_max_limit,
            rrf_k=settings.retrieval_rrf_k,
            chunks_alias=settings.qdrant_chunks_alias,
        )

        strategy_results: dict[str, Any] = {}
        for strategy in ("keyword", "semantic", "hybrid"):
            ranks: list[int | None] = []
            latencies: list[float] = []
            cases: list[dict[str, Any]] = []
            for item in corpus:
                started_at = perf_counter()
                result = await retrieval.retrieve(
                    item["query"],
                    strategy=strategy,  # type: ignore[arg-type]
                    limit=args.limit,
                    vault_id=vault.id,
                )
                latency_ms = (perf_counter() - started_at) * 1000
                rank = document_rank(
                    [chunk.relative_path for chunk in result.chunks],
                    item["expected_path"],
                )
                ranks.append(rank)
                latencies.append(latency_ms)
                cases.append(
                    {
                        "id": item["id"],
                        "rank": rank,
                        "warnings": [warning.code for warning in result.warnings],
                    }
                )
            reciprocal_ranks = [1.0 / rank if rank else 0.0 for rank in ranks]
            strategy_results[strategy] = {
                "document_recall_at_5": sum(rank is not None for rank in ranks) / len(ranks),
                "document_mrr_at_5": sum(reciprocal_ranks) / len(reciprocal_ranks),
                "latency_ms_p50": statistics.median(latencies),
                "latency_ms_p95": percentile(latencies, 0.95),
                "cases": cases,
            }

        return {
            "vault_id": str(vault.id),
            "scan": {
                "scan_id": str(scan.scan_id),
                "discovered": scan.result.discovered_count,
                "hashed": scan.result.hashed_count,
                "parsed_documents": scan.parsed_documents,
                "failed_documents": scan.failed_documents,
            },
            "projection": {
                "model_profile_id": str(projection.model_profile_id),
                "collection": projection.collection,
                "dimension": projection.vector_dimension,
                "enqueued_upserts": projection.enqueued_upserts,
                "projected_upserts": projection.projected_upserts,
            },
            "strategies": strategy_results,
        }
    finally:
        await provider.close()
        await vectors.close()
        await engine.dispose()


def main() -> None:
    print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
