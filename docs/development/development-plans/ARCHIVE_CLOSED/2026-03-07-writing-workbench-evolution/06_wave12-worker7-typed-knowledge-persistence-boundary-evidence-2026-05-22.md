# Wave12 Worker 7 - Writing Consumer Boundary Evidence

Scope: local closure slice for `2026-03-07-writing-workbench-evolution` consuming typed-knowledge persistence references.

## Result

- The writing workbench still consumes typed knowledge through `typed_knowledge.writing_handoff.v1` and `writing.typed_knowledge_context.v1`.
- The new persistence/API boundary preserves writing handoff references as metadata on `knowledge_item` records.
- The preserved reference remains constrained to:
  - `consumer=writing.keyword_card`
  - `card_source_type=resource`
  - selection hash/text for selected writing context
- No writing product UI was changed.
- No graph projection or source-library write-back path was added.

## Boundary Readiness Markers

- contract_readiness: ready
- live_db_persistence: false
- public_api_route: false
- governance_ui: false
- remaining_live_gaps:
  - live_db_persistence_not_implemented
  - public_typed_knowledge_api_route_not_implemented
  - governance_ui_not_implemented
  - migration_and_backfill_not_executed

## Writing-Side Interpretation

- Ready: writing can rely on a stable typed-knowledge object identity and handoff reference shape in a contract-only envelope.
- Not ready: writing cannot fetch typed knowledge from a live public typed-knowledge API yet.
- Not ready: writing cannot mutate typed-knowledge governance state from UI yet.
- Not ready: writing cannot claim persisted typed-knowledge cards survive process restart through a production database.

## Validation

```bash
python3 scripts/check_typed_knowledge_persistence_api_boundary.py
/Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_typed_knowledge_persistence_boundary_unittest.py main/backend/tests/unit/test_writing_keyword_card_service_unittest.py -q
```
