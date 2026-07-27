# Adattár- és provenance-modell v0

## 1. Közös konvenciók

- Külső és cross-store azonosító: UUID.
- Időpont: UTC, timezone-aware.
- Path: vaulton belüli normalizált POSIX relatív path.
- Hash: SHA-256 hex.
- Minden származtatott rekord verziózott parser/chunker/schema/model
  hivatkozást kap.
- Qdrant és Neo4j a PostgreSQLből újraépíthető projekció.
- Törölt vagy lecserélt forrás történeti szövegét nem őrizzük meg.

## 2. PostgreSQL modell

### 2.1 Vault és aktuális fájlállapot

#### `vaults`

| Mező | Szerep |
|---|---|
| `id` | stabil vault UUID |
| `name` | emberi név |
| `root_path` | WSL/container oldali root |
| `path_case_mode` | path összehasonlítási mód |
| `include_globs` | alapértelmezetten `**/*.md` |
| `exclude_globs` | `.obsidian`, trash és konfigurált kizárások |
| `internal_uri_prefix` | `vault://<vault-id>/` |
| `obsidian_uri_template` | opcionális |
| `status` | active/disabled/error |
| `created_at`, `updated_at` | auditidő |

Az API nem módosíthat szabadon tetszőleges root pathot. A rootnak
konfigurált allowlisten kell szerepelnie.

#### `vault_file_states`

Az ismert aktuális filesystem snapshot. Nem készül minden scanhez teljes
historikus másolat.

| Mező | Szerep |
|---|---|
| `vault_id`, `relative_path_key` | egyedi aktuális fájl |
| `relative_path` | megjelenítési path |
| `size_bytes`, `mtime_ns` | gyors változásdetektálás |
| `content_sha256` | utolsó ismert tartalomhash |
| `document_id` | feloldott dokumentum |
| `last_seen_scan_id` | utolsó scan |
| `updated_at` | frissítés |

#### `scan_runs`

Scanner version, státusz, kezdés/befejezés, discovered/hashed/new/modified/
renamed/deleted/unchanged/failed számlálók, warningok és hibaösszegzés.

#### `scan_changes`

Csak a scan során változott elemek:

```text
created
modified
renamed
deleted
ambiguous_rename
read_failed
```

Rename esetén old/new path és az azonos hash is rögzül.

### 2.2 Dokumentum és strukturális tartalom

#### `documents`

| Mező | Szerep |
|---|---|
| `id` | stabil dokumentum UUID |
| `vault_id` | tulajdonos vault |
| `current_relative_path` | aktuális path |
| `path_key` | case-normalizált összehasonlítási kulcs |
| `current_version_id` | csak teljes projekció után vált |
| `title` | parser által meghatározott cím |
| `lifecycle_status` | active/deleted/error |
| `first_seen_at`, `last_seen_at`, `deleted_at` | életciklus |

Egyértelmű hash-alapú rename megtartja az `id` értékét.

#### `document_versions`

Történeti metaadatot tarthat, történeti forrásszöveget nem.

| Mező | Szerep |
|---|---|
| `id`, `document_id` | verzióazonosító |
| `content_sha256` | nyers fájl hash |
| `size_bytes`, `mtime_ns` | forrásmetaadat |
| `source_encoding` | v1-ben UTF-8 |
| `parser_name`, `parser_version` | reprodukálhatóság |
| `chunker_name`, `chunker_version` | reprodukálhatóság |
| `frontmatter_json` | biztonságosan parse-olt metadata |
| `quality_flags_json` | parser warning |
| `processing_status` | discovered/parsing/projecting/ready/failed/superseded |
| `created_at`, `superseded_at` | életciklus |

#### `sections`

- `id`, `document_version_id`, `parent_section_id`;
- `heading_level`, `heading_text`;
- `heading_path_json`;
- `heading_occurrence`;
- `char_start`, `char_end`;
- `content_sha256`;
- `ordinal`;
- `metadata_json`.

#### `content_blocks`

- section;
- block type;
- ordinal;
- pontos source span;
- content hash;
- code language;
- block metadata.

Block típusok v0:

```text
paragraph
list
table
fenced_code
indented_code
blockquote
heading
thematic_break
html
other
```

#### `chunks`

Csak az aktuális vagy építés alatt álló dokumentumverzió szövegét tárolja.

