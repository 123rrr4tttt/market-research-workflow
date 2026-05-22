# Wave17 Worker6 Persisted Typed-Card UI Readback (2026-05-22)

Scope: worker-local slice for `2026-03-07-writing-workbench-evolution`, advancing the Writing Workbench typed-card consumer from Wave16 fetch/readback into a deterministic persisted-document UI request path. Shared supervisor indexes were intentionally not edited.

## Result

- Added `buildPersistedTypedKnowledgeKeywordCardRequest` in the frontend writing API domain.
- The helper reads `writing.typed_knowledge_context.v1` from a persisted writing document's `metadata_json`, attaches it to the existing `/writing/keyword-cards` request, and keeps typed knowledge constrained to the `writing.keyword_card` resource-card boundary.
- `WritingWorkbenchPage` now routes selection lookup card fetches through that persisted-document helper, so the UI consumer path is explicit and deterministic for component/checker readback.
- Added `check:writing-workbench-persisted-typed-card-readback`, a node checker that verifies the helper, page wiring, scoped selection lookup, backend preview/detail readback test, and this evidence document.

## Deterministic Readback Boundary

Covered:

- persisted document field: `WritingDocument.metadata_json`
- typed context: `writing.typed_knowledge_context.v1`
- handoff: `typed_knowledge.writing_handoff.v1`
- consumer: `writing.keyword_card`
- card source type: `resource`
- backend readback: card preview/detail cache readback after consumer fetch

This is a repo-controlled checker/component path. No live browser/UI persisted readback was claimed.

## Validation

```bash
cd main/frontend-modern && npm run check:writing-workbench-persisted-typed-card-readback
cd main/frontend-modern && npm run check:writing-workbench-typed-fetch
/Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_writing_keyword_card_service_unittest.py -q
python3 scripts/check_current_dev_wave17_plan.py
git diff --check
```

## Remaining Live Conditions

Still partial:

- `public_typed_knowledge_api_route_not_implemented`
- `live_db_persistence_not_implemented`
- `persisted_typed_knowledge_cards_live_readback_not_verified`

The slice proves deterministic persisted metadata consumption by the Writing Workbench card request path, not live persisted UI closure.
