# ADR-0004: Stabil dokumentumazonosító és rename

- Állapot: Accepted
- Dátum: 2026-07-23

## Kontextus

A path változhat, de a dokumentum üzleti identitása egyértelmű rename
esetén megmarad. Windows-mounton az inode nem megbízható.

## Döntés

Új dokumentum stabil UUID-t kap. Ha egy scanben egy törölt és egy új path
egyértelműen azonos content hashhez tartozik, rename történik és az ID
megmarad. Többértelmű párosítás delete+add.

## Következmény

- pathból képzett dokumentum-UUID nem használható;
- rename warning és döntési metadata tárolandó;
- chunk és section ID dokumentumverzión belül determinisztikus.

