# Retrieval pilot v0 — LM Studio baseline

## Környezet

- dátum: 2026-07-23;
- vault: `/mnt/d/hack/MCP_Test_ObsidianVault`;
- aktuális Markdown dokumentumok: 18;
- chunkok: 284;
- embedding provider: LM Studio OpenAI-compatible API;
- embedding model: `text-embedding-bge-m3`;
- runtime-probe dimenzió: 1024;
- Qdrant collection: `gks_chunks__text_embedding_bge_m3_1024__v1`;
- model profile ID: `98c70d7c-a4cb-48af-a188-8eb777c5334c`;
- kérdések: 12;
- limit: 5;
- stratégiánkénti futások: 12.

Az első teljes projekció 284 outbox upsertet hozott létre és 284 Qdrant
pointot írt ki. Dokumentum- vagy projection-hiba nem történt.

## Eredmények

| Stratégia | Document Recall@5 | Document MRR@5 | p50 | p95 |
|---|---:|---:|---:|---:|
| keyword | 0,8333 | 0,5903 | 21,35 ms | 28,34 ms |
| semantic | 1,0000 | 0,9583 | 41,35 ms | 43,90 ms |
| hybrid | 1,0000 | 0,7639 | 52,31 ms | 58,33 ms |

## Értelmezés

A BGE-M3 semantic csatorna ezen a kis pilotkorpuszon minden elvárt
dokumentumot visszaadott az első öt között, tizenegyet első, egyet második
dokumentumrangon.

Az eredeti `plainto_tsquery` minden kérdésszót kötelező AND-feltétellé tett,
ezért a természetes nyelvű magyar kérdéseken nulla recallt adott. A javított
lexikai csatorna normalizált, rövid stopword-szűrt OR queryt használ; ezzel a
Recall@5 0,8333 lett.

A hybrid csatorna teljes recallt tartott, de az azonos témájú
AI-Asszisztens-dokumentumok lexikai átfedése rontotta a sorrendet. A channel
weight tuningot nem rögzítjük ezen a kis mintán; ez Phase 5 mérési feladat.

A chunk-szintű 0/1/2 relevanciaítélet és az nDCG@5 továbbra is kézi
értékelést igényel. A jelen baseline dokumentumszintű recallt és MRR-t rögzít.

## Generációs modell smoke

A kiválasztott későbbi generációs profil:

- model: `qwen/qwen3.5-9b`;
- endpoint: LM Studio OpenAI-compatible chat completions;
- reasoning effort: `none`;
- eredmény: nem üres, szabályosan lezárt tartalmi válasz.

A GenerationProvider implementációja továbbra is Phase 4 scope; ez a smoke
csak a pontos helyi modellazonosítót és az alap inference-beállítást rögzíti.
