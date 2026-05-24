# Lane 7 Landing: Source-Library Capability Assertions (2026-05-22)

## Scope

This lane only lands minimum source-library capability and fallback assertions. It does not reopen the closed three-lane migration shape or move fields between item definition, execution derivation, and runtime diagnostics.

## AC Evidence Added

| Area | Current status | Evidence |
| --- | --- | --- |
| `site_search` remains an execution lane, not an item-definition field | Preserved | New diagnostics are emitted from `resource_pool/search_template_service.py`; no item schema or `item_plan.py` field change. |
| URL routing keeps mechanical routes before default `url_pool` fallback | Minimum assertion landed | `test_url_router_prefers_keyword_aware_search_template_before_url_pool_default` asserts search endpoints route to `generic_web.search_template`, sitemap routes to `generic_web.sitemap`, and plain article URLs fall back to `url_pool`. |
| Capability/fallback state is observable without changing three-lane taxonomy | Minimum assertion landed | `candidate_filter_state`, `fallback_allowed`, and `used_term_fallback` are added to execution diagnostics only. |

## Remaining Blockers

- Full real-site probe closure remains outside this minimum lane because it requires stable external-site/network fixtures and dirty-source sampling evidence.
- Broader crawler/browser fallback execution is intentionally not implemented here; it belongs to a later capability lane after deterministic fixtures exist.

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
