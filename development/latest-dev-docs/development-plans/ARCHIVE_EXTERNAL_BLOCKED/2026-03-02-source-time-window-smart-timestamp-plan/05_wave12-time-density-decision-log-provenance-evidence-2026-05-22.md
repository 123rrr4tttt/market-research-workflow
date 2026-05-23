# Wave12 Time-Density Decision-Log Provenance Evidence (2026-05-22)

Scope: bounded source-time provenance slice for prompt-time-density decision logs.

## Landed Slice

- `main/backend/app/services/stats/prompt_time_density.py` now exposes `resolve_document_effective_time_provenance()`.
- Prompt-time-density rows now carry an `effective_time_provenance` summary with:
  - effective timestamp source counts
  - timestamp gap counts
  - parse-version markers
  - the deterministic fallback chain used by density stats
- Priority rows propagate that provenance into the policy decision trace and persisted `features_json` payload shape.

## Local Stale/Drift Status

- `doc_stale`: reduced for the decision-log provenance slice because runtime stats now emit an explicit source-time summary instead of relying only on prose evidence.
- `doc_drift`: reduced for the stats/log boundary because the checker verifies that provenance is present in the deterministic decision-log payload.
- `external_gap`: still open for live historical backfill and production source-time quality measurement.

## Status Boundary

This is not a full source-time closure claim. It does not verify production coverage, historical backfill, or source timestamp extraction precision. It only records the deterministic provenance required by the decision-log contract.

## Repeatable Validation

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 scripts/check_time_density_decision_log_contract.py
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  tests/unit/test_prompt_time_density_decision_log_contract_unittest.py \
  tests/unit/test_prompt_time_density_priority_unittest.py \
  tests/unit/test_document_queries_policy_filters_unittest.py
```

Observed locally:

- checker: `status=passed_with_known_gaps`, `failures=[]`
- pytest group: `10 passed`
