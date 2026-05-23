# Atomic Task List: Item Layering Migration (2026-03-27)

## Execution Status Snapshot

- `AT-ITEM-01`: completed, field classification freeze.
- `AT-ITEM-02`: completed, derived execution plan contract freeze.
- `AT-ITEM-03`: completed, plan-builder extraction.
- `AT-ITEM-04`: completed, unified search plan-consumer cutover.
- `AT-ITEM-05`: completed, runtime diagnostics separation.
- `AT-ITEM-06`: completed, item definition surface contraction.

## Reference Pack

- [01_source-library-ingest-minimal-migration-plan-2026-03-25.md](./01_source-library-ingest-minimal-migration-plan-2026-03-25.md)
- [05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md](./05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md)
- [07_validation-closure-item-layering-migration-2026-03-27.md](./07_validation-closure-item-layering-migration-2026-03-27.md)
- [references/INDEX.md](./references/INDEX.md)
- [references/2026-03-26-item-layering-boundary-constraints.md](./references/2026-03-26-item-layering-boundary-constraints.md)
- [references/2026-03-27-item-field-classification-freeze.md](./references/2026-03-27-item-field-classification-freeze.md)
- [references/2026-03-27-item-execution-plan-contract.md](./references/2026-03-27-item-execution-plan-contract.md)

## Serial Rules

- L0 serial boundary freeze:
  - `AT-ITEM-01`
  - `AT-ITEM-02`
- L1 serial infrastructure extraction:
  - `AT-ITEM-03`
- L2 serial consumer cutover:
  - `AT-ITEM-04`
  - `AT-ITEM-05`
- L3 serial surface cleanup:
  - `AT-ITEM-06`

## Global Acceptance Contract

- `item` remains an abstract source-set definition.
- A natural item may be derived from execution analysis, but once materialized it is still an item-level abstraction.
- Route selection, adapter selection, API-vs-template split, fallback policy, and browser/crawler behavior belong to execution derivation or runtime diagnostics.
- Runtime diagnostics may explain one run, but must not silently redefine stable item meaning.
- Migration must remain backward-compatible until the final surface-contraction task.

## Task AT-ITEM-01: Freeze Field Classification

- Goal: Freeze which existing fields belong to item definition, derived execution plan, and runtime diagnostics.
- Status: completed
- Depends_on: `[]`
- Blocks: `["AT-ITEM-02","AT-ITEM-03","AT-ITEM-04","AT-ITEM-05","AT-ITEM-06"]`
- Input:
  - [references/2026-03-26-item-layering-boundary-constraints.md](./references/2026-03-26-item-layering-boundary-constraints.md)
  - `main/backend/app/services/source_library/resolver.py`
  - `main/backend/app/services/resource_pool/unified_search.py`
- Output:
  - frozen field classification table
  - explicit keep/move/drop decisions for item-facing fields
- Acceptance:
  - every field touched by later tasks has a single declared owner layer.
- Minimum validation:
  - `rg -n "site_entries|official_access_site_entries|search_template_adapter|site_policy|candidate_source_plan|browser_candidate_deferred|search_service_degraded_to" main/backend/app/services -S`

## Task AT-ITEM-02: Freeze Derived Execution Plan Contract

- Goal: Define the minimum contract for a derived execution plan so consumers can stop reading raw item internals.
- Status: completed
- Depends_on: `["AT-ITEM-01"]`
- Blocks: `["AT-ITEM-03","AT-ITEM-04","AT-ITEM-05","AT-ITEM-06"]`
- Input:
  - outputs from `AT-ITEM-01`
  - current handler-cluster refine behavior in `resolver.py`
- Output:
  - frozen plan contract for:
    - route buckets
    - source-route semantics
    - plan-local execution metadata
- Acceptance:
  - the plan contract is sufficient for unified search and downstream runtime consumers without reading execution detail from item definition.
- Minimum validation:
  - `rg -n "_refine_handler_cluster_search_template_item|official_access_site_entries|api_preferred_rerouted" main/backend/app/services/source_library/resolver.py main/backend/app/services/resource_pool/unified_search.py -S`

## Task AT-ITEM-03: Extract Plan Builder

- Goal: Introduce a dedicated plan-builder function/module that derives executable routes from item definition.
- Status: completed
- Depends_on: `["AT-ITEM-01","AT-ITEM-02"]`
- Blocks: `["AT-ITEM-04","AT-ITEM-05","AT-ITEM-06"]`
- Input:
  - `main/backend/app/services/source_library/resolver.py`
  - current handler-cluster refine logic
- Output:
  - explicit `build_item_execution_plan(...)` or equivalent
  - migrated route-bucket derivation path for handler-cluster search items
- Acceptance:
  - plan derivation behavior is centralized and item semantics remain unchanged.
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_resolver_unittest.py`

## Task AT-ITEM-04: Cut Unified Search Over To Derived Plan

- Goal: Make unified search consume the derived execution plan instead of reading mixed-definition item internals.
- Status: completed
- Depends_on: `["AT-ITEM-03"]`
- Blocks: `["AT-ITEM-05","AT-ITEM-06"]`
- Input:
  - plan-builder output from `AT-ITEM-03`
  - `main/backend/app/services/resource_pool/unified_search.py`
- Output:
  - unified search path reads route buckets from the derived plan
  - backward-compatible fallback path retained during migration
- Acceptance:
  - existing item-backed source-library search still works while consumer logic no longer depends on item-internal execution shaping.
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_resource_pool_unified_search_unittest.py main/backend/tests/unit/test_source_library_official_access_adapter_unittest.py`

## Task AT-ITEM-05: Separate Runtime Diagnostics From Item Surface

- Goal: Move execution-observation fields into runtime diagnostics/result structures rather than item views.
- Status: completed
- Depends_on: `["AT-ITEM-04"]`
- Blocks: `["AT-ITEM-06"]`
- Input:
  - current runtime fields emitted by unified search and source-library runtime
  - outputs from `AT-ITEM-01`
- Output:
  - execution-observation fields emitted from runtime diagnostics only
  - no new runtime field added to stable item definition
- Acceptance:
  - runtime trace quality is preserved while item-facing structure becomes narrower.
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_resource_pool_unified_search_unittest.py main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py`

## Task AT-ITEM-06: Contract Item Surface To Definition-First View

- Goal: Make item-facing output definition-first and isolate execution/debug views behind explicit opt-in.
- Status: completed
- Depends_on: `["AT-ITEM-05"]`
- Blocks: `[]`
- Input:
  - completed outputs from `AT-ITEM-01 ~ AT-ITEM-05`
  - source-library item listing paths
- Output:
  - definition-first item surface
  - explicit execution/debug expansion path if still needed
  - closure note with removed-or-relocated fields
- Acceptance:
  - user-facing item output reads as source abstraction, not execution config.
  - compatibility impact is documented node by node.
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_item_resolver_unittest.py main/backend/tests/unit/test_source_library_resolver_unittest.py main/backend/tests/unit/test_resource_pool_unified_search_unittest.py`
