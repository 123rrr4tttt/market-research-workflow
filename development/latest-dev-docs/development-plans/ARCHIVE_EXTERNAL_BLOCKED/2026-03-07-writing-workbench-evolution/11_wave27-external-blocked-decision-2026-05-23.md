# Wave27 External-Blocked Decision (2026-05-23)

Status: `external_blocked` / `wave27_checked`

## Decision

Move `2026-03-07-writing-workbench-evolution` from `CURRENT_DEV` to `ARCHIVE_EXTERNAL_BLOCKED`.

Repo-local blockers were not found in the current evidence set. The Writing Workbench typed-card request shape and backend readback are deterministic; the remaining closure conditions depend on live DB/API/UI execution and governance mutation evidence.

## Repo-Local Evidence

- The Writing Workbench consumer path preserves `metadata_json.typed_knowledge_context` using `writing.typed_knowledge_context.v1`.
- The keyword-card request uses the existing `POST /api/v1/writing/keyword-cards` contract with default `document/resource/graph` sources.
- Backend readback feeds the typed-knowledge API boundary request body into `aggregate_cards()` with external card sources stubbed out.
- Preview/detail readback confirms the generated card remains `source_type=resource` and `publisher=typed_knowledge`.
- The browser/live closure flags remain false and are guarded by backend tests.

## Remaining External Conditions

- live DB-backed typed-knowledge persistence and API readback
- live browser UI request/readback against persisted typed cards
- governance UI mutation and human acceptance evidence
- migration/backfill execution evidence

## Validation

Run from repository root:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_typed_writing_live_boundary.py --format text
/Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_writing_keyword_card_service_unittest.py main/backend/tests/unit/test_typed_writing_live_boundary_checker_unittest.py main/backend/tests/integration/test_typed_knowledge_api_route_unittest.py -q
cd main/frontend-modern && ./node_modules/.bin/playwright test tests/e2e/writing-workbench.spec.ts tests/e2e/agent-chat-writing-crossflow.spec.ts --project=chromium
```

Do not move this topic to `ARCHIVE_CLOSED` until the live conditions above are recorded.

## Wave27 Validation Result

- `check_typed_writing_live_boundary.py --format text`: passed; deterministic coverage is present while live DB/API/UI/governance/migration gaps remain open.
- `check_typed_knowledge_persistence_api_boundary.py`: passed; typed-card request/response readback remains repo-local deterministic evidence.
- Targeted backend pytest: `21 passed`.
- Targeted frontend Playwright e2e: `6 passed`, `2 skipped`.
- Targeted docs link check for the archived typed/writing directories and `ARCHIVE_EXTERNAL_BLOCKED/INDEX.md`: passed.
