# Wave16 Long-Cycle Durable Repository Readback Contract

Date: 2026-05-22 PST
Branch: `codex/devdocs-wave16-long-cycle-live-repository-readback`
Status: `durable repository readback contract landed / live scheduler and live DB remain open`

## Status Check

This lane advances the Wave11 fake repository E2E and Wave13 scheduler-readiness boundary without claiming production automation closure.

Wave16 adds a topic-local durable readback slice:

- `JsonlLongCycleTaskRepository` persists long-cycle task snapshots, write results, and lifecycle events to JSONL files;
- the checker reopens the repository after the scheduler/readiness contract writes and reads back the terminal task record;
- the lifecycle event sequence is checked as `mark_ready -> dispatch -> succeed`;
- the live scheduler and live DB boundaries remain explicit.

## Contract Markers

- contract_version: ingest.long_cycle_repository_readback_check.v1
- durable_readback: true
- live_db_write: false
- closure_claim: false
- live_scheduler_closure_validated: false

## Code Facts

| Surface | Current repo fact | Evidence |
| --- | --- | --- |
| Durable repository | Added `JsonlLongCycleTaskRepository`, a JSONL-backed local contract repository that can be reopened for readback. | [digestion_scaffold.py](../../../../../main/backend/app/services/ingest/digestion_scaffold.py) |
| Readback contract | Added `LongCycleRepositoryReadbackCheck` and `check_long_cycle_repository_readback_contract()`. | [ingest_digestion.py](../../../../../main/backend/app/contracts/ingest_digestion.py), [digestion_scaffold.py](../../../../../main/backend/app/services/ingest/digestion_scaffold.py) |
| CLI gate | Added `check_ingest_long_cycle_repository_readback_contract.py` to verify durable readback and evidence markers. | [check_ingest_long_cycle_repository_readback_contract.py](../../../../../main/backend/scripts/check_ingest_long_cycle_repository_readback_contract.py) |
| Unit coverage | Added JSONL reopen/readback and repository-readback boundary tests. | [test_ingest_digestion_scaffold_unittest.py](../../../../../main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py) |

## Checker Semantics

`check_long_cycle_repository_readback_contract()` returns contract version `ingest.long_cycle_repository_readback_check.v1`.

The narrow gate passes when:

- the Wave13 scheduler readiness contract passes locally;
- the scheduler readiness payload still has `closure_claim=false` and `live_scheduler_closure_validated=false`;
- repository writes remain `live_db_write=false`;
- a reopened JSONL repository reads back the completed persistent-task record;
- the readback lifecycle events preserve `mark_ready`, `dispatch`, and `succeed`;
- remaining gaps still include the live scheduler and live DB boundaries.

This proves a durable local repository readback/event contract. It does not prove a migration, real database table, live scheduler enqueue, production worker execution, digestion-output readback, or downstream handoff.

## Remaining Topic Gap

- Configure and start the real scheduler runtime.
- Execute a bounded live scheduler dry-run with worker consumption evidence.
- Prove live persistent-task table write/readback.
- Prove digestion output readback and downstream handoff.

Do not archive this topic from this slice. The topic remains `partial` until live scheduler and live DB evidence exists.

## Validation

Commands to run from this worktree:

```bash
python3 scripts/check_current_dev_wave16_plan.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_digestion_scaffold_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_long_cycle_repository_readback_contract.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 scripts/check_current_dev_status_evidence.py
git diff --check
```

