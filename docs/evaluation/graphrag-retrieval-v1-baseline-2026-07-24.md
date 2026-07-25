# GraphRAG retrieval v1 baseline — 2026-07-24

## Scope

- Running local API with PostgreSQL, Qdrant and Neo4j projections
- Read-only vault: `/mnt/d/hack/MCP_Test_ObsidianVault`
- Semantic graph scope: three explicitly extracted pilot documents
- Embedding model: `text-embedding-bge-m3`, runtime dimension 1024
- Extraction model: `qwen/qwen3.5-9b`, `reasoning_effort=none`
- Reviewed corpus: `docs/evaluation/graphrag-retrieval-v1.json`
- Runner: `scripts/run_phase5_evaluation.py`

The query planner is deterministic and does not call the generation model.
This keeps routing stable despite the intentionally small local model. Model
output participates only after schema, ontology, exact-evidence and
current-source validation.

## Result

| Metric | Result |
|---|---:|
| Reviewed cases passed | 4/4 |
| Query-type checks | 4/4 |
| Planner-reason checks | 4/4 |
| Required source-path checks | 4/4 |
| Required entity checks | 4/4 |
| Required predicate checks | 4/4 |
| Required claim checks | 4/4 |
| Minimum path-depth checks | 4/4 |
| Bounded path checks | 4/4 |
| Complete hydrated provenance checks | 4/4 |
| API latency p50 | 357.08 ms |
| API latency p95 | 432.36 ms |
| Retrieval warnings | 0 |

The reviewed cases cover:

- relationship-cued OTRS retrieval;
- short-acronym entity routing for OTRS;
- DHCP → PPPoE and WAN connection retrieval;
- a verified two-hop path:
  `Obsidian vault → Tudásbázis mód → általános modellválaszok`.

Every returned relationship, claim and graph path referenced a source chunk
present in the response. Every path stayed within the hard limits of four hops
and 50 paths.

## Acceptance interpretation

This closes the Phase 5 plumbing and provenance acceptance: deterministic
planning, vector/entity seeds, bounded graph expansion, claim retrieval,
deterministic fusion and current-source hydration work together through the
public API.

The corpus is deliberately small and tied to the three reviewed pilot
documents. It is not a claim of whole-vault semantic precision. In particular,
the current candidate limits favor recall and can return unrelated graph
neighbors or claims alongside the expected evidence. Broader extraction,
precision-oriented ranking, negative queries and calibrated confidence require
a larger reviewed set. `confidence` therefore remains `null`.
