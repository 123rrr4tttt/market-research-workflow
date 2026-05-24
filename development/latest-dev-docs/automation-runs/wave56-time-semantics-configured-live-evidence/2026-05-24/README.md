# Wave56 Time Semantics Configured Live Evidence

Date: 2026-05-24

Scope: configured DB semantic-chain readback for `2026-03-14-time-semantics-density-merged-plan`.

## Artifacts

- `time_semantics_configured_live_evidence.json`
- `time_semantics_release_gate_configured_evidence.json`
- `time_semantics_release_gate_strict_closure.json`

## Evidence Result

- `contract_version=time-semantics.configured-semantic-chain-evidence.v1`
- `evidence_tier=production_like`
- `data_source=configured_db_production_like_sample`
- `production_data_semantic_chain_verified=true`
- `decision_log_row_count=3`
- `feedback_row_count=3`
- `source_time_coverage=1.0`
- `cleanup_performed=true`

## Gate Readback

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_time_semantics_release_gate.py \
  --live-evidence-json development/latest-dev-docs/automation-runs/wave56-time-semantics-configured-live-evidence/2026-05-24/time_semantics_configured_live_evidence.json \
  --json
```

Result:

- `status=passed_with_configured_evidence`
- `configured_semantic_chain_evidence_verified=true`
- `production_data_semantic_chain_live_verified=false`
- `full_closure_allowed=false`

Strict production/live closure still fails with this production-like artifact:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_time_semantics_release_gate.py \
  --strict-closure \
  --live-evidence-json development/latest-dev-docs/automation-runs/wave56-time-semantics-configured-live-evidence/2026-05-24/time_semantics_configured_live_evidence.json \
  --json
```

Result:

- `status=failed`
- `failures=["production_data_semantic_chain_live_required"]`
