# Architecture Decision Records

| ADR | Döntés | Állapot |
|---|---|---|
| [0001](0001-modular-monolith-and-durable-worker.md) | Moduláris monolit, külön tartós worker | Accepted |
| [0002](0002-read-only-vault-source.md) | Közvetlen read-only vault az egyetlen emberi forrás | Accepted |
| [0003](0003-postgresql-control-plane-and-projections.md) | PostgreSQL control plane, Qdrant/Neo4j projekció | Accepted |
| [0004](0004-stable-document-identity.md) | Stabil dokumentum-ID és hash-alapú rename | Accepted |
| [0005](0005-no-historical-source-text-retention.md) | Nincs történeti forrásszöveg-retention | Accepted |
| [0006](0006-provider-separation.md) | Külön generation és embedding provider | Accepted |
| [0007](0007-controlled-versioned-ontology.md) | Kontrollált, verziózott távközlési ontológia | Accepted |
| [0008](0008-api-network-boundary.md) | Loopback és statikus service token | Accepted |

Az ADR módosításakor a korábbi döntést nem kell átírni. Új ADR supersede-elje
a régit.

