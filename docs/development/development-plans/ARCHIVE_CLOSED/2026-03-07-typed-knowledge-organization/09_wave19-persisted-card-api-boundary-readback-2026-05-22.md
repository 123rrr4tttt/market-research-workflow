# Wave19 Persisted Card API Boundary Readback (2026-05-22)

Scope: worker-local slice for `2026-03-07-typed-knowledge-organization`, connecting the typed-knowledge public API boundary to a repo-local persisted writing-card request/response readback.

shared_indexes_edited: false

## Result

- contract_version: typed_knowledge.persisted_card_request_response_readback.v1
- persisted_card_request_response_readback: true
- deterministic_persisted_ui_api_boundary: true
- live_db_closure: false
- live_api_closure: false
- live_ui_closure: false
- governance_ui: false

Wave19 adds `persisted_card_request_response_readback` to the typed-knowledge route contract payload. The readback starts from the deterministic typed-knowledge API boundary, reconstructs the persisted writing document `metadata_json.typed_knowledge_context`, builds the Writing Workbench keyword-card request body, and records the expected typed-knowledge resource-card response shape.

## Closed Deterministic Slice

| Boundary | Evidence |
|---|---|
| Typed API boundary | `GET /api/v1/typed-knowledge/persistence-boundary` returns the persisted-card readback payload beside the existing persistence boundary. |
| Persisted document context | The payload includes `metadata_json.typed_knowledge_context` with `writing.typed_knowledge_context.v1`. |
| UI request shape | The readback preserves the Writing Workbench default sources `document/resource/graph` and embeds the typed context under the keyword-card request `context`. |
| Response readback | The expected card response is a single `source_type=resource`, `publisher=typed_knowledge` card tied to `ki:robotics-policy`. |
| Overclaim guard | The contract keeps `live_db_closure=false`, `live_api_closure=false`, and `live_ui_closure=false`. |

## Remaining Live Boundaries

- live_db_persistence_not_implemented
- live_db_backed_typed_knowledge_readback_not_verified
- live_api_request_response_closure_not_verified
- live_browser_ui_readback_not_verified
- governance_ui_not_implemented
- migration_and_backfill_not_executed

This proves a repo-local typed-knowledge API boundary request/response readback for persisted writing cards. It does not prove production DB persistence, live API traffic against tenant data, browser UI execution, or governance mutation.

## Validation

```bash
python3 scripts/check_typed_knowledge_persistence_api_boundary.py
/Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_typed_knowledge_persistence_boundary_unittest.py main/backend/tests/unit/test_writing_keyword_card_service_unittest.py main/backend/tests/integration/test_typed_knowledge_api_route_unittest.py -q
python3 scripts/check_current_dev_wave19_plan.py
git diff --check
```
