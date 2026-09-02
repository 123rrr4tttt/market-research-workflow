# C7 Target Movement Implementation Design v2

Status: `MAINLINE_CORRECTION_FIXED · PRIOR_V1_IMPLEMENTATION_EVIDENCE_INVALIDATED_PENDING_REWORK · NO_MOVEMENT_CLOSURE · NO_PROMOTION`

This non-normative implementation design supersedes
`C7TargetMovementImplementationDesign.v1.md`. Frozen `20/21` and the current
semantic movement matrix remain authoritative. This file does not change a
movement disposition and does not authorize production canonical write, live
provider, external delivery, cutover, authority transfer or candidate creation.

## Review findings that force v2

Independent pure and admission reviews rejected the v1 package for these exact
reasons:

1. `RawSnapshot.snapshot_ref` retained only the first sixteen hexadecimal
   characters of the raw-byte digest and did not bind project, source locator or
   provenance.
2. `DigestionDecision.decision_digest` did not bind the normalized envelope;
   legacy used raw input length while target used collapsed normalized length.
3. candidate verification rechecked only a self-consistent candidate object. A
   caller could replace envelope/provenance/order/authority fields, recompute the
   candidate digest and still obtain a verified result.
4. PostgreSQL admission accepted a test-local fake object, not the production
   pure `VerifiedMaterialCandidate`; the two contracts were structurally
   incompatible.
5. admission did not bind exact runtime program/plan/step/attempt/actor/capability
   identity, did not use the exact ordered event payloads, and did not produce a
   canonical `DocumentRef`.
6. the disposable canonical-head readback did not compare the complete
   commit-intent, verification, content, authority and base identity closure.

The v1 files remain historical implementation evidence only. Their green tests
must not be used as movement closure evidence.

## Corrected pure identity chain

### `RawSnapshot`

The object owns:

- `project_key`, `source_locator`, exact `raw_bytes`;
- full `raw_content_digest = sha256(raw_bytes)`;
- `revision` and non-reusable `incarnation`;
- `mime_type` and ordered `provenance_refs`;
- `snapshot_identity_digest`, computed from every field above except raw bytes,
  with full `raw_content_digest` in their place;
- `snapshot_ref = raw:c7:sha256:<snapshot_identity_digest>`.

Caller-supplied content or identity digests must be recomputed and compared.
No prefix digest is an identity.

### `NormalizedIngestEnvelope`

The envelope carries the exact `snapshot_ref`, `snapshot_identity_digest`, full
`raw_content_digest`, raw byte length, decoded source-character length,
project/source identity, input kind,
content format, normalized text, time semantics, lineage, ordered downstream
targets and a named normalization profile/loss record. Its digest binds all of
those values. Until a separately bound parser/normalizer port exists, a caller
may not replace decoded raw text through a free `text` override. Whitespace
collapse is not called lossless preservation; the raw snapshot remains retained
and the loss is declared as normalization-only. When `source_time` is valid and
no explicit effective time is supplied, effective time is `source_time`, matching
the legacy time contract.

### `DigestionDecision`

The decision carries `envelope_digest`, raw byte length as a resource metric,
the decoded source-character length passed to the legacy selector, exactly one
alternative, reason and a branch-internal structuring requirement. Its digest
binds all fields. Long/derived legacy `extract_required` is re-expressed as
deterministic branch-internal structural formation inside the selected Chunk or
Summarize port; it is not a second `Extract` alternative and does not add an edge
between alternatives. Provider/model enrichment performed by legacy extraction
is explicitly declared unavailable in the local no-provider realization and is
therefore a reviewed `DECLARED_LOSS`, not silent parity. The four alternatives remain
`one_of`, ordered only after the common prefix, with no commutativity claim.

### `StructuredMaterialCandidate`

The candidate carries:

- project, full snapshot identity/raw content digest and envelope digest;
- exact decision digest and selected alternative;
- canonical structured-payload content digest;
- ordered source refs and their closure digest;
- provenance refs and their closure digest;
- a closed staging-only authority enum, never caller-provided authority text;
- candidate digest over the complete record.

