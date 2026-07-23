# ADR-0003: PostgreSQL control plane, Qdrant és Neo4j projekció

- Állapot: Accepted
- Dátum: 2026-07-23

## Kontextus

A rendszer PostgreSQLt, Qdrantot és Neo4jt használ, de nincs köztük közös
ACID tranzakció.

## Döntés

PostgreSQL az auditálható vezérlő és kanonikus feldolgozási állapot.
Qdrant és Neo4j idempotens, újraépíthető projekció. A szinkronizáció
transactional outbox és reconciliation segítségével történik.

## Következmény

- Qdrant nem dokumentumforrás;
- Neo4j nem job- vagy audit-adatbázis;
- projection failure nem teszi automatikusan ready állapotúvá a verziót;
- stale találatot PostgreSQL alapján ki kell szűrni.

