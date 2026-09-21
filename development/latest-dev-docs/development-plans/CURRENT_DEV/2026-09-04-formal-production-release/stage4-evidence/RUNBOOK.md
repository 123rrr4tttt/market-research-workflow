# Stage 4 local runbook

The run used the dedicated Compose project `mrw-stage4-local`, localhost ports `18142` (backend) and `15142` (frontend), retained r13x images, and the final non-r13x derived backend/Celery image `mrw-local/stage4-business001:stage4-c9-effect` (`sha256:f247a1492400311e032710df01f84365c7e700f61c122b7243ae58eda982af19`). The base r13x backend remains unchanged; the exact build inputs and copy mapping are recorded in `runtime/c9-effect-build.json`.

Start/replay:

```sh
STAGE4_HOLD_SECONDS=900 python3 stage4-evidence/runtime/run-stage4-runtime.py
```

The final C9 effect image is built locally with the retained base and no
network/publish action:

```sh
docker build --platform linux/amd64 --pull=false --load \
  -f development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage4-evidence/runtime/Dockerfile.business003 \
  -t mrw-local/stage4-business001:stage4-c9-effect .
```

For a C9 effect replay, use `runtime/compose.business001.override.yml` for
both `backend` and `celery-worker`, start the task-local `db`, `es`, and
`redis` services with the same `run-stage4-runtime.py` lifecycle, then run
`runtime/seed-c9-effect.py` inside the backend container. That seed is the
sole task-tenant setup path: it creates the project schema, source closure,
initial offset, capability, grant, approval, and step authorization; the
actor is derived from the injected bearer and no credential or complete HTTP
body is persisted. Issue the redacted request described by
`runtime/s4-c9-effect-live.json` twice with the same command id and approval,
then read back the receipt/idempotency rows and projection snapshot. Stop
with `docker compose -p mrw-stage4-local ... down --volumes --remove-orphans`
after capture; do not use a global prune.

The focused PostgreSQL authority/transaction check is reproducible without
the application stack. It uses a disposable `ankane/pgvector:latest`
container and the retained test runtime image, mounts the current `main/backend`
and `src`, and runs the exact four-test selector recorded in
`runtime/s4-c9-effect-focused.json`. The original authority/transaction run exited 0 with 4 passed; the rework selector in `runtime/s4-c9-effect-rework-focused.json` covers terminal/replay, authority, and expected-base concurrency with 8 passed and 37 deselected.
The original four-test run covered missing approval/grant rejection, receipt-write failure,
pre-durable-commit failure, and inconsistent partial-commit rollback. Its
JUnit and text logs are `runtime/s4-c9-effect-focused.junit.xml` and
`runtime/s4-c9-effect-focused.log`.

Business effect probes run only through the task-local TLS edge (`https://localhost:15442`) with the task bearer, `X-Project-Key: stage4_s4_20260913`, and an exact `X-Approval-Id`; direct HTTP is denied by the TLS policy. Do not issue unauthenticated effect requests. The C9 route is narrowly admitted for `rebuild_projection` and is recorded in `runtime/s4-c9-effect-live.json`; all other effect routes retain their existing bindings.

The narrow secure-config recheck reused `synthetic-production-like.snapshot.dump` without rerunning migrations or the snapshot matrix. It verified backend/Celery authenticated readiness, shallow/deep direct and proxy health, actual `Secure`/`HttpOnly` cookie serialization, and successor auth middleware admission (unauthenticated 401; authenticated request passed middleware and returned route-level 404). The retained frontend image's healthcheck was overridden in the Stage4 test Compose to use `127.0.0.1` because its BusyBox `wget localhost` resolved to IPv6 while Nginx listened on IPv4; the exact image was not changed.

The bounded TLS/upgrade probe used the task-local `compose.tls-probe.override.yml` and `tls-edge.nginx.conf`. It passed a CA-verified TLS handshake, a trusted proxy request returning 200, and an untrusted direct HTTP request returning 403 with `tls_denied` (not `observability_rollback_latched`). It also read back a constructed `20260830_000001` to `20260905_000001` upgrade with a non-empty legacy offset backfill and sibling branch completion; this is representative evidence, not an actual production predecessor or all-version coverage. The probe reused the prior upgrade logs and did not rerun the migration/snapshot matrix.

S4-BUSINESS-003 focused checks bind production cold-start queries to PostgreSQL registry scope and the trusted actor, with a real C9 query repository and deterministic no-write command port. Focused tests, PostgreSQL readback, cross-tenant rejection, and the production import witness passed. The rebuilt derived backend/Celery runtime then returned an exact seeded `projection_snapshot` (scope fields exact, three required sinks, generation/cursor readback, `control_feedback=false`) and rejected a foreign locator/header (typed `SCOPE_RESOLUTION_FAILED` and HTTP 503). Evidence is `runtime/s4-business-003-live-readback.json`; this closes only local scope/query wiring and remains non-authoritative.

The live scope runner used `mrw-local/stage4-business003:f0e694fa35a8227e` (`sha256:24f875d73a7efc0f2b4023393b27c6f0a50045c502e70c96b29c925691c6d901`) derived from the retained r13x backend base, with only the production query assembly files overlaid. It restored the bound synthetic snapshot, seeded only the task tenant and exact projection identity, issued container-loopback requests with the task bearer, and removed all Compose resources afterward. No command write, canonical mutation, provider call, or route-admission change occurred.

The C9 effect run used `mrw-local/stage4-business001:stage4-c9-effect` (manifest `sha256:f247a1492400311e032710df01f84365c7e700f61c122b7243ae58eda982af19`) derived from the retained r13x backend/Celery image with the production C9 command port and effect binding. It seeded only the task tenant's exact C9 capability, grant, approval and successor step authorization, executed one transactional rebuild to generation 1, and read back three local sinks. The receipt is `TERMINAL` and exact replay returned the same receipt without a second generation; changed-intent and stale-base requests conflicted without new rows; foreign tenant resolution failed closed. External sinks remained declared loss/no-call and no provider/model call was made. Evidence is `runtime/s4-c9-effect-live.json`.

Stop/cleanup is performed by the runner through `docker compose ... down --volumes --remove-orphans`. No global prune is allowed. The last run completed cleanup with no `mrw-stage4-local` resources remaining.
