# Wave21 Time Semantics Closure Priority (2026-05-22)

Topic: Source Time Window.

## Decision

Decision: `external_blocked`, not `retained_partial`.

Wave20 deterministic sample/provenance readback leaves no repo-local code blocker for this topic. The local chain is checker-backed:

- `deterministic_source_time_contract=passed`
- `decision_log_provenance=passed`
- `deterministic_sample_readback_chain=passed`
- `production_data_semantic_chain=ready_not_run`
- `closure_claim=false`

This means the topic can be reduced from an unqualified partial to an external/live-production blocked state. It should not claim full closure because production data semantic-chain evidence has not been supplied.

## Remaining Blocker

The remaining blocker is the production data semantic chain, not missing repository code:

- `production_data_semantic_chain_live_validation_not_run`
- `live_source_time_coverage_distribution_not_measured`
- `live_decision_log_features_readback_not_verified`

Inherited live-only boundaries remain covered by the same blocker: production freshness proof, live policy-decision-log volume, live feedback alignment, and configured production service readback.

## Migration Recommendation

- Keep the topic in `CURRENT_DEV` until live production evidence exists.
- Recommended shared-index label, for a supervisor/index lane only: `[partial][external_blocked][wave21_checked]`.
- Do not move this topic to `ARCHIVE_CLOSED` until a real production evidence JSON proves live query usage, configured services, source-time coverage distribution, decision-log row readback, decision-log features readback, and at least one semantic-chain sample.
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
