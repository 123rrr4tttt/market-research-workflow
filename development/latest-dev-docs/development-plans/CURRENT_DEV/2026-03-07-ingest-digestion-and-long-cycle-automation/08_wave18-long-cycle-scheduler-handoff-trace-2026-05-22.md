# Wave18 Long-Cycle Scheduler Handoff Trace Contract

Date: 2026-05-22 PST
Branch: `codex/devdocs-wave18-long-cycle-scheduler-handoff`
Status: `scheduler handoff trace landed / live scheduler, live DB, and end-to-end automation remain open`

## Status Check

This lane advances Wave16 durable JSONL repository readback into a scheduler dispatch handoff trace. It still does not claim production automation closure.

Wave18 adds a deterministic trace that binds:

- the Wave11 dispatch intent and stable `dispatch_key`;
- the Wave13 contract-only scheduler readiness boundary;
- the Wave16 reopened JSONL task/event repository;
- the durable `dispatch` lifecycle event read back from JSONL.

The topic remains in `CURRENT_DEV`: no Celery beat, cron scheduler, production worker, live persistent-task DB row, live digestion output, or downstream handoff was executed in this branch.

## Contract Markers

- contract_version: ingest.long_cycle_scheduler_handoff_trace_check.v1
- durable_event_readback: true
- dispatch_intent_matches_readback: true
- live_dispatch: false
- live_db_write: false
- closure_claim: false
- live_scheduler_closure_validated: false

## Code Facts

| Surface | Current repo fact | Evidence |
| --- | --- | --- |
| Handoff trace schema | Added `LongCycleSchedulerHandoffTraceEntry` and `LongCycleSchedulerHandoffTraceCheck`. | [ingest_digestion.py](../../../../../main/backend/app/contracts/ingest_digestion.py) |
| Handoff trace builder | Added `check_long_cycle_scheduler_handoff_trace_contract()` over the durable repository readback contract. | [digestion_scaffold.py](../../../../../main/backend/app/services/ingest/digestion_scaffold.py) |
| CLI gate | Added `check_ingest_long_cycle_scheduler_handoff_trace_contract.py` for the Wave18 focused checker. | [check_ingest_long_cycle_scheduler_handoff_trace_contract.py](../../../../../main/backend/scripts/check_ingest_long_cycle_scheduler_handoff_trace_contract.py) |
| Unit coverage | Added a focused unit test that checks dispatch intent, dispatch ref, JSONL event readback, and live-boundary markers. | [test_ingest_digestion_scaffold_unittest.py](../../../../../main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py) |

## Checker Semantics

`check_long_cycle_scheduler_handoff_trace_contract()` returns contract version `ingest.long_cycle_scheduler_handoff_trace_check.v1`.

The narrow gate passes when:

- the durable repository readback contract passes;
- `dispatch_intent.live_dispatch=false`;
- `dispatch_ref` is derived from `dispatch_intent.dispatch_key`;
- the reopened JSONL repository reads back `mark_ready -> dispatch -> succeed`;
- the durable `dispatch` event has the same task key, run time, and dispatch ref as the dispatch intent;
- the terminal task record is read back as `succeeded`;
- `closure_claim=false`, `live_scheduler_closure_validated=false`, and `live_db_write=false`.

The handoff trace sequence is:

```text
dispatch_intent_created
scheduler_handoff_recorded
durable_event_readback
terminal_output_readback
```

## Remaining Topic Gap

- Configure and start the real scheduler runtime.
- Execute a bounded live scheduler handoff with worker consumption evidence.
- Prove live persistent-task table write/readback.
- Prove digestion output readback and downstream handoff.

Do not archive this topic from this slice. The topic remains `partial` until live scheduler, live DB, and end-to-end automation evidence exists.

## Validation

Commands to run from this worktree:

```bash
python3 scripts/check_current_dev_wave18_plan.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_long_cycle_scheduler_handoff_trace_contract.py
git diff --check
```

Observed result:

- Wave18 plan gate passed.
- `22 passed` for `test_ingest_digestion_scaffold_unittest.py`.
- scheduler handoff checker output: `status=pass`, `contract_status=closed_narrow_scheduler_handoff_trace_contract`, `durable_event_readback=true`, `dispatch_intent_matches_readback=true`.
- `git diff --check` passed.