- determinisztikus `id`;
- document version és section;
- chunk ordinal;
- pontos source span;
- forráshű Markdown text;
- content hash;
- parser/chunker verzió;
- kanonikus `retrieval_role`: `structural_anchor` vagy `content_evidence`;
- a structural anchor kereshető navigációs seed, de nem önálló bizonyító
  evidence;
- node type és quality metadata;
- token count model profile szerint;
- `search_vector` PostgreSQL `tsvector`;
- projection generation.

Javasolt egyediség:

```text
(document_version_id, char_start, char_end, chunker_version)
```

Javasolt indexek:

- GIN `search_vector`;
- `(document_version_id, ordinal)`;
- `(section_id, ordinal)`;
- `(content_sha256)`;
- `(document_version_id, projection_generation)`.

#### `document_links`

| Mező | Szerep |
|---|---|
| `source_document_version_id` | link forrás |
| `source_chunk_id` | opcionális pontos hely |
| `link_kind` | wikilink/markdown/embed |
| `raw_target` | forráshű cél |
| `target_path`, `target_heading`, `target_block_id` | parse-olt cél |
| `alias` | megjelenített alias |
| `resolved_document_id` | feloldott cél |
| `resolution_status` | resolved/unresolved/ambiguous/external |

Attachment embed felismerhető, de a célfájl nem kerül feldolgozásra.

### 2.3 Jobok és futások

#### `jobs`

- `job_type`;
- `status`: queued/running/succeeded/failed/cancelled;
- `priority`;
- `payload_json`;
- `progress_current`, `progress_total`;
- `checkpoint_json`;
- `lease_owner`, `lease_expires_at`, `heartbeat_at`;
- `attempt_count`, `max_attempts`, `next_attempt_at`;
- `error_code`, `error_message`;
- időpontok.

#### `processing_runs`

Közös run envelope:

- run type és scope;
- vault/document/version;
- parser, prompt, schema, ontology és model profile verzió;
- input paraméterek;
- számlálók;
- validation status;
- error/warning összegzés.

#### `run_inputs` és `run_outputs`

A futás konkrét input- és outputobjektumai, sequence numberrel és opcionális
hash/metaadat payload-dal.

### 2.4 Provider- és verziónyilvántartás

#### `model_profiles`

- kind: generation/embedding/reranker;
- provider type;
- model identifier;
- endpoint configuration reference;
- vector dimension, ha releváns;
- context limit;
- normalized generation settings;
- active status.

#### `prompt_versions`

Prompt neve, verziója, content hash, feladat és státusz. A secret vagy
érzékeny runtime konfiguráció nem kerül ide.

#### `schema_versions`

Pydantic/JSON schema név, verzió és schema hash.

#### `ontology_versions`

Az aktív entity/predicate taxonómia verziója.

### 2.5 Extraction, entity resolution és assertions

#### `extraction_runs`

- processing run;
- source document version/chunkok;
- generation model profile;
- prompt/schema/ontology version;
- raw response hash;
- opcionális korlátozott raw response debug artifact;
- schema és evidence validation status;
- hiba.

#### `entity_candidates`

Az LLM vagy determinisztikus extractor validált, de még nem feltétlenül
kanonizált jelöltje.

#### `entities`

- `entity_type_code`;
- `entity_subtype_code`;
- `entity_scope`;
- canonical name;
- normalized key;
- status;
- rövid, forrással rendelkező leírás;
- merge/supersede mezők.

#### `entity_aliases`

Alias, normalizált alias, nyelv, forrás és validációs státusz.

#### `entity_mentions`

Entity/candidate, chunk, evidence span, surface form, extraction run és
mention status.

#### `relationship_assertions`

- subject entity;
- kontrollált predicate;
- object entity;
- assertion kind;
- review status;
- network layer és egyéb typed properties;
- extraction run;
- aktív/inaktív állapot.

#### `claims`

Forráshű és opcionális normalizált állításszöveg, assertion kind, review
status és extraction run.

#### `evidence_spans`

| Mező | Szerep |
|---|---|
| `document_version_id`, `section_id`, `chunk_id` | forrás |
| `quote_text` | csak aktuális forráshoz |
| `char_start`, `char_end` | pontos globális span |
| `quote_sha256`, `chunk_content_sha256` | integritás |
| `extraction_run_id` | eredet |
| `validation_status` | exact/normalized-invalid/missing |

Törölt vagy superseded forrásnál a quote törlődik a származtatott
tartalommal együtt. Kizárólag erre támaszkodó assertion inaktiválódik.

