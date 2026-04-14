# LLM + Crawler Unified FrontDoor A10 Closure and Validation

Date: 2026-03-08 (PST)
Owner: backend ingest / crawler pipeline
Scope: `main/backend/app/services/ingest/*`

## 1. Closure Summary

This iteration closes remaining AT items up to `AT-10` in the atomic tasklist:

- `AT-06` Retry policy standardization:
  - Added reason-aware retry classification (`transient` / `permanent`).
  - Exposed stable retry counters: `retry_count_by_reason`, `retry_count_by_class`, `retryable`.
- `AT-09` Observability payload:
  - Added stable `metrics_payload` contract (`a9.v1`) in ingest result `meta/debug`.
  - Required fields present: `url_only_document_rate`, `empty_body_rate`, `reason_code_top_n`, `adapter_hit_rate`.
- `AT-10` Gray rollout and rollback:
  - Added project-level rollout toggle for ingest frontdoor (`on/off/canary/passthrough`).
  - Added canary project allowlist and rollback path (`off`).

## 2. Code Landing Map

- `main/backend/app/services/ingest/frontdoor_rollout.py`
- `main/backend/app/services/ingest/retry_policy.py`
- `main/backend/app/services/ingest/metrics_payload.py`
- `main/backend/app/services/ingest/single_url.py`
- `main/backend/app/services/ingest/url_pool.py`
- `main/backend/app/settings/config.py`

Related tests:

- `main/backend/tests/unit/test_ingest_frontdoor_rollout_unittest.py`
- `main/backend/tests/unit/test_ingest_retry_policy_unittest.py`
- `main/backend/tests/unit/test_ingest_metrics_payload_unittest.py`
- `main/backend/tests/unit/test_frontdoor_orchestrator_unittest.py`
- `main/backend/tests/unit/test_single_url_ingest_unittest.py`

## 3. Rollout Controls (AT-10)

New config keys:

- `ingest_frontdoor_rollout_mode`:
  - `on`: always allow frontdoor when request asks for it.
  - `off`: force-disable frontdoor (fast rollback).
  - `canary`: allow only when `project_key` in allowlist.
  - `passthrough`: keep request-driven behavior (compatibility alias with `on` semantics in current implementation).
- `ingest_frontdoor_canary_projects`:
  - comma-separated project keys (case-insensitive).

Routing behavior:

- `url_pool` and `single_url` now both use the same rollout gate.
- Request-level `single_url_frontdoor_enabled=true` no longer bypasses global rollback mode.

## 4. Validation Evidence

### Round-1 Contract and frontdoor unit suite

Command:

```bash
cd main/backend
.venv311/bin/pytest -q \
  tests/unit/test_ingest_retry_policy_unittest.py \
  tests/unit/test_ingest_metrics_payload_unittest.py \
  tests/unit/test_ingest_frontdoor_rollout_unittest.py \
  tests/unit/test_frontdoor_orchestrator_unittest.py \
  tests/unit/test_url_unwrap_unittest.py \
  tests/unit/test_ingest_frontdoor_context_unittest.py \
  tests/unit/test_single_url_ingest_unittest.py \
  tests/core_business/test_ingest_core_contract.py \
  tests/core_business/test_api_group_b_core_contract.py
```

Result: `74 passed, 12 warnings, 8 subtests passed`.

### Round-2 Existing source-library compatibility

Command:

```bash
cd main/backend
.venv311/bin/pytest -q \
  tests/unit/test_source_library_runner_gray_rollout_unittest.py \
  tests/unit/test_source_library_resolver_unittest.py \
  tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py
```

Result: `21 passed, 3 warnings`.

### Round-3 Empirical ingest smoke (real URLs)

Method:

- Execute `collect_urls_from_list` with frontdoor enabled using multiple keyword/url mixes.
- Verify workflow selection, frontdoor enabled flag, and output `metrics_payload` fields.

Observed:

- Case-1: `workflow=front_door_url_routing`, `frontdoor_enabled=true`.
- Case-2: `workflow=front_door_url_routing`, `frontdoor_enabled=true`.
- Payload fields returned with stable schema `a9.v1` including top reason codes and adapter hit rates.

Additional rollout smoke:

- `rollout_mode=off` => `workflow=single_url`, `frontdoor_enabled=false`.
- `rollout_mode=canary` + allowlisted project => frontdoor enabled.
- `rollout_mode=canary` + non-allowlisted project => frontdoor disabled.

## 5. Known Runtime Gaps

- Local smoke run logged `OPENAI_API_KEY` missing for optional LLM extraction steps.
  - This does not block frontdoor routing/persistence contract verification.
- One local environment run showed missing table `etl_job_runs` in a no-migration DB context.
  - Does not affect the validated unit test suites above.

## 6. Acceptance Mapping to Tasklist

- `AT-06`: done.
- `AT-09`: done.
- `AT-10`: done.

Current status: atomic tasklist `AT-01` to `AT-10` implemented with passing regression gates in backend test environment.
