# GraphRAG Knowledge Service

Önálló, lokálisan futó GraphRAG-alapú tudásszolgáltatás egy vagy több
Obsidian-vault read-only feldolgozásához.

## Projektállapot

A Phase 0–6 lezárult. A projekt a Phase 4 fail-closed tudásgráfmagját, a teljes
**Phase 5 – GraphRAG retrieval** vertikális szeletét, valamint a külön
AI Assistanttal ellenőrzött **Phase 6 – Assistant integrációs szerződést** is
tartalmazza:

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
- PostgreSQL current-version visszaellenőrzés és exact provenance;
- section-aware szomszédos context chunkok, valamint erős hybrid konszenzushoz
  kötött, nem-index dokumentumokon belüli korlátos fejezetfa-hidratálás;
- kanonikus `structural_anchor`/`content_evidence` chunk-szerep, amely a
  címsorhorgonyokat kereshető navigációként megtartja, de önálló válaszforrásként
  kizárja és egyértelmű dokumentum esetén korlátos tartalmi hidratálást indít;
- retrieval query audit és verziózott pilot evaluation corpus;
- kontrollált telecom-core@0.1 PostgreSQL ontológia registry;
- külön GenerationProvider port és LM Studio Qwen structured-output adapter;
- Pydantic + ontológia + exact quote/span validáció;
- auditálható entity/relationship/claim candidate-ek és resumable pilot job;
- forráscserével kaszkádoló evidence/candidate retention és valós 3×2 chunk baseline;
- determinisztikus strong-ID resolution, névegyezési review queue és kanonikus assertionök;
- outbox-auditált, tranzakciósan cserélhető Neo4j vault snapshot;
- entity detail, bounded neighbors és legfeljebb 4 hopos path REST API;
- lokális kis modelltől független, determinisztikus query planner;
- keyword/vector/entity/graph/claim retrieval és determinisztikus fusion;
- aktuális forráshoz kötött claim/assertion/path hidratálás;
- 4/4-es review-zott Phase 5 baseline, benne ellenőrzött kétlépéses gráfút.

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

Követelmény: Python 3.12, WSL és Docker Compose. Másold a `.env.example`
fájlt `.env` néven, cseréld le a `change-me` secreteket, majd Windows
PowerShellből indítsd:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-system.ps1
```

PostgreSQL, Qdrant és Neo4j külön Docker-konténerben fut. Az API és a worker
natív WSL-processz, így a Windows loopbackre kötött LM Studio (`127.0.0.1:1234`)
elérhető marad anélkül, hogy hálózatra kellene megnyitni vagy proxyt telepíteni.
A leállítás: `powershell -ExecutionPolicy Bypass -File .\scripts\stop-system.ps1`.

A host portok kizárólag loopbackre vannak publikálva és az `.env` fájlban
felülírhatók. Az alap kiosztás: PostgreSQL `56001`, Qdrant `6433/6434`, Neo4j
`7474/7687`, API `8080`. A PostgreSQL `56001` szándékosan nem a Windows által
foglalható `55432–55731` porttartományba esik. A liveness a
`http://127.0.0.1:8080/health`, a komponensenkénti readiness a
`http://127.0.0.1:8080/ready` címen érhető el.

Lokális ellenőrzés:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .[dev]
.venv/bin/ruff check src migrations tests
.venv/bin/pytest
```

## Helyi GraphRAG kezelő

A szolgáltatás elindítása után a loopbacken elérhető operátori felület:
http://127.0.0.1:8080/operator

A kapcsolódáshoz a helyi .env fájl GKS_SERVICE_TOKEN értéke szükséges.
A felület read-only változáselőnézetet, komponens- és gráfállapotot, tartós
jobkövetést, valamint külön vagy teljes frissítési workflow-t biztosít. A teljes
workflow csak a kijelölt, létrehozott vagy módosított dokumentumokra indít
korlátos extractiont; törlésnél vagy átnevezésnél modellhívás nélkül újraépíti
a Neo4j-projekciót. A vaultba a felület sem ír.
A scan után a diff-lista helyett a legutóbbi, még nem gráfprojektált scan
feldolgozási listája marad látható. Ez oldalfrissítés vagy újranyitás után is
visszaállítható, így a scan és a vektorindex külön futtatása után az extraction
és a gráfépítés biztonságosan folytatható.
A **Frissítés** gomb teljesen újraolvassa az operátori állapotot. Ha egy már
nyitott felület mögött a GraphRAG API leáll, a következő kézi frissítés piros
kapcsolatvesztési állapotot és „utoljára ismert” jelölést mutat, a műveleti
gombokat letiltja, majd a szolgáltatás visszatérésekor ugyanazzal a gombbal helyreállítja az élő állapotot.

A **Vektorprojekció** panel a PostgreSQL kanonikus aktuális chunk-számát
összeveti a Qdrant aktív aliasával és tényleges pontszámával. Ha ez eltér,
a semantic retrieval nem megbízható, a panel piros **rebuild_required**
állapotot és a **Teljes vektorprojekció újraépítése** gombot mutatja.
Ez a tartós, teljes Qdrant-helyreállító job az összes aktuális PostgreSQL
chunkból építi újra a vektorprojekciót; vault-, PostgreSQL- és Neo4j-adatot nem
töröl. A **Vektorindex frissítése** ezzel szemben a normál, vault-változás
utáni inkrementális feldolgozási lépés.

Az operátori felületen a három különböző felelősség elkülönül:

- a **Változások** panelen dokumentumok jelölhetők ki;
- a **Gráfépítésre váró kivonatolások** panelen sikeres extraction futások
  jelölhetők ki resolutionre és gráfprojekcióra;
- a **Legutóbbi tartós jobok – napló** csak tájékoztató, nem tartalmaz
  műveleti checkboxokat.

## AI Assistant integráció

A sibling /home/bober/projects/AI_Assistant alkalmazásban explicit GraphRAG
mód készült. A user kapcsoló minden kérdésnél determinisztikusan meghívja a
tokenvédett POST /v1/retrieve végpontot; a modell nem dönthet a retrieval
kihagyásáról. A GraphRAG, Obsidian MCP és Excel MCP mód kölcsönösen kizáró,
a reasoning kapcsoló ettől függetlenül használható. A kliens típusosan
validálja és méretkorlátozza a választ, forráscímkézett evidence-et ad a
modellnek, és hiba esetén nem vált vissza csendben normál chatre. A két rendszer
egymástól függetlenül indítható és állítható le.

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
- [GraphRAG retrieval v1 corpus](docs/evaluation/graphrag-retrieval-v1.json)
- [GraphRAG retrieval v1 baseline](docs/evaluation/graphrag-retrieval-v1-baseline-2026-07-24.md)
 
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

A következő mérföldkő a retrieval-minőség és az üzemeltetés megerősítése:
bővített pozitív/negatív review corpus a frissített gráfon, operátori workflow
integration tesztek, valamint a retrieval-zaj és a forrásrelevancia további
determinista regresszióvédelme.
