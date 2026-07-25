from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

import httpx

from graphrag_service.config import Settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the running Phase 5 GraphRAG retrieval API."
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("docs/evaluation/graphrag-retrieval-v1.json"),
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--vault-id", type=UUID)
    return parser.parse_args()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _contains_all(actual: set[str], expected: list[str]) -> bool:
    return {item.casefold() for item in expected}.issubset({item.casefold() for item in actual})


def evaluate_case(case: dict[str, Any], body: dict[str, Any]) -> dict[str, bool]:
    source_ids = {item["source_id"] for item in body["sources"]}
    referenced_source_ids = {item["source_chunk_id"] for item in body["relationships"]} | {
        item["source_chunk_id"] for item in body["claims"]
    }
    for path in body["retrieval_paths"]:
        referenced_source_ids.update(path["source_chunk_ids"])

    source_paths = {item["relative_path"] for item in body["sources"]}
    entity_names = {item["canonical_name"] for item in body["entities"]}
    predicates = {item["predicate"] for item in body["relationships"]}
    claim_text = "\n".join(item["text"] for item in body["claims"]).casefold()
    path_hops = [item["hops"] for item in body["retrieval_paths"]]
    expected_claims = case.get("expected_claim_substrings", [])

    return {
        "query_type": body["query_type"] == case["expected_query_type"],
        "planner_reason": body["planner_reason_code"] == case["expected_reason_code"],
        "source_paths": _contains_all(source_paths, case.get("expected_source_paths", [])),
        "entities": _contains_all(entity_names, case.get("expected_entities", [])),
        "predicates": _contains_all(predicates, case.get("expected_predicates", [])),
        "claims": all(item.casefold() in claim_text for item in expected_claims),
        "minimum_path_hops": max(path_hops, default=0) >= case.get("min_path_hops", 0),
        "bounded_paths": max(path_hops, default=0) <= 4 and len(body["retrieval_paths"]) <= 50,
        "provenance_complete": referenced_source_ids.issubset(source_ids),
    }


async def run() -> dict[str, Any]:
    args = parse_args()
    settings = Settings()  # type: ignore[call-arg]
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    headers = {
        "Authorization": f"Bearer {settings.service_token.get_secret_value()}",
    }
    cases: list[dict[str, Any]] = []
    latencies: list[float] = []
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        headers=headers,
        timeout=60,
    ) as client:
        for case in corpus["cases"]:
            request: dict[str, Any] = {
                "query": case["query"],
                "strategy": case["strategy"],
                "limit": case["limit"],
            }
            if args.vault_id is not None:
                request["vault_id"] = str(args.vault_id)
            started_at = perf_counter()
            response = await client.post("/v1/retrieve", json=request)
            response.raise_for_status()
            latency_ms = (perf_counter() - started_at) * 1000
            latencies.append(latency_ms)
            body = response.json()
            checks = evaluate_case(case, body)
            cases.append(
                {
                    "id": case["id"],
                    "passed": all(checks.values()),
                    "checks": checks,
                    "warnings": [item["code"] for item in body["warnings"]],
                    "result_counts": {
                        "chunks": len(body["chunks"]),
                        "entities": len(body["entities"]),
                        "relationships": len(body["relationships"]),
                        "claims": len(body["claims"]),
                        "paths": len(body["retrieval_paths"]),
                    },
                    "max_path_hops": max(
                        (item["hops"] for item in body["retrieval_paths"]),
                        default=0,
                    ),
                    "latency_ms": round(latency_ms, 2),
                }
            )

    check_names = list(cases[0]["checks"]) if cases else []
    passed_count = sum(item["passed"] for item in cases)
    return {
        "corpus_version": corpus["version"],
        "case_count": len(cases),
        "passed_cases": passed_count,
        "all_passed": passed_count == len(cases),
        "check_pass_rates": {
            name: sum(item["checks"][name] for item in cases) / len(cases) for name in check_names
        },
        "latency_ms": {
            "p50": round(statistics.median(latencies), 2),
            "p95": round(percentile(latencies, 0.95), 2),
        },
        "cases": cases,
    }


def main() -> None:
    result = asyncio.run(run())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
