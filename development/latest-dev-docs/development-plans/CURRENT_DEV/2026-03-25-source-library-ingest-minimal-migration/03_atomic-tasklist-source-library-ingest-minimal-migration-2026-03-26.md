# Atomic Task List: Source-Library / Ingest Minimal Migration (2026-03-26)

## Execution Status Snapshot

- `AT-SLIM-01`: completed, migration scope and acceptance contract freeze.
- `AT-SLIM-02`: completed, contract regression pack freeze.
- `AT-SLIM-03`: completed, node-mapping and touched-node execution sheet freeze.
- `AT-SLIM-04`: completed, compat and observability invariants freeze.
- `AT-SLIM-05`: completed, batch routing primitive extraction.
- `AT-SLIM-06`: completed, explicit batch frontdoor handoff helper introduction.
- `AT-SLIM-07`: completed, `collect_urls_from_list(...)` internal switch landing.
- `AT-SLIM-08`: completed, shared ingress convergence while preserving compat callers.
- `AT-SLIM-09`: completed, batch default switch with rollback knob.
- `AT-SLIM-10`: completed, regression pack and documentation closure.

## Reference Pack

- [01_source-library-ingest-minimal-migration-plan-2026-03-25.md](./01_source-library-ingest-minimal-migration-plan-2026-03-25.md)
- [02_wave0-freeze-and-acceptance-contract-2026-03-26.md](./02_wave0-freeze-and-acceptance-contract-2026-03-26.md)
- [references/INDEX.md](./references/INDEX.md)
- [references/02_source-library-ingest-node-mapping-and-preservation-checklist-2026-03-26.md](./references/02_source-library-ingest-node-mapping-and-preservation-checklist-2026-03-26.md)
- [references/2026-03-26-batch-helper-input-boundary-and-runtime-target-contract.md](./references/2026-03-26-batch-helper-input-boundary-and-runtime-target-contract.md)
- [references/2026-03-26-batch-switch-rollout-dispatch-precedence-matrix.md](./references/2026-03-26-batch-switch-rollout-dispatch-precedence-matrix.md)
- [references/2026-03-26-compat-observability-invariants-source-library-ingest-minimal-migration.md](./references/2026-03-26-compat-observability-invariants-source-library-ingest-minimal-migration.md)
- [05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md](./05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md)
- [04_parallel-wave-plan-source-library-ingest-minimal-migration-2026-03-26.md](./04_parallel-wave-plan-source-library-ingest-minimal-migration-2026-03-26.md)

## Serial-Parallel Rules

- L0 serial bootstrap:
  - `AT-SLIM-01`
- L1 parallel freeze pack:
  - `AT-SLIM-02` contract regression baseline
  - `AT-SLIM-03` node mapping and touched-node execution sheet
  - `AT-SLIM-04` compat and observability invariant freeze
- L2 serial shared-helper extraction:
  - `AT-SLIM-05` batch routing primitive extraction
  - `AT-SLIM-06` explicit batch frontdoor handoff helper
- L3 serial call-graph switch:
  - `AT-SLIM-07` `collect_urls_from_list(...)` internal switch
  - `AT-SLIM-08` shared ingress convergence with compat retention
- L4 serial rollout and closure:
  - `AT-SLIM-09` batch default switch and rollback knob
  - `AT-SLIM-10` regression and documentation closure

## Global Acceptance Contract

- Search and Harvest remain two upstream business chains.
- The convergence target is shared called services, not semantic flattening of the two chains.
- `site_search` and `url_execution` remain Search-side runtime views, not new top-level standardized service families.
- `collect_urls_from_list(...)`, `ingest_url_via_source_library_frontdoor(...)`, `terminal_output`, `legacy_result`, and `job_logger` stay visible until a dedicated removal plan exists.
- `ingress_envelope` remains the pre-frontdoor unified contract.
- `document_candidate -> accept` and `records-only -> defer` remain individually traceable in docs, code, and tests.
- Every task touching code must update the node mapping baseline or explicitly mark touched nodes as `unchanged`.
- No task may replace a node-level call chain with a summary box or a generic “merged service layer” description.

## Task AT-SLIM-01: Freeze Migration Scope and Shared Acceptance Contract

- Goal: Freeze the exact migration scope so later implementation does not drift from the clarified target.
- Status: completed
- Depends_on: `[]`
- Blocks: `["AT-SLIM-02","AT-SLIM-03","AT-SLIM-04"]`
- Input:
  - [01_source-library-ingest-minimal-migration-plan-2026-03-25.md](./01_source-library-ingest-minimal-migration-plan-2026-03-25.md)
  - [references/2026-03-25-ingest-structure-clarification-log.md](./references/2026-03-25-ingest-structure-clarification-log.md)
  - [references/2026-03-26-source-library-ingest-expected-flow-v2.md](./references/2026-03-26-source-library-ingest-expected-flow-v2.md)
- Output:
  - frozen scope note
  - frozen acceptance contract for Search/Harvest + shared called services
  - frozen batch-helper input boundary contract
  - frozen batch-switch precedence matrix
