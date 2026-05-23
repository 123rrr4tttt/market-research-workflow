<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-06-handler-cluster-frontdoor-middle-layer-alignment/02_atomic-tasklist-handler-cluster-frontdoor-middle-layer-alignment-2026-03-06.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-06-handler-cluster-frontdoor-middle-layer-alignment/02_atomic-tasklist-handler-cluster-frontdoor-middle-layer-alignment-2026-03-06.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Atomic Task List: Handler-Cluster Frontdoor Middle-Layer Alignment (2026-03-06)

## Execution Status Snapshot

- closure_status: ready_to_close
- `A1-A4`: 已完成最小收敛切口，可作为当前实现基线。
- `A5-A7`: 已完成，系统中间层协议、运行时配置层语义、最小回归门禁均已补齐。
- `A8`: 已完成。provider 解析、错误收口、本机 `scrapyd` 运行态与最前侧文档写入均已验证。

## Global Serial-Parallel Rules

- L0 serial bootstrap: `A1` 先冻结入口契约与任务边界。
- L1 serial convergence: `A2 -> A3 -> A4` 按入口到回灌链顺序执行，避免前侧与中段协议打架。
- L2 parallel extension:
  - group-1 orchestration: `A5`, `A6`
  - group-2 verification: `A7`
- L3 serial closure: `A8` 在 `A5-A7` 通过后执行。
- File-conflict rule: touching `source_library.py`, `resolver.py`, `single_url.py` 的任务必须按 task-id 串行。

## Global Module IO Contract

Each task must declare:

- `module_input_vars`: `in_*` names + type + source + default
- `module_output_vars`: `out_*` names + type + sink
- `io_mapping`: `in_* -> out_*` and side effects
- `io_boundary`: allowed read/write scope

## Task A1: Front-Door Contract Freeze

- 目标: Freeze the system middle-layer contract for `handler-cluster/site-entry` routing before further changes.
- status: completed
- depends_on: `[]`
- blocks: `["A2","A5","A6","A8"]`
- 输入: current source-library front-door flow, handler-cluster item shape, item/url routing assumptions
- 输出: one stable contract describing:
  - `search params + item/url -> 系统中间层 -> 文档产出`
  - `url -> 系统中间层 -> 搜索适配 -> 系统中间层`
- 验收:
  - No documentation path still treats project-level `crawler.*` as system middle layer.
  - Front-door ownership is explicitly assigned to `run_item_by_key/run_item_payload`.
- 最小门禁:
  - review plan doc and atomic task doc consistency
- 模块 IO:
  - module_input_vars: `in_item_payload(obj)`, `in_query(str?)`, `in_url(str?)`
  - module_output_vars: `out_middle_layer_contract(doc)`, `out_frontdoor_owner(str)`, `out_non_goals(list)`
  - io_mapping: `in_*` -> contract sections + ownership decision
  - io_boundary: development docs only

## Task A2: Remove Adapter-Side Bypass

- 目标: Ensure `handler_cluster_item` no longer bypasses the front door from adapter-side special casing.
- status: completed
- depends_on: `["A1"]`
- blocks: `["A3","A7","A8"]`
- 输入: `main/backend/app/services/collect_runtime/adapters/source_library.py`
- 输出: adapter path delegates back to unified front-door item execution.
- 验收:
  - Adapter no longer directly treats `unified_search_by_item_payload(...)` as front-door owner.
  - Runtime path enters `run_item_by_key` first.
- 最小门禁:
  - `cd main/backend && .venv311/bin/python -m pytest tests/unit/test_source_library_handler_cluster_unittest.py -q`
- 模块 IO:
  - module_input_vars: `in_handler_cluster_item(obj)`, `in_query(str)`, `in_runtime_ctx(obj?)`
  - module_output_vars: `out_runner_call(str)`, `out_frontdoor_path(str)`, `out_bypass_removed(bool)`
  - io_mapping: `in_handler_cluster_item` -> `out_runner_call=run_item_by_key` -> `out_bypass_removed=true`
  - io_boundary: `collect_runtime/adapters/source_library.py`, related unit test

