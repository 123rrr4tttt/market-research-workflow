# Wave19 Crawler Public Replay Shards

Date: 2026-05-22
Branch: `codex/devdocs-wave19-crawler-public-replay-shards`

## Purpose

This run splits the real 45-site public replay boundary into five shards. Wave55 C1 added generated per-shard public outputs from the existing full 45-site public replay artifact and revalidated the shard checker against those outputs.

## Artifacts

- `shard_manifest.json`: five 9-target shards in source manifest order.
- `output.public.shard-01.json` through `output.public.shard-05.json`: per-shard public replay outputs generated from `source-library-replay-scaleout/2026-05-22/output.public.json`.
- `shard_readback.json`: public-output readback for the five shard outputs.
- `build_summary.json`: shard generation summary from `main/backend/scripts/build_crawler_public_replay_shard_outputs.py`.
- `check.json`: checker output from `main/backend/scripts/check_crawler_public_replay_shards.py`.

## Current Result

`check.json` reports:

- `status=shard_outputs_present_review_required`
- `shard_manifest.shard_count=5`
- `shard_manifest.target_count=45`
- `shard_manifest.enabled_public_target_count=40`
- `shard_manifest.policy_disabled_target_count=5`
- `shard_manifest.present_public_output_count=5`
- `shard_manifest.missing_public_output_count=0`
- `crawler_public_replay_gate.live_public_replay_status=real_evidence_present_review_required`
- `browser_replay_fixture_gate.status=fixture_replay_passed_public_replay_not_closed`
- `closure.overall_status=public_replay_shards_present_review_required`

## Boundary

The shard builder does not contact public sites itself; it consumes the existing full public replay output that already records `allow_public_network=true`, `public_targets_attempted=40`, and five policy-disabled platform/API targets. The checker validates the generated shard outputs and keeps `full_closure_allowed=false` because this is review-required public evidence, not an automatic global closure.

The LLM high-JS browser fixture remains separate. Wave55 C1 ran an opt-in Chrome attempt under:

- `development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.attempt.json`
- `development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/check.attempt.json`

That run started Chrome and public network for all three high-JS targets, but X remained auth-gated, so `real_public_high_js_replay_complete=false`.

## Repeatable Commands

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/build_crawler_public_replay_shard_outputs.py \
  --output development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/build_summary.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_crawler_public_replay_shards.py \
  --repo-root . \
  --output development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/check.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_crawler_public_replay_shards_unittest.py
```
