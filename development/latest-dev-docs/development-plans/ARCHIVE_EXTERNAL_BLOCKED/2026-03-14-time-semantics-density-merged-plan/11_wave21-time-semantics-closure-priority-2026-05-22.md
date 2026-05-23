# Wave21 Time Semantics Closure Priority (2026-05-22)

Topic: Time Semantics Density.

## Decision

Decision: `external_blocked`, not `retained_partial`.

This merged topic is the cluster-level closure-priority anchor for:

- `2026-03-02-source-time-window-smart-timestamp-plan`
- `2026-03-05-time-statistics-remediation-plan`
- `2026-03-14-time-semantics-density-merged-plan`

Wave20 deterministic sample/provenance readback closes the remaining repo-local sample chain. The checker-backed boundary is:

- `deterministic_source_time_contract=passed`
- `decision_log_provenance=passed`
- `deterministic_sample_readback_chain=passed`
- `production_data_semantic_chain=ready_not_run`
- `production_data_semantic_chain_live_verified=false`
- `closure_claim=false`

The cluster can be marked as externally blocked for production data semantic-chain proof. It cannot be archived as closed yet.

## Remaining Blocker

Only the production data semantic chain remains:

- `production_data_semantic_chain_live_validation_not_run`
- `live_source_time_coverage_distribution_not_measured`
- `live_decision_log_features_readback_not_verified`

No additional repo-local code blocker was found after Wave20. The unresolved work requires live production data, configured services, decision-log readback, and source-time coverage distribution evidence.

## Migration Recommendation

- Keep all three topics in `CURRENT_DEV` until live production evidence exists.
- Recommended shared-index label, for a supervisor/index lane only: `[partial][external_blocked][wave21_checked]`.
- If a later live evidence JSON passes `check_source_time_production_readiness.py --live-evidence-json <production-evidence.json>`, the cluster can be re-evaluated for archive migration.
- Until then, do not move these topics to `ARCHIVE_CLOSED`; use `external_blocked` rather than `retained_partial` for the time-semantics cluster.
- No shared navigation index is changed in this branch.

## Validation Commands

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_time_semantics_sample_provenance_readback_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_time_semantics_sample_provenance_readback.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_source_time_production_readiness.py
git diff --check
```

Optional future live-evidence gate:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_source_time_production_readiness.py --live-evidence-json <production-evidence.json>
```
