# Nyitott kérdések és szükséges mérések

Az alapvető rendszerhatár-döntések, a Phase 0–6 megvalósítása és az Assistant
integráció lezárult. Az alábbi pontok a további minőség-, adatkezelési és
üzemeltetési döntéseket, illetve a még szükséges méréseket rögzítik.

## Phase 1 előtt vagy közben

1. Lezárva: a Compose csak PostgreSQL/Qdrant/Neo4j és migration runtime.
   Az API és a worker natív WSL-processz, ezért eléri a Windows
   `127.0.0.1:1234` LM Studio-t proxy és hálózati LM Studio binding nélkül.
2. Helyileg validált host portok: PostgreSQL 55433 (55432: AI Assistant PostgreSQL), Qdrant 6433/6434, Neo4j 7474/7687
   és API 8080; mindegyik környezeti változóval felülírható.
3. A service token rotációja az első verzióban restarttal történhet-e?

## Phase 2 során lezárt mérések

1. A vaultban 18 Markdown fájl van, 131 153 byte Markdown-adattal; az összes
   28 fájl 4 169 714 byte. Attachmentet az ingest nem dolgoz fel.
2. Az aktív kizárások: .obsidian/** és .trash/**; további globot a pilot nem
   igényelt.
3. A méréskor symlink nem volt a vaultban.
4. A frontmatter kulcsok tényleges registryje a pilotadatokkal tovább
   bővíthető; a loader jelenleg biztonságos és típuskontrollált.
5. Az első vault path módja sensitive; ez konfigurálható vaultonként.
6. A scan gyakorisága továbbra is üzemeltetési döntés; a teljes stat scan és
   az inkrementális hash-optimalizálás elkészült.

## Phase 3 baseline eredmények

1. A validált embedding model identifier text-embedding-bge-m3, runtime dimenziója 1024.
2. A 16-os embedding batch a teljes 284 chunkos piloton hiba nélkül lefutott.
3. A 12 kérdéses baseline elkészült; a semantic Recall@5 1,0000, MRR@5 0,9583.
4. Section embedding egyelőre nem indokolt; a chunk-only semantic baseline teljes Recall@5 értéket adott.

## Phase 4 pilot eredmények és fennmaradó kérdések

1. A pilot három domaint fedett le: NOC folyamat, belső alkalmazás és ONT eszközkezelés.
2. A validált generatív modell `qwen/qwen3.5-9b`; az LM Studio JSON Schema structured output működik `reasoning_effort=none` beállítással.
3. A 6 chunkos baseline 47 entity, 45 relationship és 36 claim candidate-et fogadott el; mind a 128 exact evidence-szel rendelkezik.
4. A kanonikus baseline 47 aktív entitást, 45 kapcsolatállítást és 36 claimet
   adott; a Neo4j snapshot 2 082 objektummal és teljes constraint-készlettel
   sikeresen felépült.
5. A mintában nem volt kompatibilis type/scope-pal ismétlődő erős azonosító,
   ezért automatikus merge helyesen nem történt. A merge policy célzott
   strong-ID gold setet igényel.
6. Szükséges-e személy- vagy ügyféladat külön adatklasszifikációja?
7. Milyen emberi felület vagy workflow kezeli majd az entity merge
   jelölteket?
8. A dokumentáció aktuális állapotot vagy történeti folyamatleírásokat is
   tartalmaz-e, és milyen frontmatter jelzi ezt?

## Phase 5–6 lezárt eredmények és további mérések

1. A négyes Phase 5 acceptance corpus 4/4 esetet teljesített, teljes aktuális
   forrásprovenance-szel és egy ellenőrzött kétlépéses gráfúttal.
2. A Kiskőrös éjszakai üzemzavar kérdésénél feltárt általános ügyfél-entity
   zajt determinisztikus retrieval gate javította; az SMTP-források kikerültek
   a találatokból.
3. Az explicit Assistant GraphRAG mód hitelesített HTTP klienssel, típusos és
   méretkorlátos válasszal, reasoning támogatással, safe provenance-szel és
   silent fallback nélküli hibakezeléssel működik.
4. Az öt módosított Helyi_AI_Asszisztens dokumentum 2026-07-25-én teljes
   inkrementális feldolgozást kapott. A jelenlegi gráf 172 entitást,
   137 kapcsolatállítást és 113 claimet tartalmaz; nincs függő frissítés.
5. Következő mérés: bővített whole-vault pozitív/negatív precision corpus,
   különösen témán kívüli, közös szavas és elégtelen-forrás kérdésekkel.
6. Nyitott üzemeltetési döntés: service-token rotációs eljárás és dokumentált
   kulcscsere mindkét runtime leállításának minimalizálásával.

## Kötelező Phase 0/2 kapacitásmérés

Read-only mérőscan eredménye:

```text
Markdown file count
Markdown total bytes
min/avg/p50/p90/p99/max size
heading count
estimated section count
estimated chunk count
wikilink count
code/table/list frequency
language sample
```

Ez a mérés nem indexel és nem módosítja a vaultot.

