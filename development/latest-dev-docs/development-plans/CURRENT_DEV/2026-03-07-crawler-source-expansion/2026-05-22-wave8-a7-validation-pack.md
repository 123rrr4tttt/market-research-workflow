# Wave8-1 A7 Validation Pack

Date: 2026-05-22
Branch: `codex/devdocs-wave8-crawler-external-closure`
Scope: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-crawler-source-expansion/`

## A7 Validation Pack

A7 is closed as a validation/documentation pack, not as full topic archival.

The pack makes the current crawler source-expansion boundary repeatable:

- A1-A4 and A6 have local code, policy, handoff, and test evidence.
- A5 remains `blocked_external` because a real 45-site public replay depends on public site availability, anti-bot behavior, rate limits, and parser volatility.
- A7 records the validation commands and stored outputs that prove the topic is no longer plain `not_closed`.
- Shared indexes stay untouched in this lane.

## Evidence Pack

Stored run directory:

- [crawler-source-expansion-wave8-a7-validation-pack/2026-05-22](../../../automation-runs/crawler-source-expansion-wave8-a7-validation-pack/2026-05-22/README.md)

Stored outputs:

- [crawler_source_expansion_closure_check.json](../../../automation-runs/crawler-source-expansion-wave8-a7-validation-pack/2026-05-22/crawler_source_expansion_closure_check.json)
- [a5_public_replay_gate_check.json](../../../automation-runs/crawler-source-expansion-wave8-a7-validation-pack/2026-05-22/a5_public_replay_gate_check.json)

Executable anchors:

- [check_crawler_source_expansion_closure.py](../../../../../main/backend/scripts/check_crawler_source_expansion_closure.py): task-level closure checker and overall status classifier.
- [check_source_library_public_replay_a5_gate.py](../../../../../main/backend/scripts/check_source_library_public_replay_a5_gate.py): deterministic A5 gate and external blocker recorder.
- [test_crawler_source_expansion_closure_check_unittest.py](../../../../../main/backend/tests/unit/test_crawler_source_expansion_closure_check_unittest.py): closure semantics and protected-index boundary.
- [test_source_library_public_replay_a5_gate_unittest.py](../../../../../main/backend/tests/unit/test_source_library_public_replay_a5_gate_unittest.py): no-network replay fixture and term-fallback review boundary.
- [test_clue_chain_source_library_expansion_unittest.py](../../../../../main/backend/tests/unit/test_clue_chain_source_library_expansion_unittest.py): deterministic clue-chain source expansion fixture replay.

## External Blocker Boundary

The validation pack does not fabricate a public 45-site replay result.

`output.public.json` is intentionally absent from `development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/`. The deterministic A5 gate checks the embedded 45-site manifest and stored no-network replay output, then records the missing public replay as `external_public_network_or_site_stability`.

This preserves the distinction between:

- repository-controlled evidence: manifest shape, replay skip safety, policy-disabled targets, public-live fixture classification, and checker behavior;
- external evidence: live public replay success across 45 sites under unstable network and website conditions.

## Overall Status

Expected checker state after this pack:

| Field | Expected |
| --- | --- |
| `validation.passed` | `true` |
| `overall_status` | `external_blocked` |
| A1 | `closed` |
| A2 | `closed` |
| A3 | `closed` |
| A4 | `closed` |
| A5 | `blocked_external` |
| A6 | `closed` |
| A7 | `closed` |

The topic should remain under `CURRENT_DEV` until a later integration lane decides how to represent externally blocked topics in shared navigation.

## Repeatable Commands

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

## Shared Index Boundary

The following shared navigation files are intentionally not edited by Wave8-1:

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`
