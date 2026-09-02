# C9 Movement Closure Implementation Design v1

Status: `MAINLINE_IO_FIXED · IMPLEMENTATION_NOT_COMPLETE · MOVEMENTS_REMAIN_BLOCKED · NO_PROMOTION`

This non-normative design fixes a bounded local implementation for
`C9-M001..M005`. Frozen `06/20/21` and the current P1–P3 movement matrix remain
authoritative. It grants no live provider, production canonical write,
external delivery, cutover, authority transfer, candidate or promotion.

## Command/query facade

External command v2 carries only `command_id`, `project_locator`,
`command_kind`, typed payload, optional expected-base token and trace/approval
locator. It never carries actor, resolved schema/scope, authority, `execute`,
completion or projection metadata. External query v2 follows the same locator
rule and is read-only.

Server code resolves an exact `ProjectScopeRef` and authenticated actor, then
derives request identity from scope digest, actor ref, command id/kind and
canonical payload digest. A PostgreSQL idempotency reservation plus one
submission port call occur in one caller transaction. Same ID + same intent
returns the same receipt; same ID + changed intent is a typed conflict. A route
or shadow comparison never performs provider/index/rebuild effects and never
submits a command twice.

Envelope variants always preserve `status`, `data`, `error`, `meta`:

- `ok` and `waiting`: data required, error null;
- `blocked`, `unavailable`, `conflict`, `error`: typed error required;
- command meta and projection meta are distinct but both carry server scope and
  trace identity.

## Frontend successor client

The successor client bypasses legacy project header/query injection. Browser
storage is preference plus pending exact command ID/fingerprint only; it never
stores actor, resolved scope, approval or authority. Explicit retry reuses the
same command ID and byte-equivalent body. Changed payload requires a new ID or
receives server conflict. Double submission shares one in-flight request.

The read decoder retains the entire envelope. Missing/invalid meta, scope
mismatch, stale source revision/digest or malformed status variant fails closed.
Query invalidation causes refetch only and never a command/completion mutation.

## Projection generation and rebuild

The local milestone uses existing PostgreSQL project values and public
projection offsets; no new root schema is introduced. Exact canonical source
closure produces a content-addressed candidate generation per registered local
sink, independent typed receipts and one offset CAS activation. Prior generation
values remain recoverable. Required-sink failure records typed repair and does
not switch generation. Rollback CAS points the active offset back to the prior
generation without changing canonical source or deleting receipts.

AgentSession, graph and search/vector each register an explicit loss profile.
Local PostgreSQL sink adapters are deterministic and readback-capable. Live
Elasticsearch/Qdrant/graph provider realization is `DECLARED_LOSS` in this
milestone; legacy best-effort external writes are not called and do not return
`ok`. This local declared loss must remain visible to consumers and future
promotion gates.

## File ownership

Backend package may write only family-local facade contracts/service,
PostgreSQL idempotency/rebuild adapters and their tests. It must reuse existing
`IdempotencyRepository`, `ValueRepository`, `ProjectionOffsetRepository` and
project-scope authority. No shared reducer/assignment/work-item/root schema or
frozen file changes are allowed.

Frontend package may add one typed successor client/domain module, one bounded
consumer adapter and Playwright pure-contract tests. It must not alter legacy
global client behavior for non-successor routes.

## Required acceptance

- exact server scope/actor injection and scope digest validation;
- one durable submission for concurrent exact duplicate; changed-body conflict;
- five envelope variants and complete meta preservation;
- frontend localStorage non-authority, exact retry, double-click dedupe,
  malformed/stale decoder and query-refetch-no-command;
- source-bound offset CAS, generation candidate/receipt/activation, required
  sink partial failure, prior-generation rollback and fresh-session rebuild;
- explicit per-sink loss and no memory fallback;
- legacy named observational comparison without live external effects;
- independent movement double review with all authority flags false.

Movement dispositions remain blocked until these traces exist and current
artifacts are regenerated and independently reviewed.
