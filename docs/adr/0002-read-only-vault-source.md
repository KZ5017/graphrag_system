# ADR-0002: Közvetlen read-only vault az egyetlen emberi forrás

- Állapot: Accepted
- Dátum: 2026-07-23

## Kontextus

Az Obsidian-vault a hiteles, ember által szerkesztett forrás. Nem készül
kézzel karbantartott másolat, és az első verzió nem függ az Obsidian
alkalmazástól.

## Döntés

A vault közvetlen filesystem adapteren, Dockerben read-only bind mounton
érhető el. A port nem tartalmaz write műveletet.

## Következmény

- nincs frontmatter- vagy wikilink-visszaírás;
- path allowlist és root-escape védelem kötelező;
- read-only acceptance teszt készül;
- attachment embed felismerhető, de attachment nem kerül feldolgozásra.

