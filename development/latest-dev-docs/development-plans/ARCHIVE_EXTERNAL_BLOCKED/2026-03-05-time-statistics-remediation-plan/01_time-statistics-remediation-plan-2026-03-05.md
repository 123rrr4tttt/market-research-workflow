# Time & Statistics Remediation Plan (2026-03-05)

## 1. Background

Based on the current repo audit (time-related features + statistics coupling), the core risk is inconsistent time semantics across API, ingest, graph, and dashboard paths, causing inconsistent counts/trends under the same date range.

## 2. Scope

- Backend API time filtering and aggregation consistency
- Ingest/extraction time parsing robustness and timezone normalization
- Graph time-window and time-decay correctness
- Frontend (legacy + modern) time filter contract alignment
- Minimum regression set for time+statistics behavior

## 3. Goals

1. Unify query-time semantics for statistics-related endpoints.
2. Remove silent fallback on invalid date parameters.
3. Make graph temporal behavior deterministic and configurable.
4. Ensure frontend filter behavior matches backend contracts.
5. Add minimum regression coverage for time+statistics coupling.

## 4. Non-Goals

- No full architecture migration to the planned `source_time/effective_time/time_confidence` model in one iteration.
- No large schema refactor in this batch.

## 5. Key Risks (from audit)

- Invalid date inputs are silently ignored in multiple APIs.
- Different endpoints use different primary time fields (`publish_date/effective_date/created_at`).
- Graph `tau`/`window` behavior does not match API parameter semantics.
- Naive/aware datetime mixing can shift boundary-day stats.
- Ingest date parsing coverage is narrow; malformed `since` can break task runs.

## 6. Milestones

- M1 Contract hardening: date input validation + error response contract.
- M2 Time semantics alignment: common filtering helper for stats/list/trend.
- M3 Graph temporal fix: apply `tau`, enforce `window`, guard future-date decay.
- M4 Frontend alignment: parameter and cache-key normalization.
- M5 Regression gate: minimum time+statistics test set in CI.

## 7. Deliverables

- Code fixes for P0/P1 items.
- One unified helper module for date-range parsing and normalization.
- Updated endpoint behavior notes.
- New/updated tests (backend + frontend critical paths).
- Execution report with before/after checks.

## 8. Acceptance Criteria

- Same time range yields consistent totals/trends across list/stats/report endpoints.
- Invalid date inputs return explicit 4xx with stable error payload.
- Graph temporal params (`start/end/tau/window`) have observable and tested effects.
- Minimum regression suite passes in Python 3.11 and frontend CI pipeline.

## 9. Dependencies

- Python 3.11 test runtime
- Existing core_business test suite
- Frontend-modern lint/test baseline stabilization

## 10. Execution Order

Follow atomic task list in:
- `02_atomic-tasklist-time-statistics-remediation-2026-03-05.md`
- `03_prompt-space-time-window-density-spec-2026-03-05.md`
- `04_executable-plan-task-orchestration-prompt-time-density-2026-03-05.md`

Primary task-id system:

- Use `A1-A8` as the canonical dependency graph.
- `T01-T12` in `04` are execution-level refinements and must map back to `A*` when reporting.

## 11. Serial-Parallel Execution Spec

- L0 (serial): baseline checks, contract freeze, and risk snapshot.
- L1 (parallel): atomic tasks without dependency and without file overlap.
- L2 (serial): conflict merge, cross-module integration, and full regression gate.
- Dependency policy:
  - each task must declare `depends_on` and `blocks` (can be empty arrays);
  - blocked tasks cannot start before dependencies pass gate.
- Conflict policy:
  - if two running tasks touch same file, both tasks enter merge queue;
  - merged patch must be applied by one owner task in serial mode.

## 12. Module IO Contract (Atomic Tasks)

Each atomic task must define module-level IO before implementation:

- `module_input_vars`
  - variable name
  - type
  - source (API/query/body/config/db)
  - default/nullable rule
- `module_output_vars`
  - variable name
  - type
  - semantic meaning
  - sink (response field/db column/event/log)
- `io_mapping`
  - explicit mapping from input vars to output vars and side effects
- `io_boundary`
  - allowed files/modules/tables/endpoints to read-write

Naming convention:

- inputs: `in_*`
- outputs: `out_*`
- internal temporary: `tmp_*`

Gate requirement:

- any IO contract change must include at least one test assertion update or one new contract test.
