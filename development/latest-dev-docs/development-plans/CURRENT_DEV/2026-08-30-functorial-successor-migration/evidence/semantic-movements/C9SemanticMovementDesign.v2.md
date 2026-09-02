# C9 Semantic Movement Design v2

Status: `MAINLINE_REDISPOSITION_PROPOSAL · FIVE_REIMPLEMENTED_AS · DOUBLE_REVIEW_REQUIRED · NO_PROMOTION`

This design records the current local C9 command/query, frontend projection and
PostgreSQL generation evidence. Frozen `01/02/06/20/21` remain authoritative.
The P1-P3 matrix is the machine-readable movement source. This design grants no
route registration, live provider, production read routing, canonical write,
external delivery, cutover, authority transfer, candidate or P4 promotion.

## Disposition summary

| Movement | Disposition | Current realization | Preserved loss/ceiling |
| --- | --- | --- | --- |
| `C9-M001` | `REIMPLEMENTED_AS` | server-scoped facade, exact command receipt/idempotency and typed query envelope | no caller actor/scope/control; router remains unregistered |
| `C9-M002` | `REIMPLEMENTED_AS` | fixed-endpoint successor command client with project-bound retry/dedupe | browser preference/cache is non-authoritative; component remains unwired |
| `C9-M003` | `REIMPLEMENTED_AS` | fail-closed six-state decoder with exact source/candidate/freshness binding | raw fallback and optional meta are rejected |
| `C9-M004` | `REIMPLEMENTED_AS` | fixed local AgentSession/graph/search values, receipts and source-bound offset | bounded local projections are lossy read models |
| `C9-M005` | `REIMPLEMENTED_AS` | deterministic local generation, complete-sink activation, repair and rollback | Elasticsearch, Qdrant and graph provider are `DECLARED_LOSS_NO_CALL` |

Each movement has exactly one disposition. `DECLARED_LOSS_NO_CALL` is a named
sink outcome inside `C9-M005`, not a second movement disposition. Local graph
projection and live graph-provider realization are distinct.

## Preserved semantics

- server-resolved project scope, actor, grant, approval, base and exact request
  identity precede durable command reservation;
- exact duplicate returns the first persisted receipt; changed intent conflicts;
- receipt-write and commit-ACK windows are savepoint/readback-first and cannot
  return failure for an exact durable success or commit a partial state;
- frontend never injects legacy project headers/query parameters or caller
  authority/control; localStorage keeps preference and pending identity only;
- command/query/projection response identity and source/candidate closure are
  exact-bound; cursor, digest, generation, projection revision, offset revision
  and offset ref obey the declared partial order;
- required local projection sinks are fixed and complete; missing, duplicate,
  tampered, wrong-source or wrong-generation candidates fail closed;
- generation activation and rollback preserve source revision/digest and prior
  receipts without mutating canonical source.

## Named observational compatibility

Three named comparison profiles are retained without a live second dispatch:

- `c9.facade.named-observation.v2`: envelope variants, typed failure, scope,
  trace, receipt identity and submission count;
- `c9.frontend.named-observation.v2`: explicit command, retry/conflict,
  localStorage non-authority, full metadata and read-only refetch;
- `c9.projection-generation.named-observation.v2`: local candidate identity,
  digest, generation, offset, partial failure and rollback, with external sinks
  reported as no-call loss.

## Current exact implementation bindings

- backend facade/contracts/DTO/API: `runtime/facade.py`,
  `runtime/facade_contracts.py`, `contracts/successor_runtime.py`,
  `api/successor_runtime.py`;
- PostgreSQL command/query and rebuild: `substrate/postgres/facade_commands.py`,
  `scripts/c9_projection_rebuild.py`, existing values and projection offsets;
- frontend: `src/lib/api/domains/successor-runtime.ts`,
  `SuccessorRuntimeStatus.tsx` and the focused Playwright contract suite;
- backend focused pure/PostgreSQL suites and frontend Playwright/lint/build are
  current evidence. Disposable PostgreSQL teardown is zero.

Independent task-bound reviews:

- `/root/c9_backend_exact_review`: `PASS current exact backend implementation`,
  no open P0 or dependent P1;
- `/root/c9_frontend_exact_review`: `PASS current exact declared frontend scope`,
  no open P0, frontend P1 or dependent P1.

Formal movement acceptance still requires persisted exact review records,
current artifact regeneration and declared-scope plus predecessor-completeness
double review. These implementation reviews are not adoption or promotion.

