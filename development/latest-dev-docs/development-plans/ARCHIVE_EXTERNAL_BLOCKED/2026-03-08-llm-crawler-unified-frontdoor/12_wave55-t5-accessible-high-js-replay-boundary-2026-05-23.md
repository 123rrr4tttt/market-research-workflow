# Wave55 T5 Accessible High-JS Replay Boundary

Date: 2026-05-23

## Result

T5 reduced the high-JS public replay blocker through implementation and a real browser run, not docs-only evidence.

The readiness gate now distinguishes:

- full closure: every declared high-JS public target succeeds
- reduced external boundary: at least one public high-JS target succeeds, and every remaining failed target is proven by the browser artifact to be an intrinsic auth/anti-bot gate
- X lawful-session boundary: X can be reduced to `platform_blocked` only when
  the artifact shows target success before session policy or explicit
  auth/anti-bot markers; a generic rendered shell does not count as an external
  gate

Final T5 artifact:

- `development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.t5.json`
- `development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/check.t5.json`

Checker result:

- `status=accessible_public_high_js_replay_proven_external_targets_blocked`
- `validation.passed=false`
- `validation.readiness_checks_passed=true`
- `closure.accessible_public_high_js_replay_complete=true`
- `closure.real_public_high_js_replay_complete=false`
- `closure.full_closure_allowed=false`
- `successful_accessible_target_ids=["youtube_search_robotics"]`
- `remaining_external_blockers=["x_search_robotics","instagram_tag_robotics"]`

## Implementation

Changed files:

- `main/backend/scripts/run_llm_crawler_high_js_public_replay.py`
- `main/backend/scripts/check_llm_crawler_high_js_replay_readiness.py`
- `main/backend/tests/unit/test_run_llm_crawler_high_js_public_replay_unittest.py`
- `main/backend/tests/unit/test_llm_crawler_high_js_replay_readiness_check_unittest.py`

The runner now records `successful_accessible_target_ids`, `external_gate_target_ids`, and `remaining_external_blockers`. The checker accepts the reduced boundary only when every declared probe target is accounted for as either `success` or `intrinsic_external_auth_or_anti_bot_gate`; otherwise it still fails as `public_replay_artifact_not_proven`.

## Live Replay Readback

Command:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/run_llm_crawler_high_js_public_replay.py \
  --allow-public-network \
  --allow-browser-runtime \
  --operator codex-wave55-t5 \
  --run-id wave55-t5-accessible-high-js-2026-05-23-final \
  --timeout-seconds 45 \
  --output development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.t5.json
```

Observed target results:

- `youtube_search_robotics=success`
- `x_search_robotics=auth_or_anti_bot_blocked`
- `instagram_tag_robotics=auth_or_anti_bot_blocked`

The X page rendered a login-gated document. The Instagram page rendered an auth/captcha-gated document. Those are now recorded as external platform gates rather than repo-local implementation blockers.

Follow-up hardening: the checker and runner now reject X reduced-boundary claims
when the artifact only shows a rendered non-target shell with no auth/anti-bot
marker and no pre-policy success. This keeps public replay readiness separate
from `closure.full_closure_allowed`.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_llm_crawler_high_js_replay_readiness.py \
  --public-artifact development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.t5.json \
  --output development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/check.t5.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_run_llm_crawler_high_js_public_replay_unittest.py \
  main/backend/tests/unit/test_llm_crawler_high_js_replay_readiness_check_unittest.py
```

Validation result:

- readiness checker exit code is nonzero until `closure.full_closure_allowed=true`; reduced replay is exposed through `validation.readiness_checks_passed=true`
- unit tests `7 passed`

## Remaining Risk

This does not close the full target because full closure still requires every declared public high-JS target to return target-specific public content. The remaining blockers are no longer missing repo evidence; they are external platform auth/anti-bot gates observed through the live browser artifact.
