# Wave19 Public Replay Shards Readback

Date: 2026-05-22
Branch: `codex/devdocs-wave19-crawler-public-replay-shards`
Scope: `2026-03-08-llm-crawler-unified-frontdoor`

## Status

`external_blocked`

Wave18 proved the repo-local browser decision path for the three high-JS frontdoor targets. Wave19 connects that browser fixture to the broader 45-site public replay boundary by validating a shard manifest/readback gate. The checker requires the Wave18 browser fixture to stay green and still report no public network, no browser runtime, and no real public high-JS replay completion.

## Evidence

- [crawler-public-replay-shards/2026-05-22](../../../automation-runs/crawler-public-replay-shards/2026-05-22/README.md)
- [check_crawler_public_replay_shards.py](../../../../../main/backend/scripts/check_crawler_public_replay_shards.py)
- [test_crawler_public_replay_shards_unittest.py](../../../../../main/backend/tests/unit/test_crawler_public_replay_shards_unittest.py)
- [Wave18 browser replay fixture](../../../automation-runs/llm-crawler-browser-replay-fixture/2026-05-22/replay.fixture.json)
- [Wave19 check output](../../../automation-runs/crawler-public-replay-shards/2026-05-22/check.json)

## Frontdoor Readback

The Wave19 checker calls `check_llm_crawler_replay_fixture.py` as a required gate. Current `check.json` records:

- `browser_replay_fixture_gate.status=fixture_replay_passed_public_replay_not_closed`
- `browser_replay_fixture_gate.public_network_attempted=false`
- `browser_replay_fixture_gate.browser_runtime_started=false`
- `browser_replay_fixture_gate.real_public_high_js_replay_complete=false`
- `browser_replay_fixture_gate.full_closure_allowed=false`

This means the unified frontdoor browser-required path remains deterministic evidence only. It does not stand in for real public browser fleet replay.

## Boundary

The shard readback keeps missing public outputs as `external_blocked`. The repo-local fixture proves manifest and frontdoor decision consistency, not live external site access.

Full closure still requires a real opt-in public browser/crawler run that stores public output artifacts for the 45-site replay and the five shard outputs. Until those artifacts exist and validate, the LLM crawler public replay boundary remains open.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_crawler_public_replay_shards_unittest.py \
  main/backend/tests/unit/test_llm_crawler_replay_fixture_check_unittest.py

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_crawler_public_replay_shards.py \
  --repo-root .
```
