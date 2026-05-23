# Wave10 Tri-State Router Contract Evidence

Date: 2026-05-22
Scope: `2026-03-08-llm-crawler-unified-frontdoor`

## status:

`closed_deterministic_tri_state_router_contract`

## gap:

Wave8 closed the narrow provider-handoff contract. Wave10 adds a deterministic
local contract for high-JS/router tri-state consumption without claiming live
browser replay.

The backend now exposes `ingest.frontdoor_fetch_router.v1` through:

- `url_pool` high-JS route profiles
- source-library crawler provider handoff
- terminal/frontdoor/authority projections
- URL-pool frontdoor status projection

## contract:

Required states:

- `success`
- `degraded_success`
- `failed`

Required router states and reason codes:

- `needs_browser` -> `needs_browser_runtime`
- `unsupported` -> `unsupported_fetch_strategy`
- `blocked` -> policy reason such as `browser_runtime_blocked`

Fallback boundary invariants:

- high-JS/browser-required routes set `http_fetch_fallback_allowed: false`
- URL-only document writes remain blocked with `legacy_url_only_write_allowed: false`
- deterministic local checks record `public_browser_replay_performed: false`

## evidence:

- `main/backend/app/services/ingest/frontdoor_router_contract.py` defines the
  deterministic router envelope and fallback boundary.
- `main/backend/app/services/ingest/url_pool.py` attaches the router envelope to
  high-JS route profiles, queued async status, and frontdoor status projection.
- `main/backend/app/services/source_library/resolver.py` preserves the router
  envelope through crawler provider handoff.
- `main/backend/app/services/source_library/terminal_output.py`,
  `main/backend/app/services/ingest/frontdoor_ingress.py`, and
  `main/backend/app/services/collect_runtime/adapters/source_library.py` project
  the router envelope through consumer-facing DTOs.
- `main/backend/tests/unit/test_frontdoor_fetch_router_contract_unittest.py`
  covers high-JS `needs_browser`, `unsupported`, and `blocked` states without
  launching a browser.
- `main/backend/scripts/check_fetch_router_gap_closure.py` now gates the Wave10
  contract and this topic-local evidence file.

## validation:

```bash
cd main/backend
python3.11 -m pytest -q \
  tests/unit/test_frontdoor_fetch_router_contract_unittest.py \
  tests/unit/test_ingest_frontdoor_context_unittest.py \
  tests/unit/test_source_library_resolver_unittest.py \
  tests/unit/test_collect_runtime_source_library_adapter_unittest.py \
  tests/unit/test_fetch_router_gap_closure_check_unittest.py
cd ../..
python3.11 main/backend/scripts/check_fetch_router_gap_closure.py
python3.11 scripts/check_current_dev_wave10_plan.py
git diff --check
```

No public browser replay was executed. This evidence is limited to deterministic
local route, envelope, fallback-boundary, and consumer-projection contracts.
