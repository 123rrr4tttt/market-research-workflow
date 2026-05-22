# Wave20 Long-Cycle Scheduler Queue Handoff

- status: `passed`
- contract_version: `ingest.long_cycle_scheduler_queue_replay_check.v1`
- contract_status: `closed_narrow_scheduler_queue_replay_contract`
- scope: `deterministic_scheduler_intent_queue_item_repository_replay_no_live_scheduler_no_live_db`
- closure_claim: `false`
- live_scheduler_closure_validated: `false`
- live_db_write: `false`

## Validated Surfaces

| surface | result |
| --- | --- |
| scheduler intent | `scheduler_intent_validated=true` |
| queue item | `queue_item_validated=true` |
| repository write/readback | `repository_write_readback_validated=true` |
| event replay summary | `event_replay_summary_validated=true` |

## Replay Facts

- queue item state: `queued_contract_only`
- queue handoff mode: `durable_repository_replay_contract_only`
- event sequence: `mark_ready -> dispatch -> succeed`
- write status sequence: `ready -> running -> succeeded`
- terminal status: `succeeded`

## Boundary

This gate is repository-local. It does not enqueue the live scheduler, does not
consume a live queue item with a production worker, does not write a live DB row,
and does not validate downstream handoff.

## Rerun

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_long_cycle_scheduler_queue_handoff_replay_contract.py --output development/latest-dev-docs/automation-runs/wave20-long-cycle-scheduler-queue/2026-05-22/scheduler_queue_replay_check.json
```

Full deterministic output is in `scheduler_queue_replay_check.json`.
