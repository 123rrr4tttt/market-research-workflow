# Wave15 High-JS Replay Manifest Gate

Date: 2026-05-22
Scope: `2026-03-08-llm-crawler-unified-frontdoor`

## status:

`manifest_schema_valid_real_public_replay_not_closed`

## gap:

Wave13 closed deterministic high-JS readiness while leaving live public browser
replay blocked. Wave15 adds the manifest/schema gate for the missing operational
boundary: a future public replay must be explicitly opted in before any high-JS
target can be executed against public sites.

This gate does not run a browser and does not access the public network. It
keeps the high-JS replay gap open until a real public replay output proves the
browser-rendered target results.

## contract:

Checker: `main/backend/scripts/check_llm_crawler_replay_manifest.py`

Manifest: `development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-22/manifest.json`

Checker contract version: `llm_crawler.replay_manifest.check.v1`

Manifest contract version: `llm_crawler.high_js_replay_manifest.v1`

Operator opt-in contract version:
`llm_crawler.high_js_public_replay.opt_in_request.v1`

Public replay output contract version:
`llm_crawler.high_js_public_replay.v1`

## manifest boundary:

The manifest fixes the high-JS/public replay target set to the same Wave13
readiness targets:

- `x_search_robotics`: `https://x.com/search?q=robotics`
- `instagram_tag_robotics`: `https://www.instagram.com/explore/tags/robotics/`
- `youtube_search_robotics`: `https://www.youtube.com/results?search_query=robotics`

Each manifest target must remain:

- `high_js=true`
- `public_site=true`
- `render_required=true`
- `route_hint=crawler_browse`
- `fetch_strategy=browser_render`
- `public_replay_opt_in_required=true`
- `http_fetch_fallback_allowed=false`

The checker cross-checks these fields against the current frontdoor route
profile and router contract. The deterministic router boundary must still
report `router_state=needs_browser` and `public_browser_replay_performed=false`.

## opt-in schema:

A future public replay request must include:

- `contract_version=llm_crawler.high_js_public_replay.opt_in_request.v1`
- `allow_public_network=true`
- `allow_browser_runtime=true`
- `allow_high_js_targets=true`
- `acknowledge_external_site_terms=true`
- `acknowledge_rate_limits=true`
- `acknowledge_no_shared_index_edits=true`
- non-empty `operator`, `run_id`, `requested_at`, `browser_runtime`,
  `evidence_output`, and `output_contract_version`
- `target_ids` exactly matching the manifest targets
- `evidence_output` exactly matching
  `development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-22/output.public.json`

A valid opt-in request only means the replay is allowed to execute. It is not
evidence that public replay happened.

## real evidence required:

Full closure still requires a public output artifact with:

- `contract_version=llm_crawler.high_js_public_replay.v1`
- embedded operator opt-in with public network, browser runtime, and high-JS
  target permissions set to true
- `validation.real_public_high_js_replay_proven=true`
- `validation.public_network_attempted=true`
- `inputs.target_count=3`
- `outputs.public_targets_attempted=3`
- `outputs.high_js_success_count=3`
- every target result recording `status=success` and `browser_rendered=true`

No such live public output is present in this branch.

## evidence:

- `main/backend/scripts/check_llm_crawler_replay_manifest.py` validates the
  manifest, target route profiles, opt-in request schema, and real evidence
  requirements without public network access.
- `main/backend/tests/unit/test_llm_crawler_replay_manifest_check_unittest.py`
  covers the default not-closed manifest, missing opt-in schema fields, a valid
  opt-in request that still does not claim replay completion, and target-set
  mismatch rejection.
- Existing anchors remain:
  - `main/backend/scripts/check_llm_crawler_high_js_replay_readiness.py`
  - `main/backend/scripts/check_crawler_provider_handoff_contract.py`
  - `main/backend/app/services/ingest/frontdoor_router_contract.py`
  - `main/backend/app/services/ingest/url_pool.py`

## validation:

```bash
cd main/backend
python3.11 -m pytest -q tests/unit/test_llm_crawler_replay_manifest_check_unittest.py
python3.11 scripts/check_llm_crawler_replay_manifest.py
cd ../..
python3 scripts/check_current_dev_wave15_plan.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 scripts/check_current_dev_status_evidence.py
git diff --check
```

Expected checker result for this branch:

- `status=manifest_valid_real_public_replay_not_closed`
- `closure.manifest_valid=true`
- `closure.real_public_high_js_replay_complete=false`
- `closure.full_closure_allowed=false`
- `validation.public_network_attempted=false`
- `validation.browser_runtime_started=false`

## remaining blocker:

Real public high-JS replay is still unproven. The topic remains partial until a
live browser/crawler run produces the required `output.public.json` and the
readiness/public replay checker can return a real public replay completion
state.
