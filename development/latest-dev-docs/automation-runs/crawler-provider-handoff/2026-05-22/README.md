# Wave7-4 Crawler Provider Handoff Evidence

Date: 2026-05-22 PST
Branch: `codex/devdocs-wave7-crawler-provider-handoff`
Scope: crawler source expansion A6 handoff closure

## Result

Status: `A6 evidence-closed / broader topic still not_closed`.

This lane closes the A6 gap around provider-specific crawler and High-JS/browser handoff by adding a stable source-library provider handoff contract:

- Contract: `source_library.provider_handoff.v1`
- Route profile source: `ingest.frontdoor_route_profile.v1`
- Provider dispatch owner: `crawlers/providers`
- Downstream handoff owner: `ingest`

## Provider Handoff Contract

High-JS/browser-render route intent now survives the deterministic backend handoff path:

```text
frontdoor route profile
  -> source_library.resolver.run_item_with_url_routing
  -> crawler provider channel row
  -> crawler dispatch arguments
  -> result.by_url[*].provider_handoff
  -> source_library terminal_output.meta.provider_handoff
  -> frontdoor_ingress.source_ref / collection_payload
  -> authority_output.summary.provider_handoff
```

The handoff row records `handoff_kind`, `channel_key`, `provider_type`, `provider_dispatch`, `provider_job_id`, `provider_status`, `execution_layer`, route hint, fetch strategy, render requirement, and fallback provenance when present.

## High-JS/browser Handoff

The focused high-JS fixture uses `https://x.com/search?q=robotics` with:

- `route_hint=crawler_browse`
- `fetch_strategy=browser_render`
- `render_required=true`
- `prefer_crawler_first=true`
- `force_url_routing_flow=false`

The test does not claim public cross-site browser success. It proves the route intent and provider-specific crawler handoff contract remain observable until ingest-facing authority output.

## Evidence Anchors

- [source_library/resolver.py](../../../../../main/backend/app/services/source_library/resolver.py): URL routing provider handoff and crawler argument propagation.
- [source_library/terminal_output.py](../../../../../main/backend/app/services/source_library/terminal_output.py): terminal projection of provider handoff and route profile.
- [ingest/frontdoor_ingress.py](../../../../../main/backend/app/services/ingest/frontdoor_ingress.py): frontdoor source ref and collection payload preservation.
- [collect_runtime/adapters/source_library.py](../../../../../main/backend/app/services/collect_runtime/adapters/source_library.py): authority output provider handoff summary.
- [check_crawler_provider_handoff_contract.py](../../../../../main/backend/scripts/check_crawler_provider_handoff_contract.py): deterministic projection checker.
- [test_source_library_resolver_unittest.py](../../../../../main/backend/tests/unit/test_source_library_resolver_unittest.py): `test_high_js_browser_route_hands_off_to_crawler_provider_with_trace`.
- [test_collect_runtime_source_library_adapter_unittest.py](../../../../../main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py): `test_to_source_library_response_preserves_provider_handoff_contract`.

## Validation

Commands:

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  tests/unit/test_source_library_resolver_unittest.py \
  tests/unit/test_collect_runtime_source_library_adapter_unittest.py \
  tests/unit/test_crawler_source_expansion_closure_check_unittest.py
/Users/wangyiliang/.local/bin/python3.11 scripts/check_crawler_provider_handoff_contract.py --output ../../development/latest-dev-docs/automation-runs/crawler-provider-handoff/2026-05-22/provider_handoff_check.json
/Users/wangyiliang/.local/bin/python3.11 scripts/check_crawler_source_expansion_closure.py --output ../../development/latest-dev-docs/automation-runs/crawler-provider-handoff/2026-05-22/crawler_source_expansion_closure_check.json
/Users/wangyiliang/.local/bin/python3.11 -m py_compile \
  app/services/source_library/resolver.py \
  app/services/source_library/terminal_output.py \
  app/services/ingest/frontdoor_ingress.py \
  app/services/collect_runtime/adapters/source_library.py \
  scripts/check_crawler_provider_handoff_contract.py \
  scripts/check_crawler_source_expansion_closure.py
git diff --check
```

Result:

- combined focused pytest: `64 passed, 2 warnings`
- `check_crawler_provider_handoff_contract.py`: passed; wrote `provider_handoff_check.json`
- `check_crawler_source_expansion_closure.py`: validation passed; A6 is `closed`, overall topic remains `not_closed`
- `py_compile`: passed
- `git diff --check`: passed

## Remaining Risks

- A4 and A5 remain outside this lane: source-layer allow/downgrade/block policy and full 45-site public replay are still open.
- This lane proves deterministic provider handoff semantics, not live browser-render success on public high-JS domains.
- Shared navigation and overview indexes are intentionally untouched for later integration.
