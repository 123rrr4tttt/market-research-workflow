# Wave12 Relevance Review Queue Contract - Adapter Capability (2026-05-22)

## Scope

This slice turns prior `candidate_relevance_review_required` markers into a
reviewer-ready queue envelope:

- `source_library.relevance_review_queue.v1`
- `fallback_anchor_only_profile`
- `term_fallback_candidates`
- `low_confidence_candidate`
- `adapter_capability_review`

## Adapter Capability Boundary

Anchor-only fallback parser profiles stay executable for deterministic
collection, but their candidates are not auto-accepted. The queue preserves
parser and adapter state for review:

- `parser_profile_resolved`
- `adapter_capability_status`
- `adapter_capability_reason`
- `matched_by`
- `candidate_quality`
- `usable_for_search`

## Non-Closure Markers

- `claims_human_relevance_review_complete=false`
- `claims_live_public_replay_complete=false`
- this is queue readiness only, not completed human review.
- fail-closed queue entries set `auto_accept_allowed=false` and
  `auto_ingest_allowed=false`.

## Validation

```bash
PYTHONPATH=main/backend python3.11 main/backend/scripts/check_source_library_relevance_review_queue.py --repo-root .
python3.11 -m pytest -q main/backend/tests/unit/test_resource_pool_search_template_adapters_unittest.py main/backend/tests/unit/test_resource_pool_unified_search_unittest.py main/backend/tests/unit/test_source_library_relevance_review_queue_unittest.py
```