## Task A3: Candidate URL Re-Entry into Front-Door Routing

- 目标: Make handler-cluster search candidates re-enter front-door URL routing instead of mid-layer direct write.
- status: completed
- depends_on: `["A2"]`
- blocks: `["A4","A7","A8"]`
- 输入: `main/backend/app/services/source_library/resolver.py`, resource-pool candidate payloads
- 输出: candidate URLs routed through front-door URL workflow.
- 验收:
  - observed `single_write_workflow = front_door_url_routing`
  - candidate handling path is front-door routing, not direct mid-layer ingestion
- 最小门禁:
  - `cd main/backend && .venv311/bin/python -m pytest tests/unit/test_source_library_handler_cluster_unittest.py -q`
- 模块 IO:
  - module_input_vars: `in_candidate_urls(list)`, `in_item_key(str)`, `in_query(str)`
  - module_output_vars: `out_routed_urls(list)`, `out_workflow_key(str)`, `out_routing_trace(list)`
  - io_mapping: `in_candidate_urls` -> `out_workflow_key=front_door_url_routing` -> routed ingest requests
  - io_boundary: `services/source_library/resolver.py`, source-library runtime path

## Task A4: Preserve Mid-Layer Search as Capability, Not Entry Owner

- 目标: Keep `resource_pool/unified_search` as candidate-discovery capability, not as the front-door orchestration layer.
- status: completed
- depends_on: `["A3"]`
- blocks: `["A5","A7","A8"]`
- 输入: `main/backend/app/services/resource_pool/unified_search.py`
- 输出: clear role split between candidate discovery and front-door orchestration.
- 验收:
  - `unified_search` still returns/filters candidates
  - front-door ownership remains outside `unified_search`
- 最小门禁:
  - `cd main/backend && .venv311/bin/python -m pytest tests/unit/test_resource_pool_unified_search_unittest.py tests/unit/test_resource_pool_search_capabilities_unittest.py -q`
- 模块 IO:
  - module_input_vars: `in_search_params(obj)`, `in_site_entries(list)`, `in_query(str)`
  - module_output_vars: `out_candidates(list)`, `out_candidate_meta(list)`, `out_entry_role(str)`
  - io_mapping: `in_search_params/in_site_entries` -> `out_candidates`, while `out_entry_role=candidate_discovery_only`
  - io_boundary: `services/resource_pool/unified_search.py`, related unit tests

## Task A5: System Middle-Layer Protocol Formalization

- 目标: Formalize `handler.cluster` as a system-level protocol instead of an adapter-only convention.
- status: completed
- depends_on: `["A4"]`
- blocks: `["A8"]`
- 输入: front-door item contract, handler-cluster payload shape, resolver channel selection logic
- 输出: explicit protocol fields for search-capable item execution.
- 验收:
  - protocol can represent `item`, `url`, `site_entries`, `candidate_urls`, `write_mode`
  - same protocol can drive both search and URL-ingest chains
- 最小门禁:
  - `python3 -m compileall main/backend/app/services/source_library`
- 模块 IO:
  - module_input_vars: `in_item(obj)`, `in_site_entries(list?)`, `in_candidate_urls(list?)`, `in_write_mode(str?)`
  - module_output_vars: `out_protocol(obj)`, `out_route_decision(str)`, `out_usable_for_ingest(bool)`
  - io_mapping: protocol-normalized `in_*` -> one route decision contract for front door
  - io_boundary: `services/source_library/*`, protocol docs/tests

## Task A6: Project-Level Crawler Channel Demotion

- 目标: Prevent project-level `crawler.*` channels from leaking into system architecture semantics.
- status: completed
- depends_on: `["A4"]`
- blocks: `["A8"]`
- 输入: resolver channel preference logic, crawler provider selection path, docs/spec wording
- 输出: `crawler.*` treated as config-layer runtime choice only.
- 验收:
  - architecture docs no longer use `crawler.*` as system layer noun
  - channel selection output is clearly marked config/runtime
- 最小门禁:
  - `rg -n "crawler\\.[A-Za-z0-9_-]+" development/latest-dev-docs main/backend/app/services/source_library main/backend/app/services/ingest`
