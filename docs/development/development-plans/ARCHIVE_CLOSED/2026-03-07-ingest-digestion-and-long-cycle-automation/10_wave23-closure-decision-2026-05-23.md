# Wave23 Closure Decision: Ingest Digestion and Long-Cycle Automation

Date: 2026-05-23 US/Pacific

Decision result: `archive_external_blocked_candidate`

Scope note: this is a topic-local decision file only. It does not move this
directory and does not update shared indexes.

## Decision

This topic can leave `CURRENT_DEV` as an external-blocked candidate, not as a
closed archive candidate.

Repo-local deterministic evidence now covers the ingest long-cycle scheduler
contract through queue handoff and durable repository replay:

- `main/backend/app/contracts/ingest_digestion.py`
  - `LongCycleSchedulerQueueReplayCheck`
  - `LongCycleSchedulerQueueItem`
  - `LongCycleRepositoryEventReplaySummary`
- `main/backend/app/services/ingest/digestion_scaffold.py`
  - `check_long_cycle_scheduler_queue_handoff_replay_contract()`
  - `build_long_cycle_scheduler_queue_item()`
  - `summarize_long_cycle_repository_event_replay()`
  - `JsonlLongCycleTaskRepository`
- `main/backend/scripts/check_ingest_long_cycle_scheduler_queue_handoff_replay_contract.py`
- `main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py`
- `development/latest-dev-docs/automation-runs/wave20-long-cycle-scheduler-queue/2026-05-22/scheduler_queue_replay_check.json`

The latest deterministic gate reports:

- `status=pass`
- `contract_status=closed_narrow_scheduler_queue_replay_contract`
- `blockers=[]`
- `scheduler_intent_validated=true`
- `queue_item_validated=true`
- `repository_write_readback_validated=true`
- `event_replay_summary_validated=true`
- `closure_claim=false`
- `live_dispatch=false`
- `live_enqueue=false`
- `live_db_write=false`
- `live_scheduler_closure_validated=false`

Earlier topic evidence also remains aligned:

- `03_wave7-7-ingest-digestion-long-cycle-automation-evidence-2026-05-22.md`
  establishes the pre-dispatch digestion and long-cycle status contract.
- `04_wave9-6-ingest-long-cycle-lifecycle-contract-evidence-2026-05-22.md`
  establishes the lifecycle contract.
- `05_wave11-long-cycle-scheduler-e2e-evidence-2026-05-22.md`
  establishes contract-only scheduler intent and fake repository readback.
- `06_wave13-long-cycle-scheduler-readiness-2026-05-22.md`
  separates local dry-run readiness from live scheduler closure.
- `07_wave16-long-cycle-durable-repository-readback-2026-05-22.md`
  establishes JSONL durable readback.
- `08_wave18-long-cycle-scheduler-handoff-trace-2026-05-22.md`
  establishes scheduler handoff trace readback.
- `09_wave20-long-cycle-scheduler-queue-handoff-replay-2026-05-22.md`
  establishes queue item and replay summary validation.

The original `01` plan and `02` task list are historical planning inputs with
pending A1-A8 wording, but the later Wave7-Wave20 files provide the current
repo-local evidence chain. No unresolved repo-local blocker was found in this
Wave23 review.

## Remaining External Blockers

The only remaining blockers require live runtime or environment evidence:

- configure and start the real scheduler runtime;
- execute a bounded live scheduler enqueue;
- prove live queue worker consumption;
- prove live persistent-task table write/readback;
- prove live digestion output readback;
- prove downstream handoff observation.

These blockers require external runtime, credentials, live database state, or
live environment evidence. They are not resolvable by another topic-local docs
or deterministic unit-test pass alone.

## Migration Recommendation

The parent integrator may move this directory to
`ARCHIVE_EXTERNAL_BLOCKED`, preserving this file as the topic-local migration
rationale.

Do not migrate this topic to `ARCHIVE_CLOSED`: the latest contract explicitly
keeps `closure_claim=false` and `live_scheduler_closure_validated=false`.

If this topic is reopened, require a live evidence package that supplies the
complete scheduler/runtime proof expected by
`check_ingest_long_cycle_scheduler_readiness.py` and then replays the queue
handoff gate with live scheduler, worker, DB, digestion-output, and downstream
handoff evidence attached.

## Checks Performed

- Read the full topic document set `01` through `09`.
- Read `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`.
- Read `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md`.
- Inspected referenced scripts, tests, and automation artifacts:
  - `main/backend/scripts/check_ingest_long_cycle_lifecycle_contract.py`
  - `main/backend/scripts/check_ingest_long_cycle_scheduler_e2e_contract.py`
  - `main/backend/scripts/check_ingest_long_cycle_scheduler_readiness.py`
  - `main/backend/scripts/check_ingest_long_cycle_repository_readback_contract.py`
  - `main/backend/scripts/check_ingest_long_cycle_scheduler_handoff_trace_contract.py`
  - `main/backend/scripts/check_ingest_long_cycle_scheduler_queue_handoff_replay_contract.py`
  - `main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py`
  - `development/latest-dev-docs/automation-runs/wave20-long-cycle-scheduler-queue/2026-05-22/README.md`
  - `development/latest-dev-docs/automation-runs/wave20-long-cycle-scheduler-queue/2026-05-22/scheduler_queue_replay_check.json`
  - `development/latest-dev-docs/automation-runs/frontdoor-router-hardening/2026-05-22/README.md`
  - `development/latest-dev-docs/automation-runs/ingest-frontdoor-closure/2026-05-22/README.md`
- Re-ran deterministic gates:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_long_cycle_lifecycle_contract.py`
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_long_cycle_scheduler_e2e_contract.py`
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_long_cycle_scheduler_readiness.py --format text`
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_long_cycle_repository_readback_contract.py`
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_long_cycle_scheduler_handoff_trace_contract.py`
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_long_cycle_scheduler_queue_handoff_replay_contract.py`
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py`
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m py_compile main/backend/app/contracts/ingest_digestion.py main/backend/app/services/ingest/digestion_scaffold.py main/backend/scripts/check_ingest_long_cycle_scheduler_queue_handoff_replay_contract.py`
  - `python3 scripts/check_current_dev_wave20_plan.py`

Observed results:

- all six long-cycle checker scripts passed;
- scheduler readiness remained `local_deterministic_dry_run_ready` with
  `live_scheduler_closure_validated=False`;
- latest queue replay checker returned
  `closed_narrow_scheduler_queue_replay_contract`;
- unit tests returned `23 passed`;
- `py_compile` passed;
- Wave20 plan gate returned `OK wave20_current_dev_plan=passed`.
