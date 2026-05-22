# Wave19 Public Replay Shards

Date: 2026-05-22
Branch: `codex/devdocs-wave19-crawler-public-replay-shards`
Scope: `2026-03-07-crawler-source-expansion`

## Status

`external_blocked`

Wave19 adds a deterministic shard boundary for the remaining 45-site public replay. The historical replay manifest is split into five source-order shards of nine targets each, with aggregate counts preserved at 45 historical targets, 40 enabled public targets, and five policy-disabled platform/API targets.

The shard gate passes repo-local validation, but real public output remains absent. This keeps A5 public replay externally blocked instead of closed.

## Evidence

- [crawler-public-replay-shards/2026-05-22](../../../automation-runs/crawler-public-replay-shards/2026-05-22/README.md)
- [shard_manifest.json](../../../automation-runs/crawler-public-replay-shards/2026-05-22/shard_manifest.json)
- [shard_readback.json](../../../automation-runs/crawler-public-replay-shards/2026-05-22/shard_readback.json)
- [check.json](../../../automation-runs/crawler-public-replay-shards/2026-05-22/check.json)
- [check_crawler_public_replay_shards.py](../../../../../main/backend/scripts/check_crawler_public_replay_shards.py)
- [test_crawler_public_replay_shards_unittest.py](../../../../../main/backend/tests/unit/test_crawler_public_replay_shards_unittest.py)

## Shard Readback

| Shard | Targets | Enabled | Policy-disabled | Public output status |
| --- | ---: | ---: | ---: | --- |
| `crawler_public_replay_shard_01` | 9 | 8 | 1 | `external_blocked` |
| `crawler_public_replay_shard_02` | 9 | 8 | 1 | `external_blocked` |
| `crawler_public_replay_shard_03` | 9 | 7 | 2 | `external_blocked` |
| `crawler_public_replay_shard_04` | 9 | 8 | 1 | `external_blocked` |
| `crawler_public_replay_shard_05` | 9 | 9 | 0 | `external_blocked` |

The checker also reuses the Wave13 public replay gate and confirms:

- `crawler_public_replay_gate.live_public_replay_status=not_closed_missing_real_evidence`
- `crawler_public_replay_gate.public_network_attempted=false`
- `closure.overall_status=external_blocked`

## Boundary

This slice does not run public network replay, create `output.public.json`, or synthesize per-shard public output. It only proves the shard manifest/readback contract and records each missing shard output as `external_blocked`.

Full closure still requires a real opt-in public replay that stores the full 45-site output and all five shard output JSON files with 40 enabled targets attempted and five platform/API targets policy-skipped.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_crawler_public_replay_shards.py \
  --repo-root . \
  --output development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/check.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_crawler_public_replay_shards_unittest.py
```
