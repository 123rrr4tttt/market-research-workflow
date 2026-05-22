# Wave13 High-JS Public Replay Readiness Gate

Date: 2026-05-22
Scope: `2026-03-08-llm-crawler-unified-frontdoor`

## status:

`readiness_contract_closed_external_public_replay_blocked`

## gap:

Wave8 and Wave10 prove the deterministic high-JS route profile, crawler provider
handoff, router tri-state, and consumer projection boundaries. They do not prove
that a real browser/crawler runtime completed public high-JS replay against
external sites.

Wave13 adds a repo-controlled gate for that boundary:

- deterministic fixture readiness can pass without public network access
- a missing public replay artifact records an external blocker, not full closure
- a present public replay artifact must explicitly prove real public high-JS
  replay before `full_closure_allowed` can become true

## contract:

Checker: `main/backend/scripts/check_llm_crawler_high_js_replay_readiness.py`

Contract version: `llm_crawler.high_js_replay_readiness.v1`

Default deterministic targets:

- `https://x.com/search?q=robotics`
- `https://www.instagram.com/explore/tags/robotics/`
- `https://www.youtube.com/results?search_query=robotics`

Required deterministic readiness:

- `ingest.frontdoor_route_profile.v1`
- `ingest.frontdoor_fetch_router.v1`
- `route_hint=crawler_browse`
- `fetch_strategy=browser_render`
- `router_state=needs_browser`
- `reason_code=needs_browser_runtime`
- `http_fetch_fallback_allowed=false`
- `public_browser_replay_performed=false`
- crawler provider handoff checker passes with no public network attempt

Required real replay proof before full closure:

- public artifact contract: `llm_crawler.high_js_public_replay.v1`
- `validation.real_public_high_js_replay_proven=true`
- `validation.public_network_attempted=true`
- attempted public target count covers the declared high-JS target count
- every target result records `status=success` and `browser_rendered=true`

Default public artifact path:

`development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-22/output.public.json`

No such artifact is present in this branch, so the gate reports fixture
readiness only and keeps the real public replay blocker active.

## evidence:

- `main/backend/scripts/check_llm_crawler_high_js_replay_readiness.py` emits the
  readiness/public-replay split and refuses full closure without explicit public
  proof.
- `main/backend/tests/unit/test_llm_crawler_high_js_replay_readiness_check_unittest.py`
  covers the absent-artifact blocked state, a present-but-insufficient artifact,
  and the schema required for full closure.
- Existing route/handoff anchors remain:
  - `main/backend/app/services/ingest/frontdoor_router_contract.py`
  - `main/backend/app/services/ingest/url_pool.py`
  - `main/backend/scripts/check_crawler_provider_handoff_contract.py`

## validation:

```bash
cd main/backend
python3.11 -m pytest -q tests/unit/test_llm_crawler_high_js_replay_readiness_check_unittest.py
python3.11 scripts/check_llm_crawler_high_js_replay_readiness.py
cd ../..
python3 scripts/check_current_dev_wave13_plan.py
git diff --check
```

Expected gate result for this branch:

- `status=fixture_ready_real_public_replay_blocked`
- `closure.deterministic_fixture_ready=true`
- `closure.real_public_high_js_replay_complete=false`
- `closure.full_closure_allowed=false`
- `validation.public_network_attempted=false`

## remaining blocker:

Real public high-JS replay is still unproven. This topic must remain partial
until a live external replay run produces the required public artifact and the
checker returns `status=real_public_high_js_replay_proven`.
