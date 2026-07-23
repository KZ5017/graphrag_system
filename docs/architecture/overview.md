# GraphRAG Knowledge Service – architektúra v0

## 1. Cél és rendszerhatár

A GraphRAG Knowledge Service különálló, lokálisan futó backend. Egy vagy több
Obsidian-vault Markdown-dokumentumaiból strukturált, kereshető és
forráshivatkozott tudásindexeket épít.

A rendszer nem:

- ír az Obsidian-vaultba;
- függ az Obsidian alkalmazás futásától;
- része a BoberDetective-nek;
- használ közös adatbázist vagy migrációt más projekttel;
- tekinti az LLM outputját igazságforrásnak;
- készít automatikusan végleges, természetes nyelvű vállalati választ.

Függőségi irány:

```text
Obsidian-vault
    ↓
GraphRAG Knowledge Service
    ↓
AI Assistant
```

## 2. Ajánlott futtatási modell

Az első verzió moduláris monolit, két külön indítható processzel:

```text
graphrag-api
graphrag-worker
```

Mindkettő ugyanazt a Python package-et és application service réteget
használja. Ez nem microservice-felbontás: az API és a worker külön
életciklusú processz, de közös kódbázis.

A tartós job queue kezdetben PostgreSQL-alapú. Redis és Dramatiq csak akkor
vezethető be, ha a mért terhelés vagy több worker koordinációja ezt
indokolja.

FastAPI `BackgroundTasks` nem használható hosszú, tartós indexelési
feladatokhoz.

## 3. Magas szintű komponensdiagram

```text
Windows / Obsidian
└── Vault
    └── WSL/Docker read-only bind mount
             │
             ▼
      Vault Filesystem Adapter
             │
             ▼
         Vault Scanner
      path/stat/hash/diff
             │
             ▼
         PostgreSQL
      file state + run + job
             │
             ▼
     Parser and Chunker
  frontmatter + Marko + source map
             │
             ├────────► PostgreSQL FTS
             │
             └────────► Projection Outbox
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
                 Qdrant               Neo4j
              dense vectors       knowledge graph
                    └─────────┬─────────┘
                              ▼
                     Retrieval Service
              keyword + vector + graph fusion
                              │
                              ▼
                     Provenance Hydration
                              │
                              ▼
                         REST API
                              │
                              ▼
                       AI Assistant
```

## 4. Komponensek és felelősségük

### Vault Filesystem Adapter

- csak konfigurált vault rootot érhet el;
- kizárólag listázási, stat és binary read műveleteket biztosít;
- normalizálja a relatív POSIX pathot;
- megakadályozza a rootból való kilépést;
- az első verzióban tiltja a rooton kívülre mutató symlinkeket;
- olvasás előtt és után stat ellenőrzéssel észleli a versenyhelyzetet.

### Vault Scanner

- teljes path/stat felderítést végez;
- csak új vagy változottnak látszó fájlt hash-el újra;
- felismeri az új, módosult, törölt és átnevezett fájlokat;
- többértelmű rename esetén delete+add eseményt ad és warningot rögzít;
- nem indít implicit, request-élettartamhoz kötött teljes indexelést.

### Document Registry

- stabil dokumentumazonosítót kezel;
- nyilvántartja az aktuális pathot és verziót;
- egyértelmű hash-alapú rename esetén megtartja a dokumentum ID-ját;
- dokumentumváltozáskor új verziómetaadatot hoz létre;
- nem őriz történeti dokumentum- vagy chunk-szöveget.

### Markdown Parser

- UTF-8 beolvasás és normalizált line ending;
- YAML frontmatter `safe_load` használatával;
- Marko AST és explicit GFM támogatás;
- heading tree H1–H6;
- bekezdés, lista, tábla, blockquote és code block;
- wikilink, alias, heading link, block reference és embed felismerés;
- Markdown-link felismerés;
- pontos source span előállítása saját source-mapper réteggel.

Marko node-ok renderelt vagy normalizált szövege nem helyettesítheti az
eredeti forrásszöveget.

### Structural Chunker

Prioritási sorrend:

1. dokumentumszerkezet;
2. heading-szakasz;
3. összetartozó blockok;
4. embeddingmodell korlátai;
5. kontrollált fallback darabolás.

Lista, tábla és fenced code block csak indokolt hard limit esetén vágható.

### Job Service és Worker

- tartós job rekord;
- lease és heartbeat;
- `FOR UPDATE SKIP LOCKED` alapú claim;
- retry és backoff;
- progress és checkpoint;
- dokumentumonkénti hibahatár;
- megszakítás után folytatható feldolgozás.