Every built-in branch port must derive these values from the supplied snapshot,
envelope and decision. Chunk and Summarize must materialize a deterministic
branch-internal structure and include the declared provider-enrichment loss;
recording an `extract_required` marker alone is insufficient.
`execute_c7_movement` must revalidate the returned object against that complete
input closure before returning a trace. A port cannot establish absence of
provider effects merely by self-reporting a counter; only the exact built-in
port class for the selected alternative is accepted as provider-zero evidence,
not an arbitrary subclass. The selected instance must be fresh, its bound
`execute` method must be the class implementation rather than an instance
replacement, and exactly one call/receipt must match the returned outcome
digest. No other instance method or state override is accepted. Every UTF-8
chunk, including a single multi-byte codepoint, must respect the byte ceiling.

### `VerifiedMaterialCandidate`

Verification consumes the exact `RawSnapshot`, envelope, decision and candidate,
plus server-resolved expected staged-candidate digest, project scope, actor,
authority digest/epoch and canonical base revision/incarnation. It recomputes
every digest, requires the candidate digest to equal the server-resolved staged
value identity, and checks ordered source,
provenance, staging-only authority and resource ceilings. The verified object
carries:

- all candidate/snapshot/envelope/decision/content/closure digests;
- project key, canonical object id, expected base revision/incarnation;
- actor, authority digest and authority epoch;
- verification profile/receipt and a digest over the complete verified record;
- `provider_calls=0` and `canonical_write_authorized=false`.

The pure capability layer must not import runtime `VerificationBinding`; layer
direction remains `capabilities -> no runtime dependency`.

Because the accepted local branch interpreters are deterministic and
provider-zero, verification independently replays the exact selected built-in
branch from snapshot/envelope/decision and requires byte-for-byte candidate
equality. A caller cannot make a forged candidate valid by changing both the
candidate and an expected-digest argument. Direct envelope construction is
checked by recomputing normalized text, source-character length and time
semantics from raw bytes. Legacy time parity includes its one-day future-source
tolerance; arbitrary effective-time/provenance pairs are rejected.
For Chunk replay, the digest-bound candidate chunk policy is validated and used;
a non-default but valid ceiling does not create a false mismatch. Reverse return
checks candidate/outcome full snapshot identity, not only a textual ref. Chunk
and Summarize candidates carry the provider-enrichment loss in their top-level
`failure_loss_profile` as well as the nested structure.

## Exact pure-to-runtime admission bridge

The PostgreSQL admission interpreter must import and accept the concrete pure
`VerifiedMaterialCandidate`; a local runtime-checkable lookalike Protocol and a
test-only candidate class are prohibited. Runtime `VerificationBinding` and the
exact ordered event payloads are separate interpreter inputs.

Before any write it must prove:

- candidate input/output/content/verification/provenance closures equal the
  corresponding `VerificationBinding` fields;
- binding program/plan/step/attempt and actor equal the persisted run/step and
  admission config/scope;
- the admission step is `RUNNING`, its attempt is `IN_FLIGHT`, and exact step
  revision, attempt revision, execution epoch/incarnation, assignment digest,
  handler binding/realization digest and input closure match the config/binding;
  a pre-completed step or attempt is rejected;
- config capability is exactly the reviewed C7 admission capability and equals
  the locked current capability-authority row;
- project registry revision/scope digest/resolved schema/incarnation are current;
- canonical owner/object/base revision/incarnation equal the verified candidate;
- `require_admission_binding` succeeds using the exact ordered event payloads;
- those ordered records are read from canonical `runtime_events` for the exact
  run/step/attempt and match the supplied/binding closure. Zero journal rows or
  caller-only self-consistent payloads are rejected. An exact-once
  admission-request event binds commit-intent id, idempotency key, requested
  canonical commit ref and requested receipt digest;
- the capability-authority row is locked and revalidated in the same transaction
  that writes the disposable canonical head and finalizes the commit intent.

`CommitIntentBinding.verification_digest` binds the full
`VerificationBinding.binding_digest`; the latter must close candidate and
decision identities through evidence/provenance and exact ordered event
payloads. Same idempotency key with any different candidate, decision, event,
runtime, base or authority identity is a typed conflict.

The persisted step and attempt rows are selected `FOR UPDATE` and revalidated
immediately before mutation. The disposable head retains step/attempt revision,
execution epoch/incarnation, assignment digest, separate handler-binding and
handler-realization digests, and input closure for crash readback.
The frozen PostgreSQL schema currently requires those two named handler digests
to be equal; this milestone verifies both fields and preserves that equality,
without claiming a new schema relation that permits different values.

