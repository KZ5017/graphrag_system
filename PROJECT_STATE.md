# GraphRAG Knowledge Service – project state

Last updated: 2026-07-24  
Repository target: `https://github.com/KZ5017/graphrag_system.git`

This is the durable handoff snapshot. It describes what is implemented, what
was verified, what local state exists, and where work should resume.

## Executive state

Phases 0–3 are complete. The Phase 4 core is implemented:

- controlled, versioned ontology and LM Studio structured extraction;
- fail-closed Pydantic, ontology, and exact-evidence validation;
- auditable entity, relationship, and claim candidates;
- deterministic strong-identifier entity resolution;
- canonical PostgreSQL entities, aliases, mentions, identifiers, assertions,
  claims, resolution decisions, and review candidates;
- source-version cascade for source-derived semantic content;
- outbox-audited, transactionally replaceable Neo4j vault snapshots;
- Neo4j document/link and semantic graph projection;
- entity detail, bounded neighbors, and bounded path REST endpoints;
- durable `resolve_and_project_graph` worker job;
- real read-only vault extraction/resolution/projection baseline.

Phase 4 is not considered semantically finished until a reviewed gold set and
human merge-review workflow exist. Phase 5 GraphRAG retrieval has not started.

## Verified baselines

### Vault and ingest

- Vault: `/mnt/d/hack/MCP_Test_ObsidianVault`
- Mode: read-only
- Markdown documents: 18
- Latest graph pilot scan: 18 hashed, 18 parsed, 0 failed
- Structural graph covers all current documents.
- Semantic graph covers only the three explicitly selected pilot documents.

### Retrieval baseline

- Embedding model: `text-embedding-bge-m3`
- Runtime dimension: 1024
- Corpus chunks: 284 in the Phase 3 baseline
- Semantic Recall@5: 1.0000
- MRR@5: 0.9583
- Details:
  `docs/evaluation/retrieval-pilot-v0-baseline-2026-07-23.md`

### Extraction and graph baseline

- Generation model: `qwen/qwen3.5-9b`
- Reasoning effort: `none`
- Explicit scope: 3 documents × 2 chunks
- Structured generation calls: 6
- Wall time: approximately 225 seconds on local LM Studio
- Prompt tokens: 5,889
- Completion tokens: 14,032
- Valid candidates: 128
- Fail-closed invalid candidates: 7
- Exact evidence coverage for valid candidates: 128/128
- Canonical entities: 47
- Active relationship assertions: 45
- Active claims: 36
- Automatic strong-ID merges: 0
- Deferred strong-ID conflicts: 0
- Neo4j projection generation: 1
- Neo4j snapshot objects: 2,082 total
- Neo4j nodes after test cleanup: 832
- Neo4j relationships: 1,250
- Required Neo4j unique constraints: 9/9
- Snapshot hash:
  `1138ebe11047b0d18ffda269512fe95514361e7dcabcd50e4678d6e03ca8eaa2`
- Details:
  `docs/evaluation/graph-pilot-v0-baseline-2026-07-24.md`

Zero automatic merge was the expected safe outcome: the real sample did not
contain two compatible mentions with the same supported strong identifier.
Name similarity never auto-merges.

## Current schema and APIs

Alembic head:

```text
0008_scope_identifiers_by_vault
```

Relevant Phase 4 migrations:

- `0004_phase4_extraction`
- `0005_phase4_registry_seed`
- `0006_phase4_resolution_graph`
- `0007_phase4_resolution_seed`
- `0008_scope_identifiers_by_vault`

Implemented job endpoints:

- `POST /v1/index-jobs`
- `POST /v1/extraction-jobs`
- `POST /v1/resolution-jobs`

Implemented retrieval/graph endpoints:

- `POST /v1/retrieve`
- `GET /v1/entities/{entity_id}`
- `GET /v1/entities/{entity_id}/neighbors`
- `POST /v1/graph/path`

Graph hard limits:

```text
max_hops <= 4
max_paths <= 50
```

The complete contract is in `docs/api/rest-api-v0.md`.

## Important implementation map

Extraction:

- `src/graphrag_service/domain/extraction.py`
- `src/graphrag_service/domain/extraction_schema.py`
- `src/graphrag_service/application/extraction.py`
- `src/graphrag_service/adapters/postgres/extraction_store.py`
- `src/graphrag_service/adapters/providers/lmstudio_generation.py`

Resolution:

- `src/graphrag_service/domain/resolution.py`
- `src/graphrag_service/application/resolution.py`
- `src/graphrag_service/adapters/postgres/resolution_models.py`
- `src/graphrag_service/adapters/postgres/resolution_store.py`

Graph:

- `src/graphrag_service/domain/graph.py`
- `src/graphrag_service/application/graph_projection.py`
- `src/graphrag_service/adapters/postgres/graph_store.py`
- `src/graphrag_service/adapters/neo4j/client.py`
- `src/graphrag_service/api/routes/graph.py`
- `src/graphrag_service/workers/graph_handlers.py`

Pilot runners:

