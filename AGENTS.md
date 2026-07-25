# GraphRAG Knowledge Service – agent instructions

This file applies to the entire repository. Read it together with
`PROJECT_STATE.md` before changing code.

## Mission and boundaries

Build a local, auditable GraphRAG knowledge service for read-only Obsidian
vaults. The service is independent from BoberDetective at runtime.

- Primary workspace: `/home/bober/projects/graphrag_system`
- Initial vault: `/mnt/d/hack/MCP_Test_ObsidianVault`
- The vault is strictly read-only. Never write metadata, IDs, caches, or fixes
  into it.
- `/home/bober/projects/Codex_BoberDetective` is reference-only and must not be
  edited from this repository.
- Do not stop, remove, rename, or reuse BoberDetective containers or volumes.
- Default API binding is loopback and every `/v1` endpoint requires the service
  token.

## Architectural invariants

These are decisions, not implementation suggestions:

1. PostgreSQL is the canonical control, audit, provenance, resolution, and
   assertion store.
2. Qdrant and Neo4j are idempotent, reconstructable projections. Never make
   either one the source of truth.
3. Obsidian Markdown is the only human-authored source of truth.
4. No source means no active assertion.
5. Exact quotes may only refer to the current source version. Historical source
   text is not retained.
6. Replacing/deleting a source must cascade its evidence and source-derived
   semantic text. Reconciliation may rebuild remaining current knowledge.
7. Provider output is untrusted. Pydantic schema, controlled ontology, exact
   evidence, and endpoint validation are authoritative gates.
8. Schema-invalid provider output must never be partially materialized.
9. `assertion_kind` and `review_status` are separate concepts.
10. Entity types, subtypes, predicates, scopes, and typed properties come from
    the versioned ontology. The LLM cannot invent registry values.
11. Automatic entity merge is allowed only for an equal, version-normalized
    strong identifier with compatible vault, type, and scope.
12. Exact/fuzzy names, abbreviations, embeddings, or model-family similarity
    can only create review candidates; they never auto-merge.
13. Relationship assertions remain reified Neo4j nodes with evidence.
    `ENTITY_LINK` is a query-only, rebuildable path accelerator and is not
    canonical data.
14. Generation and embedding providers remain separate ports and profiles.
15. Long-running work goes through the durable PostgreSQL job queue.

The accepted decisions live in `docs/adr/`; update or add an ADR before
intentionally changing an invariant.

## Current runtime choices

- Python 3.12
- PostgreSQL 16
- Qdrant 1.15.x
- Neo4j 5.26 Community
- Generation: LM Studio OpenAI-compatible API, model
  `qwen/qwen3.5-9b`, `reasoning_effort=none`
- Embeddings: `text-embedding-bge-m3`, runtime dimension 1024
- Active ontology: `telecom-core@0.1`
- Strong identifier normalization: `strong-identifier@1.0`
- Alembic application head: check
  `src/graphrag_service/adapters/postgres/migrations.py`

Never commit provider keys, service tokens, database passwords, MCP bearer
tokens, `.env`, local databases, model files, or raw provider responses.
Credentials must be supplied through `GKS_*` environment variables.

## Code organization

- `src/graphrag_service/domain/`: pure domain values and validation
- `src/graphrag_service/application/`: use-case orchestration
- `src/graphrag_service/ports/`: external capability contracts
- `src/graphrag_service/adapters/postgres/`: canonical persistence and outbox
- `src/graphrag_service/adapters/qdrant/`: vector projection
- `src/graphrag_service/adapters/neo4j/`: graph projection and bounded queries
- `src/graphrag_service/adapters/providers/`: LM Studio provider adapters
- `src/graphrag_service/api/`: FastAPI composition, schemas, and routes
- `src/graphrag_service/workers/`: durable job handlers
- `migrations/versions/`: forward and downgrade Alembic migrations
- `scripts/`: bounded, explicit pilot runners
- `tests/unit/`: isolated behavior and contract tests
- `tests/integration/`: dedicated-service acceptance tests
- `docs/`: architecture, ADRs, API, ontology, roadmap, operations, evaluations

Keep the modular-monolith dependency direction. Domain code must not depend on
FastAPI, SQLAlchemy, Neo4j, Qdrant, or provider SDKs.

## Working rules

- Preserve user changes and inspect the worktree before editing.
- Prefer `rg`/`rg --files` for discovery.
- Work inside the WSL project path; do not modify Windows attachment files.
- Use forward migrations for an already-published schema. Keep ORM metadata and
  Alembic drift-free.
- Keep queries bounded. Current hard graph limits are 4 hops and 50 paths.
- Keep extraction scopes explicit and bounded. Do not automatically extract the
  whole vault.
- Do not persist raw model responses. Store hashes, usage, safe error codes, and
  validated candidates only.
- Public errors and logs must not contain secrets, raw provider payloads, or
  unrestricted filesystem paths.
- Any source-derived canonical text needs a deletion/cascade test.
- Any projection change needs idempotency and reconstruction coverage.
- Any merge-rule change needs positive strong-ID and negative name-only tests.
- Do not force-push or rewrite shared history unless the user explicitly asks.

## Quality gates

Run these before committing:

```bash
.venv/bin/ruff format --check src migrations tests scripts
.venv/bin/ruff check src migrations tests scripts
.venv/bin/pytest -q tests/unit
.venv/bin/python -m pip check
GKS_POSTGRES_DSN=... .venv/bin/alembic check
docker compose config --quiet
```

For integration tests, use a dedicated PostgreSQL database such as
`graphrag_test`; tests perform Alembic downgrade/upgrade and must never target
the retained pilot database.

```bash
GKS_TEST_POSTGRES_DSN=.../graphrag_test \
GKS_TEST_NEO4J_PASSWORD=... \
GKS_TEST_NEO4J_URI=bolt://127.0.0.1:7687 \
GKS_TEST_QDRANT_URL=http://127.0.0.1:6433 \
.venv/bin/pytest -q tests/integration
```

Clean only exact test databases/vault projections after integration runs.

## Resume protocol

At the start of a future session:

1. Read `PROJECT_STATE.md`, `README.md`, and the current roadmap.
2. Inspect `git status`, recent commits, and the Alembic head.
3. Verify `.env` exists locally without displaying its values.
4. Check Docker service health and `/ready`.
5. Confirm LM Studio has the configured generation/embedding models before a
   provider-dependent pilot.
6. Run the relevant unit tests before and after changes.
7. Update `PROJECT_STATE.md` whenever a milestone, migration head, test count,
   pilot baseline, known limitation, or next step changes materially.

Phase 6 Assistant integration is implemented in the sibling
/home/bober/projects/AI_Assistant repository and verified against this
service. Treat that repository as reference-only from this workspace.

The next planned milestone is retrieval quality and operational hardening:
expand the reviewed positive/negative corpus over the refreshed graph, add
operator-workflow integration coverage, and retain deterministic, source-bound
answers before broadening extraction scope.
