# Wave9-6 Ingest Long-Cycle Lifecycle Contract Evidence

Date: 2026-05-22 PST
Branch: `codex/devdocs-wave9-ingest-long-cycle-automation`
Status: `closed narrow lifecycle contract / still partial topic`

## Status Check

This lane advances the Wave7 pre-dispatch contract without claiming the full topic is closed.

Wave7 proved that `check_long_cycle_automation_status()` can normalize an ingest input, select a digestion decision, and report whether a long-cycle task is ready before dispatch. This Wave9 lane adds the next deterministic slice:

- stable persistent-task key derivation for a long-cycle ingest task;
- persistent task record shape with scheduler/persistence references;
- in-memory lifecycle events for `ready -> running -> succeeded`;
- dispatch precondition that a selected window must be present before lifecycle dispatch.

The topic must remain in `CURRENT_DEV`: no live scheduler binding, real persistent task table write, or end-to-end recurring automation run was executed in this branch.

## Code Facts

| Surface | Current repo fact | Evidence |
| --- | --- | --- |
| Lifecycle contract enums/models | Added `LongCycleLifecycleTransition`, `LongCycleTaskLifecycleEvent`, `LongCyclePersistentTaskRecord`, and `LongCycleLifecycleContractCheck`. | [ingest_digestion.py](../../../../../main/backend/app/contracts/ingest_digestion.py) |
| Persistent task key and record builder | Added deterministic task-key hashing and `build_long_cycle_persistent_task_record()`. | [digestion_scaffold.py](../../../../../main/backend/app/services/ingest/digestion_scaffold.py) |
| In-memory lifecycle transitions | Added `transition_long_cycle_persistent_task_record()` with allowed transition rules and required dispatch/output evidence. | [digestion_scaffold.py](../../../../../main/backend/app/services/ingest/digestion_scaffold.py) |
| Scheduler/persistence contract gate | Added `check_long_cycle_lifecycle_contract()` and a script-level deterministic gate. | [check_ingest_long_cycle_lifecycle_contract.py](../../../../../main/backend/scripts/check_ingest_long_cycle_lifecycle_contract.py) |
| Unit coverage | Existing digestion scaffold tests now cover stable task keys, selected-window preconditions, dry-run lifecycle success, and invalid transition rejection. | [test_ingest_digestion_scaffold_unittest.py](../../../../../main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py) |

## Checker Semantics

`check_long_cycle_lifecycle_contract()` returns contract version `ingest.long_cycle_lifecycle_contract_check.v1`.

The narrow gate passes when:

- Wave7 automation status has no blockers;
- `selected_window` is present for lifecycle dispatch;
- a persistent-task record can be built with contract version `ingest.long_cycle_persistent_task.v1`;
- the closed slice records `stable_task_key`, `persistent_task_record_shape`, `selected_window_dispatch_precondition`, and `in_memory_ready_running_terminal_lifecycle`.

The deterministic checker script then applies an in-memory transition sequence:

```text
mark_ready -> dispatch -> succeed
```

The transition model rejects invalid terminal jumps and rejects dispatch without a `dispatch_ref`.

## Remaining Boundaries

These gaps are intentionally still open:

- `live_scheduler_dispatch_not_executed`: no Celery beat, cron, or long-cycle scheduler was started.
- `persistent_task_table_write_not_executed`: no live database row was inserted or migrated for this long-cycle task.
- `end_to_end_automation_run_not_executed`: no real recurring run proved selected window -> task dispatch -> digestion output -> downstream handoff.

This means the topic status should remain `partial`; the closed slice is the scheduler/persistent-task lifecycle contract, not the production automation runtime.

## Validation

Commands run from this worktree:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_long_cycle_lifecycle_contract.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m py_compile main/backend/app/contracts/ingest_digestion.py main/backend/app/services/ingest/digestion_scaffold.py main/backend/scripts/check_ingest_long_cycle_lifecycle_contract.py
git diff --check
```

Observed result:

- `12 passed`
- checker output: `status=pass`, `contract_status=closed_narrow_lifecycle_contract`
- `py_compile` passed
- `git diff --check` passed
