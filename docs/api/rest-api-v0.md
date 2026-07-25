# REST API v0

## 1. Alapelvek

- JSON request/response.
- `/v1` alatt verziózott üzleti API.
- `/health` és `/ready` nem verziózott.
- Hosszú művelet `202 Accepted` és tartós `job_id`.
- Cursor pagination.
- Jobindításnál opcionális `Idempotency-Key`.
- Alapértelmezett bind: `127.0.0.1`.
- Minden `/v1` végpont statikus service tokent kér.
- A token környezeti változóból érkezik és nem kerül logba.

## 2. Health és readiness

### `GET /health`

Csak process liveness. Nem kérdez külső szolgáltatást.

```json
{
  "status": "ok",
  "service": "graphrag-knowledge-service",
  "version": "0.1.0"
}
```

### `GET /ready`

Ellenőrzi:

- PostgreSQL kapcsolat és migration head;
- Qdrant elérhetőség és aktív alias;
- Neo4j kapcsolat és schema constraint-ek;
- job queue;
- konfigurált provider státusz.

Provider hiba lehet degradált állapot, ha a keyword retrieval még működik.
A response jelzi, mely capability nem érhető el.

## 3. Hibaformátum

RFC 9457-szerű problem response:

```json
{
  "type": "https://local/errors/vault-not-readable",
  "title": "Vault is not readable",
  "status": 503,
  "code": "vault_not_readable",
  "detail": "The configured vault root cannot be read.",
  "request_id": "..."
}
```

A publikus hiba nem tartalmazhat secretet, raw provider payloadot vagy
korlátlan filesystem pathot.

## 4. Vault API

### `POST /v1/vaults`

Regisztrál egy allowlisten szereplő vaultot.

```json
{
  "name": "company-knowledge",
  "root_path": "/mnt/d/hack/MCP_Test_ObsidianVault",
  "include_globs": ["**/*.md"],
  "exclude_globs": [".obsidian/**", ".trash/**"],
  "obsidian_uri_template": null
}
```

### `GET /v1/vaults`

Cursoros lista.

### `GET /v1/vaults/{vault_id}`

Vault állapot, utolsó scan, dokumentum- és projection-számok.

### `POST /v1/vaults/{vault_id}/scans`

Response:

```json
{
  "job_id": "...",
  "job_type": "scan_vault",
  "status": "queued"
}
```

Alapértelmezésben a scan létrehozza a változáslistát, de nem blokkol az
összes embedding/extraction befejezéséig.

## 5. Index és job API

### `POST /v1/index-jobs`

A Phase 3 implementált kérés csak opcionális vault_id mezőt fogad, és a
project_chunks tartós jobot indítja. A válasz 202 Accepted, job_id és queued
státusz. Az alábbi összetett scope/stages szerződés későbbi bővítés.
```json
{
  "vault_id": "..."
}
```

Az `extract_knowledge_graph` nem része automatikusan minden alapindexnek.

### `POST /v1/extraction-jobs`

A Phase 4 első szelete explicit vault- és dokumentumscope-ot követel. A
`max_chunks` konfigurált felső korlátja alapértelmezetten 20; üres
`document_ids` nem engedélyezett. A végpont csak tartós jobot indít.

```json
{
  "vault_id": "...",
  "document_ids": ["...", "..."],
  "max_chunks": 6
}
```

Válasz: `202 Accepted`, `job_type=extract_knowledge_pilot`. A generation
provider kikapcsolt állapotában a végpont fail-closed `503` választ ad. A job
eredménye candidate audit; nem ír Neo4j gráfot és nem aktivál assertiont.

### `POST /v1/resolution-jobs`

Explicit extraction runokat old fel, majd a megadott vault aktuális
PostgreSQL-állapotából outbox-audittal újraépíti a Neo4j snapshotot.

```json
{
  "vault_id": "...",
  "extraction_run_ids": ["...", "..."]
}
```

Válasz: `202 Accepted`, `job_type=resolve_and_project_graph`. A worker
ellenőrzi, hogy minden run a megadott vaulthoz tartozik. Az erős azonosító
nélküli jelöltek külön kanonikus entitást kapnak; név-, fuzzy- vagy embedding
hasonlóság nem végezhet automatikus merge-et.

### `GET /v1/jobs/{job_id}`

```json
{
  "id": "...",
  "job_type": "index_changes",
  "status": "running",
  "progress": {
    "current": 320,
    "total": 1000,
    "unit": "documents"
  },
  "stage": "embed_chunks",
  "attempt": 1,
  "warnings": [],
  "error": null
}
```

### `POST /v1/jobs/{job_id}/cancel`

Kooperatív cancel. Csak biztonságos checkpointnál áll le.

## 5.1. Helyi operátori felület

A /operator HTML-oldal nem tartalmaz secretet; a böngészőben megadott service
tokennel hívja az alábbi, normál /v1 védelem alatt álló végpontokat:

- GET /v1/operator/overview: readiness, vault/gráf számlálók és legutóbbi jobok;
- GET /v1/operator/vaults/{vault_id}/preview: írásmentes inkrementális diff;
- GET /v1/operator/vaults/{vault_id}/pending-refresh: a legutóbbi,
  Neo4j-projekcióval még le nem zárt scan dokumentumai és extraction állapotuk;
