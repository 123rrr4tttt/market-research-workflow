# Wave19 Crawler Public Replay Shards

Date: 2026-05-22
Branch: `codex/devdocs-wave19-crawler-public-replay-shards`

## Purpose

This run splits the remaining real 45-site public replay boundary into five deterministic repo-local shards. It validates shard membership, readback, the existing Wave13 45-site public replay gate, and the Wave18 LLM crawler browser fixture without contacting public sites or starting a browser runtime.

## Artifacts

- `shard_manifest.json`: five 9-target shards in source manifest order.
- `shard_readback.json`: repo-local missing-output readback for the five shard outputs.
- `check.json`: checker output from `main/backend/scripts/check_crawler_public_replay_shards.py`.

## Current Result

`check.json` reports:

- `status=shard_manifest_valid_public_outputs_external_blocked`
- `shard_manifest.shard_count=5`
- `shard_manifest.target_count=45`
- `shard_manifest.enabled_public_target_count=40`
- `shard_manifest.policy_disabled_target_count=5`
- `shard_manifest.missing_public_output_count=5`
- `crawler_public_replay_gate.live_public_replay_status=not_closed_missing_real_evidence`
- `browser_replay_fixture_gate.status=fixture_replay_passed_public_replay_not_closed`
- `closure.overall_status=external_blocked`

## Boundary

The shard gate is deterministic and read-only. It does not run `--allow-public-network`, does not synthesize `output.public.json`, does not start a browser runtime, and does not edit shared navigation indexes.

Full closure still requires real opt-in public evidence:

- the full 45-site public replay output at `development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/output.public.json`;
- per-shard public output JSON for all five shard paths;
- proof that 40 enabled public targets were attempted and five platform/API-required targets were policy-skipped.

## Repeatable Commands

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_crawler_public_replay_shards.py \
  --repo-root . \
  --output development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/check.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_crawler_public_replay_shards_unittest.py
```
