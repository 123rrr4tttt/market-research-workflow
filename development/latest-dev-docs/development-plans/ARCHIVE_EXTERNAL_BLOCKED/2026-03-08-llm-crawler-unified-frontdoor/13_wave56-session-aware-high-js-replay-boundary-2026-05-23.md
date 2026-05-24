# Wave56 Session-Aware High-JS Replay Boundary

Date: 2026-05-23 PST

## Result

Wave56 adds a credential/session-aware replay path and evidence contract for the
LLM crawler high-JS public frontdoor boundary.

The latest real browser replay did not use operator-provided X/Instagram
credentials or a session profile. No relevant session env vars or repo `.env`
keys were present, and no personal browser profile was used implicitly.

Latest artifact pair:

- `development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.session-aware-attempt.json`
- `development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/check.session-aware-attempt.json`

Checker result:

- `status=accessible_public_high_js_replay_proven_external_targets_blocked`
- `validation.passed=true`
- `closure.accessible_public_high_js_replay_complete=true`
- `closure.real_public_high_js_replay_complete=false`
- `closure.full_closure_allowed=false`
- `successful_accessible_target_ids=["instagram_tag_robotics","youtube_search_robotics"]`
- `remaining_external_blockers=["x_search_robotics"]`

This improves the T5 boundary by proving that Instagram is currently accessible
without a stored session in this environment. X remains an external auth/anti-bot
gate.

## Implementation

Changed files:

- `main/backend/scripts/run_llm_crawler_high_js_public_replay.py`
- `main/backend/scripts/check_llm_crawler_high_js_replay_readiness.py`
- `main/backend/tests/unit/test_run_llm_crawler_high_js_public_replay_unittest.py`
- `main/backend/tests/unit/test_llm_crawler_high_js_replay_readiness_check_unittest.py`

Runner additions:

- `--session-user-data-dir PATH`
- `LLM_CRAWLER_HIGH_JS_SESSION_USER_DATA_DIR`
- `--copy-session-user-data-dir`
- `LLM_CRAWLER_HIGH_JS_COPY_SESSION_USER_DATA_DIR=true`

The runner records `evidence.session` with
`contract_version=llm_crawler.high_js_session_replay_evidence.v1`,
`session_aware_replay_requested`, `session_context_applied`, source/mode, and
`credential_material_logged=false`. It records a path fingerprint/name only when
an operator provides a session directory; it does not record local paths, cookie
values, tokens, or profile contents.

Checker additions:

- validates the session evidence contract when present;
- rejects artifacts that claim credential material was logged;
- includes `session_replay_evidence` in the public replay summary.

## Live Replay Readback

Command:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/run_llm_crawler_high_js_public_replay.py \
  --allow-public-network \
  --allow-browser-runtime \
  --operator codex-session-aware \
  --run-id session-aware-high-js-2026-05-23 \
  --timeout-seconds 45 \
  --output development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.session-aware-attempt.json
```

Observed target results:

- `x_search_robotics=auth_or_anti_bot_blocked`
- `instagram_tag_robotics=success`
- `youtube_search_robotics=success`

Session evidence:

- `session_aware_replay_requested=false`
- `session_context_applied=false`
- `user_data_dir_mode=ephemeral_empty_profile`
- `credential_material_logged=false`

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_llm_crawler_high_js_replay_readiness.py \
  --public-artifact development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.session-aware-attempt.json \
  --output development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/check.session-aware-attempt.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_run_llm_crawler_high_js_public_replay_unittest.py \
  main/backend/tests/unit/test_llm_crawler_high_js_replay_readiness_check_unittest.py
```

Validation result:

- readiness checker exit code `0`
- unit tests `11 passed`

## Closure Decision

Not fully closed.

Full closure still requires every declared high-JS public target to return
target-specific public content. The latest run leaves only
`x_search_robotics` blocked, and that blocker is explicitly backed by browser
evidence plus a no-session evidence contract rather than by a missing repo path.
