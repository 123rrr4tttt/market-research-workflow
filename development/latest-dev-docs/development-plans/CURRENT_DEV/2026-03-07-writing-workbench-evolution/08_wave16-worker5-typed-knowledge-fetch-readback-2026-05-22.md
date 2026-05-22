# Wave16 Worker5 Writing Workbench Typed Knowledge Fetch Readback (2026-05-22)

Scope: worker-local slice for `2026-03-07-writing-workbench-evolution`, connecting the Writing Workbench consumer surface to the typed-knowledge writing contract without claiming live typed-knowledge API or DB closure.

Shared indexes were intentionally not edited.

## Result

- Added frontend writing API helpers that read `writing.typed_knowledge_context.v1` from a writing document's `metadata_json`.
- The Writing Workbench selection lookup now sends that context through the existing `/writing/keyword-cards` request via `typed_knowledge_context`.
- Selection lookup dedupe now accepts a scoped key, so the same selected text can refetch when the typed-knowledge context attached to the current document changes.
- Added deterministic readback coverage proving a typed-knowledge resource card can be fetched and then read back through preview/detail cache APIs.
- Added a frontend contract checker that verifies the consumer fetch wiring, scoped lookup, backend readback test, and remaining live boundary conditions.

## Covered Contract

- context envelope: `writing.context_boundary.e3.v1`
- typed context: `writing.typed_knowledge_context.v1`
- handoff: `typed_knowledge.writing_handoff.v1`
- consumer: `writing.keyword_card`
- card source type: `resource`

## Validation

```bash
cd main/frontend-modern && npm run check:writing-workbench-typed-fetch
/Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_writing_keyword_card_service_unittest.py -q
python3 scripts/check_current_dev_wave16_plan.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 scripts/check_current_dev_status_evidence.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_typed_writing_live_boundary.py --format text
git diff --check
```

Observed:

- `check:writing-workbench-typed-fetch`: `status=ok`, `live_closure_claimed=false`
- backend unit test: `6 passed in 1.76s`
- `check_current_dev_wave16_plan.py`: passed on `codex/devdocs-wave16-writing-workbench-typed-fetch`
- `check_current_dev_status_evidence.py`: passed with `partial:34, not_closed:0, no_closure_claim:0`
- `check_typed_writing_live_boundary.py`: passed with `readiness_state=partial`, `closure_claim_allowed=false`
- `git diff --check`: passed

## Remaining Live Conditions

Still partial:

- `public_typed_knowledge_api_route_not_implemented`
- `live_db_persistence_not_implemented`
- `persisted_typed_knowledge_cards_live_readback_not_verified`
- No live browser/UI evidence was produced in this worker slice.

This slice only proves repo-local consumer fetch/readback through the existing writing keyword-card contract.
