# Wave16 Typed Knowledge API Route Contract Evidence (2026-05-22)

Scope: `2026-03-07-typed-knowledge-organization` API / route boundary.

Shared indexes were intentionally not edited.

## Result

- Added `typed_knowledge.public_api_route_contract.v1` as the public route contract.
- Exposed `GET /api/v1/typed-knowledge/persistence-boundary`.
- The route returns the existing `status/data/error/meta` envelope shape with:
  - `public_api_route: true`
  - `api_contract: true`
  - `live_db_persistence: false`
  - `governance_ui: false`
- The route preserves project-scoped identity readback through the `project_key` query parameter.
- The Wave15 live-boundary checker now distinguishes this deterministic route contract from writing-workbench live typed-knowledge fetch.

## Closed Deterministic Slice

- `main/backend/app/api/typed_knowledge.py`
  - public FastAPI route and typed response model
- `main/backend/app/api/__init__.py`
  - route mounted under `/api/v1`
- `main/backend/app/services/typed_knowledge/persistence_boundary.py`
  - public route contract envelope
  - route contract validation
  - project-scoped sample readback
- `main/backend/tests/integration/test_typed_knowledge_api_route_unittest.py`
  - TestClient coverage for the public route
  - OpenAPI schema visibility
  - project-scoped identity readback
- `main/backend/tests/unit/test_typed_knowledge_persistence_boundary_unittest.py`
  - route contract service validation and live DB overclaim guard
- `main/backend/scripts/check_typed_writing_live_boundary.py`
  - records the public route contract as deterministic coverage while retaining live DB and writing-fetch gaps

## Remaining Boundaries

- live_db_persistence_not_implemented
- live_db_backed_typed_knowledge_api_readback_not_verified
- governance_ui_not_implemented
- migration_and_backfill_not_executed
- writing_live_typed_knowledge_fetch_not_available
- writing_ui_governance_mutation_not_available
- persisted_typed_knowledge_cards_live_readback_not_verified

The branch does not add a typed-knowledge DB table, migration/backfill run, governance UI, or writing-workbench live fetch integration.

## Validation

```bash
python3 scripts/check_current_dev_wave16_plan.py
/Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_typed_knowledge_contracts_unittest.py main/backend/tests/unit/test_typed_knowledge_persistence_boundary_unittest.py main/backend/tests/unit/test_typed_writing_live_boundary_checker_unittest.py main/backend/tests/integration/test_typed_knowledge_api_route_unittest.py -q
python3 main/backend/scripts/check_typed_writing_live_boundary.py --format text
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 scripts/check_current_dev_status_evidence.py
git diff --check
```

Observed:

- `check_current_dev_wave16_plan`: passed
- related pytest: `24 passed`
- `check_typed_writing_live_boundary`: passed
- `check_current_dev_status_evidence`: passed
- `git diff --check`: passed
