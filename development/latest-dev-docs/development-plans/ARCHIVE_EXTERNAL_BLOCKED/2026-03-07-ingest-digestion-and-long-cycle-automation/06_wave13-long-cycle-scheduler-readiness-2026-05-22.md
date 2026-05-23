# Wave13 Long-Cycle Scheduler Readiness Boundary

Date: 2026-05-22 PST
Branch: `codex/devdocs-wave13-long-cycle-scheduler-readiness`
Status: `scheduler readiness/dry-run boundary landed / live scheduler closure remains open`

## Status Check

This lane advances the Wave11 deterministic scheduler E2E contract without claiming a live recurring scheduler run.

Wave11 proved a scheduler dispatch intent plus fake repository write/readback for `ready -> running -> succeeded`. Wave13 adds a readiness boundary on top of that contract:

- local deterministic readiness is explicit and repeatable;
- the dry-run dispatch plan is checked for contract-only payload shape, stable idempotency, selected window, and `live_dispatch=false`;
- live scheduler closure is a separate evidence stage and remains unvalidated unless explicit runtime evidence is supplied.

The topic must remain in `CURRENT_DEV`: no Celery beat, cron scheduler, production worker, live persistent-task table write, or live downstream handoff was executed in this branch.

## Code Facts

| Surface | Current repo fact | Evidence |
| --- | --- | --- |
| Readiness contracts | Added `LongCycleSchedulerReadinessStage` and `LongCycleSchedulerReadinessCheck`. | [ingest_digestion.py](../../../../../main/backend/app/contracts/ingest_digestion.py) |
| Readiness builder | Added `check_long_cycle_scheduler_readiness_contract()` over the existing scheduler E2E contract. | [digestion_scaffold.py](../../../../../main/backend/app/services/ingest/digestion_scaffold.py) |
| CLI gate | Added `check_ingest_long_cycle_scheduler_readiness.py` with JSON/text output and optional live evidence input. | [check_ingest_long_cycle_scheduler_readiness.py](../../../../../main/backend/scripts/check_ingest_long_cycle_scheduler_readiness.py) |
| Unit coverage | Extended scaffold tests for local dry-run readiness, incomplete live evidence, and complete live evidence classification. | [test_ingest_digestion_scaffold_unittest.py](../../../../../main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py) |

## Checker Semantics

`check_long_cycle_scheduler_readiness_contract()` returns contract version `ingest.long_cycle_scheduler_readiness_check.v1`.

The default bounded gate passes when:

- the existing scheduler E2E contract passes;
- the dispatch intent remains contract-only with `live_dispatch=false`;
- fake repository writes remain non-live and keep the `ready -> running -> succeeded` lifecycle;
- dry-run payload fields preserve `task_key`, `selected_window`, `cadence`, `output_target`, `persistent_ref`, `dispatch_mode`, and idempotency.

The gate reports:

- `readiness_state=local_deterministic_dry_run_ready`;
- `local_deterministic_readiness=true`;
- `dry_run_dispatch_ready=true`;
- `live_scheduler_closure_validated=false`;
- `closure_claim=false`.

Incomplete live evidence is a failing evidence condition, not a silent partial. A future live scheduler closure claim must supply all required evidence fields:

- `live_scheduler_dispatch_executed`
- `recurring_schedule_registered`
- `production_worker_task_executed`
- `live_persistent_task_table_write`
- `digestion_output_readback`
- `downstream_handoff_observed`

## Current Gate Output

Command:

```bash
PYTHONPATH=main/backend python3 main/backend/scripts/check_ingest_long_cycle_scheduler_readiness.py --format text
```

Observed status:

```text
status=pass
readiness_state=local_deterministic_dry_run_ready
closure_claim=False
local_deterministic_readiness=True
dry_run_dispatch_ready=True
live_scheduler_closure_validated=False
deterministic_scheduler_e2e_contract=passed passed=True validated=True
scheduler_dry_run_dispatch_plan=ready passed=True validated=True
live_scheduler_closure=not_configured passed=True validated=False
```

## Remaining Topic Gap

- Configure and start the real scheduler runtime.
- Run a bounded live scheduler dry-run with production worker consumption evidence.
- Prove live persistent-task table write/readback.
- Prove digestion output readback and downstream handoff.

Do not archive this topic from this slice. It is now gated for scheduler readiness, but the live scheduler proof remains unrun.

## Validation

Commands run from this worktree:

```bash
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py
PYTHONPATH=main/backend python3 main/backend/scripts/check_ingest_long_cycle_scheduler_readiness.py --format text
python3 -m py_compile main/backend/app/contracts/ingest_digestion.py main/backend/app/services/ingest/digestion_scaffold.py main/backend/scripts/check_ingest_long_cycle_scheduler_readiness.py
```

Observed result:

- `19 passed`
- scheduler readiness checker output: `status=pass`, `readiness_state=local_deterministic_dry_run_ready`, `closure_claim=False`
- `py_compile` passed
