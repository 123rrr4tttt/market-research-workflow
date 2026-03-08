# Atomic Task List: Time & Statistics Remediation (2026-03-05)

## Global Serial-Parallel Rules

- L0 serial bootstrap: A1 contract hardening starts first.
- L1 parallel batch:
  - group-1 backend: A2, A3, A4, A5
  - group-2 frontend: A6, A7
- L2 serial closure: A8 regression gate after A2-A7 pass.
- File-conflict rule: tasks touching same file run serially in task-id order.

## Global Module IO Contract

Each task must declare:

- `module_input_vars`: `in_*` names + type + source + default
- `module_output_vars`: `out_*` names + type + sink
- `io_mapping`: `in_* -> out_*` and side effects
- `io_boundary`: allowed read/write scope

## Task A1: API Date Validation Hardening

- 目标: Remove silent `pass` branches for invalid date inputs in stats/list APIs.
- depends_on: `[]`
- blocks: `["A2","A8"]`
- 输入: `main/backend/app/api/policies.py`, `main/backend/app/api/dashboard.py`
- 输出: Explicit 4xx error response on invalid date formats.
- 验收:
  - Invalid `start/end/start_date/end_date` returns deterministic error payload.
  - No silent fallback to unfiltered query.
- 最小门禁:
  - `python3 -m compileall main/backend/app/api/policies.py main/backend/app/api/dashboard.py`
  - `cd main/backend && python3.11 -m pytest -q tests/core_business/test_api_group_b_core_contract.py`
- 模块 IO:
  - module_input_vars: `in_start(str?)`, `in_end(str?)`, `in_start_date(str?)`, `in_end_date(str?)`
  - module_output_vars: `out_http_status(int)`, `out_error_code(str?)`, `out_filters_applied(bool)`
  - io_mapping: invalid `in_*` -> `out_http_status=4xx`, `out_error_code=INVALID_DATE_PARAM`
  - io_boundary: `api/policies.py`, `api/dashboard.py`, shared API error contract

## Task A2: Time Field Semantics Unification for Statistics

- 目标: Ensure list/stats/trend/report share one consistent filtering semantics.
- depends_on: `["A1"]`
- blocks: `["A8"]`
- 输入: `main/backend/app/api/policies.py`, `main/backend/app/services/report.py`, related helpers
- 输出: Shared filtering utility and consistent aggregation behavior.
- 验收:
  - Same range -> same included record set across list/stats/report.
  - Trend bucket source field aligned with filtering semantics.
- 最小门禁:
  - `python3 -m compileall main/backend/app/api/policies.py main/backend/app/services/report.py`
  - `cd main/backend && python3.11 -m pytest -q tests/core_business/test_admin_dashboard_process_core_contract.py`
- 模块 IO:
  - module_input_vars: `in_start_date(date?)`, `in_end_date(date?)`, `in_project_key(str)`
  - module_output_vars: `out_record_set(list)`, `out_total_count(int)`, `out_trend_series(list)`
  - io_mapping: same `in_*` must produce aligned `out_record_set/out_total_count` across list/stats/report
  - io_boundary: `api/policies.py`, `services/report.py`, shared filter helper module

## Task A3: Ingest Date Parsing & Since Robustness

- 目标: Expand date parsing support and harden `since` parsing fallback.
- depends_on: `[]`
- blocks: `["A8"]`
- 输入: `main/backend/app/services/ingest/news.py`, `main/backend/app/services/resource_pool/extract.py`
- 输出: Broader parser support and non-fatal handling for malformed `since`.
- 验收:
  - Common timestamp formats parse successfully.
  - Malformed `since` does not crash whole task flow.
- 最小门禁:
  - `python3 -m compileall main/backend/app/services/ingest/news.py main/backend/app/services/resource_pool/extract.py`
- 模块 IO:
  - module_input_vars: `in_raw_datetime(str?)`, `in_since(str?)`
  - module_output_vars: `out_publish_date(date?)`, `out_since_dt(datetime?)`, `out_parse_error(str?)`
  - io_mapping: parse success -> normalized `out_*`; parse fail -> non-fatal `out_parse_error`
  - io_boundary: `services/ingest/news.py`, `services/resource_pool/extract.py`

## Task A4: Datetime Timezone Consistency

- 目标: Remove naive/aware datetime mixing in statistics-critical paths.
- depends_on: `[]`
- blocks: `["A8"]`
- 输入: `main/backend/app/services/governance/retention.py`, `main/backend/app/services/job_logger.py`
- 输出: Unified timezone-aware datetime policy.
- 验收:
  - Boundary-day retention and duration metrics deterministic across environments.
- 最小门禁:
  - `python3 -m compileall main/backend/app/services/governance/retention.py main/backend/app/services/job_logger.py`
