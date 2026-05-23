# Wave13 Worker 7 Crawler Public Replay Gate

Date: 2026-05-22
Branch: `codex/devdocs-wave13-crawler-public-replay-gate`
Scope: `2026-03-07-crawler-source-expansion`

## Decision

Live 45-site public replay remains not closed.

This lane adds a bounded checker and manifest that validate the current deterministic replay artifacts without contacting public sites. The checker explicitly keeps the live public replay at `not_closed_missing_real_evidence` unless a real `output.public.json` exists and proves a full opt-in run: 45 historical target results, 40 enabled public targets attempted, and five platform/API entries policy-skipped.

## Evidence

- [crawler-public-replay-gate/2026-05-22](../../../automation-runs/crawler-public-replay-gate/2026-05-22/README.md)
- [manifest.json](../../../automation-runs/crawler-public-replay-gate/2026-05-22/manifest.json)
- [check_crawler_public_replay_gate.py](../../../../../main/backend/scripts/check_crawler_public_replay_gate.py)
- [test_crawler_public_replay_gate_unittest.py](../../../../../main/backend/tests/unit/test_crawler_public_replay_gate_unittest.py)

## Gate Coverage

| Check | Expected |
| --- | --- |
| Historical manifest target count | `45` |
| Enabled public target count | `40` |
| Policy-disabled platform/API target count | `5` |
| No-network deterministic replay status | `skipped_public_network_disabled=45` |
| Deterministic public targets attempted | `0` |
| Stored A5 gate status | `deterministic_replay_gate_closed_external_public_replay_blocked` |
| Closure checker status | `external_blocked` |
| Live public replay status | `not_closed_missing_real_evidence` |

## Boundary

The checker is read-only with respect to public sites. It reads existing JSON artifacts, runs fresh deterministic check builders in-process, and writes only its own output when `--output` is supplied.

It does not:

- run `--allow-public-network`;
- create or synthesize `output.public.json`;
- count four-target public fixture evidence as the 45-site replay;
- edit shared navigation indexes.

## Repeatable Commands

From the repository root:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_crawler_public_replay_gate.py \
  --repo-root . \
  --output development/latest-dev-docs/automation-runs/crawler-public-replay-gate/2026-05-22/crawler_public_replay_gate_check.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_crawler_public_replay_gate_unittest.py
```

Expected current result: deterministic artifacts pass; live 45-site public replay remains `not_closed_missing_real_evidence`.
