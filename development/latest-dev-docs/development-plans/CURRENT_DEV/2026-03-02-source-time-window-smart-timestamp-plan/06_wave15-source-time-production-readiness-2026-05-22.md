# Wave15 Source-Time Production Readiness (2026-05-22)

Scope: production readiness boundary for the source-time smart timestamp plan. This slice separates deterministic source-time correctness, decision-log provenance, and live production semantic-chain validation.

## Landed Slice

- Added `main/backend/scripts/check_source_time_production_readiness.py`.
- Added `main/backend/tests/unit/test_source_time_production_readiness_unittest.py`.
- The checker imports the existing Wave10 `check_time_semantics_ope_contract.py` and Wave12 `check_time_density_decision_log_contract.py` contracts instead of duplicating their fixtures.
- The default checker mode does not call live services or claim production closure. Optional `--live-evidence-json` can prove the production semantic chain when real evidence is supplied.

## Boundary Result

- `deterministic_source_time_contract`: `passed`
  - Proves `source_time -> effective_time` preference, source-time-anchored window bounds, and prompt-time-density effective-day usage.
- `decision_log_provenance`: `passed`
  - Proves policy decision traces and persisted `features_json` carry effective-time provenance, OPE freshness inputs, priority trace, and live-gap markers.
- `production_data_semantic_chain`: `ready_not_run`
  - The gate keeps live validation open until a production evidence JSON proves live query usage, configured services, effective-time distribution readback, source-time coverage measurement, decision-log row readback, decision-log features readback, and a nonzero semantic-chain sample count.
- `closure_claim=false`
- Default checker result: `status=passed_with_known_gaps`, `failures=[]`

## Local Stale/Drift Status

- `doc_stale`: reduced for the readiness boundary because the checker validates current Wave10 and Wave12 runtime contracts on each run.
- `doc_drift`: reduced for the source-time and decision-log slices because the new gate imports the underlying checker modules directly.
- `external_gap`: still open for live production semantic-chain validation.

## Remaining Live Gaps

- `production_data_semantic_chain_live_validation_not_run`
- `live_source_time_coverage_distribution_not_measured`
- `live_decision_log_features_readback_not_verified`

## Protected Scope

This worker branch intentionally does not modify shared navigation indexes:

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`

It also does not modify `main/backend/scripts/workflow_graph_smoke_local.py`.

## Repeatable Validation

```bash
python3 scripts/check_current_dev_wave15_plan.py
/Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_source_time_production_readiness.py
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_source_time_production_readiness_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 scripts/check_current_dev_status_evidence.py
git diff --check
```

Observed locally:

- `check_source_time_production_readiness.py`: `status=passed_with_known_gaps`, `deterministic_source_time_contract=passed`, `decision_log_provenance=passed`, `production_data_semantic_chain=ready_not_run`
- pytest: `3 passed`
