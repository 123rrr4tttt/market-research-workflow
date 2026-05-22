# Wave12 Time-Density Decision-Log Contract Evidence (2026-05-22)

Scope: bounded merged-plan slice for the live decision-log/production freshness gap left after Wave10/Wave11 deterministic gates.

## Landed Slice

- Contract version: `time-density-decision-log-freshness-contract.v1`
- Stats implementation now records the contract in prompt-time-density priority traces and persisted `features_json`.
- The contract covers:
  - effective time provenance
  - OPE/freshness replay inputs
  - priority decision trace and ranking context
  - live-data gap markers
- New checker: `main/backend/scripts/check_time_density_decision_log_contract.py`
- New focused unit coverage: `main/backend/tests/unit/test_prompt_time_density_decision_log_contract_unittest.py`

## Local Stale/Drift Status

- `doc_stale`: reduced for the decision-log contract slice because the runtime payload is now checker-backed.
- `doc_drift`: reduced for merged time-semantics/density docs because the source-time and OPE freshness fields meet in one deterministic payload contract.
- `external_gap`: remains open for live production volume, feedback reward alignment, production freshness proof, and release-pipeline wiring.

## Status Boundary

This is a bounded local contract, not a full closure. It intentionally reports `passed_with_known_gaps` and keeps production freshness open until a live-data worker validates decision-log volume and feedback alignment.

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
