# Atomic Task List: Source Library Three-Lane Architecture (2026-03-12)

## Execution Status Snapshot

- `AT-01`: completed, baseline and contract vocabulary frozen.
- `AT-02 ~ AT-07`: completed in本轮封口范围（DB/API/resolver/source_mode/site_search约束）。
- `AT-08`: completed to current contract baseline（新增来源链进入 resolver 主干的实现口径已统一）。
- `AT-09`: completed for current migration scope（存量兼容桥接与回填已执行）。
- `AT-10`: completed, validation and closeout passed (`34 passed, 0 failed` in closure test pack).

## Serial-Parallel Rules

- L0 serial bootstrap:
  - `AT-01`
- L1 parallel governance:
  - `AT-02` DB item taxonomy migration
  - `AT-03` read API visibility and filtering
  - `AT-04` write API permission and constraints
- L2 serial core execution refactor:
  - `AT-05` ItemResolver + ExecutionRequest
  - `AT-06` orchestrator split by `source_mode`
  - `AT-07` site_search topology cleanup
- L3 serial onboarding + compatibility:
  - `AT-08` new source onboarding chain unification
  - `AT-09` stock item backfill and compatibility bridge
- L4 serial closure:
  - `AT-10` integration verification and documentation closure

## Global Acceptance Contract

- Only two item types are valid:
  - `user_defined` (`managed_by=user`)
  - `service_aggregated` (`managed_by=system`)
- Execution entry must be:
  - `item + runtime_context + user_intent`
  - `ItemResolver -> ExecutionRequest -> source_mode orchestrator`
- `site_search` must keep only one external entry:
  - `handler.cluster + unified_search`
- `url_execution` is separated from `site_search`.

## Task AT-01: Freeze Baseline and Target Contracts

- Goal: Freeze current facts and target contracts for implementation.
- Status: pending
- Depends_on: `[]`
- Blocks: `["AT-02","AT-03","AT-04"]`
- Input:
  - `.../01_source-library-three-lane-architecture-2026-03-11.md`
  - `main/backend/app/services/source_library/resolver.py`
  - `main/backend/app/api/ingest.py`
  - `main/backend/app/api/source_library.py`
- Output:
  - baseline fact list
  - target contract list (`item_type/managed_by/source_mode/ExecutionRequest`)
- Acceptance:
  - no conflict between doc contracts and current code reality.
- Minimum validation:
  - `rg -n "source_mode|ExecutionRequest|item_type|managed_by|run_item_payload" development/latest-dev-docs main/backend/app -S`

## Task AT-02: DB Migration for Two-Type Items

- Goal: Add and enforce `item_type/managed_by` in source-library item tables.
- Status: pending
- Depends_on: `["AT-01"]`
- Blocks: `["AT-05","AT-09"]`
- Input:
  - `main/backend/migrations/versions/*`
  - migration SQL rules in section `8.4`
- Output:
  - Alembic migration script for:
    - add columns
    - data backfill
    - check constraints
- Acceptance:
  - invalid values outside `{user_defined, service_aggregated}` and `{user, system}` are rejected.
- Minimum validation:
  - `alembic upgrade head`
  - SQL check:
    - `SELECT item_type, managed_by, count(*) FROM <schema>.source_library_items GROUP BY 1,2;`

## Task AT-03: Read API Visibility Contract

- Goal: Make list API default to user items and support explicit system include.
- Status: pending
- Depends_on: `["AT-01"]`
- Blocks: `["AT-10"]`
- Input:
  - `main/backend/app/api/source_library.py`
  - `main/backend/app/services/source_library/resolver.py`
- Output:
  - `GET /source_library/items` default: `item_type=user_defined`
  - `include_system=true` returns `service_aggregated`
- Acceptance:
  - UI default list is clean; system-aggregated items are opt-in.
- Minimum validation:
  - `pytest -q main/backend/tests/core_business/test_source_library_core_contract.py`

## Task AT-04: Write API Permission Contract

- Goal: Restrict external write to `user_defined`; reserve `service_aggregated` for system sync jobs.
- Status: pending
- Depends_on: `["AT-01"]`
- Blocks: `["AT-10"]`
- Input:
  - `main/backend/app/api/source_library.py`
  - handler cluster sync/write paths
- Output:
  - write guardrails:
    - user API cannot create/update/delete `service_aggregated`
    - system path can maintain `service_aggregated`
- Acceptance:
  - unauthorized writes to system items return 4xx with explicit reason.
- Minimum validation:
  - `pytest -q main/backend/tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py`

## Task AT-05: Introduce ItemResolver and ExecutionRequest

