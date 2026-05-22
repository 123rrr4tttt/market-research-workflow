# Wave12 Relevance Review Queue Contract - Ingest Minimal Migration (2026-05-22)

## Scope

This slice adds a deterministic fail-closed review queue between source-library
candidate discovery and downstream ingest/replay closure:

- `source_library.relevance_review_queue.v1`
- source-library records are annotated with
  `record_meta.source_library_relevance_review`
- queue entries include reviewer-ready fields and explicit open gap markers

## Ingest Boundary

The queue does not claim a live ingest canary and does not complete external
public replay. It only makes candidate records safe to hand to a reviewer.

Fail-closed state:

- `state=review_required`
- `review_completed=false`
- `auto_accept_allowed=false`
- `auto_ingest_allowed=false`
- `live_public_replay_completed=false`

## Non-Closure Markers

- `claims_human_relevance_review_complete=false`
- `claims_live_public_replay_complete=false`
- live replay gap remains `live_public_replay_not_run`.
- completed human review must be represented by a later explicit review result,
  not by this queue-readiness contract.

## Validation

```bash
PYTHONPATH=main/backend python3.11 main/backend/scripts/check_source_library_relevance_review_queue.py --repo-root .
python3.11 -m pytest -q main/backend/tests/unit/test_source_library_relevance_review_queue_unittest.py
```
