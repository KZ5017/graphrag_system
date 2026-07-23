# GraphRAG Knowledge Service

Önálló, lokálisan futó GraphRAG-alapú tudásszolgáltatás egy vagy több
Obsidian-vault read-only feldolgozásához.

## Projektállapot

A Phase 0–3 lezárult. A projekt jelenleg a
**Phase 4 – Tudásgráf** első, fail-closed extraction szeletét is tartalmazza:

- allowlistes, kizárólag olvasó filesystem adapter;
- inkrementális stat/hash scan és stabil dokumentumidentitás;
- Marko GFM AST, YAML safe loader és pontos globális source span;
- section, content block és strukturális chunk modell;
- PostgreSQL full-text index és forráshidratálás;
- tartós scan worker job és vault/document/source REST API;
- read-only acceptance és dokumentuméletciklus integration teszt;
- külön LM Studio-compatible EmbeddingProvider port, runtime dimenzió-probe és
  strukturált providerhiba;
- PostgreSQL model profile, idempotens projection outbox és projection status;
- model-specifikus Qdrant collection, biztonságos aliasváltás és delete
  reconciliation;
- keyword, semantic és determinisztikus RRF hybrid retrieval;
- PostgreSQL current-version visszaellenőrzés, exact provenance és
  section-aware szomszédos context chunkok;
- retrieval query audit és verziózott pilot evaluation corpus;
- kontrollált telecom-core@0.1 PostgreSQL ontológia registry;
- külön GenerationProvider port és LM Studio Qwen structured-output adapter;
- Pydantic + ontológia + exact quote/span validáció;
- auditálható entity/relationship/claim candidate-ek és resumable pilot job;
- forráscserével kaszkádoló evidence/candidate retention és valós 3×2 chunk baseline;
- determinisztikus strong-ID resolution, névegyezési review queue és kanonikus assertionök;
- outbox-auditált, tranzakciósan cserélhető Neo4j vault snapshot;
- entity detail, bounded neighbors és legfeljebb 4 hopos path REST API.

A candidate extraction, a kanonikus entity resolution és a Neo4j szemantikus
projekció működik. A retrieval, extraction és graph baseline is a valós 18
dokumentumos vaulton, lokális LM Studio modellekkel futott.

Az elsődleges cél egy stabil, auditálható alap megtervezése:

- az Obsidian Markdown a hiteles, ember által szerkesztett forrás;
- a szolgáltatás nem írhat vissza a vaultba;
- PostgreSQL kezeli a vezérlő-, feldolgozási és auditállapotot;
- Qdrant szolgálja ki a szemantikus retrievalt;
- Neo4j tárolja az újraépíthető tudásgráf-projekciót;
- a külső AI Assistant strukturált, forráshivatkozott kontextust kap;
- a GraphRAG nem része és futásidőben nem függ a BoberDetective projekttől.

## Rögzített környezeti alapadatok

```text
WSL projekt: /home/bober/projects/graphrag_system
Első vault:  /mnt/d/hack/MCP_Test_ObsidianVault
Vault mód:   read-only
```

Tervezési felső határok:

```text
50 000 fájl
20 GB vault
20 MB maximális Markdown note
```

A rendszer adatmodellje az első verziótól több vaultot támogat, még akkor is,
ha kezdetben csak egy vaultot használunk.

## Fejlesztői indítás

Követelmény: Python 3.12 és Docker Compose. Másold a `.env.example` fájlt
`.env` néven, cseréld le a `change-me` secreteket, majd indítsd a
stacket a `docker compose up -d` paranccsal. A host portok kizárólag
loopbackre vannak publikálva és az `.env` fájlban felülírhatók.

A liveness a `http://127.0.0.1:8080/health`, a komponensenkénti readiness
a `http://127.0.0.1:8080/ready` címen érhető el.

Lokális ellenőrzés:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .[dev]
.venv/bin/ruff check src migrations tests
.venv/bin/pytest
```

## Dokumentáció

- [Architektúra](docs/architecture/overview.md)
- [Adattár- és provenance-modell](docs/architecture/data-model.md)
- [REST API v0](docs/api/rest-api-v0.md)
- [Kapacitás és inkrementális ingest](docs/operations/capacity-and-ingest.md)
- [Távközlési ontológia v0.1](docs/ontology/telecom-core-v0.1.md)
- [Megvalósítási roadmap](docs/implementation/roadmap.md)
- [Döntési napló](docs/adr/README.md)
- [Nyitott kérdések és mérések](docs/open-questions.md)
- [Agent működési szabályok](AGENTS.md)
- [Aktuális projektállapot és handoff](PROJECT_STATE.md)
- [Retrieval pilot v0](docs/evaluation/retrieval-pilot-v0.md)
- [LM Studio retrieval baseline](docs/evaluation/retrieval-pilot-v0-baseline-2026-07-23.md)
- [LM Studio extraction baseline](docs/evaluation/extraction-pilot-v0-baseline-2026-07-23.md)
- [LM Studio graph baseline](docs/evaluation/graph-pilot-v0-baseline-2026-07-24.md)
 
## Alapelvek

```text
No source -> no assertion.
```

- A modell outputja nem igazságforrás.
- Minden kinyert állításnak pontos evidence-re kell mutatnia.
- A forrás read-only.
- Az indexek és a gráf újraépíthető projekciók.
- Az indexelés inkrementális, idempotens és megszakítás után folytatható.
- A parser, chunker, prompt, schema, ontológia és modellek verziózottak.
- A REST API elsősorban strukturált retrieval-kimenetet ad, nem végső választ.

## Következő mérföldkő

A következő implementációs mérföldkő a **Phase 5 GraphRAG retrieval**: entity
seed, bounded graph expansion és determinisztikus vector/graph fusion. A Phase 4
graph baseline 47 entitást, 45 kapcsolatállítást és 36 claimet vetített Neo4j-be.
