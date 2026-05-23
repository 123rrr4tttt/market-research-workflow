# Wave20 Time Semantics Sample/Provenance Readback (2026-05-22)

Topic: Source Time Window.

Scope: repo-local deterministic readback gate for the remaining production data semantic chain boundary. This advances the chain by requiring a repeatable sample/provenance gate before any future live production evidence can be treated as closure evidence.

## Landed Slice

- New checker: `main/backend/scripts/check_time_semantics_sample_provenance_readback.py`
- New focused unit coverage: `main/backend/tests/unit/test_time_semantics_sample_provenance_readback_unittest.py`
- Automation evidence: `development/latest-dev-docs/automation-runs/wave20-time-semantics-sample-provenance-readback/2026-05-22/`

## Gate Result

- `contract_version=time-semantics.sample-provenance-readback.v1`
- `status=passed_with_known_gaps`
- `deterministic_sample_readback_gate=true`
- `provenance_readback_gate=true`
- `production_data_semantic_chain_live_verified=false`
- `closure_claim=false`

## Readback Evidence

- `source_time`: `2026-03-02T12:00:00Z`
- `processed_time`: `2026-03-10T12:00:00Z`
- `time_provenance`: `source_time`
- `document_effective_day`: `2026-03-02`
- `target_overlap_gap_90d`: `0.21666666666666667`
- `features_json_target_overlap_gap_90d`: `0.21666666666666667`
- `production_freshness_probe_not_run` remains present in captured live-gap markers.

## Remaining Open Production Chain

- `production_data_semantic_chain_live_validation_not_run`
- `live_source_time_coverage_distribution_not_measured`
- `live_decision_log_features_readback_not_verified`

This evidence does not use live production data, configured production services, public network replay, or production DB/API/UI readback. The production data semantic chain remains open.

## Protected Scope

This worker branch intentionally does not modify shared navigation indexes:

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`

## Repeatable Validation

```bash
/Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_time_semantics_sample_provenance_readback.py
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_time_semantics_sample_provenance_readback_unittest.py
```
