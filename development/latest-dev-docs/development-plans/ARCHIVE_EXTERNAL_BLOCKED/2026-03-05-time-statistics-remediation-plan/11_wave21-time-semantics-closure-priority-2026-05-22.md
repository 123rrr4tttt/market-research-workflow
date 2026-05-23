# Wave21 Time Semantics Closure Priority (2026-05-22)

Topic: Time Statistics.

## Decision

Decision: `external_blocked`, not `retained_partial`.

Wave20 deterministic sample/provenance readback covers the remaining repo-local time-statistics chain that can be closed without production data. The current checker-backed state is:

- `deterministic_source_time_contract=passed`
- `decision_log_provenance=passed`
- `deterministic_sample_readback_chain=passed`
- `production_data_semantic_chain=ready_not_run`
- `closure_claim=false`

The statistics remediation topic therefore no longer has an identified repo-local code blocker in this cluster. Its remaining partial state is caused by missing live production semantic-chain evidence.

## Remaining Blocker

The remaining blocker is external/live production evidence:

- `production_data_semantic_chain_live_validation_not_run`
- `live_source_time_coverage_distribution_not_measured`
- `live_decision_log_features_readback_not_verified`

This blocker also covers the older live-only expectations for prompt-time policy-decision-log volume, feedback alignment, production freshness, and release-pipeline enforcement. Those are not repo-local deterministic gaps.

## Migration Recommendation

- Keep the topic in `CURRENT_DEV` until live production evidence exists.
- Recommended shared-index label, for a supervisor/index lane only: `[partial][external_blocked][wave21_checked]`.
- Do not archive this topic while the production data semantic chain is unverified.
- Do not retain an unqualified `retained_partial` label for this cluster unless a future checker identifies a new repo-local code blocker.
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
