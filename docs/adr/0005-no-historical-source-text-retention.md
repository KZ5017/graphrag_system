# ADR-0005: Nincs történeti forrásszöveg-retention

- Állapot: Accepted
- Dátum: 2026-07-23

## Kontextus

Nem cél törölt vagy lecserélt Markdown tartalom történeti másolatának
megőrzése.

## Döntés

Superseded vagy törölt dokumentumverzióból nem marad teljes Markdown,
chunk text vagy evidence quote. Minimális hash-, run- és életciklusmetaadat
maradhat.

## Következmény

- törölt source nem nyitható meg történeti quote-tal;
- régi Qdrant és Neo4j projekció törlendő;
- kizárólag eltűnt evidence-re épülő assertion inaktiválódik;
- query audit nem használható történeti dokumentumarchívumként.

