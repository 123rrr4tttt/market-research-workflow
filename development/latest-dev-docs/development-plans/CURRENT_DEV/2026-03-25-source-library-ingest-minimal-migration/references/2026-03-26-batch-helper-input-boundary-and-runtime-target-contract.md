# Batch Helper Input Boundary And Runtime Target Contract

Updated: 2026-03-26 PST

## Purpose

This file freezes one execution-critical decision for the current
source-library / ingest minimal migration:

- what exactly the future batch helper is allowed to receive
- what must stay owned by `collect_urls_from_list(...)`
- what data must remain traceable during rollback and regression checks

This file is the prerequisite contract for:

- `AT-SLIM-05`
- `AT-SLIM-07`
- `AT-SLIM-09`

It should be read together with:

- [../01_source-library-ingest-minimal-migration-plan-2026-03-25.md](../01_source-library-ingest-minimal-migration-plan-2026-03-25.md)
- [../03_atomic-tasklist-source-library-ingest-minimal-migration-2026-03-26.md](../03_atomic-tasklist-source-library-ingest-minimal-migration-2026-03-26.md)
- [2026-03-25-ingest-structure-clarification-log.md](./2026-03-25-ingest-structure-clarification-log.md)
- [2026-03-25-source-library-to-db-service-flow-investigation.md](./2026-03-25-source-library-to-db-service-flow-investigation.md)

## Frozen Decision

The canonical input boundary for the new batch helper is:

- `runtime_targets`

The canonical batch helper input is not:

- raw caller `urls`
- normalized `urls`
- pre-resolution `targets`
- a bare list of resolved URL strings without target metadata

This means the helper extracted in `AT-SLIM-05` must consume the same
runtime-level unit that the current `collect_urls_from_list(...)` loop
actually executes after normalization, target expansion, query-contract
resolution, and de-duplication.

## Execution Stages And Ownership

### Stage 1. Raw Caller Input

- Name: `raw_urls`
- Current shape: direct caller payload to `collect_urls_from_list(...)`
- Owner: `collect_urls_from_list(...)`
- Must preserve:
  - caller-visible input count
  - original batch entry semantics
  - batch-level debug counts

### Stage 2. Normalized URL Set

- Name: `normalized_urls`
- Current shape: result after `_normalize_url_list(...)`
- Owner: `collect_urls_from_list(...)`
- Must preserve:
  - `raw_url_count`
  - `normalized_url_count`
  - `filtered_out`

### Stage 3. Expanded Target Set

- Name: `targets`
- Current shape: result of `_resolve_runtime_targets(...)`
- Owner: `collect_urls_from_list(...)`
- Must preserve:
  - target expansion semantics
  - `entry_type`
  - `domain`
  - `from_url`
  - `is_site_seed`
  - target-mode specific behavior like `site_only`, `detail_only`, `site_then_detail`

### Stage 4. Executed Runtime Target Set

- Name: `runtime_targets`
- Current shape: de-duplicated list of `(target_url, target)` after `_resolve_target_url(...)`
- Owner after migration:
  - produced by `collect_urls_from_list(...)`
  - consumed by the new batch helper
- This is the frozen helper boundary.

Each runtime target must still carry enough metadata to support:

- `source_template_health`
- `url_pool_context` annotation
- batch detail rows
- rollback comparison against legacy per-URL path

## Minimum Runtime Target Contract

The new batch helper should consume a list of runtime target objects that
preserve at least the following fields:

| Field | Why It Must Survive |
|---|---|
| `target_url` | actual execution URL |
| `entry_type` | target-mode semantics and debug |
| `domain` | context annotation and per-domain reasoning |
| `from_url` | source-traceability for search-template and seed expansion |
| `is_site_seed` | site-seed metrics and target accounting |

If extra metadata is needed later, it may be added. These fields are the
minimum frozen floor for this migration topic.

## What Stays Outside The Batch Helper

The extracted batch helper must not silently absorb the following
responsibilities:

- raw input normalization
- target expansion policy
- target de-duplication policy
- batch-level job creation
- batch-level aggregate counters
- `source_template_health` aggregation
- `url_pool_context` annotation
- batch-level debug payload assembly
- rollback-path selection

Those concerns remain owned by `collect_urls_from_list(...)` unless a
later dedicated plan explicitly changes their ownership.

## What The Batch Helper Is Allowed To Own

The extracted helper may own:

- routing/materialization over `runtime_targets`
- batch-slice execution
- preservation of per-target outputs
- explicit handoff payload preparation for frontdoor

The helper must preserve explicit visibility of:

- `by_url`
- `records`
- `stats`
- `diagnostics`
- `legacy_counts`
- `rejection_breakdown`
- `degradation_flags`

## No-Silent-Drift Rules

For this migration topic:

1. No implementation may pass raw caller `urls` directly into the new
   batch helper and call that "equivalent" to current behavior.
2. No implementation may strip `target` metadata and retain only the
   resolved URL string.
3. No implementation may move target expansion into the helper without
   first updating this file, the plan, and the caller matrix.
4. No implementation may compare old and new paths only on top-level
   `inserted / skipped`; comparisons must still include target-level and
   middle-output visibility.

## Task-Level Consequences

### For `AT-SLIM-05`

- the extracted helper boundary must be frozen around `runtime_targets`
- the helper output must still be comparable with current per-target loop

### For `AT-SLIM-07`

- the internal switch must sit above the helper boundary
- both old and new paths must consume the same `runtime_targets`

### For `AT-SLIM-09`

- default switching must not alter raw-input normalization or target
  expansion semantics
- rollback must mean "same `runtime_targets`, different downstream path"

## Recommended Verification

- `rg -n "_resolve_runtime_targets|_resolve_target_url|source_template_health|_annotate_url_pool_context|collect_urls_from_list" main/backend/app/services/ingest/url_pool.py -S`
- `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_url_pool_adapter_unittest.py main/backend/tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py`
