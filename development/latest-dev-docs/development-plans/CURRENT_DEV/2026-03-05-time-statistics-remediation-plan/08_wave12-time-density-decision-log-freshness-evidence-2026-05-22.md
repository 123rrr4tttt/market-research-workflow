# Wave12 Time-Density Decision-Log Freshness Evidence (2026-05-22)

Scope: bounded decision-log/freshness contract for prompt-time-density statistics.

## Landed Slice

- `main/backend/app/services/stats/prompt_time_density.py` now writes a decision-log contract version into policy traces and persisted feature payloads.
- Decision-log payloads now record:
  - effective time provenance
  - OPE/freshness inputs, including `created_at` as the freshness timestamp field
  - priority decision trace fields for ranking and behavior-policy replay
  - live-data gap markers for pending feedback and local no-production-probe status
- `main/backend/scripts/check_time_density_decision_log_contract.py` verifies the deterministic contract without depending on live production data.
- `main/backend/tests/unit/test_prompt_time_density_decision_log_contract_unittest.py` locks the provenance, trace, OPE/freshness input, and persisted `features_json` shape.

## Local Stale/Drift Status

- `doc_stale`: reduced for local decision-log payload shape because the checker now verifies the freshness contract.
- `doc_drift`: reduced between stats implementation and OPE inputs because `features_json` now carries the fields consumed by OPE/freshness replay.
- `external_gap`: still open for live `prompt_time_policy_decision_logs` volume, live `prompt_time_window_feedback` alignment, and release-pipeline enforcement.

## Status Boundary

This advances the partial topic but does not close it. Production freshness remains unclaimed because this worker did not probe live data, did not validate decision-log volume, and did not wire the release pipeline to require the gate.

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
