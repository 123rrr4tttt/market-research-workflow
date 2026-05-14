# Agent Source Candidate Review Decision Loop

Date: 2026-05-13
Status: active gap reduction, no closure claim

## Scope

This pass closes the next gap left by `30_agent-source-candidate-review-ui-2026-05-13.md`: source candidates were visible, but the user could not make an inspectable per-candidate decision that returned a concrete next collection boundary.

The target behavior is:

- searched candidates remain distinct from ingested evidence;
- the user can approve, defer, or reject a candidate from the AgentChat card;
- the decision returns to AgentCore instead of being a frontend-only state change;
- approved candidates produce a concrete `source_library` or `url_pool` ingest payload.

## Implementation

- Added AgentCore tool `source.candidate.review`.
  - Writes a session artifact named `source.candidate_reviews.json`.
  - Records `approved`, `deferred`, and `rejected` decisions with candidate metadata, reason, idempotency key, counts, and next gate.
  - Approved source-library item candidates return an `ingest.source_library.run` payload.
  - Approved URL candidates return a `url_pool` ingest payload.
  - The tool performs no external I/O and does not claim ingestion has happened.
- Exposed `source.candidate.review` in external discovery, material collection, long-task investigation, and writing workbench AgentCore tool windows.
- Added provider guidance for native and JSON AgentCore:
  - when the user approves, defers, or rejects a concrete candidate, call `source.candidate.review`;
  - use `ingest_payload` and `next_gate` in the answer;
  - do not present searched candidates as already ingested evidence.
- Added AgentChat source-card actions:
  - `采集`
  - `暂缓`
  - `拒绝`
  Each action submits a model-owned follow-up turn with `source_candidate_review JSON`.
- Updated the real-backend scripted provider so candidate-card approval calls `source.candidate.review` and returns the URL-pool payload boundary.
- Added tool-pool metadata so the capabilities endpoint lists `source.candidate.review` as an implemented core tool.

## Validation

- Focused backend tests:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q -k "source_candidate_review or source_web_search or capabilities_route_marks_core"` -> `3 passed, 11 warnings`
- Backend Agent matrix:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_interactive_agent_runtime_unittest.py main/backend/tests/unit/test_agent_run_loop_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q` -> `106 passed, 11 warnings`
- Frontend lint:
  - `npm run lint -- src/pages/AgentChatPage.tsx src/pages/agent-chat.css tests/e2e/agent-chat-real-backend-long-task.spec.ts` -> `0 errors, 1 existing CSS ignored warning`
- Real-backend AgentChat E2E:
  - backend: `AGENT_CORE_E2E_SCRIPTED_PROVIDER_ENABLED=true PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8021`
  - frontend: `AGENT_CORE_REAL_BACKEND_E2E=1 VITE_API_PROXY_TARGET=http://127.0.0.1:8021 npm run test:e2e -- tests/e2e/agent-chat-real-backend-long-task.spec.ts --reporter=line` -> `2 passed`

## Result

| Row | Before | After |
| --- | --- | --- |
| Candidate action | Candidate card displayed a review gate but had no concrete decision loop. | Each card offers approve/defer/reject controls. |
| Model ownership | Candidate decision was not part of AgentCore. | Button submits a follow-up turn; AgentCore calls `source.candidate.review`. |
| Boundary substance | Candidate visibility did not produce a concrete ingest payload. | Approved URL candidates produce a `url_pool` payload; approved source-library candidates produce an `ingest.source_library.run` payload. |
| Auditability | There was no durable record of candidate review decisions. | Decisions are recorded in `source.candidate_reviews.json` session artifacts with counts and idempotency. |

## Remaining Gap

This is still not a full external-source closure. Remaining work:

- execute URL-pool ingest directly from the approved payload through a first-class AgentCore tool;
- support per-candidate decision state in the UI after reload instead of only showing the session artifact and latest tool result;
- validate the same path against a live non-E2E external search provider.