#### `resolution_decisions`

- candidate entityk;
- döntés: merge/split/keep_separate/defer;
- method: deterministic/human;
- score és rule version;
- indoklás;
- döntéshozó és időpont.

Fuzzy vagy embedding alapú jelölt nem hajthat végre automatikus merge-et.

### 2.6 Projekció és query audit

#### `projection_outbox`

- target: qdrant/neo4j;
- operation: upsert/delete;
- object type/id;
- generation;
- idempotency key;
- payload reference;
- status, attempts, last error.

#### `projection_status`

Dokumentumverzió és target szerinti projected count, expected count,
checkpoint, státusz és utolsó siker.

#### `query_runs`

Query hash, scope, strategy, limitek, model profile, időtartam, warningok.
Alapértelmezésben nem őriz teljes query kontextust vagy source quote-ot
korlátlan ideig.

#### `retrieval_hits`

Query run, object ID, channel rank/score, fusion score, match type,
selected/context-only flag.

## 3. Qdrant modell

### 3.1 Collectionök

Logikai aliasok:

```text
gks_chunks_active
gks_sections_active
gks_entities_active
```

Fizikai név:

```text
gks_<kind>__<embedding-profile>__v<schema>
```

Modellváltáskor új collection épül, validáció után aliasváltással.

### 3.2 Chunk point

Point ID a PostgreSQL chunk UUID.

Payload:

```text
vault_id
document_id
document_version_id
section_id
chunk_id
relative_path
heading_path
content_sha256
parser_version
chunker_version
retrieval_role
language
tags
projection_generation
is_current
```

Payload index javasolt:

- vault ID;
- document ID;
- document version ID;
- section ID;
- `is_current`;
- tag és language csak tényleges filterigény esetén.

A teljes chunk text PostgreSQLből hidratálandó.

### 3.3 Section és entity collection

Section embedding nem kötelező az első globális indexben. Csak mérés után
aktiválható.

Entity point:

- canonical név;
- aliasok;
- rövid, evidence-alapú leírás;
- entity type/subtype/scope;
- vault scope és entity ID.

## 4. Neo4j modell

### 4.1 Node-ok

```text
Vault
Document
DocumentVersion
Section
Chunk
Entity
RelationshipAssertion
Claim
Evidence
```

Minden node `id` tulajdonsága a PostgreSQL UUID string alakja.

### 4.2 Szerkezeti élek

```text
(Vault)-[:CONTAINS]->(Document)
(Document)-[:HAS_VERSION]->(DocumentVersion)
(DocumentVersion)-[:HAS_SECTION]->(Section)
(Section)-[:HAS_CHILD]->(Section)
(Section)-[:HAS_CHUNK]->(Chunk)
(Document)-[:LINKS_TO]->(Document)
```

### 4.3 Szemantikai élek

```text
(Chunk)-[:MENTIONS]->(Entity)

(RelationshipAssertion)-[:SUBJECT]->(Entity)
(RelationshipAssertion)-[:OBJECT]->(Entity)
(RelationshipAssertion)-[:SUPPORTED_BY]->(Evidence)

(Claim)-[:ABOUT]->(Entity)
(Claim)-[:SUPPORTED_BY]->(Evidence)

(Evidence)-[:LOCATED_IN]->(Chunk)
```

Az assertion reifikált node, mert egy kapcsolatnak több evidence,
extraction run, review státusz és typed property tartozhat hozzá.

A Phase 4 vetület ENTITY_LINK gyorsítóéle kizárólag bounded path queryhez
használt, assertion ID-t hordozó, újraépíthető materializáció; nem kanonikus
adat és minden vault snapshot-cserénél újragenerálódik.

### 4.4 Constraint és index

- unique constraint minden label `id` mezőjére;
- entity type + normalized key index;
- document vault + path index;
- assertion predicate és aktív státusz index;
- evidence chunk ID index.

## 5. Stabil ID szabályok

- Vault: létrehozáskor UUID.
- Document: létrehozáskor UUID, rename esetén megmarad.
- Document version: UUID vagy determinisztikus UUID a document ID + hashból.
- Section: determinisztikus UUID a version + heading path + occurrence +
  source span alapján.
- Chunk: determinisztikus UUID a version + section + span + chunker version
  alapján.
- Qdrant point: azonos a megfelelő PostgreSQL objektum UUID-jával.
- Neo4j node ID property: azonos PostgreSQL UUID.

