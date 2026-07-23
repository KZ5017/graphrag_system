# Kapacitás és inkrementális ingest terv v0

## 1. Tervezési felső határok

```text
50 000 fájl
20 GB vault
20 MB maximális Markdown note
```

## 1.1 Valós pilotmérés – 2026-07-23

A /mnt/d/hack/MCP_Test_ObsidianVault read-only mérőscan eredménye:

```text
összes fájl:             28
összes vault byte:       4 169 714
Markdown fájl:           18
Markdown byte:           131 153
min/avg/p50/p90/p99/max: 1 510 / 7 286 / 2 977 / 14 461 / 39 739 / 43 523 byte
section:                 302
content block:           950
chunk:                   284
wikilink:                85
Markdown link:           3
fenced code / table:     14 / 34
list / blockquote:       133 / 13
```

A corpus túlnyomóan magyar nyelvű. Automatikus nyelvdetektálás még nincs;
ez Phase 3 evaluation előtti mérés marad. A nem-Markdown fájlokat az ingest
nem dolgozta fel.

Az első kapacitásmérésnek külön meg kell állapítania:

- hány `.md` fájl van;
- mekkora csak a Markdown összméret;
- mennyi attachment van, amelyet nem dolgozunk fel;
- átlagos és percentilis note-méret;
- várható section- és chunk-szám;
- nyelvi megoszlás;
- code block, tábla és wikilink gyakoriság.

## 2. Scan algoritmus

### Első scan

1. Csak include szabályra illeszkedő fájlok listázása.
2. Rooton belüli path ellenőrzés.
3. Size és `mtime_ns` olvasása.
4. SHA-256 streamelt számítása.
5. `vault_file_states` létrehozása.
6. `created` változás létrehozása minden dokumentumhoz.

### Inkrementális scan

1. Teljes path/stat felderítés.
2. Korábbi file state összevetés.
3. Változatlan size + mtime esetén hash kihagyható.
4. Új vagy változott fájl streamelt hash-elése.
5. Hiányzó korábbi pathok delete jelöltként.
6. Új és törölt elemek azonos hash alapján rename párosítása.
7. Többértelmű párosítás delete+add és warning.
8. File state és scan change tranzakciós mentése.

Az inode csak diagnosztikai hint. Windows-mounton nem stabil identitás.

### Integritás-ellenőrzés

A stat-alapú gyorsítás ritkán kihagyhat olyan módosítást, amely megtartja a
size és mtime értéket. Ezért konfigurálható:

- kézi full verify scan;
- időszakos teljes rehash;
- determinisztikus mintavételes rehash.

## 3. Fájlolvasás

- Hash 1–8 MiB blokkokban.
- Parser egyszerre egy note teljes szövegét tarthatja memóriában.
- 20 MB-os note miatt parser concurrency alapérték alacsony.
- Stat-before/read/stat-after ellenőrzés.
- Közben változott fájl retry vagy `source_changed_during_read`.
- Encoding v0-ban UTF-8; BOM kezelhető.
- Binárisnak vagy túl nagynak ítélt fájl warning/failure.

## 4. Pipeline és checkpoint

```text
scan
  → parse
  → lexical persistence
  → chunk embedding
  → document graph projection
  → optional LLM extraction
  → semantic graph projection
  → ready
```

Checkpoint granularitás:

- scan: utolsó rendezett relative path;
- parse: dokumentum;
- embedding: dokumentum + chunk batch;
- extraction: dokumentum + chunk/section batch;
- projection: outbox sequence.

Egy hibás dokumentum nem állíthatja le a teljes vault jobot.

## 5. Párhuzamosság

Külön konfiguráció:

```text
scan_hash_concurrency
parse_concurrency
embedding_concurrency
extraction_concurrency
qdrant_upsert_batch_size
neo4j_batch_size
```

Kezdeti konzervatív értékeket mérés után kell beállítani. LM Studio
terhelhetősége különösen nem következik a CPU- vagy worker-számból.

## 6. Chunk mennyiség és storage

A 20 GB szövegből több millió chunk is készülhet. A tényleges becsléshez
pilot szükséges.

Mérendő:

- chunk/document eloszlás;
- karakter/chunk;
- token/chunk az aktív embedding profilhoz;
- Qdrant point count;
- embedding nyers méret és HNSW overhead;
- PostgreSQL chunk text és GIN index méret;
- Neo4j node/edge szám.

Az első globális index csak chunk embeddinget készít. Section embedding csak
akkor aktiválható, ha az evaluation igazolja a hozzáadott értéket.

## 7. LLM extraction költségkontroll

Nem fut automatikusan teljes-vault extraction minden scan után.

Sorrend:

1. determinisztikus document/section/link graph;
2. chunk retrieval index;
3. reprezentatív pilot corpus;
4. extraction token- és időmérés;
5. prioritásos extraction;
6. csak megváltozott source unit újra-extractálása.

Prioritási jelöltek:

- konfigurált path prefix;
- frontmatter tag;
- dokumentumtípus;
- wikilink-centralitás;
- explicit felhasználói index scope;
- korábban ki nem nyert új dokumentum.

Az extraction budget konfigurálható:

```text
max_documents
max_chunks
max_input_tokens
max_runtime
```

## 8. Törlés és módosítás

### Módosítás

1. Új document version feldolgozása.
2. PostgreSQL aktuálisjelölt tartalom mentése.
3. Qdrant/Neo4j új generation projekciója.
4. Reconciliation.
5. `current_version_id` váltás.
6. Régi chunk text, vector és graph evidence törlése.

### Törlés

- document lifecycle `deleted`;
- aktuális chunk text és FTS törlése;
- Qdrant pontok törlése;
- Neo4j mention/evidence törlése;
- kizárólag törölt evidence-re épülő assertion inaktiválása;
- dokumentumazonosító és minimális hash/run metaadat maradhat.

Történeti quote vagy teljes forrásszöveg nem marad meg.

## 9. Watcher

WSL alatti Windows mounton a watcher nem hiteles változásforrás.

Használható:

- gyors scan triggerként;
- debounce után;
- periodikus scan mellett.

Nem használható:

- egyetlen változásdetektálási mechanizmusként;
- törlések vagy rename-ek végleges bizonyítékaként.

## 10. Reconciliation

Időszakosan ellenőrizendő:

- PostgreSQL ready chunk count vs Qdrant current point count;
- PostgreSQL entity/assertion count vs Neo4j projection count;
- hiányzó vagy beragadt outbox rekord;
- lejárt worker lease;
- stale Qdrant hit;
- orphan Neo4j Evidence/Chunk;
- superseded generation maradványok.

Eltérés esetén célzott projection rebuild job készül.

## 11. Read-only acceptance test

Egy tesztvault minden fájljára scan előtt:

```text
relative path
size
mtime_ns
sha256
```

Scan és teljes index után ugyanaz a snapshot készül. Bármilyen különbség
teszthiba.

