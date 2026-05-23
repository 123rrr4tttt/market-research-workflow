# Wave8-1 A7 Validation Pack

Date: 2026-05-22
Branch: `codex/devdocs-wave8-crawler-external-closure`

## Result

Status: A7 validation/documentation evidence closed; A5 remains `blocked_external`; overall topic status is expected to be `external_blocked`.

This run stores repeatable outputs for the crawler source-expansion closure boundary without claiming a real public 45-site replay. The public replay output remains absent by design, and the A5 checker records `external_public_network_or_site_stability`.

## Inputs

- Topic evidence document: [2026-05-22-wave8-a7-validation-pack.md](../../../../../docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-crawler-source-expansion/2026-05-22-wave8-a7-validation-pack.md)
- Closure checker: [check_crawler_source_expansion_closure.py](../../../../../main/backend/scripts/check_crawler_source_expansion_closure.py)
- A5 gate checker: [check_source_library_public_replay_a5_gate.py](../../../../../main/backend/scripts/check_source_library_public_replay_a5_gate.py)

## Outputs

- [crawler_source_expansion_closure_check.json](./crawler_source_expansion_closure_check.json)
- [a5_public_replay_gate_check.json](./a5_public_replay_gate_check.json)

Expected output contract:

| Output | Expected |
| --- | --- |
| closure checker `validation.passed` | `true` |
| closure checker `overall_status` | `external_blocked` |
| A5 task status | `blocked_external` |
| A7 task status | `closed` |
| A5 gate `validation.public_network_attempted` | `false` |
| A5 gate `external_blocker.blocker_type` | `external_public_network_or_site_stability` |

## Commands

From the repository root:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_source_library_public_replay_a5_gate.py \
  --repo-root . \
  --output development/latest-dev-docs/automation-runs/crawler-source-expansion-wave8-a7-validation-pack/2026-05-22/a5_public_replay_gate_check.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_crawler_source_expansion_closure.py \
  --repo-root . \
  --output development/latest-dev-docs/automation-runs/crawler-source-expansion-wave8-a7-validation-pack/2026-05-22/crawler_source_expansion_closure_check.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_crawler_source_expansion_closure_check_unittest.py \
  main/backend/tests/unit/test_source_library_public_replay_a5_gate_unittest.py

git diff --check
```

## Boundary

This pack validates repository-owned closure evidence only. It does not run `--allow-public-network`, does not create `output.public.json`, and does not edit shared navigation indexes.
