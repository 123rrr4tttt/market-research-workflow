# Wave27 Structured / Consumer Closure Decision Evidence

- status: `split_retained_and_external_blocked_candidate`
- structured topic: `2026-03-12-data-structured-service-modularization`
- consumer topic: `2026-03-14-consumer-side-modularization`
- contract_version: `wave27.structured_consumer_closure.v1`
- checker: `main/backend/scripts/check_wave27_structured_consumer_closure.py`

## Result

Wave27 adds a combined deterministic gate for the structured endpoint/query helpers and the consumer facade surfaces.

- The structured endpoint/query and SQL helper gates pass.
- The consumer facade, admin/dashboard, policy-state, and prompt-time-density gates pass.
- The consumer-side topic is archive-eligible because the remaining blocker is live DB/API smoke.
- The structured topic stays in `CURRENT_DEV` because no exported generic `DocumentQuery -> SQLAlchemy statement` builder exists under `main/backend/app/services/document_queries`.

Machine-readable output:

- [`structured_consumer_closure_decision.json`](./structured_consumer_closure_decision.json)

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_wave27_structured_consumer_closure.py \
  --output development/latest-dev-docs/automation-runs/wave27-structured-consumer-closure/2026-05-23/structured_consumer_closure_decision.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_wave27_structured_consumer_closure_unittest.py
```

Observed result: checker passed; pytest `2 passed`.