### Embedding Service

- külön `EmbeddingProvider` port;
- LM Studio/OpenAI-kompatibilis első adapter;
- opcionális külön lokális embedding runtime;
- modellprofil és vektordimenzió runtime ellenőrzése;
- batch embedding;
- Qdrant collection blue/green újraépítés és aliasváltás.

### Extraction Service

- verziózott prompt és Pydantic output schema;
- strukturált entity, relationship és claim jelölt;
- minden elemhez source label, quote és span;
- schema-validáció és pontos quote-ellenőrzés;
- hibás outputból nem készül részleges gráfobjektum.

### Entity Resolution

- exact identifier és erős determinisztikus normalizálás automatikus;
- fuzzy és embedding egyezések csak jelöltek;
- merge, split és keep-separate döntések külön auditált rekordok;
- entity type és scope kompatibilitás kötelező.

### Projection Service

- PostgreSQL transactional outboxot fogyaszt;
- idempotensen vetít Qdrantba és Neo4jbe;
- projection státuszt és hibát rögzít;
- csak teljes új projekció után vált aktuális dokumentumverziót;
- törléskor eltávolítja a régi, újraépíthető tartalmat.

### Retrieval Service

- PostgreSQL full-text/keyword;
- Qdrant dense semantic;
- hibrid fusion;
- entity lookup;
- közvetlen gráfszomszédság;
- limitált több lépéses gráfbejárás;
- section-aware context expansion;
- provenance hidratálás PostgreSQLből.

### API Layer

- verziózott request/response sémák;
- stabil azonosítók;
- cursor pagination;
- típusos warning és error envelope;
- idempotency key a jobindításokhoz;
- graph hop, result és context limitek.

## 5. Adattári felelősségek

### PostgreSQL

A vezérlő és auditálható állapot elsődleges tára:

- vault, file state, document és aktuális verzió;
- section, block és aktuális chunk;
- full-text index;
- job és run állapot;
- extraction jelölt és validáció;
- kanonikus entity és resolution döntés;
- assertion, claim és evidence;
- projection outbox és státusz;
- query audit.

### Qdrant

Kizárólag újraépíthető vektorprojekció:

- chunk embedding;
- opcionális section embedding;
- a gráffázistól entity-leírás embedding.

Nem dokumentumforrás, és nem tartalmaz szükségszerűen teljes chunk-szöveget.

### Neo4j

Kizárólag újraépíthető gráfprojekció:

- dokumentum- és szakaszgráf;
- wikilinkek;
- entitások és említések;
- relationship assertionök;
- claim és evidence kapcsolatok;
- szomszédság és útvonalak.

Nem kezeli az általános job-, run- vagy auditállapotot.

## 6. Több adattár konzisztenciája

PostgreSQL, Qdrant és Neo4j között nincs közös ACID tranzakció. A kötelező
minta:

```text
PostgreSQL business transaction
  ├── aktuális feldolgozási állapot
  └── projection_outbox rekord
              ↓
       projection worker
       ├── Qdrant upsert/delete
       └── Neo4j MERGE/delete
              ↓
       projection_status
```

Minden projection művelet idempotency keyt kap:

```text
target + object_type + object_id + generation + operation
```

A retrieval a Qdrant/Neo4j találatokat visszaellenőrzi az aktuális
PostgreSQL dokumentumverzióval. Külön reconciler feladat vizsgálja a
projection eltéréseket.

## 7. Read-only biztonsági invariánsok

- A vault Docker bind mount `read_only: true`.
- A konténer nem root felhasználóként fut.
- A konfiguráció vault allowlistet tartalmaz.
- Nincs write metódus a vault adapter portjában.
- Teszt igazolja, hogy scan/index után a vault file hash és mtime változatlan.
- Az API nem fogad tetszőleges, requestből származó filesystem pathot.
- A source URI logikai hivatkozás, nem írható fájlendpoint.

## 8. Forrás- és igazságmodell

Az LLM output mindig javaslat. Az assertion igazolható eredete:

```text
vault
  → document
  → current document version
  → section
  → chunk
  → exact evidence span
  → extraction run
  → relationship assertion / claim
```

Külön tengely:

```text
assertion_kind:
  explicit_source
  normalized_source
  inferred

review_status:
  unreviewed
  accepted
  rejected
  superseded
```

A confidence nem igazságérték és nem helyettesíti a review státuszt.

