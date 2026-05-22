# Wave4 Source Library Replay Scaleout - 2026-05-22

## Scope

This lane advances the remaining `AT-AC-10` blocker from "selected four-target public probe" to a full historical `demo_proj` 45-site replay manifest for `handler.cluster.search_template`.

Evidence package:

- [source-library-replay-scaleout/2026-05-22](../../../automation-runs/source-library-replay-scaleout/2026-05-22/README.md)
- Script: `main/backend/scripts/source_library_replay_scaleout.py`
- Gate test: `main/backend/tests/unit/test_source_library_replay_scaleout_unittest.py`

## What Changed

- Added a deterministic 45-target replay manifest based on the historical `project_demo_proj.resource_pool_site_entries` `search_template` set.
- Kept public network execution opt-in via `--allow-public-network` or `SOURCE_LIBRARY_ALLOW_PUBLIC_REPLAY=1`.
- Added default no-network replay output so CI can validate manifest shape without public-site dependency.
- Added blocker taxonomy for:
  - operator gate skips
  - policy/platform-required skips
  - public network / anti-bot failures
  - parser / dirty-source failures
  - term-fallback relevance review
  - probe runtime exceptions

## Current Status

| Item | Status | Evidence |
| --- | --- | --- |
| `AT-AC-06` anti-bot / transport resilience | advanced, not globally closed | Replay script can classify public network and anti-bot blockers separately from code failures when opt-in public replay is run. |
| `AT-AC-10` real site-entry replay / dirty-source shortlist | advanced, not closed | The full historical 45-site manifest and skip-safe output exist. Public dirty-source replay still needs an explicit network-enabled run. |

Default gate result:

```text
target_count=45
enabled_target_count=40
policy_skipped_target_count=5
status_counts={"skipped_public_network_disabled": 45}
validation.passed=true
validation.full_historical_manifest=true
```

## Remaining Risk

- No public 45-site network run is claimed by this lane.
- Five platform/API-required historical targets are preserved in the manifest but skipped when public replay is enabled.
- `candidate_ready_with_term_fallback` remains review evidence only; it must not be treated as full dirty-source closure without relevance review.

## Validation

```bash
cd main/backend
.venv311/bin/python -m pytest -q \
  tests/unit/test_source_library_replay_scaleout_unittest.py \
  tests/unit/test_source_library_public_live_probe_gate_unittest.py
```

Result: `8 passed, 2 warnings`.
