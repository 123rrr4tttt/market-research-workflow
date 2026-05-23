# Source Library Adapter Capability Remediation

Date: 2026-03-14

## 1. Context

This note records the current diagnosis for the high error rate observed on `demo_proj` source-library runs, especially `handler.cluster.search_template`, and the chosen remediation direction.

The current decision is:

1. Treat the dominant issue as adapter capability insufficiency first.
2. Do not start with source cleaning as the primary fix.
3. Use dirty-source pruning only as a secondary follow-up after capability repair.

## 2. Evidence Summary

### 2.1 Real item state

The three-lane migration itself is already materially in place for system-generated handler-cluster items.

- `handler.cluster.search_template`
- `handler.cluster.rss`
- `handler.cluster.sitemap`

Observed runtime/storage properties:

- `channel_key=handler.cluster`
- `item_type=service_aggregated`
- `managed_by=system`
- `stable_handler_cluster=true`
- `creation_handler=handler.entry_type`

This matches the intended post-migration target from the three-lane architecture docs.

### 2.2 Real sample run behavior

Real local runs against `demo_proj` using actual keywords and actual site entries showed:

- end-to-end parallel execution improved runtime by about `~2x`
- result counts stayed roughly stable
- error counts remained very high

This means concurrency changes improved throughput, but did not solve the dominant correctness/coverage issue.

### 2.3 Per-site probing result

A targeted probe over `handler.cluster.search_template` site entries showed:

- tested sites: `20`
- ok sites: `1`
- error sites: `19`

Representative failing sites:

- `https://arxiv.org/search?q={{q}}`
- `https://iyiou.com/search?q={{q}}`
- `https://actiontoaction.ai/search?q={{q}}`
- `http://news.cn/search?q={{q}}`
- `https://stcn.com/search?q={{q}}`
- `https://moorinsightsstrategy.com/find?q={{q}}`
- `https://dcrainmaker.com/search?q={{q}}`
- `https://thequalityedit.com/search?q={{q}}`
- `https://youtube.com/search?q={{q}}`

Most failures were not hard transport failures. The dominant signal was:

- `url_term_filter_empty_no_fallback`

This strongly suggests that many pages were fetched, but candidate extraction / term matching / fallback behavior was too strict for real search result pages.

## 3. Main Diagnosis

The high error rate is better explained by adapter capability insufficiency than by migration omission.

### 3.1 Not a migration-missed primary issue

The migration concern was checked against:

- `2026-03-11-source-library-three-lane-architecture`
- live `demo_proj` item state

Conclusion:

1. system-generated `handler.cluster.*` items are already migrated
2. user-defined items such as `report1.root_site_search` still remain `user_defined`, but runtime dispatch already forces them into the `site_search -> handler.cluster + unified_search` path
3. therefore the dominant runtime issue is not “migration forgotten”

### 3.2 Capability issues currently dominating

#### A. `generic_web.search_template` is still too weak

The adapter path is underpowered compared with real-world search pages.

Observed/confirmed gaps:

1. search page extraction behavior is too brittle
2. fallback behavior is too strict when URL text does not directly contain the query terms
3. search-template handling historically lagged behind unified-search behavior
4. pagination support is incomplete / inconsistent across call paths

#### B. `unified_search` previously filtered too aggressively

The `unified_search` capability gate could incorrectly exclude entries before execution.

Important cases:

1. `rss/sitemap` entries were treated as filter-only and could be excluded too early
2. incomplete or stale `capabilities` metadata could cause valid entries to be misclassified

#### C. anti-bot / fetch resilience is still weak

Transport behavior is still fragile for real external sites.

Examples:

1. `403/429` handling is not robust enough
2. some sites likely require more tolerant retry/backoff behavior
3. some failures are hard fetch failures, not only extraction failures

#### D. observability is still too coarse

A large portion of failures collapse into generic “empty after filter” style signals.

This makes it hard to distinguish:

1. source is actually dirty
2. parser mismatch
3. anti-bot failure
4. wrong entry type / wrong routing

## 4. Current Fix Direction

The working direction is to fix adapter capability first.

### Phase 1: adapter capability repair

Prioritize:

1. strengthen `generic_web.search_template`
2. relax overly strict candidate filtering / fallback behavior
3. align simplified adapter behavior with the richer `unified_search` search-template path
4. ensure `rss/sitemap/search_template` capability inference degrades safely when metadata is incomplete

### Phase 2: routing and unified-search normalization

Prioritize:

1. prevent valid `rss/sitemap` entries from being filtered out before execution
2. normalize capability inference from `entry_type + channel_key`
3. keep `domain_root` and unrelated entry types excluded

### Phase 3: dirty-source cleanup

Only after capability repair:

1. re-run site-level probes
2. compute per-site success/error/timeout distribution
3. disable or downgrade truly bad sites

## 5. Compatibility Constraints

The repair should preserve the following boundaries:

1. `generic_web.*` must remain blocked from arbitrary external direct execution
2. `handler.cluster + unified_search` remains the only authoritative `site_search` execution path
3. `frontdoor` / `terminal_output` / `legacy_result` compatibility must stay intact
4. `service_aggregated/system` and `user_defined/user` taxonomy must not be broken

## 6. Minimal Validation Set

Use the following as the minimal regression set after adapter-capability changes:

1. `main/backend/tests/unit/test_resource_pool_unified_search_unittest.py`
2. `main/backend/tests/unit/test_resource_pool_search_capabilities_unittest.py`
3. `main/backend/tests/unit/test_source_library_resolver_unittest.py`
4. `main/backend/tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py`
5. `main/backend/tests/unit/test_source_library_terminal_output_unittest.py`
6. `main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py`
7. `main/backend/tests/unit/test_frontdoor_orchestrator_unittest.py`

## 7. Decision Record

Decision taken on 2026-03-14:

1. Proceed under the assumption that the primary issue is adapter capability insufficiency.
2. Do not frame the current work as a migration rollback/fix.
3. Keep source cleaning as a later data-governance pass after capability improvements are verified.
