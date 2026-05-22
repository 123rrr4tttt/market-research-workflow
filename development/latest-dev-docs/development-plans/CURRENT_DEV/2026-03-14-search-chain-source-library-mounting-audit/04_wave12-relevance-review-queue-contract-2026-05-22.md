# Wave12 Relevance Review Queue Contract - Mounting Audit (2026-05-22)

## Scope

This slice extends the Wave10 mounting governance with a deterministic review
queue for search results that require human relevance inspection:

- `source_library.relevance_review_queue.v1`
- reason codes for fallback-anchor-only profiles, term fallback, low-confidence
  candidates, and adapter capability review
- reviewer-ready fields for URL, domain, query terms, source-library item,
  site entry, parser profile, adapter status, search service, and match signal

## Mounting Boundary

The review queue is emitted by the capability path and propagated by the
source-library front door:

- `/api/v1/resource_pool/unified-search` remains a capability endpoint.
- `/api/v1/ingest/source-library/run` remains the authoritative sync front door.
- legacy item-run closure remains separate from review queue readiness.

## Non-Closure Markers

- `claims_human_relevance_review_complete=false`
- `claims_live_public_replay_complete=false`
- public replay gap remains `live_public_replay_not_run`.
- queue entries are fail-closed until an explicit review result exists.

## Validation

```bash
PYTHONPATH=main/backend python3.11 main/backend/scripts/check_source_library_relevance_review_queue.py --repo-root .
python3.11 -m pytest -q main/backend/tests/unit/test_source_library_search_governance_check_unittest.py main/backend/tests/unit/test_source_library_relevance_review_queue_unittest.py
```
