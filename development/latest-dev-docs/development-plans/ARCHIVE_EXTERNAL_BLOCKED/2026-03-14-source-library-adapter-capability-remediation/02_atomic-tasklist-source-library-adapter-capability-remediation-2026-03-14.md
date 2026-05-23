# Atomic Task List: Source Library Adapter Capability Remediation (2026-03-14)

## Execution Status Snapshot

- `AT-AC-01`: completed, diagnosis frozen as “adapter capability insufficiency first”.
- `AT-AC-02`: completed, `collect_runtime` auto-batch concurrency already landed.
- `AT-AC-03`: completed, `source_library` concurrency budget and URL timeout isolation already landed.
- `AT-AC-04`: completed, `unified_search` capability gate relaxed to stop excluding valid `filter` entries.
- `AT-AC-05`: phase-1 implementation boundary refined to “extract shared search_template service first”.
- `AT-AC-05/07/08`: 2026-05-22 lane-7 minimum assertion slice landed; see `09_lane7-capability-fallback-assertions-2026-05-22.md`.
- `AT-AC-06/10`: partially advanced on 2026-05-22 by deterministic local fixture, Wave3 public live probe evidence, and Wave4 full historical 45-site replay manifest/gate. Full closure still requires an opt-in public 45-site run in a controlled environment.

## Serial-Parallel Rules

- L0 serial baseline:
  - `AT-AC-01`
- L1 parallel capability fixes:
  - `AT-AC-04` unified_search capability gate repair
  - `AT-AC-05` generic_web.search_template extraction and pagination repair
  - `AT-AC-06` anti-bot / transport resilience improvement
- L2 serial orchestration alignment:
  - `AT-AC-07` handler.cluster routing and fallback normalization
  - `AT-AC-08` error taxonomy and observability normalization
- L3 parallel regression and probe:
  - `AT-AC-09` contract regression pack
  - `AT-AC-10` real site-entry probe rerun and dirty-source shortlist

## Global Acceptance Contract

- The primary remediation target is adapter capability, not migration rollback.
- `site_search` authoritative path remains:
  - `handler.cluster + unified_search`
- Content-site runtime shape remains:
  - `query -> search -> candidate generation -> detail fetch`
- `generic_web.*` remains internal-plugin only for direct execution purposes.
- `frontdoor` / `terminal_output` / `legacy_result` compatibility must remain intact.
- Capability repair may reduce false-empty / false-error outcomes, but must not widen unsupported entry types such as `domain_root`.

## Task AT-AC-01: Freeze Diagnosis and Remediation Boundary

- Goal: Freeze the problem statement as adapter-capability-first.
- Status: completed
- Depends_on: `[]`
- Blocks: `["AT-AC-04","AT-AC-05","AT-AC-06"]`
- Input:
  - `01_source-library-adapter-capability-remediation-2026-03-14.md`
  - real probe outputs from `demo_proj`
- Output:
  - frozen diagnosis note
  - scope boundary for this repair round
- Acceptance:
  - team agrees this round does not start with source pruning as the mainline fix.
- Minimum validation:
  - document review only

## Task AT-AC-02: collect_runtime Auto-Batch Concurrency

- Goal: Replace serial auto-batch with controlled parallel execution.
- Status: completed
- Depends_on: `["AT-AC-01"]`
- Blocks: `["AT-AC-09"]`
- Input:
  - `main/backend/app/services/collect_runtime/runtime.py`
- Output:
  - controlled parallel auto-batch
  - diagnostics: `batch_parallelism`, `batch_fail_fast`, `batches_failed/succeeded`
- Acceptance:
  - result merge contract unchanged
  - throughput better than serial on synthetic benchmark
- Minimum validation:
  - `python3.11 -m pytest -q tests/unit/test_collect_runtime_auto_batch_unittest.py`

## Task AT-AC-03: source_library Concurrency Budget and URL Timeout Isolation

