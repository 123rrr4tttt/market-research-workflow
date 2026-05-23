# LLM + Crawler Unified FrontDoor A10 Closure and Validation

Date: 2026-03-08 (PST)
Owner: backend ingest / crawler pipeline
Scope: `main/backend/app/services/ingest/*`

## 0. 2026-05-22 Refresh Note

Status: `需更新 -> 已完成当前入口重映射` for this lane.

The old closure note mentioned `single_url.py` and `test_single_url_ingest_unittest.py`; neither exists in the current worktree. Current validation should treat `single_url` as the legacy contract name for `url_pool.single_url_compat -> source_library URL routing -> frontdoor_ingress -> postprocess_frontdoor`.

Lane-6 validation after this refresh:
- `python3.11 -m pytest -q tests/unit/test_ingest_frontdoor_context_unittest.py tests/unit/test_frontdoor_orchestrator_unittest.py tests/unit/test_postprocess_frontdoor_unittest.py` -> `17 passed`.
- `python3.11 -m pytest -q tests/core_business/test_ingest_core_contract.py tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py` -> `27 passed`.
- `git diff --check` -> passed.

Wave3-H follow-up:
- `collect_urls_from_pool` now passes the current pool target into sync/thread frontdoor execution. This prevents search-template/source-search contracts from drifting to the last target in the pool batch.
- Added focused regression in `main/backend/tests/unit/test_ingest_frontdoor_context_unittest.py`.
- Evidence: [automation-runs/ingest-frontdoor-closure/2026-05-22/README.md](../../../automation-runs/ingest-frontdoor-closure/2026-05-22/README.md).
- Still not closed here: high-JS crawler/browser-first router completeness and frontend/dashboard tri-state display.

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
- `main/backend/app/services/ingest/url_pool.py`
- `main/backend/app/services/ingest/frontdoor_ingress.py`
- `main/backend/app/services/ingest/postprocess_frontdoor.py`
- `main/backend/app/services/ingest/terminal_writer.py`
- `main/backend/app/services/source_library/resolver.py`
- `main/backend/app/settings/config.py`

Related tests:

- `main/backend/tests/unit/test_ingest_frontdoor_rollout_unittest.py`
- `main/backend/tests/unit/test_ingest_retry_policy_unittest.py`
- `main/backend/tests/unit/test_ingest_metrics_payload_unittest.py`
- `main/backend/tests/unit/test_frontdoor_orchestrator_unittest.py`
- `main/backend/tests/unit/test_ingest_frontdoor_context_unittest.py`

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

- `url_pool` and the legacy single-URL compatibility path now use the same rollout/frontdoor route context.
- Request-level frontdoor enablement no longer bypasses global rollback mode.

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

- `rollout_mode=off` => legacy URL execution compatibility falls back according to rollout config.
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
