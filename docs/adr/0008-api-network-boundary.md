# ADR-0008: Loopback és statikus service token

- Állapot: Accepted
- Dátum: 2026-07-23

## Kontextus

A szolgáltatás lokális AI Assistant számára készül, de vállalati és
potenciálisan érzékeny tudást szolgáltat.

## Döntés

Az API alapértelmezetten `127.0.0.1` interfészre bindol. A `/v1` végpontok
statikus, környezeti változóból betöltött service tokent kérnek.

## Következmény

- a health endpoint nem igényel feltétlenül tokent;
- token nem kerülhet logba vagy error response-ba;
- LAN kitettség külön explicit konfigurációt és firewall döntést igényel;
- későbbi auth mechanizmus az API dependency határon cserélhető.

