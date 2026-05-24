# Wave12 Relevance Review Queue Contract - Three-Lane Architecture (2026-05-22)

## Scope

This slice adds a deterministic review queue envelope for source-library search
candidates that are not safe to auto-close:

- `source_library.relevance_review_queue.v1`
- low-confidence selected candidates
- fallback-anchor-only parser profiles
- term-fallback-selected candidates

## Three-Lane Boundary

The queue belongs to the source-library/search lane. It does not reopen legacy
item execution, and it does not make resource-pool unified search the
authoritative front door.

Runtime propagation now keeps these states visible:

- `resource_pool.unified_search` emits `relevance_review_queue`.
- `source_library.handler_cluster_frontdoor` merges queue entries across search
  batches.
- source-library records receive `record_meta.source_library_relevance_review`
  with `state=review_required`.

## Non-Closure Markers

- `claims_human_relevance_review_complete=false`
- `claims_live_public_replay_complete=false`
- queue readiness means reviewer-ready records exist, not that review was done.
- fail-closed fields set `auto_accept_allowed=false` and
  `auto_ingest_allowed=false`.

## Validation

```bash
PYTHONPATH=main/backend python3.11 main/backend/scripts/check_source_library_relevance_review_queue.py --repo-root .
python3.11 -m pytest -q main/backend/tests/unit/test_source_library_relevance_review_queue_unittest.py
```
