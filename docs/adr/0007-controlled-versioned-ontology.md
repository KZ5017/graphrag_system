# ADR-0007: Kontrollált, verziózott ontológia

- Állapot: Accepted
- Dátum: 2026-07-23

## Kontextus

A távközlési vállalati tudás üzleti, szervezeti, informatikai és több
hálózati réteget átfogó fogalmakat tartalmaz. Korlátlan LLM-generált
entity- és predicate-típusok kezelhetetlenné tennék a gráfot.

## Döntés

Kis felső szintű entity type és predicate készlet, verziózott subtype és
property registry készül. Ismeretlen típus `OTHER` vagy review-jelölt.

## Következmény

- CMTS/CBR/ASR/OLT/ONT kontrollált subtype;
- extraction run hivatkozik ontológiaverzióra;
- új ontológia nem írja át automatikusan a régi extractiont;
- predicate allowlist kötelező.

