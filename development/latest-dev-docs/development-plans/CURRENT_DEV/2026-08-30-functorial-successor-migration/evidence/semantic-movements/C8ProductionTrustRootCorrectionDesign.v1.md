# C8 Production Trust-Root Correction Design v1

Status: `MAINLINE_IO_FIXED · IMPLEMENTATION_NOT_COMPLETE · C8_MOVEMENTS_REMAIN_BLOCKED · NO_PROMOTION`

This non-normative design closes the C8 self-signed-authority gap found by the
independent current-byte review. Frozen `01/02/06/10/20/21`, the C8 movement
design, and the P1-P3 matrix remain authoritative. This file grants no
production canonical write, live provider, external delivery, cutover,
authority transfer, candidate or movement re-disposition.

## Boundary decision

Production authority is owned by one family-local PostgreSQL composition root,
not by pure DTO fields, caller-created registries, positive booleans or caller
claims about the active projection. Pure C8 retains deterministic semantics and
an explicitly nominal `TEST_ONLY` interpreter. The production root exact-reads
existing stores, issues opaque process-local witnesses, and re-reads durable
state after restart or uncertain outcomes.

Python seals prevent ordinary public API, DTO and dependency-injection
self-signing. They are not a sandbox against malicious same-process reflection
or monkeypatching. Stronger isolation would require an OS/process/DB-role
boundary and is outside this local milestone.

## Pure semantic surface

The pure package must:

- recursively freeze JSON values; require string mapping keys and finite
  numbers; reject unsupported types instead of falling back to `str(value)`;
- recompute canonical payload bytes against every stored content digest;
- reject registry key rebinding and preserve exact-duplicate idempotency;
- close artifact identity over citation ID, source identity/digest,
  revision/incarnation, handle ID, fields digest, evidence ref and position;
- expose no public production authority token, production registry constructor
  or production-positive boolean path;
- move caller-creatable registries and legacy-oracle helpers behind nominal
  `TestOnly*` types in `capabilities/c8_test_interpreter.py`;
- make production functions reject every `TestOnly*` value by nominal type,
  not by a mutable string field.

Pure domain results use state-specific variants. Production paths must not
accept caller-supplied `verified=True`, `admitted=True`, `prepared=True`,
`approved=True`, `delivered=True` or `provenance_preserved=True`.

## PostgreSQL production composition

`substrate/postgres/c8_production.py` is the single family-local assembly root.
It composes existing C7 head/value readback, project values, staged artifacts,
CommitIntent/admission, approvals/internal export, and projection-offset CAS.
It introduces no new table, root schema, shared AST, compiler, reducer,
RuntimeAssignment union or work-item schema.

The production factory accepts only server-resolved `Connection`,
`RuntimeScope` and existing effect dependencies. It does not accept an
authority token, issuer/verifier/loss registry, caller receipt digest,
caller canonical commit ref or caller active-projection assertion.

Production operations are:

1. exact-read C7 head and project value, deep-freeze decoded bytes, and issue an
   opaque material witness;
2. form and stage knowledge, then exact-read the staged value before issuing a
   bounded knowledge-read witness;
3. resolve knowledge handle IDs inside the root, validate exact citations and
   removals, compose deterministic Markdown and stage it;
4. structurally verify the staged bytes and issue a verifier-owned witness;
5. admit only that witness through exact assignment/authority/base/event and
   CommitIntent/readback closure;
6. prepare and attempt only separately approved internal content-addressed
   delivery; external delivery remains typed rejected;
7. project only canonical handles through a fixed family loss-profile catalog;
8. issue an active graph read handle only after reading the durable offset and
   generation value in one transaction; consumer re-resolves it before use.

## Witness and recovery rules

- Production witnesses are opaque nominal objects with a module-private seal
  and private no-overwrite registry. They are not persisted or deserialized.
- Fresh-process recovery starts from a durable locator, exact-reads the current
  store state and issues a new process-local witness.
- Material, knowledge, report and graph witnesses bind project, source/head or
  offset revision/incarnation, content/provenance digest, authority identity and
  registry identity.
- Commit/readback ACK loss is classified by exact authoritative readback.
  `OUTCOME_UNKNOWN` never retries a non-idempotent admission or delivery effect.
- A projection consumer accepts no caller-provided active generation, offset,
  provenance digest or arbitrary loss profile.

## File ownership

Pure owner:

- `capabilities/c8_common.py`
- `capabilities/c8_typed_knowledge.py`
- `capabilities/c8_writing.py`
- `capabilities/c8_report.py`
- `capabilities/c8_graph.py`
- `capabilities/c8_consumer.py`
- new `capabilities/c8_test_interpreter.py`
- C8 pure and legacy-oracle tests

PostgreSQL owner:

- new `substrate/postgres/c8_production.py`
- `substrate/postgres/c8_material_handler.py`
- `substrate/postgres/c8_artifact_handler.py`
- `substrate/postgres/c8_graph_projector.py`
- C8 PostgreSQL tests

Existing admission, value, staged-artifact, approval, projection-offset and
internal-export modules are reuse-only in this correction.

## Required adversarial acceptance

- public imports cannot construct or mutate a production trust root;
- caller-minted production strings/tokens, copied witnesses and every nominal
  `TestOnly*` value are rejected by production operations;
- nested payload mutation, unknown objects, non-string keys and non-finite
  numbers fail closed;
- same registry key with different bytes fails without replacing the old value;
- head/value/snapshot/revision/incarnation/provenance or source drift fails;
- writing rejects forged, stale, cross-project or test-only handles and every
  citation/removal closure mismatch;
- no production path accepts caller positive booleans or receipt/commit refs;
- admission and delivery uncertain outcomes use readback first and never repeat
  non-idempotent effects;
- arbitrary loss registry/provenance/active projection is absent from the
  production API; offset/value/source drift returns typed unavailable;
- fresh PostgreSQL sessions can re-issue from durable locators while old
  process witnesses are not treated as persisted authority;
- provider/network/external-delivery calls remain zero, and disposable
  PostgreSQL databases/schemas are absent after validation.

