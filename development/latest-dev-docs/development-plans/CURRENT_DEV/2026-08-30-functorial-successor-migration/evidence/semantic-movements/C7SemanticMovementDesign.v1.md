# C7 Semantic Movement Design v1

Status: `SUPERSEDED_UNADOPTED_BY_C7_SEMANTIC_MOVEMENT_DESIGN_V2`

Superseded by: `C7SemanticMovementDesign.v2.md` because v1 omitted branch-internal dual-flag conflicts and undercounted the required movement/blocker surface.

Normative inputs: repository semantic-movement completeness standard and frozen amendments 20/21. This file fixes semantic rows for deterministic serialization; it is not itself a promotion or authority record.

## Scope and ordering

The declared C7 scope is:

```text
RawSnapshot
  -> NormalizedIngestEnvelope
  -> DigestionDecision
  -> one_of { Extract, Chunk, Summarize, PassThrough }
  -> StructuredMaterialCandidate
  -> Verify/Admit
  -> Index/Graph Projection
  -> Recovery
```

`one_of` is exclusive. The selected branch is ordered between the prefix and suffix. Alternative branches are neither serial nor assumed commutative.

## Fixed movement rows

Every serialized row must contain all thirteen required movement fields and exactly one frozen disposition.

| movement_id | source_object | target_object | named_transform | disposition | acceptance state |
| --- | --- | --- | --- | --- | --- |
| C7-M001 | legacy raw ingress bytes plus ingress payload hash | UNASSIGNED exact `RawSnapshot` object | raw ingress capture to immutable project-scoped snapshot | UNASSIGNED_BLOCKER | current `C7IngestSubmission.raw_payload` is a mapping and caller-supplied digest is not an exact immutable snapshot readback |
| C7-M002 | legacy `NormalizedIngestEnvelope` with input kind, content format, time semantics, lineage and downstream targets | current `NormalizedIngestDocument` | `build_normalized_ingest_envelope` to successor normalization | UNASSIGNED_BLOCKER | target only preserves locator/title/text and has no reviewed loss account for omitted envelope semantics |
| C7-M003 | legacy `DigestionDecision` selected by input kind, format and length | UNASSIGNED successor decision object | `select_digestion_decision` to typed successor selector | UNASSIGNED_BLOCKER | no target selector or decision receipt exists |
| C7-M004 | `STRUCTURED_JSON` decision `EXTRACT_FIRST` | UNASSIGNED Extract branch realization | selected structured extraction | UNASSIGNED_BLOCKER | no target branch, trace or failure return |
| C7-M005 | report-shaped or long content decision `CHUNK_FIRST` | UNASSIGNED Chunk branch realization | selected bounded chunking | UNASSIGNED_BLOCKER | no target chunk object, order, resource ceiling or trace |
| C7-M006 | derived LLM/writing report decision `SUMMARIZE_FIRST` | UNASSIGNED Summarize branch realization | selected summary then extraction handoff | UNASSIGNED_BLOCKER | no target summary object, ordered handoff or trace |
| C7-M007 | safe default `PASS_THROUGH` | current direct normalize/stage path without a selector | selected pass-through | UNASSIGNED_BLOCKER | behavior resembles pass-through but no exact decision parity or branch receipt proves selection |
| C7-M008 | legacy branch output plus normalized structure | current `StagedIngestCandidate` | form `StructuredMaterialCandidate` | UNASSIGNED_BLOCKER | current candidate contains only normalized title/text and cannot carry Extract/Chunk/Summarize structured output |
| C7-M009 | legacy terminal verification and Document admission boundary | C7.2 canonical commit intent/readback scaffold | verify and admit with exact `CommitIntent`/`VerificationBinding` | REIMPLEMENTED_AS | local disposable-PostgreSQL commit/readback trace exists; remains no production authority claim |
| C7-M010 | legacy search/index handoff | C7.3 search projector with exact DocumentRef and offset | project admitted material to search read model | REIMPLEMENTED_AS | delete/rebuild named observation and exact offset are locally tested; declared projection loss required |
| C7-M011 | legacy graph handoff | C7.3 graph projector with exact DocumentRef and offset | project admitted material to graph read model | REIMPLEMENTED_AS | delete/rebuild named observation and distinct projector identity are locally tested; declared projection loss required |
| C7-M012 | legacy terminal outcome/readback | C7.4 `EffectReconciler` terminal readback | adopt terminal readback without repeating effect | REIMPLEMENTED_AS | terminal SUCCEEDED/FAILED readback forbids a new attempt in focused and PostgreSQL traces |
| C7-M013 | legacy non-start retry decision | C7.4 exact `NonStartProof` plus current authority | authorize a new execution epoch only after non-start proof | REIMPLEMENTED_AS | mismatched proof/authority/attempt/epoch fail closed in focused traces |
| C7-M014 | legacy `return_for_cleanup` reverse return with rollback token/raw snapshot ref | UNASSIGNED successor reverse-return object | return candidate to cleanup without losing raw identity | UNASSIGNED_BLOCKER | no target reverse-return trace or retained raw snapshot exists |

