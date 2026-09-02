# C8 ResearchArtifact Delivery Bridge Design v1

Status: `MAINLINE_IO_FIXED · IMPLEMENTATION_NOT_COMPLETE · C8_M003_BLOCKED · NO_PROMOTION`

This non-normative design binds the C8 report candidate to the already frozen
`ResearchArtifact.v1 -> DeliveryIntent -> DeliveryAttempt ->
DeliveryReceiptRef` owner chain. It does not rename the C8 local report value as
canonical, migrate a legacy report identity, transfer authority, authorize
external delivery or create a cutover.

## Authority decision

Frozen `09/10/06` already authorize `ResearchArtifact.v1` as a
`CANONICAL_OWNED` object admitted through the Research Ledger and project
artifact store. They separately own `DeliveryIntent`, `DeliveryAttempt` and
`DeliveryReceiptRef`. A verified C8 draft may therefore become a staged
candidate for a new successor `ResearchArtifact.v1` without an amendment.

The movement is `REIMPLEMENTED_AS`, not `MOVED_TO`: legacy report storage keeps
its identity and owner; no legacy canonical row is copied or dual-written. C8
draft/report values remain source/provenance evidence and never become delivery
authority by themselves.

## Ordered semantic path

```text
C8 knowledge reads
-> Markdown ResearchDraftArtifact candidate
-> structural/citation verification
-> ResearchArtifact.v1 candidate
-> VERIFY_ADMIT through existing ResearchAdmissionHandler
-> authoritative ResearchArtifact readback
-> separately approved DeliveryIntent
-> runtime-claimed DeliveryAttempt
-> internal content-addressed export
-> provider receipt readback
-> DeliveryReceiptRef admission + delivered_as relation
```

Report admission does not authorize delivery. Delivery remains an independent
effect step with approval, resource, attempt, idempotency, receipt and recovery
owners.

## Pure adapter

`capabilities/c8_report.py` may add a deterministic
`C8ResearchArtifactCandidate` and an adapter from an exact verified C8 draft,
staged Markdown ref and provenance/citation closure to the existing frozen
`ResearchArtifact` payload. The adapter must:

- bind canonical metadata bytes/digest, Markdown ref/digest, source draft
  digest, verification digest and provenance digest;
- keep claim/evidence-relation closures empty when exact refs are absent;
  never synthesize claim or evidence identities;
- distinguish source base revision/incarnation from the new canonical artifact
  revision/incarnation;
- reject test-only, unverified, stale or cross-project inputs.

## Program and admission

`capabilities/c8_program.py` must keep report stage and canonical admission as
distinct operations. Add `c8.report.admission.v1` with output
`ResearchArtifact.v1` and the existing research-artifact return contract. Its
Program order is report stage, report verification, report admission, then the
existing `delivery.internal_export.v1` effect. Compiler-generated admission
bindings, not a handwritten stage shortcut, own `VERIFY_ADMIT`.

The PostgreSQL bridge reuses `ResearchAdmissionHandler` in
`ARTIFACT_OBJECT` mode. It must consume an exact `RuntimeAssignment`, attempt,
operation/admission registration, qualifier and current authority/base/event
closure. Caller-supplied canonical commit refs, receipt refs or positive
booleans are forbidden.

## Delivery realization

Canonical `ResearchArtifact.v1` readback is the only delivery base. Reuse the
existing delivery gate/runtime chain:

- exact `PostgresAuthorityProvider` and `ApprovalRepository` binding;
- canonical `DeliveryIntent` admission to the Research Ledger;
- runtime work claim and `ClaimBinding.derive_attempt_id` for
  `DeliveryAttempt`;
- `InternalExportInterpreter` for internal content-addressed marker/blob;
- provider receipt persistence and `DeliveryReceiptRef` admission;
- `InternalExportReadbackFacade` plus existing reconciliation handler for
  `OUTCOME_UNKNOWN`.

The C8 composition root must not call the export interpreter directly before a
qualified Program/Plan delivery step, runtime assignment, lease/attempt and
approval exist. External channels are rejected before any write.

## Crash and recovery

- effect succeeded but PostgreSQL receipt/event failed: keep the original
  attempt `OUTCOME_UNKNOWN`; use authoritative marker/blob readback first;
- marker absent or PREPARED with no blob: WAITING, no new attempt and no
  repeated export;
- blob present: reconstruct the same provider receipt, then admit the single
  `DeliveryReceiptRef` and relation;
- receipt/marker/body, assignment, handler, attempt or idempotency drift fails
  closed;
- rollback changes future authority/routing only and preserves intents,
  attempts, events, receipts and readback identities.

## File boundary

Allowed C8 bridge files:

- `capabilities/c8_report.py`
- `capabilities/c8_program.py`
- `substrate/postgres/c8_artifact_handler.py`
- `substrate/postgres/c8_production.py`
- `substrate/projections/c8_handler_bindings.py` only for the new exact
  operation/recovery binding
- C8 pure/program/PostgreSQL/Slice-C tests

Reuse-only: `research_admission.py`, internal-export, first-specimen delivery
gate/handler/reconciliation, approvals, authority provider, shared AST/compiler,
reducer, RuntimeAssignment and work-item schemas. No new table or migration.

## Completion boundary

C8-M003 remains blocked until a real disposable PostgreSQL trace proves the
canonical ResearchArtifact admission, separately approved runtime delivery
attempt, authoritative receipt/readback recovery, legacy observational account
and rollback. Green draft/admission tests or a direct interpreter call are not
sufficient.

