# Lane 7 Landing: Capability/Fallback Assertions (2026-05-22)

## Scope

This is a minimum, non-rewrite landing for the open adapter-capability AC items. It prioritizes capability/fallback assertions and clear blockers over parser, crawler, or browser refactors.

## Landed

| AC item | Lane 7 status | Evidence |
| --- | --- | --- |
| `AT-AC-05` strengthen `generic_web.search_template` | Minimum assertion slice landed | `execute_search_template` now emits `candidate_filter_state`, `fallback_allowed`, and `used_term_fallback`; tests cover both `term_filter_empty_no_fallback` and `term_filter_empty_fallback_used`. |
| `AT-AC-07` normalize handler.cluster fallback/routing behavior | Minimum assertion slice landed | URL router fallback order is asserted in `test_source_library_resolver_unittest.py`; generic adapter still reports `site_search_internal_adapter` and fallback policy. |
| `AT-AC-08` normalize diagnostics enough to distinguish dirty source from adapter mismatch | Minimum assertion slice landed | Search-template, external-search, RSS, and sitemap execution diagnostics now expose the same fallback/filter state keys. |
| `AT-AC-09` compatibility regression pack | Partial local proof | Lane targeted pytest passed for source-library, collect-runtime source-library adapter, search-template service, unified-search, and search-capability tests. Final cross-lane merge gate still belongs to the integrator. |

## Explicit Blockers

- `AT-AC-06` anti-bot/transport resilience is not fully closed. The lane preserves existing resilient retry diagnostics but does not add a new anti-bot runtime.
- `AT-AC-10` real site-entry probe is blocked on deterministic external-site fixtures or a real-probe environment. Without that evidence, this lane must not mark dirty-source cleanup as complete.

## Validation Snapshot

```bash
cd main/backend
/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python -m pytest -q \
  tests/unit/test_resource_pool_search_template_service_unittest.py \
  tests/unit/test_source_library_generic_web_adapter_unittest.py \
  tests/unit/test_source_library_resolver_unittest.py
```

Result: `56 passed, 2 warnings`.

Broader lane gate:

```bash
cd main/backend
/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python -m pytest -q \
  tests/unit/test_source_library_*_unittest.py \
  tests/unit/test_collect_runtime_source_library_adapter_unittest.py \
  tests/unit/test_resource_pool_search_template_service_unittest.py \
  tests/unit/test_resource_pool_unified_search_unittest.py \
  tests/unit/test_resource_pool_search_capabilities_unittest.py
```

Result: `160 passed, 3 warnings`.