- GET /v1/operator/vaults/{vault_id}/documents: aktuális dokumentumválasztó;
- POST /v1/operator/vaults/{vault_id}/graph-rebuild: modellhívás nélküli,
  tartós rebuild_graph_projection job.

A módosító gombok a meglévő scan, index, extraction és resolution job API-kat
használják. Az előnézet önmagában nem hoz létre scan runt és nem módosítja a
kanonikus PostgreSQL-állapotot.
A pending-refresh nem a pillanatnyi filesystem diffet ismétli: a legutóbbi
változást tartalmazó sikeres scan auditjából állítja vissza a még be nem fejezett
workflow-t, és egy újabb sikeres Neo4j-projekció zárja le.

## 6. Retrieval API

### `POST /v1/retrieve`

A Phase 5 implementált kérésmezői: `query`, `strategy` (`keyword`,
`semantic` vagy `hybrid`), `limit` (1–50) és opcionális `vault_id`. A `hybrid`
stratégia determinisztikus query plannert, entity/vector seedeket, korlátos
Neo4j bejárást és claim retrievalt használ. Minden assertion, claim és path
csak aktuális PostgreSQL exact evidence-hidratálás után kerülhet a válaszba.
A `context_chunks` az azonos szakasz szomszédait és a szemantikus eredményeket
alátámasztó source chunkokat hordozza. A végpont nem készít végső természetes
nyelvű választ.

```json
{
  "query": "Hogyan kezelhető egy Huawei ONT?",
  "strategy": "hybrid",
  "limit": 10,
  "vault_id": "..."
}
```

Strategy v0:

```text
keyword
semantic
hybrid
```

Az `entity` és `graph` response query type/tervezési fogalom, nem elfogadott
request strategy. Hybrid kérésnél a determinisztikus planner a kérdés
szövegjegyeiből választ `hybrid`, `entity` vagy `graph` query type-ot; ehhez nem
hív generation modellt.

### Retrieval response

```json
{
  "query_type": "hybrid",
  "retrieval_plan": ["keyword", "semantic", "entity", "graph", "claim"],
  "planner_reason_code": "general_hybrid",
  "strategy": "hybrid",
  "chunks": [],
  "context_chunks": [],
  "entities": [],
  "relationships": [],
  "claims": [],
  "retrieval_paths": [],
  "sources": [],
  "warnings": [],
  "truncated": false,
  "confidence": null
}
```

Minden chunk keyword, semantic, graph, claim és fusion score mezőt hordoz.
A `retrieval_plan` a planner által kért csatornákat jelzi; az üres vagy degradált
csatornát a warningok és a tényleges találati listák teszik láthatóvá. A
`planner_reason_code` stabil, géppel feldolgozható routing-indok. A `sources`
deduplikált, és minden visszaadott relationship, claim és path aktuális
forráschunkja szerepel benne.

### `POST /v1/query`

Fenntartott későbbi orchestration végpont. A Phase 5 determinisztikus
classification és seed-tervezés jelenleg közvetlenül a `/v1/retrieve` része;
külön `/v1/query` végpont nincs implementálva.

## 7. Source szerződés

```json
{
  "source_id": "...",
  "vault_id": "...",
  "document_id": "...",
  "document_version_id": "...",
  "section_id": "...",
  "chunk_id": "...",
  "relative_path": "Operations/ONT/activation.md",
  "heading_path": ["ONT", "Aktiválás", "Hibaág"],
  "quote": "A forráshű szövegrészlet.",
  "char_start": 1200,
  "char_end": 1230,
  "content_hash": "...",
  "source_uri": "vault://<vault-id>/Operations/ONT/activation.md",
  "obsidian_uri": null
}
```

Ha a forrás időközben törlődött vagy superseded lett, nem adunk vissza
történeti quote-ot aktív retrieval találatként.

## 8. Dokumentum API

### `GET /v1/documents/{document_id}`

Aktuális verzió, path, frontmatter, heading summary, quality és projection
állapot.

### `GET /v1/documents/{document_id}/sections`

Cursoros heading tree vagy lapos lista parent ID-val.

### `GET /v1/sources/{source_id}`

Aktuális, valid source részlet. Törölt/superseded forrásnál 410 Gone
használható.

## 9. Entity és graph API

### `GET /v1/entities/{entity_id}`

Kanonikus név, type/subtype/scope, aliasok, aktív evidence-ek.

### `GET /v1/entities/{entity_id}/neighbors`

Query paraméterek:

```text
predicate
entity_type
max_results
include_unreviewed
```

### `POST /v1/graph/path`

```json
{
  "from_entity_id": "...",
  "to_entity_id": "...",
  "max_hops": 3,
  "max_paths": 10,
  "predicate_allowlist": [],
  "include_unreviewed": true
}
```

Hard server limit:

```text
max_hops <= 4
max_paths <= 50
```

## 10. Warningok

Típusos warning példák:

```text
partial_projection
provider_unavailable
result_truncated
ambiguous_link
ambiguous_entity
stale_hit_discarded
source_unavailable
graph_expansion_limited
```

