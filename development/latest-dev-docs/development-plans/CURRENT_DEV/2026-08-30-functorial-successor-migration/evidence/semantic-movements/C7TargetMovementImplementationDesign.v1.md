# C7 Target Movement Implementation Design v1

Status: `MAINLINE_SEMANTIC_IO_FIXED · IMPLEMENTATION_NOT_STARTED · NO_PROMOTION`

This design closes no movement by itself. It fixes target semantics and file ownership for bounded DeepSeek implementation. Frozen 20/21 and `C7SemanticMovementDesign.v2.md` remain authoritative.

## Domain objects

- `RawSnapshot`: project key, source locator, exact immutable bytes, content digest, revision, non-reusable incarnation, MIME type and provenance refs. Caller-supplied digest must equal bytes.
- `NormalizedIngestEnvelope`: exact RawSnapshot ref plus legacy-compatible input kind, content format, source/processed/effective time, time provenance/version, lineage ref, requested downstream targets and normalized text.
- `DigestionDecision`: exactly one selected alternative (`EXTRACT`, `CHUNK`, `SUMMARIZE`, `PASS_THROUGH`), reason, decision digest and profile ref. No boolean combination of alternatives is allowed.
- `StructuredMaterialCandidate`: selected alternative, ordered source refs, structured payload/ref, provenance closure, decision digest, candidate digest, failure/loss profile and staging-only authority.
- `VerifiedMaterialCandidate`: exact candidate identity plus verification receipt/digest; verification grants no canonical write.
- `C7ReverseReturn`: retained RawSnapshot ref, optional candidate ref, reason/failure, cleanup target, new-attempt policy and immutable reverse-return digest.
- `C7Rejected` / `C7Deferred`: typed terminal short-circuit result retaining source/candidate identity and reason.

## Decision and alternative semantics

The pure selector matches legacy decision inputs and chooses exactly one branch.

- `STRUCTURED_JSON`: choose `EXTRACT`.
- report-shaped or long content: choose `CHUNK`.
- derived LLM/writing report: choose `SUMMARIZE`.
- safe default: choose `PASS_THROUGH`.

Each branch has a handwritten port and independent effect/resource/failure profile. A branch may perform internal substeps needed to produce one `StructuredMaterialCandidate`, but it must not dispatch another alternative and must emit one branch receipt.

- `ExtractPort`: parse/validate structured JSON or call an explicitly injected extractor; invalid JSON/empty structured output is typed failure. Test interpreter uses deterministic local parsing and provider calls zero.
- `ChunkPort`: produce stable ordered chunks with byte/count ceilings and a single aggregate candidate; any per-chunk analysis is internal to this port, not an `Extract` alternative. Test interpreter is deterministic and provider calls zero.
- `SummarizePort`: produce a summary-derived structural candidate with input provenance; any metadata formation is internal, not an `Extract` alternative. Test interpreter is deterministic and provider calls zero.
- `PassThroughPort`: preserve normalized content and provenance without forced digestion; empty/unsafe content returns typed rejected/deferred, not a candidate.

Order is `RawSnapshot -> Normalize -> Decision -> selected branch -> Candidate`. No branch reorder or commutativity claim exists.

## Verify, admit and recovery

- `verify_structured_candidate` checks project/snapshot/decision/branch/candidate digests, provenance, limits, current verification profile and authority epoch. It returns Verified, Rejected or Deferred without writing.
- Local admission integration consumes only `VerifiedMaterialCandidate`, builds exact `CommitIntent`/`VerificationBinding`, and in a disposable project database performs commit plus authoritative readback. It must bind candidate/snapshot/decision digests and committed revision/incarnation. Production canonical authority remains false.
- `return_for_cleanup` emits `C7ReverseReturn`, disables admission/projection, retains RawSnapshot and forbids a new attempt without exact non-start proof/current authority.
- Existing terminal readback, projection rebuild and non-start proof semantics remain unchanged and are composed after the candidate/admission boundary; no non-idempotent effect is repeated.

## Required target and parity traces

- `C7-T-STRUCTURED-JSON`: one Extract branch, structured candidate, malformed JSON failure.
- `C7-T-LONG-REPORT`: one Chunk branch, ordered chunks, resource ceiling failure.
- `C7-T-DERIVED-REPORT`: one Summarize branch, summary candidate, empty input failure.
- `C7-T-PASS-THROUGH`: one PassThrough branch, content/provenance preservation, reject/defer case.
- `C7-T-RETURN-CLEANUP`: reverse return retains snapshot and performs zero extraction/admission/write.
- `C7-T-VERIFY-ADMIT`: candidate verification then disposable-PG commit/readback, with stale/revoked/unknown cases.

Parity compares selector result, exactly-one branch trace, source/candidate digests, failure class, provider/write counts and reverse-return retention. It does not require identical private legacy implementation details.

## Fixed implementation packages

Pure package may only add:

- `main/backend/app/successor_runtime/capabilities/ingest_c7_movements.py`
- `main/backend/app/successor_migration/legacy_c7_decision_oracle.py`
- `main/backend/tests/successor_runtime/test_c7_movement_decision_parity.py`
- `main/backend/tests/successor_runtime/test_c7_movement_failure_reverse.py`

Admission package may only add:

- `main/backend/app/successor_runtime/substrate/postgres/ingest_c7_movement_admission.py`
- `main/backend/tests/successor_runtime/test_c7_movement_admission_postgres.py`

Neither package may modify shared AST/compiler/reducer/RuntimeAssignment/work-item schema, frozen files, 03/04, existing C7 scaffold bytes or movement dispositions. Outputs are implementation evidence only.

## Acceptance before movement re-disposition

- Four legacy and target decision traces; exactly one target branch per trace.
- Typed failure/reverse-return cases and loss account.
- RawSnapshot/candidate ABA and payload mutation fail closed.
- Provider/live/external delivery/cutover/authority transfer all false.
- Disposable PostgreSQL database/schema/table teardown observed clean.
- Independent semantic review must revise movement dispositions and bind new target traces; mechanical worker cannot close blockers.
