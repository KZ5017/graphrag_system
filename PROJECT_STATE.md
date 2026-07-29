# GraphRAG Knowledge Service – project state

Last updated: 2026-07-29
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
human merge-review workflow exist.

Phase 5 GraphRAG retrieval is complete: deterministic small-model-safe query
planning, keyword/vector/entity seeds, bounded Neo4j expansion, canonical
relationship and claim retrieval, deterministic multi-channel RRF, and current
PostgreSQL evidence/source hydration are integrated in `POST /v1/retrieve`.
A reviewed four-case acceptance set includes entity, relationship, claim and
verified two-hop retrieval with complete provenance.

A production-like Assistant query exposed and fixed a precision defect where a
partial generic `ügyfél` entity/alias match amplified unrelated SMTP evidence
through graph and claim channels. Hybrid retrieval now applies a strong
keyword/semantic consensus gate, permits derived graph/claim expansion only
from an explicit full-name entity anchor, and returns structured evidence only
when its current source chunk is visible. The shorter reviewed Kiskőrös
night-outage formulation returns only night-duty sources. The longer natural
formulation can still lack a strong keyword/semantic consensus and then admit
unrelated content chunks; this remains an explicit Phase 7 precision case, not
a prompt-level workaround.

A retrieval most dokumentum-koherencia bővítést is alkalmaz: ha az erős
keyword–semantic konszenzuskapu után pontosan egyetlen nem-index dokumentum
marad jelöltként, a rendszer az aktuális dokumentumverzió releváns
fejezetfájának leszármazott chunkjait is hidratálja, dokumentumonként legfeljebb
32 chunkkal és összesen 30 000 karakterrel. Többértelmű, többdokumentumos
helyzetben a bővítés nem indul el. A rangsorolt találatok precíziós kapuja
változatlan maradt. Az Android hívásátirányítási kérdés fájlnév nélkül 2
rangsorolt találat mellé a teljes útmutató 22 további szakaszát kapta meg,
idegen vagy SMTP-forrás nélkül. A reasoning nélküli Assistant smoke teljes,
forráshivatkozott beállítási választ adott APN-, telefonszám-, ellenőrzési és
hibaelhárítási lépésekkel.

A chunker 1.1.0 és a `0009_chunk_retrieval_roles` migráció minden chunkot
kanonikus `structural_anchor` vagy `content_evidence` szereppel lát el. A csak
címsorból és elválasztóból álló horgony továbbra is keyword/vector seed lehet,
de önálló végső evidence nem lehet. Ha a rangsorolt horgonyok pontosan egyetlen
nem-index dokumentumra mutatnak, a backend abból a dokumentumból korlátosan
hidratálja a tartalmi chunkokat (legfeljebb 32 chunk és 30 000 karakter); a
content chunkok teljes heading pathja megőrzi a szerkezeti kontextust. A
Kiskőrös élő próba így már átadja a korábban hiányzó `04:00 előtt` + `minimum
150 végpont` szabályt, miközben a puszta `ÉRTESÍTENI KELL, HA` címsor nem kerül
önálló forrásként a modellhez. A nyilvános retrieval/Assistant response schema
nem változott.

A helyi operátori dashboard a /operator útvonalon elkészült. A tokenvédett
operátori API kanonikus állapotösszesítést, read-only vault-diff előnézetet,
dokumentumlistát és tartós pending-refresh állapotot ad. A felület a meglévő
scan, Qdrant projection, extraction és resolution jobokat vezérli, továbbá
külön idempotens rebuild_graph_projection jobot biztosít. A dokumentumok,
a gráfépítésre váró extraction futások és a művelet nélküli jobnapló külön
panelekben jelennek meg.
A kézi **Frissítés** teljesen újraolvassa az operator állapotát. Ha a már
betöltött UI mögött az API megszűnik, a fetch-hiba piros kapcsolatvesztési
állapotot, elhalványított „utoljára ismert” adatokat és tiltott műveleti gombokat
ad; a szolgáltatás visszatérésekor ugyanaz a Frissítés állítja vissza az élő állapotot. Automatikus polling nincs.
A dashboard a Qdrant szolgáltatás livenessén túl a vektorprojekció használhatóságát
is ellenőrzi: az aktív embedding profil elvárt fizikai kollekcióját, az aktív
aliast és a Qdrant pontszámát a PostgreSQL aktuális chunk-számával veti össze.
Eltéréskor rebuild_required állapotot és külön, tartós
rebuild_vector_projection helyreállító jobot kínál. Ez nem az inkrementális
project_chunks frissítés: kontrolláltan újraépíti a Qdrant-projekciót az összes
aktuális kanonikus chunkból, majd visszaellenőrzi az aliast és a pontszámot.

Az öt módosított Helyi_AI_Asszisztens dokumentum teljes inkrementális
feldolgozása befejeződött: a scan, Qdrant projection, öt korlátos extraction
futás, resolution és a második Neo4j-projekció sikeres. Nincs függő frissítés.

