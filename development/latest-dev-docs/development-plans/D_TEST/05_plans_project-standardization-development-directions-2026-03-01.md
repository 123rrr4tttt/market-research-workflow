# Project Standardization Development Directions (2026-03-01)

## Objectives
- Build a stable engineering baseline for `backend + frontend-modern + ops`.
- Reduce regression risk during refactor and feature expansion.
- Make delivery predictable through clear gates, ownership, and acceptance criteria.

## Scope
- In scope:
  - Architecture and module boundaries
  - API and error contract consistency
  - Test layering and CI gates
  - Config/env and migration conventions
  - Observability and release process
- Out of scope:
  - New business features unrelated to standardization
  - One-off script cleanup without team-wide rules

## Guiding Principles
1. Contract first: API/DTO/error model is a stable interface, not an implementation detail.
2. Layer isolation: `API -> services -> adapters -> models`, no cross-layer shortcuts.
3. Test before refactor: no large structural migration without layer-based test protection.
4. Incremental rollout: enforce standards by stage (`warn -> require`) where possible.
5. Evidence-driven merge: every standardization PR must include test and gate evidence.

## Workstream A: Architecture Standardization
### Direction
- Enforce backend layering boundaries and ownership.
- Define per-layer responsibilities and allowed dependencies.

### Actions
1. Add architecture conventions doc under `main/backend/docs/`.
2. Create a module map:
   - API: request/response validation only
   - services: business orchestration
   - adapters: external systems and providers
   - models/repositories: persistence access
3. Introduce static checks (or review checklist) to block cross-layer direct calls.

### Acceptance
- New backend code follows layer path.
- PR review template includes architecture check item.

## Workstream B: API/Contract Standardization
### Direction
- Unified envelope and error code model across all APIs.

### Actions
1. Standardize response envelope:
   - `status`, `data`, `error`, `meta`
2. Define error taxonomy:
   - `error.code`, `error.message`, `error.details`, trace id in `meta`
3. Add/maintain OpenAPI contract checks for key routes.
4. For contract-breaking changes, require deprecation path and migration note.

### Acceptance
- Contract tests pass for core routes.
- No new API route bypasses envelope conventions.

## Workstream C: Testing Standardization
### Direction
- Keep layered testing and dual-environment validation (local + docker).

### Current Baseline (already landed)
- Test layers: `unit`, `integration`, `contract`, `e2e`.
- Marker config via `main/backend/pytest.ini`.
- CI workflow split into parallel jobs with docker diagnostics.

### Next Actions
1. Expand `e2e` from health/middleware smoke tests to 1-2 critical ingest/search flows.
2. Add fixture conventions (`tests/conftest.py`) for dependency overrides and isolation.
3. Introduce flaky governance:
   - root-cause issue required
   - temporary quarantine expiration date

### Acceptance
- PR gate: `unit + integration + docker`.
- Mainline/nightly gate: `unit + integration + contract + e2e + docker`.

## Workstream D: Config and Environment Standardization
### Direction
- Make local/dev/docker behavior explicit and predictable.

### Actions
1. Define env variable policy:
   - naming, required/optional, defaults, sensitive fields
2. Maintain a runtime matrix doc:
   - local-start vs docker-start differences
3. Ensure every external dependency has:
   - enable/disable switch
   - fallback behavior

### Acceptance
- No hidden env dependency in production path.
- `.env.example` and runtime docs are consistent.

## Workstream E: Data and Migration Standardization
### Direction
- Make schema evolution safe and reversible.

### Actions
1. Migration naming convention:
   - timestamp + intent + scope
2. Every migration PR includes:
   - forward path
   - rollback note
   - compatibility impact
3. Standardize `project_<key>` schema bootstrap and verification checks.

### Acceptance
- Migrations are reviewable and reproducible.
- Multi-project schema isolation remains verifiable after migration.

## Workstream F: Observability and Operations Standardization
### Direction
- Uniform logs, health semantics, and operational evidence.

### Actions
1. Standardize log fields:
   - `request_id`, `project_key`, `project_key_source`, `error_code`
2. Keep two-level health:
   - light health (`/health`)
   - deep health (`/health/deep`)
3. Define incident evidence checklist:
   - compose logs, test artifacts, failing route/sample input

### Acceptance
- Failures can be triaged from logs/artifacts without re-running blindly.

## Workstream G: Delivery Process Standardization
### Direction
- Make merge quality explicit and auditable.

### Actions
1. PR template mandatory fields:
   - scope
   - risk
   - test evidence
   - rollback strategy
2. Commit and branch naming conventions.
3. Dependency update cadence:
   - regular batch updates with validation window.

### Acceptance
- Every merged standardization PR has complete evidence fields.

## Milestones
1. M1 (Week 1): baseline freeze
   - architecture/API/testing/config standards document finalized
   - CI gates active and visible
2. M2 (Week 2): enforcement stage
   - contract and migration conventions applied to active modules
   - observability fields unified on critical routes
3. M3 (Week 3-4): expansion stage
   - critical business e2e coverage increased
   - process and rollback templates fully adopted

## Suggested Ownership
- Architecture/API standards: backend lead
- Testing/CI standards: QA + backend engineer
- Env/migration standards: backend + ops
- Process standards: tech lead + repo maintainer

## Definition of Done (Program Level)
- Standards documented and referenced by PR template.
- CI gates enforce layer-based quality policy.
- Core routes follow unified contract and logging fields.
- Migration/config behavior is predictable across local and docker.
- Team can onboard and deliver changes without hidden conventions.
