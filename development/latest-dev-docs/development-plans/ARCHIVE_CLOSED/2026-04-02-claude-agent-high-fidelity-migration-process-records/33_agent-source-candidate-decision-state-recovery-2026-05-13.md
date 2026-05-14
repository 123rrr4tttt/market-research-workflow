# Agent Source Candidate Decision State Recovery

Date: 2026-05-13
Status: active gap reduction, no closure claim

## Scope

This pass closes the immediate UI recovery gap left by `32_agent-url-pool-ingest-submit-tool-2026-05-13.md`: candidate approval/defer/reject was persisted in AgentCore artifacts, but the AgentChat source candidate card did not show the decision state after page reload unless the user inspected raw run details or artifacts.

The target behavior is:

- source candidate cards remain concrete after reload even if the original search event falls outside the latest capability-call window;
- approve/defer/reject decisions are visible on the card itself;
- approved URL-pool submissions show the queued task boundary;
- the UI derives state from AgentCore events, tool results, and session artifacts instead of a frontend-only flag.

## Implementation

- Added source candidate decision recovery in `AgentChatPage`.
  - Reads `source.candidate.review` tool results.
  - Reads `source.candidate_reviews.json` session artifacts.
  - Reads `ingest.url_pool.submit` tool results.
  - Reads `ingest.url_pool_submissions.json` session artifacts.
- Added review-state fields to source quality cards:
  - decision: approved/deferred/rejected
  - reason
  - next gate
  - task id
  - reviewed/submitted timestamp
- Source quality card construction now creates cards from candidate-review results as well as discovery/search results, so the reviewed candidate is still visible after reload.
- Added a visible decision block on each reviewed card:
  - `已采集`
  - `已暂缓`
  - `已拒绝`
  - optional task id and next gate.
- Added selected-button state for the chosen decision.

## Validation

- Frontend lint:
  - `(cd main/frontend-modern && npm run lint -- src/pages/AgentChatPage.tsx src/pages/agent-chat.css tests/e2e/agent-chat-real-backend-long-task.spec.ts)` -> `0 errors, 1 existing CSS ignored warning`
- Real-backend AgentChat E2E:
  - backend: `AGENT_CORE_E2E_SCRIPTED_PROVIDER_ENABLED=true PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8021`
  - frontend: `(cd main/frontend-modern && AGENT_CORE_REAL_BACKEND_E2E=1 VITE_API_PROXY_TARGET=http://127.0.0.1:8021 npm run test:e2e -- tests/e2e/agent-chat-real-backend-long-task.spec.ts --reporter=line)` -> `2 passed`
  - The E2E now reloads after candidate approval and asserts the reviewed card shows `已采集` and the `e2e-url-pool` task boundary.
  - cleanup: `lsof -nP -iTCP:8021 -sTCP:LISTEN` returned no listener after stopping the test backend.

## Result

| Row | Before | After |
| --- | --- | --- |
| Reviewed candidate after reload | Decision was only discoverable from run details/artifacts. | Candidate card displays the recovered decision state. |
| Candidate card source | Cards depended on discovery/search result shape. | Cards can also be reconstructed from review results and URL-pool submission artifacts. |
| Submitted task visibility | URL-pool task id appeared in tool details only. | Reviewed card can show the submitted task boundary. |
| Frontend-only state risk | Button click state was not durable. | State is recovered from AgentCore-owned persisted data. |

## Remaining Gap

This is still not a full external-source closure. Remaining work:

- validate the candidate-to-ingest loop against a live non-E2E external search provider with real network variability and trust-gate behavior;
- connect completed URL-pool task outputs back into writing/workbench evidence insertion so newly collected material can be cited or inserted in the same long task;
- add richer source-candidate history controls, such as filtering approved/deferred/rejected candidates across sessions.
