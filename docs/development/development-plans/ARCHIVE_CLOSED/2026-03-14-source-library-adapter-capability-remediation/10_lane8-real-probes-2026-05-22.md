# Lane 8 Landing: Source Library Real-Probe Fixture Evidence (2026-05-22)

## Scope

This lane adds deterministic evidence for the remaining source-library probe blockers without depending on unstable public websites.

The fixture is a real local HTTP server, not a mocked `fetch_html` call. It covers:

- site-entry discovery for `sitemap`, `rss`, and `search_template` paths;
- direct `generic_web.sitemap`, `generic_web.rss`, and `generic_web.search_template` adapter execution;
- anti-bot-style `429` on the first search request followed by resilient retry success;
- request/header capture so transport behavior is auditable.

## Landed Evidence

- Probe script: `main/backend/scripts/source_library_real_probes.py`
- Regression test: `main/backend/tests/unit/test_source_library_real_probe_fixture_unittest.py`
- Run record: `development/latest-dev-docs/automation-runs/source-library-real-probes/2026-05-22/`

## Closure Status

| AC item | Lane 8 status | Evidence |
| --- | --- | --- |
| `AT-AC-06` anti-bot/transport resilience | Deterministic local evidence added | Local fixture returns `429` once on `/blocked-search`; `generic_web.search_template` switches to resilient mode and returns one candidate with zero final transport errors. |
| `AT-AC-10` real site-entry probe | Local fixture evidence added, live public replay still open | Local fixture proves the site-entry and adapter stack can route sitemap/RSS/search-template entries. The dirty-source shortlist still requires a live `demo_proj` public-site replay. |

## Validation

```bash
cd main/backend
/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python -m pytest -q \
  tests/unit/test_source_library_real_probe_fixture_unittest.py \
  tests/unit/test_resource_pool_search_template_service_unittest.py \
  tests/unit/test_source_library_generic_web_adapter_unittest.py
```

Result: `33 passed, 2 warnings`.

Broader source-library/resource-pool regression:

```bash
cd main/backend
/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python -m pytest -q \
  tests/unit/test_source_library_*_unittest.py \
  tests/unit/test_collect_runtime_source_library_adapter_unittest.py \
  tests/unit/test_resource_pool_search_template_service_unittest.py \
  tests/unit/test_resource_pool_unified_search_unittest.py \
  tests/unit/test_resource_pool_search_capabilities_unittest.py
```

Result: `161 passed, 3 warnings`.
