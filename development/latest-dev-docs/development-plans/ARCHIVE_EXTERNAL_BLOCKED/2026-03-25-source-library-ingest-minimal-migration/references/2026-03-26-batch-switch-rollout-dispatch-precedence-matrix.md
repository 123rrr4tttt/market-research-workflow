# Batch Switch / Rollout / Dispatch Precedence Matrix

Updated: 2026-03-26 PST

## Purpose

This file freezes the control-plane precedence for the current
source-library / ingest minimal migration.

Without this matrix, `AT-SLIM-07` and `AT-SLIM-09` would introduce a new
batch-path switch into a function that already has active dispatch and
frontdoor rollout knobs.

This file is the prerequisite contract for:

- `AT-SLIM-07`
- `AT-SLIM-08`
- `AT-SLIM-09`

## Current Existing Knobs

### Dispatch Knobs

- `url_async`
- `url_dispatch_mode`

Current effect:

- `url_async=true` or `url_dispatch_mode=celery_async` routes execution
  into the single-URL async task path

### Frontdoor Request Knobs

- `url_routing_frontdoor_enabled`
- `frontdoor_enabled`
- `use_frontdoor`

Current effect:

- they participate in frontdoor option resolution and frontdoor-related
  search option injection

### Frontdoor Rollout Knobs

- `settings.ingest_frontdoor_rollout_mode`
- `settings.ingest_frontdoor_canary_projects`

Current effect:

- project-level gating through `is_ingest_frontdoor_enabled(...)`

## New Frozen Migration Knob

The migration should introduce exactly one batch-path selection knob:

- `url_batch_path_mode`

Frozen values:

- `inherit`
- `legacy_per_url`
- `batch_runtime_targets`

This knob chooses the internal call graph. It must not be overloaded to
mean dispatch mode or frontdoor rollout mode.

## Frozen Default Knob For `AT-SLIM-09`

The repo-level default should be represented by one dedicated setting:

- `settings.url_batch_path_default_mode`

Frozen values:

- `legacy_per_url`
- `batch_runtime_targets`

Recommended rollout use:

- `AT-SLIM-07`: default stays `legacy_per_url`
- `AT-SLIM-09`: default switches to `batch_runtime_targets`

## Core Clarification

For this migration topic:

1. dispatch mode decides sync vs async execution shell
2. batch-path mode decides old per-URL compat path vs new batch helper
3. frontdoor rollout decides frontdoor-related rollout context, not the
   batch-path rollback mechanism

In other words:

- do not use `ingest_frontdoor_rollout_mode` as the rollback knob for the
  batch-path migration
- do not use `url_dispatch_mode` as the batch-path selector

## Precedence Order

The effective path decision must follow this order:

### P0. Early Empty-Input Return

- if `collect_urls_from_list(...)` returns before execution because input
  is empty, no other knob applies

### P1. Async Dispatch Forces Legacy Per-URL Path

If either condition is true:

- `url_async=true`
- `url_dispatch_mode=celery_async`

Then effective batch path is forced to:

- `legacy_per_url`

Reason:

- current async branch queues `task_ingest_url_via_source_library`
- that task is single-URL shaped today
- no dedicated batch async task exists in current implementation

Until a separate async-batch plan exists, async dispatch is not allowed to
implicitly select the new batch helper.

### P2. Explicit Caller Batch Override

If dispatch is not forced async, then honor explicit caller override:

- `url_batch_path_mode=legacy_per_url`
- `url_batch_path_mode=batch_runtime_targets`

`inherit` means continue to the next precedence layer.

### P3. Repo-Level Default

If the caller does not explicitly override the batch path, resolve against:

- `settings.url_batch_path_default_mode`

Recommended mapping:

   - `legacy_per_url` only for explicit rollback or canary freeze
   - `batch_runtime_targets` as the repo-level default after `AT-SLIM-09`

### P4. Frontdoor Request Knobs

Once the batch path is chosen, frontdoor request knobs are resolved in the
current existing order:

1. `url_routing_frontdoor_enabled`
2. fallback to `frontdoor_enabled`
3. fallback to `use_frontdoor`
4. then pass through project-level rollout gate

This layer must not override the batch-path choice.

### P5. Project Rollout Gate

`is_ingest_frontdoor_enabled(...)` remains the project-level rollout gate
for frontdoor-related option enablement. It must not silently remap:

- `legacy_per_url -> batch_runtime_targets`
- `batch_runtime_targets -> legacy_per_url`

## Effective Decision Table

| Dispatch | `url_batch_path_mode` | Default | Effective Path |
|---|---|---|---|
| `celery_async` | any | any | `legacy_per_url` |
| `sync/thread` | `legacy_per_url` | any | `legacy_per_url` |
| `sync/thread` | `batch_runtime_targets` | any | `batch_runtime_targets` |
| `sync/thread` | `inherit` | `legacy_per_url` | `legacy_per_url` |
| `sync/thread` | `inherit` | `batch_runtime_targets` | `batch_runtime_targets` |

## Rollback Rule

Fast rollback for this migration must be implemented by one of these two
mechanisms only:

1. explicit caller override:
   - `url_batch_path_mode=legacy_per_url`
2. repo-level default rollback:
   - `settings.url_batch_path_default_mode=legacy_per_url`

Rollback must not require changing:

- `ingest_frontdoor_rollout_mode`
- `url_dispatch_mode`
- provider payload shape

## Provider And Adapter Expectations

Current callers such as:

- `ingest/news.py`
- `ingest/market_web.py`
- `resource_pool/unified_search.py`
- `collect_runtime/adapters/url_pool.py`

may keep their existing dispatch and frontdoor options.

The migration should add only one new optional override surface:

- `url_batch_path_mode`

No caller should have to change payload shape merely because the default
batch path changes.

## Task-Level Consequences

### For `AT-SLIM-07`

- add the new batch-path knob
- keep default on `legacy_per_url`
- ensure async dispatch still forces legacy path

### For `AT-SLIM-08`

- frontdoor convergence changes must be orthogonal to batch-path selection

### For `AT-SLIM-09`

- switch only the repo-level default
- preserve explicit override and async force-legacy behavior

## Recommended Verification

- `rg -n "url_async|url_dispatch_mode|url_routing_frontdoor_enabled|frontdoor_enabled|use_frontdoor|is_ingest_frontdoor_enabled" main/backend/app/services/ingest main/backend/app/services/collect_runtime -S`
- `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_url_pool_adapter_unittest.py main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py main/backend/tests/unit/test_ingest_frontdoor_rollout_unittest.py`