- Acceptance:
  - no conflict remains between plan wording, corrected diagrams, and current implementation reality.
- Minimum validation:
  - `rg -n "Search|Harvest|shared called services|ingress_envelope|records-only|document_candidate" development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration -S`

## Task AT-SLIM-02: Freeze Contract Regression Baseline

- Goal: Freeze the current regression surface before any structural code move.
- Status: completed
- Depends_on: `["AT-SLIM-01"]`
- Blocks: `["AT-SLIM-05","AT-SLIM-06","AT-SLIM-07","AT-SLIM-08","AT-SLIM-09"]`
- Input:
  - `main/backend/app/services/source_library/resolver.py`
  - `main/backend/app/services/ingest/url_pool.py`
  - `main/backend/app/services/ingest/frontdoor_ingress.py`
  - `main/backend/app/services/ingest/postprocess_frontdoor.py`
- Output:
  - frozen regression pack for:
    - `run_item_with_url_routing(...)`
    - `collect_urls_from_list(...)`
    - `ingest_url_via_source_library_frontdoor(...)`
    - `run_postprocess_frontdoor(...)`
    - `SourceLibraryTerminalOutput v1`
  - [references/2026-03-26-at-slim-02-regression-baseline.md](./references/2026-03-26-at-slim-02-regression-baseline.md)
- Acceptance:
  - touched contracts are backed by concrete tests or an explicit missing-test gap note.
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_resolver_unittest.py main/backend/tests/unit/test_source_library_item_resolver_unittest.py`
  - `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_terminal_output_unittest.py main/backend/tests/unit/test_postprocess_frontdoor_unittest.py`

## Task AT-SLIM-03: Freeze Touched-Node Mapping and Caller Matrix

- Goal: Make the execution-side no-silent-loss rule operational for this migration scope.
- Status: completed
- Depends_on: `["AT-SLIM-01"]`
- Blocks: `["AT-SLIM-05","AT-SLIM-06","AT-SLIM-07","AT-SLIM-08","AT-SLIM-09"]`
- Input:
  - [references/02_source-library-ingest-node-mapping-and-preservation-checklist-2026-03-26.md](./references/02_source-library-ingest-node-mapping-and-preservation-checklist-2026-03-26.md)
  - current call graph nodes in `resolver.py`, `url_pool.py`, `frontdoor_ingress.py`, `postprocess_frontdoor.py`
- Output:
  - touched-node execution sheet for `AT-SLIM-05 ~ AT-SLIM-09`
  - caller matrix with `old caller / new caller / replacement note / rollback path`
  - [references/2026-03-26-at-slim-03-node-mapping-caller-matrix.md](./references/2026-03-26-at-slim-03-node-mapping-caller-matrix.md)
- Acceptance:
  - every touched node has a precise owner and replacement mapping before code changes begin.
- Minimum validation:
  - `rg -n "run_item_with_url_routing|collect_urls_from_list|ingest_url_via_source_library_frontdoor|build_source_library_ingress_envelope|build_frontdoor_ingress_envelope|run_postprocess_frontdoor" main/backend/app -S`

## Task AT-SLIM-04: Freeze Compat and Observability Invariants

- Goal: Prevent structural cleanup from accidentally removing current compat outputs or observability hooks.
- Status: completed
- Depends_on: `["AT-SLIM-01"]`
- Blocks: `["AT-SLIM-08","AT-SLIM-09","AT-SLIM-10"]`
- Input:
  - `main/backend/app/services/source_library/terminal_output.py`
  - `main/backend/app/services/collect_runtime/adapters/source_library.py`
  - `main/backend/app/services/ingest/postprocess_frontdoor.py`
- Output:
  - invariant list for:
    - `terminal_output`
    - `legacy_result`
    - `job_logger`
    - `etl_job_runs`
    - batch aggregate fields
  - [references/2026-03-26-compat-observability-invariants-source-library-ingest-minimal-migration.md](./references/2026-03-26-compat-observability-invariants-source-library-ingest-minimal-migration.md)
- Acceptance:
  - no implementation task can claim completion while these outputs or signals become implicit or untraceable.
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py main/backend/tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py`

## Task AT-SLIM-05: Extract Shared Batch Routing Primitive

- Goal: Raise `run_item_with_url_routing(...)` to an explicit shared materialization helper without changing the default call graph.
- Status: completed
- Depends_on: `["AT-SLIM-02","AT-SLIM-03"]`
- Blocks: `["AT-SLIM-06","AT-SLIM-07","AT-SLIM-09"]`
- Input:
  - `main/backend/app/services/source_library/resolver.py`
  - `main/backend/app/services/source_library/adapters/url_pool.py`
  - `main/backend/app/services/ingest/url_pool.py`
- Output:
  - explicit batch-routing helper boundary
  - preserved outputs:
    - `by_url`
    - `records`
    - `stats`
    - `diagnostics`