- Goal: Add shared concurrency plan and isolate per-URL timeout failures.
- Status: completed
- Depends_on: `["AT-AC-01"]`
- Blocks: `["AT-AC-09","AT-AC-10"]`
- Input:
  - `main/backend/app/services/source_library/types.py`
  - `main/backend/app/services/source_library/resolver.py`
- Output:
  - `SourceConcurrencyPlan`
  - staged search/url concurrency control
  - URL timeout isolation rows
- Acceptance:
  - search stage and URL stage do not multiply concurrency budgets
  - timeout of one URL does not fail the whole batch by default
- Minimum validation:
  - `python3.11 -m pytest -q tests/unit/test_source_library_resolver_unittest.py tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py`

## Task AT-AC-04: Relax unified_search Capability Gate

- Goal: Stop excluding valid `rss/sitemap` entries before execution when keyword capability is `filter`.
- Status: completed
- Depends_on: `["AT-AC-01"]`
- Blocks: `["AT-AC-07","AT-AC-09","AT-AC-10"]`
- Input:
  - `main/backend/app/services/resource_pool/unified_search.py`
  - `main/backend/app/services/resource_pool/auto_classify.py`
- Output:
  - capability inference fallback from `entry_type + channel_key`
  - allowed keyword modes widened from only `search` to `search|filter`
- Acceptance:
  - `rss/sitemap` entries no longer fail the gate only because they are filter-mode
  - unsupported types like `domain_root` remain excluded
- Minimum validation:
  - `python3.11 -m pytest -q tests/unit/test_resource_pool_unified_search_unittest.py tests/unit/test_resource_pool_search_capabilities_unittest.py`

## Task AT-AC-05: Strengthen generic_web.search_template

- Goal: Improve `generic_web.search_template` so real search result pages stop collapsing into `url_term_filter_empty_no_fallback`.
- Status: pending
- Depends_on: `["AT-AC-01"]`
- Blocks: `["AT-AC-07","AT-AC-09","AT-AC-10"]`
- Input:
  - `03_source-library-capability-service-map-and-modular-rollout-2026-03-14.md`
  - `main/backend/app/services/source_library/adapters/generic_web.py`
  - `main/backend/app/services/resource_pool/unified_search.py`
- Output:
  - `search_template` shared backend service extracted from duplicated adapter logic
  - multi-page fetch support via `page/max_pages`
  - anchor-text/title-aware candidate filtering
  - controlled fallback to top links when URL-only match is empty
  - `generic_web` and `unified_search` both consume the same service implementation
- Acceptance:
  - `generic_web.search_template` and `unified_search` no longer each own a separate search-template execution stack
  - same keyword set on known search-template sites yields fewer false-empty errors
  - no direct-execution contract break for `generic_web.*`
- Minimum validation:
  - `python3.11 -m pytest -q tests/unit/test_resource_pool_search_template_service_unittest.py`
  - `python3.11 -m pytest -q tests/unit/test_source_library_generic_web_adapter_unittest.py tests/unit/test_resource_pool_unified_search_unittest.py`

## Task AT-AC-06: Improve Transport Resilience for Real External Sites

- Goal: Reduce fetch failures caused by brittle retry/anti-bot behavior.
- Status: pending
- Depends_on: `["AT-AC-01"]`
- Blocks: `["AT-AC-09","AT-AC-10"]`
- Input:
  - `main/backend/app/services/ingest/adapters/http_utils.py`
  - `main/backend/app/services/source_library/adapters/generic_web.py`
  - fetch failures from real probes
- Output:
  - safer retry/backoff for selected 403/429-like scenarios
  - clearer separation between transport failure and extraction failure
- Acceptance:
  - no silent drop from transport-layer exceptions
  - failure reason is preserved in error payload
- Minimum validation:
  - targeted unit tests around fetch retry/error mapping

## Task AT-AC-07: Normalize handler.cluster Fallback and Routing Behavior

- Goal: Ensure `handler.cluster` fallback behavior is consistent with repaired adapter capabilities.
- Status: pending
- Depends_on: `["AT-AC-04","AT-AC-05"]`
- Blocks: `["AT-AC-09","AT-AC-10"]`
- Input:
  - `main/backend/app/services/source_library/resolver.py`
  - `main/backend/app/services/source_library/url_router.py`
