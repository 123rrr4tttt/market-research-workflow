# Wave23 External-Blocked Decision

Date: 2026-05-23
Scope: `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-08-llm-crawler-unified-frontdoor`

## Result

`archive_external_blocked_candidate`

This topic is eligible for directory-level migration to `ARCHIVE_EXTERNAL_BLOCKED`.
Do not treat that as functional full closure: the real public browser/crawler replay
boundary remains open, but the current repo-local frontdoor/router/manifest/fixture
and shard gates are already sealed.

Repo-local blocker: none found in the current evidence set.

Remaining blocker: external public replay evidence. Full closure still requires a
real opt-in browser/crawler run that stores the high-JS public output artifact and
the broader 45-site shard outputs:

- `development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-22/output.public.json`
- `development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/output.public.json`
- all five `development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/output.public.shard-*.json`

Wave55 update: the five shard outputs have since been attached, and T5 produced
`output.public.t5.json` / `check.t5.json` for the high-JS lane. The remaining
blocker is no longer missing shard evidence or a totally absent high-JS replay;
it is the intrinsic external auth/anti-bot gates observed for X and Instagram.

## Evidence Readback

Topic-local markdown reviewed:

- `01_llm-crawler-unified-frontdoor-architecture-2026-03-08.md`
- `02_atomic-tasklist-llm-crawler-unified-frontdoor-2026-03-08.md`
- `03_a10-closure-and-validation-2026-03-08.md`
- `04_wave8-2-fetch-router-gap-closure-2026-05-22.md`
- `05_wave10-tri-state-router-contract-2026-05-22.md`
- `06_wave13-high-js-public-replay-readiness-2026-05-22.md`
- `07_wave15-high-js-replay-manifest-2026-05-22.md`
- `08_wave18-browser-replay-fixture-readback-2026-05-22.md`
- `09_wave19-public-replay-shards-readback-2026-05-22.md`

Index/audit readback:

- `CURRENT_DEV/INDEX.md` still lists this topic as `partial` with
  `wave8_verified`, `wave10_verified`, `wave13_checked`, `wave15_checked`,
  `wave18_checked`, `wave19_checked`, and `doc_aligned`.
- `STATUS_AUDIT_2026-04-07.md` records the same partial state and says the real
  public browser fleet replay is still not fully sealed.

Automation-run readback:

- `frontdoor-router-hardening/2026-05-22/README.md`: backend route intent,
  browser-render routing, and dashboard-safe status projection are covered; live
  browser-render success is out of scope.
- `crawler-provider-handoff/2026-05-22/README.md`: high-JS/browser handoff is
  deterministic and observable through source-library, terminal output,
  frontdoor ingress, and authority output; live public browser success is not
  claimed.
- `llm-crawler-high-js-public-replay/2026-05-22/manifest.json`: manifest and
  opt-in schema are valid, but the live public output path is deliberately
  absent.
- `llm-crawler-browser-replay-fixture/2026-05-22/check.json`: fixture gate
  passed with `repo_local_fixture_replay_complete=true`,
  `public_network_attempted=false`, `browser_runtime_started=false`,
  `real_public_high_js_replay_complete=false`, and
  `full_closure_allowed=false`.
- `crawler-public-replay-gate/2026-05-22/crawler_public_replay_gate_check.json`:
  deterministic 45-site artifacts are valid, while live public replay evidence
  is absent with `status=not_closed_missing_real_evidence`.
- `crawler-public-replay-shards/2026-05-22/check.json`: shard manifest/readback
  is valid, five shard outputs are missing as `external_blocked`, and
  `closure.overall_status=external_blocked`.

## Decision Rationale

The remaining work is not a repo-local implementation or documentation blocker.
The repo now has repeatable gates for:

- current frontdoor entry mapping and body-only persistence contract;
- high-JS route intent and tri-state router projection;
- crawler provider handoff for browser-render routes;
- high-JS public replay manifest and opt-in schema;
- repo-local browser decision fixture readback;
- 45-site public replay shard manifest/readback.

Every current gate deliberately refuses to claim full closure without public
network and browser runtime evidence. That boundary depends on public site
availability, anti-bot behavior, rate limits, platform/API policy skips, and a
controlled operator opt-in run. Therefore the directory can be treated as an
`ARCHIVE_EXTERNAL_BLOCKED` candidate rather than retained in `CURRENT_DEV` for a
repo-local blocker.

## Minimal Gate

Command run from repository root:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_crawler_public_replay_shards.py \
  --repo-root .
```

Result:

- exit code: `0`
- `status=shard_manifest_valid_public_outputs_external_blocked`
- `closure.overall_status=external_blocked`
- `closure.real_public_browser_fleet_replay_complete=false`
- `crawler_public_replay_gate.live_public_replay_status=not_closed_missing_real_evidence`
- `browser_replay_fixture_gate.status=fixture_replay_passed_public_replay_not_closed`
- `validation.passed=true`
- `validation.public_network_attempted=false`
- `validation.browser_runtime_started=false`
- `validation.shared_indexes_edited=false`

## Risk

- This is a topic-local decision only. Shared indexes, `README.md`, and
  `MERGED_OVERVIEW.md` were intentionally not changed.
- If a future controlled public replay produces valid `output.public.json` and
  shard outputs, this decision should be revisited because the blocker would no
  longer be external-missing evidence.
- Until the directory is actually moved and shared navigation is updated by a
  coordination lane, `CURRENT_DEV/INDEX.md` and `STATUS_AUDIT_2026-04-07.md`
  remain the current shared navigation truth.