Phase 6 Assistant integration is complete in the sibling AI_Assistant
repository. The explicit user-selected GraphRAG mode deterministically calls
the authenticated POST /v1/retrieve endpoint, validates and size-bounds the
structured response, builds source-labelled evidence, supports reasoning,
remains mutually exclusive with the two MCP modes, and fails without silent
fallback. Both runtimes remain independently startable and stoppable.

## Verified baselines

### Vault and ingest

- Vault: `/mnt/d/hack/MCP_Test_ObsidianVault`
- Mode: read-only
- Markdown documents: 18
- Latest graph pilot scan: 18 hashed, 18 parsed, 0 failed
- Structural graph covers all current documents.
- Semantic graph covers the earlier pilot scope and all five refreshed Assistant documents; current graph counts are recorded below.

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

### GraphRAG retrieval acceptance baseline

- Reviewed cases: 4
- Passed cases: 4/4
- Query type, planner reason, source, entity, predicate and claim checks: 100%
- Bounded path and complete hydrated provenance checks: 100%
- Verified two-hop path:
  `Obsidian vault → Tudásbázis mód → általános modellválaszok`
- API latency: p50 357.08 ms, p95 432.36 ms
- Retrieval warnings: 0
- Details:
  `docs/evaluation/graphrag-retrieval-v1-baseline-2026-07-24.md`

This is a small, reviewed plumbing/provenance acceptance set over the three
explicitly extracted pilot documents. It does not establish whole-vault
precision or calibrated confidence.

### Incremental Assistant-document refresh

The five modified Helyi_AI_Asszisztens documents were fully processed on
2026-07-25 after the initial baseline:

- Changed documents: 5
- Extracted current chunks: 28
- Prompt tokens: 21,975
- Completion tokens: 52,520
- Valid candidates: 318
- Fail-closed invalid candidates: 39
- Resolution review candidates: 32
- Current canonical entities: 172
- Current active relationship assertions: 137
- Current active claims: 113
- Neo4j projection generation: 2
- Snapshot objects: 3,284
- Pending refresh: none

These are current operational counts, not a replacement for the fixed
three-document graph baseline. The expanded graph needs a new reviewed
retrieval-quality baseline before broader extraction.

## Current schema and APIs

Alembic head:

```text
0009_chunk_retrieval_roles
```

Relevant schema migrations:

- `0004_phase4_extraction`
- `0005_phase4_registry_seed`
- `0006_phase4_resolution_graph`
- `0007_phase4_resolution_seed`
- `0008_scope_identifiers_by_vault`
- `0009_chunk_retrieval_roles`

Implemented job endpoints:

- `POST /v1/index-jobs`
- `POST /v1/extraction-jobs`
- `POST /v1/resolution-jobs`

Implemented retrieval/graph endpoints:

- `POST /v1/retrieve` (keyword, semantic, or hybrid; hybrid uses a
  deterministic planner plus entity/graph/claim expansion)
- `GET /v1/entities/{entity_id}`
- `GET /v1/entities/{entity_id}/neighbors`
- `POST /v1/graph/path`

Implemented operator endpoints:

- GET /operator (local static UI; no-store)
- GET /v1/operator/overview
- GET /v1/operator/vaults/{vault_id}/preview
- GET /v1/operator/vaults/{vault_id}/documents
- GET /v1/operator/vaults/{vault_id}/pending-refresh
- POST /v1/operator/vaults/{vault_id}/graph-rebuild
- POST /v1/operator/vector-rebuild (teljes, PostgreSQL-ből visszaépülő
  Qdrant-projekció helyreállítása)

Every relationship, claim and graph path returned by retrieval must hydrate
through active canonical PostgreSQL state and exact evidence on the current
document version.

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

GraphRAG retrieval:

- `src/graphrag_service/application/phase5_retrieval.py`
- `src/graphrag_service/application/query_planner.py`
- `src/graphrag_service/application/graph_retrieval.py`
- `src/graphrag_service/adapters/postgres/graphrag_retrieval_store.py`
- `src/graphrag_service/api/routes/phase5_retrieval.py`
- `src/graphrag_service/api/schemas/phase5_retrieval.py`

Operator dashboard:

- src/graphrag_service/application/operator.py
- src/graphrag_service/adapters/postgres/operator_store.py
- src/graphrag_service/api/routes/operator.py
- src/graphrag_service/api/schemas/operator.py
- src/graphrag_service/api/static/operator.html

Local runtime:

- scripts/start-system.ps1
- scripts/stop-system.ps1
- scripts/native-runtime.sh

Pilot runners:

- `scripts/run_retrieval_pilot.py`
- `scripts/run_extraction_pilot.py`
- `scripts/run_graph_pilot.py`
- `scripts/run_phase5_evaluation.py`

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
- Unit tests: 66 passed
- Integration tests: 7 passed
- `pip check`: clean
- Alembic current: `0009_chunk_retrieval_roles`
- Alembic drift: none
- Docker Compose config: valid
- Live API/worker build and startup: verified
  - PostgreSQL migration current
  - job queue available
  - Qdrant available
  - Neo4j available with required schema
  - generation és embedding provider is available through native WSL runtime
