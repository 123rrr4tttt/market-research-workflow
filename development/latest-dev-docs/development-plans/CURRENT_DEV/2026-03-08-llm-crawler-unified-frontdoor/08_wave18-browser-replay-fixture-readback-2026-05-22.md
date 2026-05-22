# Wave18 Browser Replay Fixture Readback

Date: 2026-05-22
Scope: `2026-03-08-llm-crawler-unified-frontdoor`

## status:

`repo_local_browser_replay_fixture_passed_real_public_replay_not_closed`

## gap:

Wave13 proved deterministic high-JS route readiness, and Wave15 fixed the
public replay manifest and opt-in schema. Wave18 adds the missing repo-local
browser replay fixture readback: the fixture reads the Wave15 manifest target
shape, replays the current frontdoor route/profile decision for every high-JS
target, and proves the browser-required path without using public network or a
live browser fleet.

This remains a partial status. The fixture proves the local decision path, not
real public high-JS replay against external sites.

## contract:

Checker: `main/backend/scripts/check_llm_crawler_replay_fixture.py`

Fixture: `development/latest-dev-docs/automation-runs/llm-crawler-browser-replay-fixture/2026-05-22/replay.fixture.json`

Checker contract version: `llm_crawler.replay_fixture.check.v1`

Fixture contract version: `llm_crawler.browser_replay_fixture.v1`

Decision contract version: `llm_crawler.browser_replay_decision.v1`

Manifest readback source:
`development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-22/manifest.json`

## fixture boundary:

The fixture validates the three Wave15 high-JS targets:

- `x_search_robotics`
- `instagram_tag_robotics`
- `youtube_search_robotics`

For each target the checker verifies:

- manifest shape: `high_js=true`, `public_site=true`,
  `render_required=true`, `route_hint=crawler_browse`,
  `fetch_strategy=browser_render`, `public_replay_opt_in_required=true`,
  `http_fetch_fallback_allowed=false`
- frontdoor route profile: `ingest.frontdoor_route_profile.v1`
- router contract: `ingest.frontdoor_fetch_router.v1`
- browser path: `router_state=needs_browser`,
  `reason_code=needs_browser_runtime`, `browser_fetch_required=true`
- blocked fallback: `http_fetch_fallback_allowed=false`
- no public closure claim:
  `public_browser_replay_performed=false`,
  `public_network_attempted=false`, `browser_runtime_started=false`

## evidence:

- `main/backend/scripts/check_llm_crawler_replay_fixture.py` validates the
  fixture against the current Wave15 manifest and current route/profile code.
- `main/backend/tests/unit/test_llm_crawler_replay_fixture_check_unittest.py`
  covers the passing fixture, target decision drift rejection, and rejection of
  any fixture claim that public network or a live browser runtime was used.
- `development/latest-dev-docs/automation-runs/llm-crawler-browser-replay-fixture/2026-05-22/replay.fixture.json`
  is the repo-local browser decision replay fixture.

## validation:

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q tests/unit/test_llm_crawler_replay_fixture_check_unittest.py
/Users/wangyiliang/.local/bin/python3.11 scripts/check_llm_crawler_replay_fixture.py
cd ../..
/Users/wangyiliang/.local/bin/python3.11 scripts/check_current_dev_wave18_plan.py
git diff --check
```

Expected checker result:

- `status=fixture_replay_passed_public_replay_not_closed`
- `closure.manifest_readback_valid=true`
- `closure.browser_high_js_decision_path_valid=true`
- `closure.repo_local_fixture_replay_complete=true`
- `closure.real_public_high_js_replay_complete=false`
- `closure.full_closure_allowed=false`
- `validation.public_network_attempted=false`
- `validation.browser_runtime_started=false`

## remaining blocker:

Real public high-JS replay is still unproven. Full closure still requires a
live public browser/crawler run that produces
`development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-22/output.public.json`
with the Wave15 public replay proof fields.
