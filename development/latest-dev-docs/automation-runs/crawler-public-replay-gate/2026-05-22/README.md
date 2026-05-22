# Crawler Public Replay Gate - 2026-05-22

## Purpose

Wave13 worker 7 adds a bounded, no-network checker for the remaining crawler source expansion blocker: the external 45-site public replay.

The gate validates repository-owned deterministic artifacts and keeps the live public replay open unless a real `output.public.json` is present and proves an opt-in full-manifest run.

## Inputs

- [manifest.json](./manifest.json)
- [source-library-replay-scaleout input](../../source-library-replay-scaleout/2026-05-22/input.json)
- [source-library-replay-scaleout deterministic output](../../source-library-replay-scaleout/2026-05-22/output.json)
- [Wave8 A5 gate output](../../crawler-source-expansion-wave8-a7-validation-pack/2026-05-22/a5_public_replay_gate_check.json)
- [Wave8 closure output](../../crawler-source-expansion-wave8-a7-validation-pack/2026-05-22/crawler_source_expansion_closure_check.json)

## Expected Result

| Field | Expected |
| --- | --- |
| deterministic manifest targets | `45` |
| enabled public targets | `40` |
| policy-disabled platform/API targets | `5` |
| deterministic `public_targets_attempted` | `0` |
| live public replay status | `not_closed_missing_real_evidence` |
| public network attempted by checker | `false` |

## Command

From the repository root:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_crawler_public_replay_gate.py \
  --repo-root . \
  --output development/latest-dev-docs/automation-runs/crawler-public-replay-gate/2026-05-22/crawler_public_replay_gate_check.json
```

## Boundary

This gate does not run `--allow-public-network`, does not create `output.public.json`, and does not edit shared navigation indexes. A future live replay can only move out of `not_closed_missing_real_evidence` if it stores real full-manifest evidence with 40 enabled targets attempted and five platform/API entries policy-skipped.
