# Validation Closure: Item Layering Migration

Updated: 2026-03-27 PST

## Scope Closed

- `AT-ITEM-01` field classification freeze
- `AT-ITEM-02` derived execution plan contract freeze
- `AT-ITEM-03` plan-builder extraction
- `AT-ITEM-04` unified search plan-consumer cutover
- `AT-ITEM-05` runtime diagnostics separation
- `AT-ITEM-06` definition-first item surface contraction

## Delivered Code

- Added `main/backend/app/services/source_library/item_plan.py`
  - `build_item_execution_plan(...)`
  - `build_item_definition_view(...)`
- `list_effective_items(...)` now returns definition-first items by default
- `list_effective_items(..., include_execution_plan=True)` now exposes explicit plan opt-in
- unified search now consumes derived plan inputs and emits runtime observations via `runtime_diagnostics`
- handler-cluster runtime aggregation now reads runtime diagnostics instead of treating `site_entries_used` as runtime state
- source-library API item listing now supports explicit execution-plan expansion and grouped handler derivation uses execution plan internally

## Compatibility Outcome

- default item output reads as source abstraction again
- handler-cluster execution behavior remains preserved through local plan derivation
- runtime observability remains available, but no longer mutates item views

## Validation

- `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_resolver_unittest.py main/backend/tests/unit/test_resource_pool_unified_search_unittest.py`
  - `30 passed, 22 skipped`
- `python3.11 -m pytest -q main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py main/backend/tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py`
  - `13 passed`
- `python3.11 -m pytest -q main/backend/tests/core_business/test_source_library_core_contract.py`
  - `11 passed`
- `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_item_resolver_unittest.py main/backend/tests/unit/test_source_library_resolver_unittest.py main/backend/tests/unit/test_resource_pool_unified_search_unittest.py main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py main/backend/tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py`
  - `68 passed`
- `python3.11 -m pytest -q main/backend/tests/core_business/test_source_library_core_contract.py main/backend/tests/unit/test_source_library_official_access_adapter_unittest.py`
  - `16 passed`

## Residual Risk

- `item_plan.py` is now the single derivation choke point for handler-cluster source-set shaping; future execution additions should extend plan contract first, not re-inject fields into item definition.
- `site_entries_used` remains present for compatibility, but consumers should treat it as definition-level entry view only.
