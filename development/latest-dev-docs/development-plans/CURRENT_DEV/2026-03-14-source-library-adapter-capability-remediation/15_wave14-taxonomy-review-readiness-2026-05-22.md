# Wave14 Taxonomy Review Readiness - Adapter Capability Remediation (2026-05-22)

## Scope

This slice links adapter capability remediation to the review queue boundary:

- `source_library.taxonomy_review_readiness.v1`
- `source_library.relevance_review_queue.v1`
- validated domain parser profiles remain `allow`.
- unknown requested parser profiles remain `downgrade`.
- fallback-anchor-only profiles remain `review` and queue candidates for human
  relevance review.

## Boundary

The readiness gate proves that adapter capability review signals can feed a
reviewer-ready queue without becoming an auto-accept path.

- `taxonomy_readiness=ready`
- `review_queue_ready=true`
- `human_review_completed=false`

`human_review_completed` may only become true when explicit evidence covers
every queue id.

## Non-Closure Markers

- `auto_accept_allowed=false`
- `auto_ingest_allowed=false`
- `review_completion_claim=not_claimed`
- no shared index file is edited by this worker branch.

## Validation

```bash
PYTHONPATH=main/backend python3.11 main/backend/scripts/check_source_library_taxonomy_review_readiness.py --repo-root .
python3.11 -m pytest -q main/backend/tests/unit/test_source_library_taxonomy_review_readiness_unittest.py
```
