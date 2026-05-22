# Wave8-2 Fetch Router Gap Cluster Evidence

Date: 2026-05-22
Scope: `2026-03-02-ingest-platformization-assessment`

## status:

`closed_narrow_runtime_contract`

## gap:

The previous `fetch_router_gap` is closed for the narrow runtime contract covered by this lane:

- legacy `single_url` is the compatibility contract name, not a standalone module target.
- the write-capable URL path now resolves through `url_pool.single_url_compat -> source_library URL routing -> frontdoor_ingress -> postprocess_frontdoor(run_writer=True)`.
- high-JS/browser route intent is represented by `crawler_browse` + `browser_render` route metadata before provider handoff.
- dashboard-facing status remains tri-state: `success`, `degraded_success`, `failed`.

Remaining broader work is outside this gate: live browser fleet completeness, official API adapter maturity, and product dashboard polish.

## evidence:

- `main/backend/app/services/ingest/url_pool.py` builds the synthetic `url_pool.single_url_compat` source-library item, calls `run_item_with_url_routing(..., execution_layer="terminal_output_only")`, then invokes `build_frontdoor_ingress_envelope` and `run_postprocess_frontdoor(run_writer=True)`.
- `main/backend/app/services/ingest/frontdoor_ingress.py` preserves `provider_handoff`, `frontdoor_route_profile`, `frontdoor_route_hint`, and `fetch_strategy` into the frontdoor source reference and collection payload.
- `main/backend/tests/unit/test_ingest_frontdoor_context_unittest.py::test_ingest_url_via_source_library_frontdoor_uses_source_library_bridge_and_postprocess_writer` now asserts the single-url compatibility path produces a source-library frontdoor `source_ref`.
- `main/backend/tests/unit/test_ingest_frontdoor_context_unittest.py::test_high_js_frontdoor_route_prefers_browser_render_and_projects_dashboard_status` covers high-JS route intent and tri-state projection.
- `main/backend/scripts/check_fetch_router_gap_closure.py` emits this topic's current `status`, `gap`, and evidence anchors.

## validation:

```bash
cd main/backend
python3.11 -m pytest -q \
  tests/unit/test_ingest_frontdoor_context_unittest.py \
  tests/unit/test_source_library_resolver_unittest.py \
  tests/unit/test_collect_runtime_source_library_adapter_unittest.py \
  tests/unit/test_fetch_router_gap_closure_check_unittest.py
cd ../..
python3.11 main/backend/scripts/check_fetch_router_gap_closure.py
git diff --check
```
