# Source Library Replay Scaleout - 2026-05-22

## Purpose

Wave4 F expands the Wave3 four-target public probe into a full historical `demo_proj` 45-site `handler.cluster.search_template` replay manifest. Public network execution remains opt-in; the default gate validates the full manifest and writes replay output without contacting public sites.

Wave47 adds the real opt-in public replay artifact required by crawler source expansion closure. The default no-network output remains the CI-safe artifact; `output.public.json` is the controlled public-network evidence.

## Inputs

- [input.json](./input.json)
- [source_library_replay_scaleout.py](../../../../../main/backend/scripts/source_library_replay_scaleout.py)
- [test_source_library_replay_scaleout_unittest.py](../../../../../main/backend/tests/unit/test_source_library_replay_scaleout_unittest.py)

Manifest summary:

| Item | Count |
| --- | ---: |
| Historical `search_template` targets | 45 |
| Enabled public replay targets | 40 |
| Policy-disabled platform/API targets | 5 |

## Commands

Skip-safe gate, no public network:

```bash
cd main/backend
.venv311/bin/python scripts/source_library_replay_scaleout.py \
  --manifest-output ../../development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/input.json \
  --output ../../development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/output.json \
  --log-output ../../development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/logs/replay.log
```

Public replay is explicit opt-in:

```bash
cd main/backend
.venv311/bin/python scripts/source_library_replay_scaleout.py \
  --manifest ../../development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/input.json \
  --output ../../development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/output.public.json \
  --log-output ../../development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/logs/output.public.log \
  --probe-timeout 6 \
  --allow-public-network
```

## Output

- [output.json](./output.json)
- [output.public.json](./output.public.json)
- [logs/replay.log](./logs/replay.log)
- [logs/output.public.log](./logs/output.public.log)

Default gate summary:

| Field | Value |
| --- | --- |
| `validation.passed` | `true` |
| `validation.skipped` | `true` |
| `validation.full_historical_manifest` | `true` |
| `outputs.status_counts` | `{"skipped_public_network_disabled": 45}` |
| `outputs.public_targets_attempted` | `0` |

## Blocker / Closure Status

| Item | Status |
| --- | --- |
| `AT-AC-06` | Advanced: full public replay gate now separates public-network/anti-bot blockers from probe runtime exceptions when opt-in replay is run. Default CI-safe run remains no-network. |
| `AT-AC-10` | Closed for crawler source expansion: the historical 45-site set is represented by deterministic artifacts and the Wave47 `output.public.json` opt-in public replay. Dirty-source promotion still requires downstream relevance review. |

Term-fallback candidates are emitted under `outputs.term_fallback_relevance_review` during public replay and must be reviewed before they count as dirty-source closure.

Wave47 public replay summary:

| Field | Value |
| --- | --- |
| `validation.passed` | `true` |
| `validation.skipped` | `false` |
| `validation.full_historical_manifest` | `true` |
| `outputs.public_targets_attempted` | `40` |
| `skipped_policy_disabled_platform_entry` | `5` |
| `skipped_public_network_disabled` | `0` |

## Validation

```bash
cd main/backend
.venv311/bin/python -m pytest -q \
  tests/unit/test_source_library_replay_scaleout_unittest.py \
  tests/unit/test_source_library_public_live_probe_gate_unittest.py
```

Result: `8 passed, 2 warnings`.