- Workspace secret scan: clean

Integration tests must use a separate PostgreSQL database. They downgrade to
base and upgrade to head. The retained pilot database must not be used.

## Local machine state at handoff

At the time of this update:

- GraphRAG API and worker are running natively in WSL.
- PostgreSQL, Qdrant and Neo4j are running in the dedicated Compose project and
  are healthy; readiness is ready.
- Both LM Studio providers are available on Windows loopback 127.0.0.1:1234:
  qwen/qwen3.5-9b and text-embedding-bge-m3.
- The canonical PostgreSQL database contains one real read-only pilot vault with
  19 active Markdown documents and 290 current chunks.
- The 2026-07-25 incremental refresh processed five modified
  Helyi_AI_Asszisztens documents: 28 chunks, 21,975 prompt tokens,
  52,520 completion tokens, 318 valid candidates and 39 fail-closed invalid
  candidates across five extraction runs.
- Resolution and projection job 277b20fb-d7c4-47d3-8613-508a6a810345
  succeeded. Current canonical state: 172 entities, 137 active relationship
  assertions and 113 active claims.
- Neo4j projection generation 2 contains 3,284 snapshot objects with SHA-256
  c658a5bd9032ec51723e4e599170ebc97f2d426d9527cbfeceedc6d6e6f96361.
- 2026-07-29 vector-projection recovery: the Qdrant persistent volume had no
  active collection, so semantic retrieval degraded to keyword/graph channels.
  The new Operator integrity check correctly reported rebuild_required.
  The controlled rebuild_vector_projection job rebuilt the active
  gks_chunks__text_embedding_bge_m3_1024__v1 collection from PostgreSQL.
  The post-rebuild check is ready: 290 expected / 290 actual points, active
  alias correct, no pending or failed projection work; active dimension is 1024.
- 2026-07-29 runtime port alignment: Docker Qdrant is host-mapped to 6433/6434. The native WSL API and worker therefore use GKS_QDRANT_URL=http://127.0.0.1:6433 in the local environment; the same explicit value is present in .env.example. After the native runtime restart, GET /ready again reported Qdrant as available.
- 2026-07-29 API-port startup alignment: `start-system.ps1` validated formában
  kiolvassa a `.env` `GKS_API_PORT` értékét (hiányzó értéknél 8080), és ezt
  használja a natív readiness-várakozáshoz, valamint a kijelzett health/ready URL-ekhez.
- The operator pending-refresh state is false and contains no documents.
- GraphRAG uses PostgreSQL host port 56001; the separate AI Assistant PostgreSQL
  remains on 56000. This avoids the Windows által fenntartott `55432–55731` host-port tartomány.
  A full `start-system.ps1 -SkipBuild` smoke on 2026-07-28 verified healthy
  PostgreSQL, Qdrant and Neo4j, current migration, and ready native API/worker.
  BoberDetective containers and volumes were not modified.
- The sibling AI Assistant GraphRAG integration is implemented and live-smoke
  verified, but remains a separate repository and separate Git worktree.

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

1. A broad reviewed semantic gold set is still missing.
2. Human UI/workflow for merge review is not implemented.
3. Fuzzy/embedding resolution candidate generation is not implemented; these
   methods must remain review-only.
4. Personal/customer data classification policy is still open.
5. Current-vs-historical meaning may need explicit frontmatter conventions.
6. Neo4j replacement is one transaction per bounded vault snapshot; larger
   deployments may require generation-based batched replacement while retaining
   atomic activation.
7. The Phase 5 reviewed set has only four positive cases and predates the
   expanded Assistant-document graph. Whole-vault precision, negative queries
   and confidence calibration remain unmeasured.
   A hosszabb Kiskőrös/02:12/167 modem élő kérdés 2026-07-26-án a helyes pozitív
   döntési ágat már megkapta, de konszenzus hiányában SMTP- és más témán kívüli
   content chunkokat is visszaadott. Az anchor-kezelés ezt szándékosan nem
   próbálja relevanciaszűrésnek álcázni.
8. The Assistant consumer is implemented and live-smoke verified, but there is
   no version-pinned cross-repository CI contract yet. Its current worktree is
   external to this repository and must be committed separately there.
9. The operator dashboard has unit coverage and live smoke coverage, but the
   full multi-step state machine does not yet have a dedicated integration test.
10. Service-token rotation is restart-based and lacks a documented coordinated
    rotation procedure.

See docs/open-questions.md and docs/implementation/roadmap.md.

## Recommended next milestone: Phase 7 quality and operational hardening

1. Extend the reviewed retrieval corpus with positive, negative,
   insufficient-source and topic-overlap cases over the current graph.
2. Turn the Kiskőrös/SMTP precision defect into a permanent acceptance case.
3. Turn the Android document-coherence case into a permanent acceptance case.
4. Add operator workflow integration coverage for scan, projection, extraction,
   resolution, rebuild, interruption and page reload.
5. Add a version-pinned compatibility test for the Assistant retrieval client.
6. Keep broad whole-vault extraction blocked until precision is reviewed.

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
