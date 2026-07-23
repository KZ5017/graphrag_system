# ADR-0006: Külön generation és embedding provider

- Állapot: Accepted
- Dátum: 2026-07-23

## Kontextus

Az első lokális runtime LM Studio, de az embedding és generatív modell
életciklusa, endpointja és kapacitása eltérhet.

## Döntés

Külön `GenerationProvider` és `EmbeddingProvider` port készül.
Az első adapter OpenAI-kompatibilis LM Studio. Külön lokális embedding
runtime ugyanazon port mögött támogatható.

## Következmény

- az extraction nem függ LM Studio-specifikus API-tól;
- az embedding runtime külön cserélhető;
- model info, healthcheck és capability explicit;
- vektordimenzió runtime ellenőrzött, nem hardcoded.

