# Wave22 Archive External Blocked Decision

Date: 2026-05-22 PST
Scope: `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-07-crawler-source-expansion`

## Result

Decision: this topic is eligible to move from `CURRENT_DEV` to `ARCHIVE_EXTERNAL_BLOCKED`.

No repo-local blocker remains in the current checker set. The current repository-owned gates validate successfully and classify the remaining gap as external: a real opt-in 45-site public replay has not been stored.

The actual folder move is intentionally not performed in this Wave22 decision note because shared navigation updates are out of scope for this lane.

## Evidence Readback

| Evidence area | Current readback |
| --- | --- |
| A5 45-site replay gate | deterministic artifacts valid; live public replay status is `not_closed_missing_real_evidence`; `output.public.json` is absent |
| Wave19 public replay shards | five shards, 45 historical targets, 40 enabled public targets, five policy-disabled targets; all five public shard outputs remain `external_blocked` |
| Crawler provider handoff | provider handoff contract checker passes; terminal and authority summary preserve `provider_status=queued` |
| Topic closure checker | validation passes with `overall_status=external_blocked`; A1-A4, A6, and A7 are closed; A5 is `blocked_external` |

The absent required live artifact is:

```text
development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/output.public.json
```

## Validation

Commands run from `/Users/wangyiliang/market-research-workflow` unless noted:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_crawler_public_replay_gate.py \
  --repo-root . \
  --output /tmp/wave22-crawler-public-replay-gate-check.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_crawler_public_replay_shards.py \
  --repo-root . \
  --output /tmp/wave22-crawler-public-replay-shards-check.json

PYTHONPATH=. /Users/wangyiliang/.local/bin/python3.11 \
  scripts/check_crawler_provider_handoff_contract.py \
  --output /tmp/wave22-provider-handoff-check.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_crawler_source_expansion_closure.py \
  --repo-root . \
  --output /tmp/wave22-crawler-source-expansion-closure-check.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_crawler_public_replay_gate_unittest.py \
  main/backend/tests/unit/test_crawler_public_replay_shards_unittest.py \
  main/backend/tests/unit/test_crawler_source_expansion_closure_check_unittest.py
```

Validation status:

- `check_crawler_public_replay_gate.py`: passed deterministic gate; public replay evidence absent.
- `check_crawler_public_replay_shards.py`: `status=shard_manifest_valid_public_outputs_external_blocked`; `closure.overall_status=external_blocked`.
- `check_crawler_provider_handoff_contract.py`: `status=passed`.
- `check_crawler_source_expansion_closure.py`: `validation.passed=true`; `overall_status=external_blocked`.
- Focused pytest: `9 passed, 2 warnings`.

## Risk

The migration is classification-only. It must not be represented as full crawler public-source closure until a future controlled network window stores real 45-site replay evidence with 40 enabled public targets attempted and five platform/API-required targets policy-skipped.

Shared index updates still need to be done in a separate navigation lane if the directory is physically moved.
