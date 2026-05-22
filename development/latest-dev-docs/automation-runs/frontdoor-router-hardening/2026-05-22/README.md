# Frontdoor Router Hardening Evidence

Date: 2026-05-22 PST
Branch: `codex/devdocs-wave4-frontdoor-router-hardening`
Scope: Wave4 Lane G, backend ingest/frontdoor router hardening

## Closed In This Lane

- High-JS URL classification now emits a stable route profile from [url_pool.py](../../../../../main/backend/app/services/ingest/url_pool.py):
  - `route_hint=crawler_browse`
  - `fetch_strategy=browser_render`
  - `render_required=true`
  - `prefer_crawler=true`
- High-JS/search-like pages are no longer reduced to plain `search_shell` before crawler/browser routing. Search-shell context is still preserved as `prefer_search_shell=true`.
- `url_pool.single_url_compat` no longer cancels crawler-first routing through the synthetic `url_pool` item. When the frontdoor route profile asks for crawler-first, the source-library URL routing params now include:
  - `prefer_crawler_first=true`
  - `force_url_routing_flow=false`
- Backend results now include a dashboard-safe frontdoor status projection:
  - per URL in `debug.url_details[*].frontdoor_status`
  - aggregate in `meta.frontdoor_status_summary` and `debug.frontdoor_status_summary`
  - contract version: `ingest.frontdoor_status_projection.v1`
- `source_library_fetch_empty` is now a stable technical reason code rather than an ad hoc string.

## Evidence

Focused tests added/updated:

- [test_ingest_frontdoor_context_unittest.py](../../../../../main/backend/tests/unit/test_ingest_frontdoor_context_unittest.py)
  - verifies crawler-first params keep `force_url_routing_flow=false`
  - verifies high-JS `x.com/search` routes to browser-render/crawler-browse
  - verifies frontdoor dashboard status projection exposes `degraded_success + defer`

Commands run:

```bash
cd main/backend
python3.11 -m pytest -q tests/unit/test_ingest_frontdoor_context_unittest.py tests/unit/test_frontdoor_orchestrator_unittest.py tests/unit/test_postprocess_frontdoor_unittest.py
python3.11 -m pytest -q tests/unit/test_ingest_frontdoor_context_unittest.py tests/unit/test_frontdoor_orchestrator_unittest.py tests/unit/test_postprocess_frontdoor_unittest.py tests/core_business/test_ingest_core_contract.py tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py tests/unit/test_ingest_metrics_payload_unittest.py
python3.11 -m py_compile app/services/ingest/url_pool.py app/services/ingest/gate_reason_codes.py
git diff --check
```

Result:

- `19 passed, 2 warnings`
- `57 passed, 11 warnings`
- `py_compile` passed
- `git diff --check` passed
- changed Markdown link check passed: `3 files / 296 links`

## Still Blocked / Out Of Scope

- This lane proves backend route intent and status contracts; it does not prove a real browser-render runtime can fetch every high-JS domain.
- Full crawler provider/API adapter maturity remains outside this lane.
- Frontend/dashboard UI rendering was not changed. The backend now exposes a stable projection for the UI to consume, but the UI itself still needs a separate lane.
- Public source-library replay scripts and broad live-web probes were intentionally not touched.

## Integration Notes

- Keep this lane before any frontend tri-state UI lane so the UI can bind to `frontdoor_status_summary` instead of inferring from outer job status only.
- Future crawler/browser runtime work should use `frontdoor_route_profile.fetch_strategy` and `frontdoor_route_profile.render_required` as the routing contract.
