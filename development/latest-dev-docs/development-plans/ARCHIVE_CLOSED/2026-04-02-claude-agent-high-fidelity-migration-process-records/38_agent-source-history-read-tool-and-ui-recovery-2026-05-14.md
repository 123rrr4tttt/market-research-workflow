# Agent Source History Read Tool And UI Recovery

Date: 2026-05-14
Status: active gap reduction, no closure claim

## Scope

This pass addresses a remaining long-investigation and writing-workbench gap: candidate review and URL-pool submission state could be recovered inside the current UI stream, but the model had no first-class read tool for prior source decisions when a user resumed a source investigation or asked to write from earlier candidates.

The target behavior is:

- recover prior candidate decisions before repeating external search;
- include current session and optional same-project recent sessions;
- expose approved/deferred/rejected counts and URL-pool submissions;
- keep queued URL-pool candidates separate from verified writing evidence.

## Implementation

- Added AgentCore read-only tool `source.history.read`.
  - Reads `source.candidate_reviews.json` artifacts.
  - Reads `ingest.url_pool_submissions.json` artifacts.
  - Supports `include_recent_sessions=true` to include recent same-project sessions.
  - Returns session-scoped counts, reviews, submissions, and `next_gate`.
- Exposed `source.history.read` in:
  - source discovery;
  - material collection;
  - long-task investigation;
  - writing workbench tool windows;
  - tool pool and capability registry;
  - material ontology as internal existing project/session state.
- Updated native and JSON provider guidance:
  - call `source.history.read` before re-searching when continuing source work;
  - call `ingest.url_pool.status` before using queued URL-pool submissions as verified writing evidence.
- Updated AgentChat source card recovery:
  - consumes `source.history.read.sessions[].reviews`;
  - consumes `source.history.read.sessions[].submissions`;
  - reconstructs candidate cards and decision state from history tool output.
- Added compact source-history filtering in the AgentChat source quality panel:
  - all;
  - open;
  - approved;
  - deferred;
  - rejected.

## Validation

- Focused backend tests:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q -k "source_history or source_web_search or material_categories_are_shared or capabilities_route_marks_core or tool_window"` -> `7 passed, 67 deselected, 11 warnings`
- Frontend lint:
  - `(cd main/frontend-modern && npm run lint -- src/pages/AgentChatPage.tsx)` -> passed
  - `(cd main/frontend-modern && npm run lint -- src/pages/AgentChatPage.tsx src/pages/agent-chat.css)` -> `0 errors, 1 existing CSS ignored warning`
- Frontend build:
  - `(cd main/frontend-modern && npm run build)` -> passed

## Result

| Row | Before | After |
| --- | --- | --- |
| Resume source investigation | Model had to infer from recent stream/artifacts or re-search. | `source.history.read` returns prior reviews and submissions. |
| Cross-session continuity | No model-facing same-project recent-session source state. | Optional `include_recent_sessions` reads recent same-project source history. |
| Frontend recovery | Candidate cards recovered current events/artifacts, but not source-history tool output. | Candidate cards can rebuild from `source.history.read` results and filter by decision state. |
| Writing evidence boundary | Prior URL-pool submissions could be mistaken for verified evidence. | Tool guidance keeps status verification as the next gate. |

## Remaining Gap

This is still not full source-history closure. Remaining work:

- wire completed ingest job events into session artifacts automatically;
- validate with a configured non-DDG provider or mounted external-search MCP.
