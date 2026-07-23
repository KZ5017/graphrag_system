# Graph pilot v0 baseline — 2026-07-24

## Scope

- Read-only vault: `/mnt/d/hack/MCP_Test_ObsidianVault`
- Scan: 18 Markdown documents, 18 hashed, 18 parsed, 0 failed
- Explicit extraction scope: 3 representative documents
- Chunks: 2 per document, 6 structured generation calls total
- Generation model: `qwen/qwen3.5-9b`
- Ontology: `telecom-core@0.1`
- Resolution rule: `strong-identifier@1.0`
- Projection: PostgreSQL canonical state → Neo4j vault snapshot

The pilot did not write to the vault. Provider credentials were process-local
and were not persisted in the repository or audit tables.

## Extraction result

| Document | Valid candidates | Invalid candidates | Prompt tokens | Completion tokens |
|---|---:|---:|---:|---:|
| SMTP blocked-customer process | 60 | 4 | 2,600 | 6,650 |
| Local AI assistant modes/tools | 24 | 3 | 1,628 | 2,914 |
| Huawei ONT guide | 44 | 0 | 1,661 | 4,468 |
| **Total** | **128** | **7** | **5,889** | **14,032** |

These extraction counts reproduce the previous extraction-only baseline. The
wall-clock time for extraction, resolution, and projection was approximately
225 seconds on the local LM Studio runtime. No external model API cost was
incurred.

## Canonical PostgreSQL result

| Object | Count |
|---|---:|
| Active canonical entities | 47 |
| Active relationship assertions | 45 |
| Active claims | 36 |
| Deferred strong-ID conflicts | 0 |
| Pending exact-name review pairs | 0 |
| Automatic strong-ID merges | 0 |

Zero automatic merges is the expected safe result for this sample. No two
candidate mentions exposed the same supported strong identifier with compatible
type and scope. Exact/fuzzy name and embedding similarity are deliberately
incapable of automatic merge.

Every active assertion and claim references an exact current-source evidence
span. Canonical source-derived text is removed by cascade when its current
document version is replaced; remaining current candidates can be resolved
again.

## Neo4j result

- Snapshot generation: 1
- Snapshot hash:
  `1138ebe11047b0d18ffda269512fe95514361e7dcabcd50e4678d6e03ca8eaa2`
- Snapshot objects (nodes + relationships): 2,082
- Projection outbox status: succeeded
- Required unique constraints: 9/9 present
- Reified assertion → subject/object/evidence traversal: verified
- Bounded 1–4 hop entity path traversal: verified
- Repeating an unchanged snapshot: idempotent (`projected=false`) in integration
  acceptance

The snapshot covers all 18 current vault documents structurally, while semantic
nodes reflect only the three explicitly extracted pilot documents. PostgreSQL is
the canonical source; the Neo4j vault projection is transactionally replaceable
and reconstructable.

## Acceptance interpretation

This baseline validates plumbing, fail-closed provenance, deterministic
resolution policy, source-retention cascades, outbox audit, Neo4j reconstruction,
and bounded graph queries. It does not establish semantic precision or recall.
A reviewed gold set is still required before enabling broader automatic
extraction.
