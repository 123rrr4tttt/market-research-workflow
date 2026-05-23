# Wave20 Long-Cycle Scheduler Queue Handoff Replay Gate

Date: 2026-05-22 US/Pacific
Branch: `codex/devdocs-wave20-long-cycle-scheduler-queue`
Status: `scheduler queue handoff and durable repository replay gate landed / live scheduler, live DB, worker consumption, and downstream handoff remain open`

## Status Check

This lane advances the Wave18 scheduler handoff trace into a first-class queue
item and replay summary. It is still a repository-local deterministic gate; it
does not enqueue a live scheduler job and does not validate a live DB table.

Wave20 binds:

- the scheduler dispatch intent and stable idempotency key;
- a contract-only queue item with `live_enqueue=false`;
- the durable JSONL repository write/readback from Wave16/Wave18;
- an event replay summary over `mark_ready -> dispatch -> succeed`.

The topic remains in `CURRENT_DEV`: no Celery beat, cron scheduler, production
worker, live persistent-task DB row, live digestion output, or downstream
handoff was executed in this branch.

## Contract Markers

- contract_version: ingest.long_cycle_scheduler_queue_replay_check.v1
- scheduler_intent_validated: true
- queue_item_validated: true
- repository_write_readback_validated: true
- event_replay_summary_validated: true
- live_dispatch: false
- live_enqueue: false
- live_db_write: false
- closure_claim: false
- live_scheduler_closure_validated: false

## Code Facts

| Surface | Current repo fact | Evidence |
| --- | --- | --- |
| Queue/replay schemas | Added `LongCycleSchedulerQueueItem`, `LongCycleRepositoryEventReplaySummary`, and `LongCycleSchedulerQueueReplayCheck`. | [ingest_digestion.py](../../../../../main/backend/app/contracts/ingest_digestion.py) |
| Queue/replay builder | Added `build_long_cycle_scheduler_queue_item()`, `summarize_long_cycle_repository_event_replay()`, and `check_long_cycle_scheduler_queue_handoff_replay_contract()`. | [digestion_scaffold.py](../../../../../main/backend/app/services/ingest/digestion_scaffold.py) |
| CLI gate | Added `check_ingest_long_cycle_scheduler_queue_handoff_replay_contract.py` with topic-marker validation and optional JSON output. | [check_ingest_long_cycle_scheduler_queue_handoff_replay_contract.py](../../../../../main/backend/scripts/check_ingest_long_cycle_scheduler_queue_handoff_replay_contract.py) |
| Unit coverage | Extended ingest digestion scaffold coverage for scheduler intent, queue item, repository write/readback, and event replay summary. | [test_ingest_digestion_scaffold_unittest.py](../../../../../main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py) |
| Automation evidence | Added a Wave20 run artifact with the full checker payload. | [scheduler_queue_replay_check.json](../../../../automation-runs/wave20-long-cycle-scheduler-queue/2026-05-22/scheduler_queue_replay_check.json) |

## Checker Semantics

`check_long_cycle_scheduler_queue_handoff_replay_contract()` returns contract
version `ingest.long_cycle_scheduler_queue_replay_check.v1`.

The narrow gate passes when:

- the Wave18 handoff trace still passes;
- `dispatch_intent.live_dispatch=false`;
- the queue item matches `dispatch_key`, `idempotency_key`, `task_key`,
  `queue_name`, and `worker_task_name` from the scheduler intent;
- the queue item payload records `queue_handoff_mode=durable_repository_replay_contract_only`;
- `queue_item.live_enqueue=false`;
- the reopened JSONL repository reads back the terminal task record and
  `mark_ready -> dispatch -> succeed`;
- the replay summary reports `write_status_sequence=ready,running,succeeded`;
- `closure_claim=false`, `live_scheduler_closure_validated=false`, and
  `live_db_write=false`.

## Remaining Topic Gap

- Configure and start the real scheduler runtime.
- Execute a bounded live scheduler enqueue with worker consumption evidence.
- Prove live persistent-task table write/readback.
- Prove digestion output readback and downstream handoff.

Do not archive this topic from this slice. The topic remains `partial` until
live scheduler, live DB, worker, and end-to-end automation evidence exists.

## Validation

Commands to run from this worktree:

```bash
python3 scripts/check_current_dev_wave20_plan.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_long_cycle_scheduler_queue_handoff_replay_contract.py --output development/latest-dev-docs/automation-runs/wave20-long-cycle-scheduler-queue/2026-05-22/scheduler_queue_replay_check.json
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m py_compile main/backend/app/contracts/ingest_digestion.py main/backend/app/services/ingest/digestion_scaffold.py main/backend/scripts/check_ingest_long_cycle_scheduler_queue_handoff_replay_contract.py
git diff --check
```

Observed result:

- Wave20 plan gate passed.
- `23 passed` for `test_ingest_digestion_scaffold_unittest.py`.
- queue replay checker output: `status=pass`, `contract_status=closed_narrow_scheduler_queue_replay_contract`, `scheduler_intent_validated=true`, `queue_item_validated=true`, `repository_write_readback_validated=true`, `event_replay_summary_validated=true`.
- `py_compile` passed.
- `git diff --check` passed.
