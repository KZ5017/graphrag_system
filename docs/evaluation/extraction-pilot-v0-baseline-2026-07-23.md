# Phase 4 extraction pilot v0 baseline — 2026-07-23

## Scope

This baseline validates the first fail-closed knowledge-extraction vertical slice.
It does not create canonical entities or project a semantic graph to Neo4j yet.

- source: current read-only Obsidian vault snapshot;
- vault scan: 18 discovered, 18 hashed, 18 parsed, 0 failed;
- generation provider: LM Studio OpenAI-compatible chat completions;
- model: `qwen/qwen3.5-9b`;
- reasoning effort: `none`;
- temperature: `0`;
- maximum completion: 4096 tokens;
- ontology: `telecom-core@0.1`;
- prompt/schema: `telecom-knowledge-extraction@0.1` /
  `telecom_extraction@0.1`;
- sample: three representative documents, two content-rich chunks per document;
- total model calls: 6.

Representative domains:

1. NOC process: SMTP blocked-customer handling;
2. internal application: local AI assistant modes and tools;
3. access-network equipment: Huawei ONT handling guidance.

The reusable runner is `scripts/run_extraction_pilot.py`. It requires explicit
provider secrets in process environment variables and never writes those values
to the workspace or database.

## Result

| Document class | Chunks | Valid entity | Valid relationship | Valid claim | Invalid | Exact evidence |
|---|---:|---:|---:|---:|---:|---:|
| NOC process | 2 | 24 | 21 | 15 | 4 | 60 |
| Internal application | 2 | 8 | 8 | 8 | 3 | 24 |
| ONT equipment | 2 | 15 | 16 | 13 | 0 | 44 |
| **Total** | **6** | **47** | **45** | **36** | **7** | **128** |

- valid candidates: 128;
- invalid candidates: 7;
- validation acceptance: 94.81%;
- exact evidence coverage among valid candidates: 128/128, 100%;
- prompt tokens: 5,889;
- completion tokens: 14,032;
- total tokens: 19,921;
- observed end-to-end wall time: approximately 231 seconds;
- external API cost: none; inference was local.

All seven rejected candidates had `missing_quote`. They remain audit candidates
with no evidence row and cannot become active assertions. No unknown predicate
or unknown entity type reached the valid set.

The process and internal-application runs are therefore `partial`; the ONT run is
`succeeded`. `partial` is an expected fail-closed result when at least one item is
rejected while other items remain valid.

## Gates proven

- LM Studio accepts the flat, bounded JSON Schema through
  `response_format.type=json_schema`.
- Pydantic validates the provider response as a whole before candidate writes.
- Entity type, subtype, scope, predicate, assertion kind, and network layer use
  controlled allowlists.
- Relationship endpoints must resolve to local entity IDs from the same response.
- Every valid candidate owns a current-source, case-sensitive exact quote and
  global character span.
- A missing quote creates an invalid candidate without an evidence row.
- Schema-invalid output creates no partial candidates.
- Provider responses are represented by a SHA-256 hash only; raw responses are
  not retained.
- Candidate and evidence rows cascade with current source chunks. The integration
  test proves that source replacement removes quote and candidate text while the
  text-free run audit remains.
- Prompt, schema, ontology, and generation model profile IDs are pinned on every
  extraction run.
- A retried job reuses its run and only selects `pending` or `provider_failed`
  chunks.

## Interpretation and limitations

The 94.81% figure is validation acceptance, not calibrated semantic precision.
Candidates remain `unreviewed`. Human/domain review and a labelled extraction
corpus are required before measuring precision/recall.

The pilot orders chunks by content length inside each explicitly selected
document. This is suitable for a small representative probe, not a final
production sampling policy.

The following Phase 4 work remains:

- deterministic entity normalization and strong-ID merge;
- fuzzy/embedding candidate-only resolution queue;
- canonical entities, aliases, mentions, assertions, and claims;
- Neo4j document/link and semantic projections with reconciliation;
- entity detail, neighbors, and bounded path APIs;
- labelled extraction evaluation and human review workflow.
