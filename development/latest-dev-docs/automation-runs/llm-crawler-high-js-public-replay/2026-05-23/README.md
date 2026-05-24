# Wave55 High-JS Public Replay Attempts

Date: 2026-05-23

## Purpose

These runs exercise the LLM crawler unified frontdoor high-JS path against the three public browser-required targets using local headless Chrome. They record actual browser/runtime evidence without editing shared indexes.

## Artifacts

- `output.public.attempt.json`: Wave55 C1 opt-in high-JS public replay attempt.
- `check.attempt.json`: readiness checker output for the C1 attempt artifact.
- `output.public.t5.json`: Wave55 T5 opt-in high-JS public replay with accessible-target/external-gate split.
- `check.t5.json`: readiness checker output for the T5 artifact.
- `output.public.session-aware-attempt.json`: Wave56 session-aware-capable high-JS public replay attempt.
- `check.session-aware-attempt.json`: readiness checker output for the Wave56 session-aware attempt.

## C1 Result

- Chrome runtime: `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- `public_targets_attempted=3`
- `high_js_success_count=2`
- `status_counts={"auth_or_anti_bot_blocked": 1, "success": 2}`
- `instagram_tag_robotics=success`
- `youtube_search_robotics=success`
- `x_search_robotics=auth_or_anti_bot_blocked`
- `real_public_high_js_replay_complete=false`

`check.attempt.json` exits non-zero by design because a present artifact is not enough: all three target results must be `status=success` with `browser_rendered=true`.

## T5 Result

T5 updates the gate semantics to separate accessible public high-JS replay from intrinsic platform gates. The final run contacted all three targets through local headless Chrome:

- `youtube_search_robotics=success`
- `x_search_robotics=auth_or_anti_bot_blocked`
- `instagram_tag_robotics=auth_or_anti_bot_blocked`

Checker result:

- `status=accessible_public_high_js_replay_proven_external_targets_blocked`
- `validation.passed=false`
- `validation.readiness_checks_passed=true`
- `public_targets_attempted=3`
- `high_js_success_count=1`
- `successful_accessible_target_ids=["youtube_search_robotics"]`
- `remaining_external_blockers=["x_search_robotics","instagram_tag_robotics"]`
- `closure.accessible_public_high_js_replay_complete=true`
- `closure.real_public_high_js_replay_complete=false`
- `closure.full_closure_allowed=false`

This reduces the blocker from "real high-JS public replay unproven" to "accessible public high-JS replay proved; remaining failures are intrinsic external auth/anti-bot gates."

## Wave56 Session-Aware Result

Wave56 adds a credential/session-aware replay path and evidence contract. The run
below did not use an operator-provided session profile because no relevant
session env vars or repo `.env` keys were present.

The final run contacted all three targets through local headless Chrome:

- `instagram_tag_robotics=success`
- `youtube_search_robotics=success`
- `x_search_robotics=auth_or_anti_bot_blocked`

Checker result:

- `status=accessible_public_high_js_replay_proven_external_targets_blocked`
- `validation.passed=false`
- `validation.readiness_checks_passed=true`
- `public_targets_attempted=3`
- `high_js_success_count=2`
- `successful_accessible_target_ids=["instagram_tag_robotics","youtube_search_robotics"]`
- `remaining_external_blockers=["x_search_robotics"]`
- `session_replay_evidence.status=present`
- `session_replay_evidence.session_aware_replay_requested=false`
- `session_replay_evidence.session_context_applied=false`
- `closure.accessible_public_high_js_replay_complete=true`
- `closure.real_public_high_js_replay_complete=false`
- `closure.full_closure_allowed=false`

Current checker semantics reserve `validation.passed=true` for full closure. Reduced accessible replay exits nonzero unless the caller explicitly treats `validation.readiness_checks_passed=true` as an external-blocked readback state.

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

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/run_llm_crawler_high_js_public_replay.py \
  --allow-public-network \
  --allow-browser-runtime \
  --operator codex-wave55-t5 \
  --run-id wave55-t5-accessible-high-js-2026-05-23-final \
  --timeout-seconds 45 \
  --output development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.t5.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_llm_crawler_high_js_replay_readiness.py \
  --public-artifact development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.t5.json \
  --output development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/check.t5.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/run_llm_crawler_high_js_public_replay.py \
  --allow-public-network \
  --allow-browser-runtime \
  --operator codex-session-aware \
  --run-id session-aware-high-js-2026-05-23 \
  --timeout-seconds 45 \
  --output development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.session-aware-attempt.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_llm_crawler_high_js_replay_readiness.py \
  --public-artifact development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.session-aware-attempt.json \
  --output development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/check.session-aware-attempt.json
```