Initial exact `UNASSIGNED_BLOCKER` count for this declared matrix is **9**: C7-M001 through C7-M008 and C7-M014. These blockers affect C7 pilot/family and dependent Slice A/P4 promotion only; they do not revoke P0–P3 local-only records.

## Required per-row field policy

- `owner`: `backend-core/C7` for C7-M001 through C7-M009 and C7-M012 through C7-M014; `search-projection` for C7-M010; `graph-projection` for C7-M011.
- `effect`: record read, pure transform, staging, canonical admission, projection or readback effects separately. No branch may inherit another branch's effect implicitly.
- `failure`: preserve invalid input, extraction failure, empty structured output, resource ceiling, cleanup return, commit conflict, stale projection and readback conflict.
- `resource`: record bytes, chunk count, model/provider call ceiling, database transaction and projection cost. Current pilot ceiling remains provider calls zero.
- `authority`: C7.1 has project staging authority only; C7.2 owns verified admission; C7.3 is projection-only; C7.4 readback/recovery cannot grant canonical write.
- `recovery`: branch failures return typed failure or reverse return; terminal readback never repeats a non-idempotent effect; new epoch needs exact non-start proof and current authority.
- `projection_loss`: C7-M010/C7-M011 declare their read-model loss. All other rows require explicit zero loss or a reviewed loss; absence is not zero.

## Required traces

Legacy decision traces:

- `C7-L-STRUCTURED-JSON`: structured JSON selects Extract only.
- `C7-L-LONG-REPORT`: report-shaped/long input selects Chunk only.
- `C7-L-DERIVED-REPORT`: derived report selects Summarize, then the declared extraction handoff.
- `C7-L-PASS-THROUGH`: safe default selects PassThrough only.
- `C7-L-RETURN-CLEANUP`: quality failure returns for cleanup with raw identity/rollback token.

Target traces with matching observation profiles must be named `C7-T-*`. At this design boundary the five target traces are absent, so their dependent movements remain blocked.

Loss account: no global zero-loss declaration is permitted while the nine blockers remain. C7.3 search/graph projections require explicit declared-loss entries.

## Deterministic implementation package

DeepSeek may mechanically create only:

- `evidence/semantic-movements/C7LegacyDonorMovementInventory.v1.json`
- `evidence/semantic-movements/C7SuccessorMovementMatrix.v1.json`
- `main/backend/scripts/generate_c7_semantic_movement_matrix.py`
- `main/backend/tests/successor_runtime/test_c7_semantic_movement_matrix.py`

The generator must serialize exactly the fourteen fixed rows above, bind source/target/test files by SHA-256, compute canonical content digests, expose a true read-only `--check`, and report the exact blocker count. It must not alter dispositions, fill missing target traces, generate capability semantics, or decide promotion.

## Double review gate

1. Declared-scope correctness: all fourteen rows, all thirteen fields, unique movement IDs, legal dispositions, source/target/test evidence and loss account are syntactically and semantically consistent.
2. Predecessor-to-successor completeness: all donor modes and reverse-return are inventoried; no contract-only/unwired behavior disappears; legacy and target traces map; failure trace and loss account exist; blocker count is reported.

With nine blockers the second gate must return `BLOCK_DEPENDENT_SCOPE`, not PASS.