- 模块 IO:
  - module_input_vars: `in_now(datetime tz-aware)`, `in_retention_days(int)`
  - module_output_vars: `out_cutoff_dt(datetime tz-aware)`, `out_duration_seconds(float?)`
  - io_mapping: `in_now/in_retention_days` -> deterministic `out_cutoff_dt` in UTC policy
  - io_boundary: `services/governance/retention.py`, `services/job_logger.py`

## Task A5: Graph Temporal Logic Fix

- 目标: Make `tau/window` behavior effective and testable.
- depends_on: `[]`
- blocks: `["A8"]`
- 输入: `main/backend/app/services/graph/builder.py`, `main/backend/app/services/graph/adapters/policy.py`
- 输出: `tau` propagated, `window` enforced, future-date decay guarded.
- 验收:
  - Parameter changes produce expected graph/statistics differences.
  - No silent drop without trace for date parse/type issues.
- 最小门禁:
  - `python3 -m compileall main/backend/app/services/graph/builder.py main/backend/app/services/graph/adapters/policy.py`
- 模块 IO:
  - module_input_vars: `in_start_date(datetime?)`, `in_end_date(datetime?)`, `in_tau(float?)`, `in_window(int?)`
  - module_output_vars: `out_nodes(list)`, `out_edges(list)`, `out_edge_weight(float)`
  - io_mapping: `in_tau/in_window` must measurably affect `out_edges/out_edge_weight`
  - io_boundary: `services/graph/builder.py`, `services/graph/adapters/policy.py`

## Task A6: Legacy Frontend Contract Alignment

- 目标: Align date parameter naming/semantics and sorting behavior with backend contract.
- depends_on: `["A1"]`
- blocks: `["A8"]`
- 输入: `main/frontend/templates/policy-tracking.html`, `main/frontend/templates/policy-graph.html`, `main/frontend/templates/data-dashboard.html`
- 输出: Consistent request params and timeline/table sort semantics.
- 验收:
  - Same UI date range yields consistent results across pages.
- 最小门禁:
  - `rg -n "start_date|end_date|start=|end=" main/frontend/templates/policy-tracking.html main/frontend/templates/policy-graph.html main/frontend/templates/data-dashboard.html`
- 模块 IO:
  - module_input_vars: `in_start_date(str?)`, `in_end_date(str?)`, `in_sort_by(str?)`
  - module_output_vars: `out_request_query(str)`, `out_sorted_rows(list)`, `out_timeline_rows(list)`
  - io_mapping: same `in_*` should produce consistent `out_*` across three legacy pages
  - io_boundary: `frontend/templates/policy-tracking.html`, `policy-graph.html`, `data-dashboard.html`

## Task A7: Modern Frontend Query/Cache Normalization

- 目标: Prevent cache-key fragmentation and invalid date submission behavior.
- depends_on: `["A1"]`
- blocks: `["A8"]`
- 输入: `main/frontend-modern/src/pages/GraphPage.tsx`, `main/frontend-modern/src/lib/queryKeys.ts`, `main/frontend-modern/src/lib/api/domains/graph-workflow.ts`
- 输出: Graph-kind-aware key normalization and date-range validation UX.
- 验收:
  - No cache split caused by unused filters.
  - Invalid/reversed date range blocked or clearly surfaced.
- 最小门禁:
  - `cd main/frontend-modern && npm run -s lint`
- 模块 IO:
  - module_input_vars: `in_graph_kind(str)`, `in_start_date(str?)`, `in_end_date(str?)`, `in_filters(obj)`
  - module_output_vars: `out_query_key(array)`, `out_request_query(string)`, `out_validation_error(str?)`
  - io_mapping: only graph-kind-relevant `in_filters` may enter `out_query_key/out_request_query`
  - io_boundary: `frontend-modern/src/pages/GraphPage.tsx`, `lib/queryKeys.ts`, `lib/api/domains/graph-workflow.ts`

## Task A8: Time+Statistics Regression Gate

- 目标: Add minimal end-to-end regression for time/stat coupling.
- depends_on: `["A2","A3","A4","A5","A6","A7"]`
- blocks: `[]`
- 输入: backend core tests + dashboard/process API paths + optional frontend e2e
- 输出: Minimum reproducible regression suite and CI command set.
- 验收:
  - At least 3 scenarios: boundary window, invalid input behavior, trend bucket consistency.
- 最小门禁:
  - `cd main/backend && python3.11 -m pytest -q tests/core_business/test_api_group_b_core_contract.py tests/core_business/test_admin_dashboard_process_core_contract.py tests/core_business/test_process_consistency_core_contract.py`
- 模块 IO:
  - module_input_vars: `in_test_dataset(fixture)`, `in_time_window(tuple)`, `in_invalid_params(case-set)`
  - module_output_vars: `out_passed(int)`, `out_failed(int)`, `out_regression_report(file)`
  - io_mapping: each scenario binds `in_time_window/in_invalid_params` -> deterministic `out_*`
  - io_boundary: backend core tests and related contract tests only
