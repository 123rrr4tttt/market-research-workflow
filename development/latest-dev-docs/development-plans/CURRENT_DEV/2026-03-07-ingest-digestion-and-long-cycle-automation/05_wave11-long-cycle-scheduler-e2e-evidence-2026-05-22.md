# Wave11 Long-Cycle Scheduler E2E Contract Evidence

Date: 2026-05-22 PST
Branch: `codex/devdocs-wave11-long-cycle-scheduler-e2e`
Status: `closed deterministic scheduler E2E contract / still partial topic`

## Status Check

This lane advances the Wave9 lifecycle contract without claiming a production scheduler run.

Wave9 proved stable task keys, persistent-task record shape, and an in-memory lifecycle transition. Wave11 adds the next deterministic contract slice:

- scheduler dispatch intent with stable task/window/idempotency fields;
- contract-only dispatch payload that explicitly keeps `live_dispatch=false`;
- fake repository writes against a logical DB table boundary;
- readback-proven lifecycle progression through `ready -> running -> succeeded`.

The topic must remain in `CURRENT_DEV`: no Celery beat, cron scheduler, production worker, migration, or live persistent-task DB row was executed in this branch.

## Code Facts

| Surface | Current repo fact | Evidence |
| --- | --- | --- |
| Scheduler intent contracts | Added `LongCycleSchedulerDispatchIntent`, `LongCyclePersistenceWriteResult`, and `LongCycleSchedulerE2EContractCheck`. | [ingest_digestion.py](../../../../../main/backend/app/contracts/ingest_digestion.py) |
| Dispatch intent builder | Added `build_long_cycle_scheduler_dispatch_intent()` with selected-window and ready-record preconditions. | [digestion_scaffold.py](../../../../../main/backend/app/services/ingest/digestion_scaffold.py) |
| Fake DB repository boundary | Added `InMemoryLongCycleTaskRepository` with logical-table upsert results and readback. | [digestion_scaffold.py](../../../../../main/backend/app/services/ingest/digestion_scaffold.py) |
| Scheduler E2E contract gate | Added `check_long_cycle_scheduler_e2e_contract()` and a script-level deterministic gate. | [check_ingest_long_cycle_scheduler_e2e_contract.py](../../../../../main/backend/scripts/check_ingest_long_cycle_scheduler_e2e_contract.py) |
| Unit coverage | Extended the ingestion scaffold tests to assert dispatch intent, fake repository writes, and readback status progression. | [test_ingest_digestion_scaffold_unittest.py](../../../../../main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py) |

## Checker Semantics

`check_long_cycle_scheduler_e2e_contract()` returns contract version `ingest.long_cycle_scheduler_e2e_contract_check.v1`.

The narrow gate passes when:

- the existing lifecycle contract passes;
- the persistent task is `ready` and has a selected window;
- dispatch intent records `task_key`, `selected_window`, `cadence`, `queue_name`, `worker_task_name`, and an idempotency key;
- dispatch intent remains contract-only with `live_dispatch=false`;
- the fake repository records three logical table writes with statuses `ready`, `running`, and `succeeded`;
- readback returns the final `succeeded` persistent-task record.

The fake repository writes to logical table `long_cycle_persistent_tasks` with `live_db_write=false`. This proves the DB-write abstraction and payload shape only; it does not prove a real table, migration, or live transaction.

## Remaining Boundaries

These gaps are intentionally still open:

- `live_scheduler_dispatch_not_executed`: no Celery beat, cron, or long-cycle scheduler was started.
- `live_persistent_task_table_write_not_executed`: no live database row was inserted, updated, or migrated for this long-cycle task.
- `production_worker_task_not_executed`: no production worker consumed the dispatch intent.
- `end_to_end_automation_run_not_executed`: no real recurring run proved selected window -> scheduler -> worker -> persisted digestion output -> downstream handoff.

This means the topic status should remain `partial`; the closed slice is the deterministic scheduler/persistent-task/DB-write contract, not the production automation runtime.

## Validation

Commands run from this worktree:

```bash
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py
PYTHONPATH=main/backend python3 main/backend/scripts/check_ingest_long_cycle_lifecycle_contract.py
PYTHONPATH=main/backend python3 main/backend/scripts/check_ingest_long_cycle_scheduler_e2e_contract.py
python3 -m py_compile main/backend/app/contracts/ingest_digestion.py main/backend/app/services/ingest/digestion_scaffold.py main/backend/scripts/check_ingest_long_cycle_lifecycle_contract.py main/backend/scripts/check_ingest_long_cycle_scheduler_e2e_contract.py
python3 scripts/check_current_dev_wave11_plan.py
git diff --check
```

Observed result:

- `16 passed`
- lifecycle checker output: `status=pass`, `contract_status=closed_narrow_lifecycle_contract`
- scheduler E2E checker output: `status=pass`, `contract_status=closed_narrow_scheduler_e2e_contract`
- `py_compile` passed
- Wave11 plan gate passed
- `git diff --check` passed
