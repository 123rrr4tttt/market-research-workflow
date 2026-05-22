# Wave15 Typed Knowledge / Writing Live Boundary Inventory (2026-05-22)

Scope: `2026-03-07-typed-knowledge-organization` boundary with the writing workbench consumer.

Shared indexes were intentionally not edited.

## Result

- wave15_live_boundary_inventory: passed
- deterministic_persistence_api_boundary: covered
- closure_claim_allowed: false
- live_db_persistence: false
- public_api_route: false
- governance_ui: false

This slice adds `main/backend/scripts/check_typed_writing_live_boundary.py` as the repeatable inventory gate for the typed-knowledge to writing-workbench boundary.

## Deterministic Coverage

The checker verifies these closed deterministic items:

| Area | Covered evidence |
|---|---|
| Typed object identity | `type_node`, `knowledge_item`, `topic_cluster`, and `booklet` records keep project-scoped identity refs in `typed_knowledge.persistence_api_boundary.v1`. |
| API envelope | The contract-only boundary uses the existing `status/data/error/meta` envelope and records `contract_readiness: ready`. |
| Repository readback | The in-memory repository returns deterministic records and writes with `live_db_write=false`. |
| Writing handoff refs | `knowledge_item` records preserve `consumer=writing.keyword_card` and `card_source_type=resource`. |
| Writing context schema | `writing.typed_knowledge_context.v1` remains exposed through `WritingContextEnvelope.typed_knowledge_context`. |
| Writing card consumer | The writing keyword-card path still consumes typed knowledge as resource cards only. |

## Live DB/API/UI Not Closed

remaining_live_gaps:

- live_db_persistence_not_implemented
- public_typed_knowledge_api_route_not_implemented
- governance_ui_not_implemented
- migration_and_backfill_not_executed
- writing_live_typed_knowledge_fetch_not_available
- writing_ui_governance_mutation_not_available
- persisted_typed_knowledge_cards_live_readback_not_verified

These gaps are intentionally preserved as blockers against any typed-knowledge live closure claim. The current branch does not add a typed-knowledge DB model/table, public typed-knowledge router, migration/backfill run, or governance UI.

## Validation

```bash
python3 main/backend/scripts/check_typed_writing_live_boundary.py --format text
/Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_typed_writing_live_boundary_checker_unittest.py -q
```

Expected checker position:

- readiness_state: `partial`
- closure_position: `deterministic_persistence_api_boundary_covered_live_db_api_ui_not_closed`
- unsupported closure claim: `typed_writing_live_boundary_closed`