- `scripts/run_retrieval_pilot.py`
- `scripts/run_extraction_pilot.py`
- `scripts/run_graph_pilot.py`

## Resolution behavior

Active strong identifier normalization version: `strong-identifier@1.0`.

Recognized deterministic identifiers:

- IP address;
- MAC address;
- FQDN;
- email address;
- explicitly labelled serial number;
- explicitly labelled system ID;
- explicitly labelled asset ID.

Labelled identifiers are accepted only when the candidate name equals the exact
identifier value in its evidence. Matching also requires equal vault, entity
type, and entity scope.

Without a strong identifier, a candidate gets its own canonical entity. Exact
normalized names can create `resolution_review_candidates`, but never merge.
Fuzzy and embedding candidate generation are not implemented yet; the table and
policy boundary are ready for later review-only methods.

## Projection behavior

PostgreSQL remains canonical. A graph projection:

1. Builds one current PostgreSQL vault snapshot.
2. Computes a canonical SHA-256.
3. Creates a durable `projection_outbox` item and
   `neo4j_projection_runs` audit row.
4. Ensures constraints and indexes.
5. Replaces all managed nodes for that vault inside one Neo4j transaction.
6. Marks the outbox/run succeeded or failed.
7. Skips an already-succeeded identical snapshot.

The snapshot currently has a configurable safety limit:

```text
GKS_GRAPH_PROJECTION_MAX_OBJECTS=20000
```

`ENTITY_LINK` is derived from reified assertions solely for bounded path
queries. It carries assertion metadata and is rebuilt with every snapshot.

## Test and quality state

Latest verified gates:

- Ruff format: clean
- Ruff lint: clean
- Unit tests: 57 passed
- Integration tests: 6 passed
- `pip check`: clean
- Alembic current: `0008_scope_identifiers_by_vault`
- Alembic drift: none
- Docker Compose config: valid
- Live readiness: ready
  - PostgreSQL migration current
  - job queue available
  - Qdrant available
  - Neo4j available with required schema
- Workspace secret scan: clean

Integration tests must use a separate PostgreSQL database. They downgrade to
base and upgrade to head. The retained pilot database must not be used.

## Local machine state at handoff

At the time of this update:

- project PostgreSQL container is healthy;
- project Neo4j container is healthy;
- project Qdrant container is healthy and has no leftover test collections;
- retained canonical database contains exactly one real pilot vault;
- retained Neo4j contains exactly the `phase4-graph-pilot` vault;
- pytest PostgreSQL database and Neo4j test vault were removed;
- BoberDetective PostgreSQL and Qdrant containers remain untouched.

Container/volume state is local only and is not part of Git. A fresh clone must
run migrations, ingest, extraction, resolution, and projection again.

## Security state

- No credential is stored in the repository.
- `.env` is ignored.
- Provider/MCP secrets supplied in chat were used only process-locally.
- Raw provider responses are not stored.
- The workspace was scanned for the supplied secret prefixes and was clean.
- Because tokens appeared in chat, they should be rotated by the user.
- The Obsidian MCP token/config is not required by the current filesystem
  ingestion path and was not persisted.

## Known limitations and open decisions

1. A reviewed semantic gold set is still missing.
2. Human UI/workflow for merge review is not implemented.
3. Fuzzy/embedding resolution candidate generation is not implemented; these
   methods must remain review-only.
4. Personal/customer data classification policy is still open.
5. Current-vs-historical meaning may need explicit frontmatter conventions.
6. Neo4j replacement is one transaction per bounded vault snapshot; larger
   deployments may require generation-based batched replacement while retaining
   atomic activation.
7. Phase 5 entity/vector/graph retrieval fusion is not implemented.
8. Final Assistant integration and stable client example are not implemented.

See `docs/open-questions.md` and `docs/implementation/roadmap.md`.

## Recommended next milestone: Phase 5

Implement GraphRAG retrieval without generating final prose:

1. Add entity seed retrieval from canonical PostgreSQL entities/aliases.
2. Add vector seed retrieval from current Qdrant chunks.
3. Expand only through bounded, active Neo4j assertions.
4. Hydrate every graph result back through current PostgreSQL evidence.
5. Discard stale/missing source paths fail-closed.
6. Deterministically fuse keyword, vector, entity, and graph channels.
7. Return entities, assertions, claims, paths, and exact sources through the
   existing structured retrieval response.
8. Add a multi-hop reviewed evaluation set and provenance regression tests.
9. Update this state file, roadmap, API contract, and baseline after acceptance.

Do not begin broad whole-vault extraction as part of Phase 5.

## Fresh-session checklist

```bash
cd /home/bober/projects/graphrag_system
git status --short --branch
git log -5 --oneline
cat AGENTS.md
cat PROJECT_STATE.md
docker compose ps
.venv/bin/ruff format --check src migrations tests scripts
.venv/bin/ruff check src migrations tests scripts
.venv/bin/pytest -q tests/unit
```

Then verify the current Alembic head and `/ready` before modifying persistence
or projection code.
