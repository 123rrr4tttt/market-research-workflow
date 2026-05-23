# Wave27 External-Blocked Decision (2026-05-23)

Status: `external_blocked` / `wave27_checked`

## Decision

Move `2026-03-07-typed-knowledge-organization` from `CURRENT_DEV` to `ARCHIVE_EXTERNAL_BLOCKED`.

Repo-local blockers were not found in the current evidence set. The deterministic typed-knowledge persistence/readback/API boundary is already covered; remaining conditions require live DB/API/UI evidence and should not keep this topic counted as an active `CURRENT_DEV` partial.

## Repo-Local Evidence

- `JsonlTypedKnowledgeRepository` durable readback reopens typed-knowledge records from local JSONL without claiming live DB writes.
- `GET /api/v1/typed-knowledge/persistence-boundary` exposes the public route contract and retains `status/data/error/meta`.
- The persisted-card request/response readback reconstructs `metadata_json.typed_knowledge_context`, builds the writing keyword-card request, and verifies a `publisher=typed_knowledge` resource-card response.
- Overclaim guards keep `live_db_closure=false`, `live_api_closure=false`, and `live_ui_closure=false`.

## Remaining External Conditions

- live typed-knowledge DB table/model, migration, write, and readback evidence
- live DB-backed typed-knowledge API request/response evidence
- browser UI readback against persisted live data
- governance UI mutation and human acceptance evidence
- migration/backfill execution evidence

## Validation

Run from repository root:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_typed_writing_live_boundary.py --format text
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_typed_knowledge_durable_repository_readback.py
/Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_typed_knowledge_persistence_boundary_unittest.py main/backend/tests/unit/test_writing_keyword_card_service_unittest.py main/backend/tests/unit/test_typed_writing_live_boundary_checker_unittest.py main/backend/tests/integration/test_typed_knowledge_api_route_unittest.py -q
```

Do not move this topic to `ARCHIVE_CLOSED` until the live conditions above are recorded.

## Wave27 Validation Result

- `check_typed_writing_live_boundary.py --format text`: passed; `closure_claim_allowed=false` and remaining live gaps are explicit.
- `check_typed_knowledge_durable_repository_readback.py`: passed; JSONL durable repository readback is closed while `live_db_persistence=false`.
- `check_typed_knowledge_persistence_api_boundary.py`: passed; deterministic persisted-card request/response boundary is ready.
- Targeted backend pytest: `21 passed`.
- Targeted docs link check for the archived typed/writing directories and `ARCHIVE_EXTERNAL_BLOCKED/INDEX.md`: passed.