- Output:
  - stable fallback semantics between `search_template`, `rss`, `sitemap`, and crawler-first/crawler-fallback logic
  - no premature “empty” conclusion before capable fallback path is tried
- Acceptance:
  - routing remains explainable in `middle_layer_protocol`
  - no regression in `terminal_output_only`
- Minimum validation:
  - `python3.11 -m pytest -q tests/unit/test_source_library_resolver_unittest.py tests/unit/test_frontdoor_orchestrator_unittest.py`

## Task AT-AC-08: Normalize Error Taxonomy and Diagnostics

- Goal: Make errors distinguishable enough to tell dirty source from adapter mismatch.
- Status: pending
- Depends_on: `["AT-AC-05","AT-AC-06","AT-AC-07"]`
- Blocks: `["AT-AC-10"]`
- Input:
  - `generic_web` / `unified_search` current error payloads
  - `terminal_output` compatibility rules
- Output:
  - normalized reason categories such as:
    - transport failure
    - parse mismatch
    - term filter empty with fallback used
    - term filter empty without fallback
    - entry_type mismatch
- Acceptance:
  - same failure class is emitted consistently across search_template/rss/sitemap
- Minimum validation:
  - `python3.11 -m pytest -q tests/unit/test_source_library_terminal_output_unittest.py tests/unit/test_collect_runtime_source_library_adapter_unittest.py`

## Task AT-AC-09: Run Compatibility Regression Pack

- Goal: Prove capability fixes did not break existing source-library/frontdoor contracts.
- Status: pending
- Depends_on: `["AT-AC-04","AT-AC-05","AT-AC-06","AT-AC-07"]`
- Blocks: `["AT-AC-10"]`
- Input:
  - all code changes from this round
- Output:
  - green regression pack
- Acceptance:
  - no contract break on:
    - `terminal_output`
    - `frontdoor`
    - `legacy_result`
    - direct generic_web rejection
- Minimum validation:
  - `python3.11 -m pytest -q tests/unit/test_resource_pool_unified_search_unittest.py`
  - `python3.11 -m pytest -q tests/unit/test_resource_pool_search_capabilities_unittest.py`
  - `python3.11 -m pytest -q tests/unit/test_source_library_resolver_unittest.py`
  - `python3.11 -m pytest -q tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py`
  - `python3.11 -m pytest -q tests/unit/test_source_library_terminal_output_unittest.py`
  - `python3.11 -m pytest -q tests/unit/test_collect_runtime_source_library_adapter_unittest.py`
  - `python3.11 -m pytest -q tests/unit/test_frontdoor_orchestrator_unittest.py`

## Task AT-AC-10: Re-run Real Site-Entry Probe and Produce Dirty-Source Shortlist

- Goal: After capability repair, re-run the real `demo_proj` probe and isolate truly dirty sites.
- Status: pending
- Depends_on: `["AT-AC-05","AT-AC-06","AT-AC-08","AT-AC-09"]`
- Blocks: `[]`
- Input:
  - `handler.cluster.search_template`
  - the real keyword sample:
    - `openai api pricing`
    - `anthropic claude code`
    - `gpt 4.1 release`
    - `langchain sqlitecache`
- Output:
  - updated per-site success/error/timeout list
  - shortlist of sites to disable or downgrade
- 2026-05-22 Wave4 status:
  - Full historical 45-site manifest and skip-safe gate added.
  - Default run is no-network and produced `status_counts={"skipped_public_network_disabled": 45}`.
  - Public dirty-source closure remains pending until `--allow-public-network` is run in a controlled environment.
- Acceptance:
  - “dirty source” list is produced only after adapter capability repair is verified
  - report distinguishes:
    - fetch failures
    - parse/filter failures
    - anti-bot failures
- Minimum validation:
  - real local probe script / notebook / shell command output attached to doc or task log