- 模块 IO:
  - module_input_vars: `in_project_key(str)`, `in_channel_candidates(list)`, `in_provider_registry(obj)`
  - module_output_vars: `out_channel_key(str?)`, `out_runtime_provider(str?)`, `out_arch_layer_label(str)`
  - io_mapping: config/runtime selection must not mutate `out_arch_layer_label` into system middle layer
  - io_boundary: source-library docs + routing modules + ingest routing docs

## Task A7: Front-Door Regression and Live Trace Gate

- 目标: Add a minimum regression set proving that real handler-cluster execution re-enters front-door routing.
- status: completed
- depends_on: `["A2","A3","A4"]`
- blocks: `["A8"]`
- 输入: unit tests, one live replay query, routing trace output
- 输出: reproducible verification bundle for front-door convergence.
- 验收:
  - unit tests cover adapter no-bypass and candidate re-routing
  - live replay can expose `single_write_workflow = front_door_url_routing`
- 最小门禁:
  - `cd main/backend && .venv311/bin/python -m pytest tests/unit/test_source_library_handler_cluster_unittest.py tests/unit/test_resource_pool_unified_search_unittest.py tests/unit/test_resource_pool_search_capabilities_unittest.py -q`
- 模块 IO:
  - module_input_vars: `in_query(str)`, `in_item_key(str)`, `in_test_cases(list)`
  - module_output_vars: `out_passed(int)`, `out_trace(obj)`, `out_regression_note(file?)`
  - io_mapping: replay + tests -> deterministic trace + pass/fail summary
  - io_boundary: listed unit tests and one front-door runtime replay path

## Task A8: Provider Runtime Closure

- 目标: After front-door convergence is stable, close the remaining provider-runtime breakpoints that still block document insertion.
- status: completed
- depends_on: `["A5","A6","A7"]`
- blocks: `[]`
- 输入: crawler provider registry, runtime provider adapter, live insertion path
- 输出: provider runtime path no longer fails on incompatible provider type registration.
- 验收:
  - no `unsupported crawler provider_type` on the validated live path
  - provider failure must surface as explicit runtime availability error when `scrapyd` is absent
  - high-quality URL can proceed from front-door routing to document insertion once runtime env is available
- 最小门禁:
  - targeted provider registration test or one validated live replay in `demo_proj`
- 模块 IO:
  - module_input_vars: `in_provider_type(str)`, `in_url(str)`, `in_project_key(str)`
  - module_output_vars: `out_provider_adapter(obj?)`, `out_inserted_docs(int)`, `out_runtime_error(str?)`
  - io_mapping: valid provider registry + routed URL -> `out_inserted_docs > 0`, invalid registry -> explicit `out_runtime_error`
  - io_boundary: crawler provider registry/runtime adapter + validated live path only

## Verification Snapshot

- Source-library gate:
  - `tests/unit/test_source_library_resolver_unittest.py`
  - `tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py`
  - result: `13 passed`
  - contract guards: merged candidate first-seen order, aggregated `by_url` input order, static URL-list item and runtime URL-list path convergence
- Resource-pool gate:
  - `tests/unit/test_resource_pool_unified_search_unittest.py`
  - `tests/unit/test_resource_pool_search_capabilities_unittest.py`
  - result: `6 passed`
- Combined targeted gate:
  - result: `19 passed`
- Live replay:
  - item: `report1.root_site_search`
  - query-set: `["Humane AI Pin", "rabbit r1", "Oura Ring"]`
  - observed: local `scrapyd` daemon healthy at `http://127.0.0.1:6800`
  - observed: `single_write_workflow = front_door_url_routing`
  - observed: default front-door route is mechanical-first with `prefer_crawler_first = false`
  - observed: `channels_used = ["url_pool", "generic_web.search_template"]` on the mechanical-first live path
  - observed: no longer hits `unsupported crawler provider_type: scrapy`
  - observed: static URL-list item and runtime URL-list now share the same front-door `url_routing` path
  - observed: `mechanical_first_30 = 20.092s`, `crawler_first_30 = 53.529s`, speedup `2.664x`