## Disposable canonical adapter and readback

The PostgreSQL table remains a disposable test adapter and is not added to an
Alembic production migration. Its receipt must still materialize the existing
family `CanonicalCommitReadback` and `DocumentRef` contracts. The result must
remain explicitly `production_canonical_authority=false` and `disposable=true`.

Authoritative local readback compares, without trusting caller config:

- commit intent id/idempotency/capability/owner/object;
- exact duplicate request identity, including commit-intent id, requested
  canonical commit ref and receipt digest; a committed row never bypasses the
  same exact-binding comparison used by prepare;
- committed revision/incarnation/content digest;
- ordered event, verification and authority digests;
- canonical commit ref and receipt digest stored in both intent and head;
- pure candidate snapshot/decision/candidate/verification closure retained in
  the local head.

Readback requires the original content-addressed `VerificationBinding`, not only
caller config. The disposable head retains `commit_intent_id` plus enough pure
verified-candidate fields to reconstruct and revalidate its verification digest,
evidence/provenance/receipt digests and runtime identity. Head
program/plan/step/attempt/actor/authority epoch, candidate closure and commit
intent identity are each compared to an independent binding/intent value; a
digest recomputed only from the same mutable head row is insufficient.

Exact-request readback and by-idempotency readback are separate APIs. The former
requires the original config and rejects any config drift; the latter accepts
only capability/idempotency plus the original `VerificationBinding` and returns
the stored historical authoritative fact. It validates the head's recorded
runtime closure but does not require mutable step/attempt snapshots to remain at
their admission-time revision after they legitimately advance to `SUCCEEDED`.
Mutation runs inside an interpreter-owned nested
transaction/savepoint, so catching a finalize failure and committing the outer
transaction cannot retain a head with only a `PREPARED` intent.

Exact duplicate returns the same `DocumentRef`. Same committed revision and
incarnation with different bytes is `C7CanonicalAbaError`; revision or
incarnation drift is `C7StaleCanonicalRevisionError`. `OUTCOME_UNKNOWN` and
`REJECTED` never start another commit. A fault injected after head write and
before intent finalize must roll back both rows. A commit-after-receipt-loss
case may only read back the existing exact commit.

## Required correction tests

Pure tests must add:

- project/source/provenance mutation changes full snapshot identity;
- raw-byte ABA with retained digest fails;
- decision digest changes with envelope identity and raw-length boundary matches
  the legacy selector, including non-ASCII character-versus-byte cases;
- long/derived dual flags map only to deterministic branch-internal structuring,
  with provider enrichment recorded as declared loss;
- forged envelope/order/provenance/authority candidate is rejected even after
  recomputing its candidate digest; arbitrary payload mutation is rejected by
  the server-resolved expected candidate digest;
- a subclassed or otherwise substituted deterministic port is rejected;
- caller text that differs from decoded raw bytes is rejected and source-time
  effective-time parity is tested;
- pass-through reports normalization loss while retaining exact raw snapshot;
- reverse return binds full snapshot identity, requires any failure outcome to
  carry the same snapshot, binds its digest and exact retry prohibition; typed
  reject/defer short-circuits branch/admission/write.

PostgreSQL tests must use the actual pure candidate and add:

- program/plan/step/attempt/actor/capability mismatch, project-scope drift and
  authority-epoch drift;
- step `RUNNING` / attempt `IN_FLIGHT` plus execution epoch/incarnation,
  assignment, handler realization and revision mismatch;
- candidate/decision/event/provenance mutation idempotency conflict;
- exact `CanonicalCommitReadback -> DocumentRef`;
- readback tamper, `REJECTED` no-retry and locked authority revalidation;
- committed duplicate config drift and commit-intent primary identity tamper;
- fault injection between canonical head and intent finalize with zero residual;
- exact duplicate, stale, ABA and `OUTCOME_UNKNOWN` no-retry;
- zero canonical runtime-event rows, journal/config event drift and prepared
  requested-ref/receipt drift;
- concurrent step/attempt terminalization while admission validates;
- caught finalize failure followed by outer transaction commit leaves zero
  head/intent rows;
- database/table teardown count zero.

Only after these tests pass may mainline create a new semantic design/matrix
version and independently reconsider dispositions. Green tests alone still do
not authorize movement closure or promotion.