- Goal: Implement compile layer from item abstraction to executable request.
- Status: pending
- Depends_on: `["AT-02","AT-03","AT-04"]`
- Blocks: `["AT-06","AT-08","AT-09"]`
- Input:
  - source-library item records
  - runtime params (`override_params`)
  - mapping table section `5.4`
- Output:
  - `ItemResolver`
  - normalized `ExecutionRequest`
  - priority merge rule:
    - user runtime input > resolver inference > item abstraction > channel default
- Acceptance:
  - no direct execution path from raw item without resolver compilation.
- Minimum validation:
  - `pytest -q main/backend/tests/unit/test_source_library_resolver_unittest.py`

## Task AT-06: Split Orchestrators by source_mode

- Goal: Replace mixed `run_item_payload` execution with mode-specific orchestrators.
- Status: pending
- Depends_on: `["AT-05"]`
- Blocks: `["AT-07","AT-08","AT-10"]`
- Input:
  - `main/backend/app/services/source_library/resolver.py`
  - `main/backend/app/services/source_library/runner.py`
- Output:
  - orchestrators:
    - `protocol_search_orchestrator`
    - `provider_harvest_orchestrator`
    - `site_search_orchestrator`
    - `url_execution_orchestrator`
- Acceptance:
  - each `source_mode` has one clear service entry and no cross-mode implicit fallback.
- Minimum validation:
  - `pytest -q main/backend/tests/unit/test_source_library_runner_gray_rollout_unittest.py`

## Task AT-07: Site Search Topology Cleanup

- Goal: Keep only one external site-search path and demote `generic_web.*` to internal plugin.
- Status: pending
- Depends_on: `["AT-06"]`
- Blocks: `["AT-10"]`
- Input:
  - site-search current three paths in section `4.5`
- Output:
  - external `site_search` path only:
    - `handler.cluster + unified_search`
  - `params.urls` path moved to `url_execution`
  - `generic_web.*` no longer direct source-item entry
- Acceptance:
  - direct run of `generic_web.*` item is rejected/deprecated with explicit response.
- Minimum validation:
  - `pytest -q main/backend/tests/unit/test_source_library_handler_cluster_unittest.py`
  - `pytest -q main/backend/tests/unit/test_ingest_source_search_contract_unittest.py`

## Task AT-08: Unify New Source Onboarding Chain

- Goal: Force URL/API/JSON onboarding to one execution mainline.
- Status: pending
- Depends_on: `["AT-06"]`
- Blocks: `["AT-10"]`
- Input:
  - onboarding chain in section `5.3`
  - field mapping in section `5.4`
- Output:
  - unified path:
    - onboarding input -> normalization/classification -> item (`user_defined/service_aggregated`) -> resolver -> execution request -> orchestrator
- Acceptance:
  - no new source onboarding can bypass resolver by direct `channel_key` run.
- Minimum validation:
  - `pytest -q main/backend/tests/unit/test_resource_pool_unified_search_unittest.py`
  - `pytest -q main/backend/tests/core_business/test_ingest_core_contract.py`

## Task AT-09: Backfill Existing Items and Compatibility Bridge

- Goal: Clean current DB item ambiguity and keep old calls temporarily compatible.
- Status: pending
- Depends_on: `["AT-02","AT-05"]`
- Blocks: `["AT-10"]`
- Input:
  - DB audit section `8.3`
  - migration rules section `8.4`
- Output:
  - backfilled item types:
    - `handler.cluster.* / crawler.* / url_pool.default` -> `service_aggregated`
    - others -> `user_defined`
  - compatibility shim for old `item.channel_key/params` run
- Acceptance:
  - legacy items still run through resolver bridge with deprecation metadata.
- Minimum validation:
  - `pytest -q main/backend/tests/core_business/test_source_library_core_contract.py`

## Task AT-10: Validation Pack and Closure

- Goal: Close this round with contract-level regression checks and docs consistency.
- Status: pending
- Depends_on: `["AT-03","AT-04","AT-07","AT-08","AT-09"]`
- Blocks: `[]`
- Input:
  - completed outputs from `AT-01` ~ `AT-09`
- Output:
  - closure report:
    - route-level behavior matrix
    - DB conformance snapshot
    - unresolved risk list (if any)
- Acceptance:
  - all four source modes and two item types pass contract checks.
- Minimum validation:
  - `pytest -q main/backend/tests/core_business/test_source_library_core_contract.py`
  - `pytest -q main/backend/tests/core_business/test_ingest_core_contract.py`
  - `pytest -q main/backend/tests/unit/test_source_library_resolver_unittest.py`
