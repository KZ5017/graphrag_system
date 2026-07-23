# Megvalósítási roadmap

## Fázis 0 – Feltárás és tervezés

**Állapot:** lezárva (2026-07-23).

### Scope

- architektúra;
- adattári felelősségek;
- read-only modell;
- inkrementális ingest;
- provenance;
- REST API v0;
- kezdeti távközlési ontológia;
- kapacitási terv;
- ADR-ek;
- nyitott mérések.

### Kilépési feltétel

- blokkoló útvonal- és rendszerhatár-döntések lezárva;
- architektúra dokumentált;
- nincs alkalmazáskód;
- Phase 1 scope egyértelmű.

## Fázis 1 – Infrastrukturális alap

**Állapot:** megvalósítva és helyi Docker stacken ellenőrizve (2026-07-23).

Ellenőrzött: import és app startup, konfigurációvalidáció, health/readiness,
Alembic upgrade/downgrade, mindhárom adattár kapcsolata, dummy job claim és
befejezés, queued job megmaradása PostgreSQL restart után, unit/integration
tesztek és Docker Compose config.

### Szállítandó

- Python 3.12 `src` layout;
- FastAPI app factory;
- külön API és worker entrypoint;
- Pydantic Settings;
- strukturált JSON logging és request ID;
- async SQLAlchemy és psycopg;
- Alembic;
- PostgreSQL 16;
- Qdrant;
- Neo4j;
- Docker Compose loopback portokkal;
- `/health`, `/ready`;
- PostgreSQL job queue skeleton;
- unit és containeres integration tesztalap.

### Nem része

- vault parsing;
- embedding;
- extraction;
- Assistant integráció.

### Kilépési feltétel

- mindhárom adattár elérhető és healthcheckelt;
- migration upgrade/downgrade tesztelt;
- worker tartós dummy jobot képes claimelni és lezárni;
- restart után a queued job nem vész el.

## Fázis 2 – Vault ingest

**Állapot:** megvalósítva és valós read-only vaulton ellenőrizve (2026-07-23).

Ellenőrzött: 18 Markdown note első és változatlan újrascanje, source span,
strukturális chunk és FTS, stabil rename, módosítás és törlés lifecycle,
feldolgozási hiba dokumentumszintű izolálása/újrapróbálása, valamint a teljes
vault hash- és mtime-snapshotjának változatlansága.

### Szállítandó

- allowlistes read-only vault adapter;
- scan és file state;
- hash-alapú create/modify/delete/rename;
- document és document version;
- YAML frontmatter;
- Marko + GFM + source mapper;
- heading tree és content blockok;
- strukturális chunker;
- wikilink/alias/heading/block/embed felismerés;
- PostgreSQL full-text index;
- inkrementális és resumable parse job;
- read-only acceptance teszt.

### Kilépési feltétel

- változatlan vault ismételt scan/index esetén nincs új chunk/projection;
- egyértelmű rename megtartja a document ID-t;
- többértelmű rename delete+add warning;
- módosítás csak érintett dokumentumot dolgoz fel;
- törlés eltávolítja az aktuális származtatott szöveget.

## Fázis 3 – Embedding és keresés

**Állapot:** lezárva, valós PostgreSQL + Qdrant stacken és LM Studio
text-embedding-bge-m3 modellel ellenőrizve (2026-07-23). A runtime dimenzió
1024; a 12 kérdéses semantic Recall 1,0000 és MRR 0,9583.

Ellenőrzött: runtime dimenzió-probe és titokmentes providerhibák, valós Qdrant
collection/upsert/query/alias/delete folyamat, tranzakciós outbox és retry
failure injection, deterministic RRF, stale PostgreSQL-verziószűrés, exact
provenance, section context és strukturált REST response.

### Szállítandó

- `EmbeddingProvider` port;
- LM Studio/OpenAI-kompatibilis adapter;
- külön runtime adapter lehetősége;
- model profile és dimension probe;
- Qdrant chunk collection és alias;
- transactional projection outbox;
- batch és resumable embedding;
- keyword, semantic és hybrid retrieval;
- section-aware context packing;
- retrieval evaluation corpus és metrikák.

### Kilépési feltétel

- source chunkok pontos provenance-szel visszaadhatók;
- modellcsere új collectionben, aliasváltással tesztelt;
- partial Qdrant failure javítható outbox/reconciler segítségével;
- stale találat nem kerül API response-ba.

## Fázis 4 – Tudásgráf

**Állapot:** a kanonikus resolution + Neo4j mag megvalósítva és valós vaulton
ellenőrizve (2026-07-24); a szemantikai gold-set review és emberi merge workflow
még nyitott.

Ellenőrzött: qwen/qwen3.5-9b structured extraction, exact evidence cascade,
verziózott strong-ID normalizálás, névalapú auto-merge tiltása, kanonikus
entity/assertion/claim réteg, outbox-auditált tranzakciós Neo4j snapshot,
constraint-ek, idempotens rebuild, entity detail, neighbors és legfeljebb 4
hopos path API. A 18 dokumentumos, 3×2 chunk graph baseline: 47 entitás, 45
kapcsolatállítás, 36 claim és 2 082 projekciós objektum. Baseline:
docs/evaluation/graph-pilot-v0-baseline-2026-07-24.md.

### Szállítandó

- ontológia registry v0.1;
- `GenerationProvider` port;
- Pydantic extraction schema;
- entity/relationship/claim candidate;
- exact quote és span validáció;
- determinisztikus entity resolution;
- fuzzy/embedding decision queue;
- Neo4j document/link graph;
- Neo4j semantic graph projection;
- entity detail, neighbors és path API;
- extraction pilot és költségmérés.

### Kilépési feltétel

- nincs evidence nélküli aktív assertion;
- ismeretlen predicate nem kerül gráfba;
- Qdrant/Neo4j partial failure rekonstruálható;
- törölt forrás evidence-e eltűnik;
- kizárólag arra épülő assertion inaktiválódik.

## Fázis 5 – GraphRAG retrieval

### Szállítandó

- query classification;
- entity seed retrieval;
- vector seed és graph expansion;
- deterministic fusion;
- path- és source-kiválasztás;
- strukturált retrieval response;
- relevancia- és provenance-regressziós tesztek.

### Kilépési feltétel

- multi-hop result minden eleme aktív forráshoz vezet;
- graph limitek betartottak;
- warning és truncation látható;
- `confidence` csak kalibrált módszerrel kap értéket.

## Fázis 6 – Assistant integráció

### Szállítandó

- stabil OpenAPI contract;
- klienspélda;
- `127.0.0.1` binding;
- service token;
- timeout, retry és rate/size limitek;
- AI Assistant integration test;
- későbbi MCP adapterhez application service határ.

### Nem része automatikusan

- kész GraphRAG végső válaszgenerálás;
- Obsidian plugin;
- vault write-back;
- többtenant adminrendszer.

## Minőségi kapuk

Minden fázisban:

- migráció vagy schema változás teszttel;
- unit és integration teszt;
- idempotencia;
- structured logging;
- secret redaction;
- bounded query;
- failure injection a külső adattáraknál;
- dokumentációfrissítés.

