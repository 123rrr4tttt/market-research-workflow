# Wave15 Writing Workbench / Typed Knowledge Live Boundary Inventory (2026-05-22)

Scope: `2026-03-07-writing-workbench-evolution` as the writing-side consumer of typed knowledge.

Shared indexes were intentionally not edited.

## Result

- wave15_live_boundary_inventory: passed
- deterministic_persistence_api_boundary: covered
- closure_claim_allowed: false
- live_db_persistence: false
- public_api_route: false
- governance_ui: false

This slice adds a backend inventory checker that keeps the writing workbench boundary explicit: writing can consume typed-knowledge handoff envelopes as resource cards, but it cannot claim live typed-knowledge DB/API/UI closure.

## Deterministic Coverage

The checker verifies these writing-side covered items:

| Area | Covered evidence |
|---|---|
| Frontend API type parity | `main/frontend-modern/src/lib/api/domains/writing.ts` exposes `TypedKnowledgeWritingHandoff`, `TypedKnowledgeWritingContext`, `typed_knowledge_context`, `context_boundary`, and `dependency_gate`. |
| Backend API surface | `main/backend/app/api/writing.py` keeps typed response models for documents, keyword cards, LLM actions, and Markdown export. |
| Keyword-card service | `main/backend/app/services/writing/keyword_card_service.py` parses `writing.typed_knowledge_context.v1` and reports the typed-knowledge consume-only boundary. |
| Card view | `main/backend/app/services/document_views/writing_card_view.py` renders typed knowledge as `source_type=resource`, `publisher=typed_knowledge`. |
| Workbench consumer | `WritingWorkbenchPage.tsx` remains a writing API consumer surface, not a typed-knowledge governance UI. |

## Live DB/API/UI Not Closed

remaining_live_gaps:

- live_db_persistence_not_implemented
- public_typed_knowledge_api_route_not_implemented
- governance_ui_not_implemented
- migration_and_backfill_not_executed
- writing_live_typed_knowledge_fetch_not_available
- writing_ui_governance_mutation_not_available
- persisted_typed_knowledge_cards_live_readback_not_verified

Writing-side interpretation:

- Ready: stable typed-knowledge object identities and handoff references can enter the writing context envelope.
- Ready: keyword-card rendering is deterministic and contract-tested.
- Not ready: the workbench cannot fetch typed knowledge from a live public typed-knowledge API.
- Not ready: the workbench cannot mutate typed-knowledge governance state from UI.
- Not ready: persisted typed-knowledge cards have not been proven to survive process restart through live DB/API readback.

## Validation

```bash
python3 main/backend/scripts/check_typed_writing_live_boundary.py --format text
/Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_typed_writing_live_boundary_checker_unittest.py -q
```

Expected checker position:

- readiness_state: `partial`
- closure_position: `deterministic_persistence_api_boundary_covered_live_db_api_ui_not_closed`
- unsupported closure claim: `typed_writing_live_boundary_closed`
