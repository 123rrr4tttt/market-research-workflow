# Wave14 Taxonomy Review Readiness - Search Chain Mounting Audit (2026-05-22)

## Scope

This slice keeps search-chain mounting evidence separate from completed human
review:

- `source_library.taxonomy_review_readiness.v1`
- `source_library.relevance_review_queue.v1`
- site-search authoritative taxonomy still wins over explicit protocol-search
  overrides.
- candidate URL payloads still resolve to URL execution.

## Boundary

The new checker verifies deterministic source taxonomy rows through
`ItemResolver`, then folds the existing relevance-review queue into a readiness
summary.

- `taxonomy_readiness=ready`
- `review_queue_ready=true`
- `human_review_completed=false`

This is a search-chain readiness gate, not a closure claim for live reviewer
decisions.

## Non-Closure Markers

- no public network is attempted.
- review queue ready is not equivalent to completed human review.
- `review_completion_claim=not_claimed`
- shared index updates are reserved for the Wave14 integration branch.

## Validation

```bash
PYTHONPATH=main/backend python3.11 main/backend/scripts/check_source_library_taxonomy_review_readiness.py --repo-root .
python3.11 -m pytest -q main/backend/tests/unit/test_source_library_taxonomy_review_readiness_unittest.py
```
