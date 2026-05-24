# Wave55 C1 High-JS Public Replay Attempt

Date: 2026-05-23

## Purpose

This run exercises the LLM crawler unified frontdoor high-JS path against the three public browser-required targets using local headless Chrome. It records actual browser/runtime evidence without editing shared indexes.

## Artifacts

- `output.public.attempt.json`: opt-in high-JS public replay attempt.
- `check.attempt.json`: readiness checker output for the attempt artifact.

## Result

- Chrome runtime: `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- `public_targets_attempted=3`
- `high_js_success_count=2`
- `status_counts={"auth_or_anti_bot_blocked": 1, "success": 2}`
- `instagram_tag_robotics=success`
- `youtube_search_robotics=success`
- `x_search_robotics=auth_or_anti_bot_blocked`
- `real_public_high_js_replay_complete=false`

`check.attempt.json` exits non-zero by design because a present artifact is not enough: all three target results must be `status=success` with `browser_rendered=true`.

## Commands

```bash
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
