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

**Állapot:** lezárva, valós PostgreSQL + Qdrant + Neo4j adaton és lokális
LM Studio embeddinggel ellenőrizve (2026-07-24).

Ellenőrzött: determinisztikus query classification, canonical entity és vector
seed, legfeljebb 4 hopos/50 pathos Neo4j bejárás, active current-source
PostgreSQL assertion/claim hydration, stale path fail-closed szűrés,
determinisztikus keyword/vector/entity/graph/claim RRF, source retention,
warning/truncation és containeres provenance-regresszió. A négyes review-zott
baseline 4/4 esetet teljesített, köztük egy igazolt kétlépéses gráfutat.

### Szállítandó

- determinisztikus query classification;
- entity seed retrieval;
- vector seed és graph expansion;
- deterministic fusion;
- path- és source-kiválasztás;
- aktuális forráshoz kötött assertion- és claim-hidratálás;
- strukturált retrieval response;
- relevancia- és provenance-regressziós tesztek.

### Kilépési feltétel

- multi-hop result minden eleme aktív forráshoz vezet;
- graph limitek betartottak;
- warning és truncation látható;
- `confidence` csak kalibrált módszerrel kap értéket.

Baseline:
`docs/evaluation/graphrag-retrieval-v1-baseline-2026-07-24.md`.

## Üzemeltetési kiegészítés – helyi GraphRAG kezelő

**Állapot:** megvalósítva, unit és élő smoke szinten ellenőrizve (2026-07-25).

A loopbacken elérhető, service tokennel vezérelt operátori oldal megmutatja a
komponensek, a vault, a Qdrant projection és a kanonikus gráf állapotát.
Írásmentes diff-előnézetből indítható scan, embedding projection, dokumentumra
korlátozott extraction, resolution és Neo4j-rebuild. A lépések tartós jobok,
a vault továbbra is read-only.
A legutóbbi, még nem Neo4j-projektált scan feldolgozási listája PostgreSQL
auditból visszaállítható, ezért a külön futtatott lépések és az oldal újranyitása
nem veszítik el a dokumentumscope-ot. A dokumentumkijelölés, a gráfépítésre váró
extraction futások és a művelet nélküli jobnapló külön panelen jelennek meg.

## Fázis 6 – Assistant integráció

**Állapot:** megvalósítva és két-rendszeres élő smoke-kal ellenőrizve
(2026-07-25). A fogyasztóoldali implementáció a sibling
/home/bober/projects/AI_Assistant repositoryban található.

Ellenőrzött: explicit user által választott GraphRAG mód, minden kérdésnél
determinista hybrid POST /v1/retrieve hívás, service-token hitelesítés, teljes
típusos response-validáció, timeout és válaszméret-korlát, forráscímkézett
evidence csomagolás, safe provenance, reasoninggel való kombinálhatóság,
MCP-módokkal való kölcsönös kizárás és silent fallback nélküli hibakezelés.
Az Assistant és a GraphRAG külön indítható és állítható le.

### Nem része

- végső válaszgenerálás a GraphRAG szolgáltatáson belül;
- Obsidian plugin;
- vault write-back;
- többtenant adminrendszer.

## Fázis 7 – Retrieval-minőség és üzemeltetési megerősítés

**Állapot:** folyamatban (2026-07-26).

### Tervezett scope

- bővített, review-zott pozitív és negatív retrieval corpus a frissített gráfon;
- a Kiskőrös/SMTP relevancia-regresszió tartós acceptance esetté alakítása;
- az Android hívásátirányítási útmutató dokumentum-koherencia regressziójának
  tartós acceptance esetté alakítása, idegen dokumentum bővítése nélkül;
- operator workflow integration tesztek a scan → projection → extraction →
  resolution/rebuild állapotátmenetekre;
- stale, törölt és átnevezett források dashboard- és retrieval-regressziója;
- retrieval response contract kompatibilitási teszt az Assistant kliensével;
- mért whole-vault precision a broad extraction scope további bővítése előtt.

Első leszállított minőségi szelet: a chunker 1.1.0 kanonikus
`structural_anchor`/`content_evidence` szerepet tárol PostgreSQLben. A
strukturális horgony keresési seed marad, de önálló evidence nem lehet; egyetlen
nem-index dokumentumra mutató anchor esetén a backend a már létező 32 chunk /
30 000 karakter korlát alatt csak tartalmi chunkokat hidratál. A Kiskőrös
döntési dokumentum pozitív `04:00 előtt` ága így visszakerül a contextbe. A
konszenzus nélküli témán kívüli találatok precision-kezelése továbbra is nyitott.

### Kilépési feltétel

- a review-zott negatív esetek nem szivárogtatnak témán kívüli forrást;
- az operátori workflow megszakítás után, oldalfrissítéssel is folytatható;
- a GraphRAG és az Assistant contract eltérése tesztben bukik;
- nincs broad extraction ember által jóváhagyott scope és mérés nélkül.

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

