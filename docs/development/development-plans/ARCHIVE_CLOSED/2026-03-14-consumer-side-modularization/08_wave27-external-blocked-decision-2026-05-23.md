# Wave27 Consumer-Side External-Blocked Decision (2026-05-23)

## Status

- Topic: `2026-03-14-consumer-side-modularization`
- Decision: `external_blocked`
- Gate: `main/backend/scripts/check_wave27_structured_consumer_closure.py`

Wave27 moves this topic out of `CURRENT_DEV` because the repo-local consumer facade/query gates now pass and the remaining blocker is live DB/API smoke.

## Repo-Local Evidence

The combined gate validates these consumer surfaces:

1. `consumer_side_facade_contract`
2. `consumer_sql_predicate_facade`
3. `admin_dashboard_consumer_boundary`
4. `policy_state_document_query_boundary`
5. `prompt_time_density_consumer_boundary`

It also confirms the paired endpoint projection gates pass for `/api/v1/search` and `project.structured_data.search`. The structured-service topic stays in `CURRENT_DEV` because its generic DB statement-builder scope remains repo-local.

## External Blocker

```text
live_db_api_smoke_not_run
```

Focused gates are deterministic and do not start a live tenant DB/API stack. Reopening this topic requires live DB/API smoke evidence against the target runtime.

## Evidence

- [automation-runs/wave27-structured-consumer-closure/2026-05-23/README.md](../../../automation-runs/wave27-structured-consumer-closure/2026-05-23/README.md)
- [automation-runs/wave27-structured-consumer-closure/2026-05-23/structured_consumer_closure_decision.json](../../../automation-runs/wave27-structured-consumer-closure/2026-05-23/structured_consumer_closure_decision.json)

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_wave27_structured_consumer_closure.py

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_wave27_structured_consumer_closure_unittest.py
```

Observed result: checker passed; pytest `2 passed`.