- Acceptance:
  - helper extraction does not change public return fields or batch semantics.
  - helper input boundary follows the frozen `runtime_targets` contract instead of raw caller `urls`.
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_resolver_unittest.py main/backend/tests/unit/test_source_library_url_pool_adapter_unittest.py`

## Task AT-SLIM-06: Introduce Explicit Batch Frontdoor Handoff Helper

- Goal: Make batch frontdoor handoff explicit instead of burying it in single-url wrapper behavior.
- Status: completed
- Depends_on: `["AT-SLIM-05"]`
- Blocks: `["AT-SLIM-07","AT-SLIM-08","AT-SLIM-09"]`
- Input:
  - `main/backend/app/services/ingest/url_pool.py`
  - `main/backend/app/services/ingest/frontdoor_ingress.py`
  - `main/backend/app/services/ingest/postprocess_frontdoor.py`
- Output:
  - bulk handoff helper for `record -> document_candidate`
  - explicit ingress path for:
    - `document_candidate -> accept`
    - `records-only -> defer`
- Acceptance:
  - frontdoor admission semantics remain unchanged while caller relationships become explicit.
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_postprocess_frontdoor_unittest.py main/backend/tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py`

## Task AT-SLIM-07: Add Internal Switch to collect_urls_from_list(...)

- Goal: Introduce a controlled switch so batch path can be exercised without deleting the old compat path.
- Status: completed
- Depends_on: `["AT-SLIM-05","AT-SLIM-06"]`
- Blocks: `["AT-SLIM-09","AT-SLIM-10"]`
- Input:
  - `main/backend/app/services/ingest/url_pool.py`
  - `main/backend/app/services/collect_runtime/adapters/url_pool.py`
- Output:
  - internal switch or feature flag in `collect_urls_from_list(...)`
  - two selectable paths:
    - old per-URL compat path
    - new batch-routing path
- Acceptance:
  - disabling the switch preserves current behavior exactly enough for rollback.
  - switch precedence follows the frozen matrix, including async force-legacy behavior.
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_url_pool_adapter_unittest.py main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py`

## Task AT-SLIM-08: Converge on Shared Ingress Builders While Preserving Compat Callers

- Goal: Route the new batch path through shared ingress builders without regressing retained compat callers.
- Status: completed
- Depends_on: `["AT-SLIM-04","AT-SLIM-06","AT-SLIM-07"]`
- Blocks: `["AT-SLIM-09","AT-SLIM-10"]`
- Input:
  - `main/backend/app/services/ingest/frontdoor_ingress.py`
  - `main/backend/app/services/ingest/url_pool.py`
  - `main/backend/app/services/collect_runtime/adapters/source_library.py`
- Output:
  - shared convergence on:
    - `build_source_library_ingress_envelope(...)`
    - `build_frontdoor_ingress_envelope(...)`
  - retained caller visibility for:
    - `ingest_url_via_source_library_frontdoor(...)`
    - direct frontdoor callers
    - provider compat paths
- Acceptance:
  - the migration merges shared called services only; Search and Harvest caller semantics remain traceable.
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py`

## Task AT-SLIM-09: Switch Batch Default With Rollback Knob

- Goal: Make batch routing the default for `collect_urls_from_list(...)` while keeping a fast rollback path.
- Status: completed
- Depends_on: `["AT-SLIM-07","AT-SLIM-08"]`
- Blocks: `["AT-SLIM-10"]`
- Input:
  - completed outputs from `AT-SLIM-05 ~ AT-SLIM-08`
- Output:
  - default-on batch path
  - explicit rollback knob
  - updated caller matrix and touched-node sheet
- Acceptance:
  - default path no longer depends on single-url wrapper as the mainline
  - rollback path still exists and is documented node by node
  - rollback is implemented through the batch-path knob/default, not by reusing frontdoor rollout knobs.
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_url_pool_adapter_unittest.py main/backend/tests/unit/test_source_library_terminal_output_unittest.py main/backend/tests/unit/test_postprocess_frontdoor_unittest.py`

## Task AT-SLIM-10: Run Closure Regression Pack and Documentation Closure

- Goal: Close this migration round with code-level regression evidence and documentation consistency.
- Status: completed
- Depends_on: `["AT-SLIM-08","AT-SLIM-09"]`
- Blocks: `[]`
- Input:
  - all outputs from `AT-SLIM-01 ~ AT-SLIM-09`
  - root plan doc
  - references bundle
- Output:
  - closure report:
    - preserved call-chain matrix
    - compat retention status
    - unresolved risks and follow-up list
  - [05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md](./05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md)
- Acceptance:
  - Search-side provider compat path remains traceable
  - Search-side discovery and url-execution paths remain traceable
  - Harvest-side direct and compat paths remain traceable
  - frontdoor / writer / observability hooks remain traceable
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_item_resolver_unittest.py main/backend/tests/unit/test_source_library_resolver_unittest.py`
  - `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_terminal_output_unittest.py main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py`
  - `python3.11 -m pytest -q main/backend/tests/unit/test_postprocess_frontdoor_unittest.py main/backend/tests/core_business/test_source_library_core_contract.py`
