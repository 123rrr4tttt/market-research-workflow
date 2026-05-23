# Wave10 Source-Time Window Contract Evidence (2026-05-22)

Scope: local deterministic closure slice for `source_time -> effective_time` and source-time-window anchoring.

## Landed Slice

- `main/backend/app/contracts/ingest_digestion.py` now makes `effective_time`, `time_confidence`, `time_provenance`, and `time_parse_version` explicit in ingest time semantics and normalized ingest envelopes.
- `main/backend/app/services/ingest/digestion_scaffold.py` now prefers trusted `source_time`, falls back to `processed_time`, rejects far-future source timestamps, and derives `task_window_start/end` from `effective_time`.
- `main/backend/app/services/stats/prompt_time_density.py` now resolves document effective days in this order:
  1. `extracted_data.effective_time`
  2. `extracted_data.source_time`
  3. `extracted_data.policy.effective_date`
  4. `publish_date`
  5. `created_at`
- `main/backend/app/services/document_queries/policy_filters.py` now includes explicit `effective_time` and `source_time` in `policy_time_expr()`.

## Status Boundary

This closes the warehouse-local deterministic contract for source-time preference and time-window anchoring. It does not claim historical backfill completion, live ingest coverage, or production source-time quality verification.

Known remaining gaps:

- live historical document backfill not run in this worker branch
- source-time coverage dashboard not validated against production data
- production timestamp extraction precision not measured here

## Repeatable Validation

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  tests/unit/test_ingest_digestion_scaffold_unittest.py \
  tests/unit/test_document_queries_policy_filters_unittest.py
```

Observed locally:

- `16 passed`

Combined Wave10 checker:

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 scripts/check_time_semantics_ope_contract.py
```

Observed locally:

- `status=passed_with_known_gaps`
- `source_time_window.effective_time_uses_source_time=true`
- `source_time_window.window_bounds_anchor_to_effective_time=true`
- `source_time_window.density_day_uses_source_time=true`
