# Wave57 Yiliang Session X Replay Boundary

Date: 2026-05-23 PST

## Result

Wave57 used the operator-selected Chrome profile `亦梁` as explicit session
input for the high-JS public replay lane. The runner copied the profile to a
disposable runtime directory and recorded only non-secret session evidence.

Latest artifact pair:

- `development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.yiliang-session.json`
- `development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/check.yiliang-session.json`

Checker result:

- `status=accessible_public_high_js_replay_proven_external_targets_blocked`
- `validation.readiness_checks_passed=true`
- `validation.external_blocked=true`
- `validation.closure_ready=false`
- `shared_indexes_edited=false`

Observed target results:

- `x_search_robotics=platform_blocked`
- `instagram_tag_robotics=success`
- `youtube_search_robotics=success`

The X target rendered the X shell with login markers:

- `title="X - 包罗万象的应用 / X"`
- `contains_login=true`
- `contains_robotics=false`
- `lawful_session_evidence.accepted=false`

## Session Evidence

The replay was session-aware but did not expose credential material:

- `session_aware_replay_requested=true`
- `session_context_applied=true`
- `session.user_data_dir_mode=copied_operator_profile`
- `session.source_path_name=Profile 3`
- `credential_material_logged=false`
- `path_disclosed=false`

The profile copy was attempted as disposable runtime state. The source path is
not stored in the artifact.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/run_llm_crawler_high_js_public_replay.py \
  --allow-public-network \
  --allow-browser-runtime \
  --timeout-seconds 25 \
  --operator codex \
  --run-id x-lawful-session-yiliang-2026-05-24 \
  --session-user-data-dir '/Users/wangyiliang/Library/Application Support/Google/Chrome/Profile 3' \
  --copy-session-user-data-dir \
  --output development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.yiliang-session.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_llm_crawler_high_js_replay_readiness.py \
  --public-artifact development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/output.public.yiliang-session.json \
  --output development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-23/check.yiliang-session.json
```

The checker intentionally exits nonzero while `closure_ready=false`; the JSON
result is still valid external-blocker evidence because readiness checks pass
and no shared index edits were required.

## Closure Decision

Not fully closed.

This wave removes the ambiguity that the X blocker was only caused by an empty
ephemeral profile. With the operator-selected `亦梁` Chrome profile copied into
the replay, X still returns a login/platform gate rather than target-specific
public robotics search content. Full closure requires a lawful X session that
renders `x_search_robotics=success`; the current local profile does not provide
that state.
