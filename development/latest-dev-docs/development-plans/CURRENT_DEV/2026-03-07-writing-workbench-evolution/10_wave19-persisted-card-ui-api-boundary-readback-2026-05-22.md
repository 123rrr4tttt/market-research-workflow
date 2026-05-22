# Wave19 Persisted Card UI/API Boundary Readback (2026-05-22)

Scope: worker-local slice for `2026-03-07-writing-workbench-evolution`, proving the persisted typed-card UI request shape can be read back through the typed-knowledge API boundary without editing the frontend page.

shared_indexes_edited: false

## Result

- contract_version: typed_knowledge.persisted_card_request_response_readback.v1
- persisted_card_request_response_readback: true
- deterministic_persisted_ui_api_boundary: true
- live_db_closure: false
- live_api_closure: false
- live_ui_closure: false
- governance_ui: false

Wave19 keeps the Writing Workbench as a consumer surface. The new backend readback payload mirrors the existing frontend helper path: persisted writing document metadata supplies `writing.typed_knowledge_context.v1`, the keyword-card request carries that context, and the deterministic response shape remains a typed-knowledge resource card.

## UI/API Boundary

Covered:

- persisted document field: `metadata_json.typed_knowledge_context`
- typed context: `writing.typed_knowledge_context.v1`
- handoff: `typed_knowledge.writing_handoff.v1`
- API boundary: `GET /api/v1/typed-knowledge/persistence-boundary`
- card request: `POST /api/v1/writing/keyword-cards`
- consumer: `writing.keyword_card`
- card source type: `resource`
- response publisher: `typed_knowledge`

The backend unit test feeds the request body from the typed-knowledge API boundary into `aggregate_cards()` with external card sources stubbed out, then reads back preview/detail from the keyword-card cache. No live browser/UI persisted readback was claimed.

## Remaining Live Conditions

Still partial:

- live_db_persistence_not_implemented
- live_db_backed_typed_knowledge_readback_not_verified
- live_api_request_response_closure_not_verified
- live_browser_ui_readback_not_verified
- governance_ui_not_implemented
- migration_and_backfill_not_executed

This slice proves the repo-local persisted-card UI/API boundary and response shape. It does not prove live DB/API/UI closure.

## Validation

```bash
python3 scripts/check_typed_knowledge_persistence_api_boundary.py
/Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_typed_knowledge_persistence_boundary_unittest.py main/backend/tests/unit/test_writing_keyword_card_service_unittest.py main/backend/tests/integration/test_typed_knowledge_api_route_unittest.py -q
python3 scripts/check_current_dev_wave19_plan.py
git diff --check
```
