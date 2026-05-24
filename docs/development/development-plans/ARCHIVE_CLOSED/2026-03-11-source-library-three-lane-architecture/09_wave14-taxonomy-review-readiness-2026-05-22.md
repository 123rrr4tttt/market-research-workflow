# Wave14 Taxonomy Review Readiness - Three-Lane Architecture (2026-05-22)

## Scope

This slice adds a deterministic readiness gate for the source-library live
source taxonomy and relevance-review boundary:

- `source_library.taxonomy_review_readiness.v1`
- `source_library.relevance_review_queue.v1`
- `handler.cluster` site-search taxonomy
- `generic_web.*` internal site-search taxonomy
- crawler provider-harvest taxonomy
- URL execution override taxonomy

## Boundary

The gate treats taxonomy readiness and human review as separate states.

- `taxonomy_readiness=ready`
- `review_queue_ready=true`
- `human_review_completed=false`

Review queue readiness means the candidate has stable reviewer fields and a
deterministic queue id. It does not mean a reviewer accepted or rejected the
candidate.

## Non-Closure Markers

- no public network is required by this gate.
- `human_review_completed=false` unless explicit review evidence is supplied.
- `review_completion_claim=not_claimed`
- shared index files remain out of scope for this worker branch.

## Validation

```bash
PYTHONPATH=main/backend python3.11 main/backend/scripts/check_source_library_taxonomy_review_readiness.py --repo-root .
python3.11 -m pytest -q main/backend/tests/unit/test_source_library_taxonomy_review_readiness_unittest.py
```
