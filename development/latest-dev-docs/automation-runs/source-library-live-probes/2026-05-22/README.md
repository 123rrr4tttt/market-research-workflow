# Source Library Public Live Probes - 2026-05-22

## Purpose

Wave3 G adds a skip-safe public live replay for the Wave2 source-library blocker. The probe is intentionally opt-in for public network access, records real public-site output when allowed, and keeps term-fallback output separate from full dirty-source closure evidence.

## Inputs

- [input.json](./input.json)
- [source_library_public_live_probes.py](../../../../../main/backend/scripts/source_library_public_live_probes.py)
- [test_source_library_public_live_probe_gate_unittest.py](../../../../../main/backend/tests/unit/test_source_library_public_live_probe_gate_unittest.py)

## Commands

Skip-safe gate, no public network:

```bash
cd main/backend
/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python scripts/source_library_public_live_probes.py \
  --target-file ../../development/latest-dev-docs/automation-runs/source-library-live-probes/2026-05-22/input.json \
  --output ../../development/latest-dev-docs/automation-runs/source-library-live-probes/2026-05-22/output.json \
  --log-output ../../development/latest-dev-docs/automation-runs/source-library-live-probes/2026-05-22/logs/live-probe.log
```

Public live replay:

```bash
cd main/backend
/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python scripts/source_library_public_live_probes.py \
  --target-file ../../development/latest-dev-docs/automation-runs/source-library-live-probes/2026-05-22/input.json \
  --output ../../development/latest-dev-docs/automation-runs/source-library-live-probes/2026-05-22/output.json \
  --log-output ../../development/latest-dev-docs/automation-runs/source-library-live-probes/2026-05-22/logs/live-probe.log \
  --probe-timeout 6 \
  --allow-public-network
```

## Output

- [output.json](./output.json)
- [logs/live-probe.log](./logs/live-probe.log)

Live run summary:

| Target | Status | Candidates | Notes |
| --- | --- | ---: | --- |
| `commercialobserver_parser_weak` | `candidate_ready_with_term_fallback` | 21 | Public fetch works and parser returns article cards, but query term selection required fallback. Keep as relevance review evidence. |
| `pymnts_parser_weak` | `candidate_ready` | 2 | Public fetch works and selected candidates matched without term fallback. |
| `investopedia_validated_query` | `candidate_ready` | 17 | Public baseline works and selected candidates matched without term fallback. |
| `hai_stanford_mixed_shell` | `candidate_ready_with_term_fallback` | 6 | Public fetch works, but selection required fallback against research/publication hubs. Keep as relevance review evidence. |

Status counts from the run:

```text
candidate_ready: 2
candidate_ready_with_term_fallback: 2
```

## Blocker / Closure Status

| Item | Status |
| --- | --- |
| `AT-AC-06` | Advanced: public live probe produced candidate-ready evidence with zero transport errors across the selected target set. |
| `AT-AC-10` | Partial: selected public replay now produces a dirty-source shortlist. `commercialobserver.com` and `hai.stanford.edu` remain `relevance_review` because selected candidates required term fallback. |

This artifact does not close the full historical 45-site `demo_proj` replay. It converts the public-network blocker into a controlled, repeatable gate plus a current four-target evidence snapshot.

## Validation

Focused skip/classification unit test:

```bash
cd main/backend
/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python -m pytest -q \
  tests/unit/test_source_library_public_live_probe_gate_unittest.py
```

Result: `4 passed, 2 warnings`.

Public live probe command:

Result: `passed`, `live_evidence_sufficient=true`, `skipped=false`.
