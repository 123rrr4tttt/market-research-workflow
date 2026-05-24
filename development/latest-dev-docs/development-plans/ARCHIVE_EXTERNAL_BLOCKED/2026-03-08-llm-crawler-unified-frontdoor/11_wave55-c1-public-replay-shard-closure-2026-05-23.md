# Wave55 C1 Public Replay Shard Evidence

Date: 2026-05-23

## Result

The 45-site crawler public replay shard boundary is now backed by real public replay shard outputs, not only a missing-output readback. This does not close the full LLM crawler target because one high-JS public target remains auth/anti-bot blocked.

Generated artifacts:

- `development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/output.public.shard-01.json`
- `development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/output.public.shard-02.json`
- `development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/output.public.shard-03.json`
- `development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/output.public.shard-04.json`
- `development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/output.public.shard-05.json`
- `development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/build_summary.json`
- `development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/check.json`

Checker result:

- `status=shard_outputs_present_review_required`
- `validation.passed=true`
- `shard_manifest.present_public_output_count=5`
- `shard_manifest.missing_public_output_count=0`
- `closure.real_public_browser_fleet_replay_complete=true`
- `closure.full_closure_allowed=false`

## High-JS Attempt

Wave55 C1 also ran the high-JS public frontdoor path with local headless Chrome:

- `development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.attempt.json`
- `development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/check.attempt.json`

The attempt contacted all three high-JS targets through Chrome:

- `instagram_tag_robotics=success`
- `youtube_search_robotics=success`
- `x_search_robotics=auth_or_anti_bot_blocked`

Therefore the high-JS readiness checker correctly remains not proven:

- `status=public_replay_artifact_not_proven`
- `public_targets_attempted=3`
- `high_js_success_count=2`
- `real_public_high_js_replay_complete=false`

Superseding T5 note: `12_wave55-t5-accessible-high-js-replay-boundary-2026-05-23.md` keeps full closure false, but reduces the high-JS blocker by proving the accessible public replay path and classifying the remaining failed targets as intrinsic external auth/anti-bot gates.

## Commands

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/build_crawler_public_replay_shard_outputs.py \
  --output development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/build_summary.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_crawler_public_replay_shards.py \
  --repo-root . \
  --output development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/check.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/run_llm_crawler_high_js_public_replay.py \
  --allow-public-network \
  --allow-browser-runtime \
  --operator codex-wave55-c1 \
  --run-id wave55-c1-high-js-2026-05-23 \
  --timeout-seconds 12 \
  --output development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.attempt.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_llm_crawler_high_js_replay_readiness.py \
  --public-artifact development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.attempt.json \
  --output development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/check.attempt.json
```

The final command exits `1` because the X public target is auth-gated in this environment; that exit is the expected non-closure signal for high-JS proof.
