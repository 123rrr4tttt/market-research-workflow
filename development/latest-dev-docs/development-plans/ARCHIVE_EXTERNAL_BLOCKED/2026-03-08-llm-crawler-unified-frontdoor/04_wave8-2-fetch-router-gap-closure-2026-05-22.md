# Wave8-2 Fetch Router Gap Cluster Evidence

Date: 2026-05-22
Scope: `2026-03-08-llm-crawler-unified-frontdoor`

## status:

`closed_narrow_runtime_contract`

## gap:

The high-JS/browser route intent gap is closed for the narrow provider-handoff contract:

- ingest-facing URL routing marks high-JS domains with `crawler_browse`, `browser_render`, `render_required`, and `prefer_crawler` intent.
- source-library URL routing can hand that intent to the crawler provider and preserve the `source_library.provider_handoff.v1` envelope.
- collect-runtime projection carries the provider handoff back into `terminal_output`, `frontdoor_ingress`, and `authority_output`.
- tri-state dashboard wording is fixed as `success`, `degraded_success`, and `failed`; lack of a live browser fleet is recorded as outside this narrow gate, not as a blocker to contract closure.

## evidence:

- `main/backend/tests/unit/test_ingest_frontdoor_context_unittest.py::test_high_js_frontdoor_route_prefers_browser_render_and_projects_dashboard_status` verifies the ingest-facing high-JS route intent and dashboard status projection.
- `main/backend/tests/unit/test_source_library_resolver_unittest.py::test_high_js_browser_route_hands_off_to_crawler_provider_with_trace` verifies provider handoff with `source_library.provider_handoff.v1`, `provider_dispatch=crawlers/providers`, and `fetch_strategy=browser_render`.
- `main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py::test_to_source_library_response_preserves_provider_handoff_contract` verifies the handoff is projected through terminal output, frontdoor ingress, and authority output.
- `main/backend/scripts/check_fetch_router_gap_closure.py` emits this topic's current `status`, `gap`, evidence anchors, and tri-state blocker scope.

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
