# Wave55 Live Collection / Provider Extraction Readback (2026-05-23)

## Scope

Worker C2 target: `2026-03-11-source-library-three-lane-architecture`.

This pass is not docs-only. It adds and runs a checker that composes:

- public source-library live collection via `source_library_public_live_probes.py`
- provider article-body extraction via the external-project `article_extractor`
- human-review readback via `source_library.relevance_review_queue.v1` and `source_library.taxonomy_review_readiness.v1`

No global manifest, shared index, or navigation file is edited.

## Evidence

Artifact:

`development/latest-dev-docs/automation-runs/wave55-source-library-three-lane-live-closure/2026-05-23/closure.json`

Checker:

`main/backend/scripts/check_source_library_three_lane_live_closure.py`

Contract:

`source_library.three_lane_live_closure.v1`

Runtime result:

- `closure_state=live_collection_article_extraction_ready_human_review_open`
- `claims_live_source_collection_complete=true`
- `claims_provider_article_extraction_complete=true`
- `claims_human_review_complete=false`
- `claims_human_relevance_review_complete=false`
- `shared_indexes_edited=false`
- `global_manifest_indexes_edited=false`

Live collection readback:

- `candidate_count=4`
- `status_counts={"candidate_ready": 2, "candidate_ready_with_term_fallback": 2}`
- candidate-ready targets: `commercialobserver_parser_weak`, `pymnts_parser_weak`, `investopedia_validated_query`, `hai_stanford_mixed_shell`

Provider article extraction readback:

- `status=ok`
- `candidate_url_count=4`
- `record_count=4`
- `article_body_extracted_count=4`
- `state_counts={"article_body_extracted": 4}`

Human-review readback:

- review queue state: `ready_for_review`
- open queue id: `sl_review:cba6e135df79b9d5`
- missing human-review evidence: `sl_review:cba6e135df79b9d5`

Human review is therefore wired and readable, but not closed by this worker.
Completion requires explicit evidence with `queue_id`, `reviewed_by`,
`reviewed_at`, `decision`, and `state=completed` for every live queue id.

## Implementation Notes

- The provider article extraction runner now follows HTTP redirects for article
  fetches. The first strict attempt reached live candidates but failed on normal
  `301 Moved Permanently` article URLs; redirect-following converted that into
  successful article-body extraction.
- The Wave55 checker samples extraction-capable candidates before fallback-only
  candidates while preserving at least one review-required fallback candidate
  when present.
- Human review completion remains evidence-gated. The checker can validate
  completion through `--human-review-evidence`, but this run did not supply
  actual human-review evidence.

## Commands

```bash
python3.11 -m pytest -q \
  main/backend/tests/unit/test_source_library_three_lane_live_closure_unittest.py \
  main/backend/tests/unit/test_source_library_external_project_adapter_unittest.py \
  main/backend/tests/unit/test_source_library_ingest_external_project_contract_check_unittest.py \
  main/backend/tests/unit/test_source_library_public_live_probe_gate_unittest.py
```

Result: `16 passed, 2 warnings`.

```bash
PYTHONPATH=main/backend python3.11 \
  main/backend/scripts/check_source_library_three_lane_live_closure.py \
  --allow-public-network \
  --strict \
  --probe-timeout 8 \
  --max-candidates 4 \
  --output development/latest-dev-docs/automation-runs/wave55-source-library-three-lane-live-closure/2026-05-23/closure.json
```

Result: passed. `strict_live_runtime_complete=true`,
`human_review_completed=false`.

## Decision

The live source-collection and provider article-extraction gaps now have
runtime evidence for this topic. The topic should remain `ARCHIVE_EXTERNAL_BLOCKED`
until an explicit human-review evidence file closes the live queue id and an
integration owner decides whether archive/index migration is in scope.
