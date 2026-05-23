# Compat And Observability Invariants

Updated: 2026-03-26 PST

## Scope

This file freezes the compat and observability invariants for
`AT-SLIM-04` in the source-library / ingest minimal migration topic.

It exists to prevent later structural work from silently dropping:

- terminal output compatibility
- legacy response compatibility
- job lifecycle observability
- ETL job sink visibility
- batch aggregate counters and debug payloads

## Frozen Invariants

### 1. `terminal_output` Must Remain a First-Class Boundary

The source-library runtime must continue to emit a structured terminal
output object with the contract version `source_library.terminal_output.v1`.

Observed responsibilities in current code:

- `build_source_library_terminal_output(...)` remains the collect-runtime
  compatibility entry
- `to_terminal_output_dto(...)` remains the canonical shape builder
- the DTO keeps the current `item`, `request`, `results`, `errors`, `meta`
  and `raw_snapshot` sections

This boundary must remain explicit because downstream code and tests use
it to distinguish:

- raw runtime output
- compatibility response
- frontdoor handoff payload

### 2. `legacy_result` Must Stay Visible Until a Separate Removal Plan Exists

`legacy_result` is not the authority boundary, but it is still a visible
compatibility field in current responses.

Current behavior worth preserving:

- `to_source_library_response(...)` returns `legacy_result`
- if raw collect output is a dict, the legacy structure is preserved
- if raw collect output is not a dict, a compatibility-shaped fallback is
  synthesized
- `legacy_result_is_deprecated` remains explicit rather than implicit

This task does not remove or rewrite `legacy_result`.

### 3. `job_logger` Must Stay a Real Lifecycle Hook

The job logger must continue to record start / complete / fail lifecycle
events.

Current invariants:

- `start_job(...)` inserts a running `EtlJobRun`
- `complete_job(...)` updates the existing row and merges result payload
- `fail_job(...)` marks the job failed and stores a stable fallback error
  code
- callers must continue to emit job lifecycle records around source-library
  and URL-pool work

The important observability property is not just "logs exist". It is that
the lifecycle is persisted in the ETL job sink.

### 4. `etl_job_runs` Must Stay Visible As The Persistence Sink

`etl_job_runs` is the persistent sink for job lifecycle visibility.

Current code paths that must remain traceable:

- `startup_hooks` references `etl_job_runs` as the observability table
- `job_logger` writes to `EtlJobRun`
- API and operational layers continue to surface job history from that sink

This task freezes the sink visibility, not the schema design.

### 5. Batch Aggregate Fields Must Stay Explicit

`collect_urls_from_list(...)` and related URL-pool work must keep the
batch-level result fields visible and independently testable.

The following are frozen as named outputs, not summary prose:

- `inserted`
- `updated`
- `skipped`
- `inserted_valid`
- `rejected_count`
- `rejection_breakdown`
- `degradation_flags`
- `debug`

Current code also keeps:

- `single_write_workflow`
- `urls`
- `skipped_exists`
- `skipped_fetch_error`
- `queued`
- `display_meta`
- metrics payload attachment
- `source_template_health`

These are observable surfaces, not incidental implementation details.

## Compatibility Rules

1. Do not collapse `terminal_output` into a generic "runtime output" box.
2. Do not drop `legacy_result` while the current source-library response
   path still exposes it.
3. Do not replace `job_logger` / `etl_job_runs` with an implicit tracing
   note.
4. Do not reduce batch aggregate fields to a single `batch_result`
   summary.
5. Do not remove `debug` or `degradation_flags` from URL-pool output
   without a dedicated removal plan.

## Current Evidence From Code

The current implementation already exposes these boundaries:

- `main/backend/app/services/collect_runtime/adapters/source_library.py`
- `main/backend/app/services/source_library/terminal_output.py`
- `main/backend/app/services/ingest/url_pool.py`
- `main/backend/app/services/job_logger.py`
- `main/backend/app/services/ingest/postprocess_frontdoor.py`

This task freezes the contract surface that those modules already expose.

## Minimum Verification

- `python3.11 -m pytest -q main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py main/backend/tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py`
- `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_terminal_output_unittest.py main/backend/tests/unit/test_postprocess_frontdoor_unittest.py`
