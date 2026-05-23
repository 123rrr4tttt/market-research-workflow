<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/35_agent-url-pool-candidate-to-writing-workbench-2026-05-13.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/35_agent-url-pool-candidate-to-writing-workbench-2026-05-13.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent URL-Pool Candidate To Writing Workbench

Date: 2026-05-13
Status: active gap reduction, no closure claim

## Scope

This pass closes the next writing-chain gap left by `34_agent-live-search-empty-result-diagnostics-2026-05-13.md`: approved URL-pool candidates could be submitted and recovered, but the demonstrated loop did not yet bring the submitted source boundary back into the writing workbench.

The target behavior is:

- after a URL-pool candidate is submitted, a follow-up writing request can read the session submission artifact;
- the Agent can append a writing-workbench paragraph that clearly marks the source as pending until ingestion completion is confirmed;
- the flow does not pretend queued source collection is already verified evidence.

## Implementation

- Updated native and JSON AgentCore provider guidance:
  - when the user asks to use a just-submitted URL-pool candidate in writing, read session artifacts first;
  - use `agent_artifact.search` / `agent_artifact.read` before writing;
  - use `writing.document.insert_paragraph` for the writeback;
  - label queued sources as pending evidence until ingest completion is confirmed.
- Expanded the deterministic real-backend E2E provider:
  - follow-up request: `把刚才采集的候选来源写进工作台草稿，标记为待复核来源`
  - tool chain:
    - `agent_artifact.search`
    - `agent_artifact.read`
    - `writing.document.insert_paragraph`
  - inserted paragraph cites the URL-pool boundary and marks it as a pending source.
- Expanded the real-backend AgentChat Playwright scenario to verify:
  - the follow-up stream includes artifact read tools and writing insertion;
  - the writing workbench editor contains the URL-pool pending-source paragraph.

## Validation

- Frontend lint:
  - `(cd main/frontend-modern && npm run lint -- src/pages/AgentChatPage.tsx src/pages/agent-chat.css tests/e2e/agent-chat-real-backend-long-task.spec.ts)` -> `0 errors, 1 existing CSS ignored warning`
- Focused backend tests:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q -k "source_web_search or source_candidate_review or ingest_url_pool_submit or capabilities_route_marks_core"` -> `5 passed, 63 deselected, 11 warnings`
- Real-backend AgentChat E2E:
  - backend: `AGENT_CORE_E2E_SCRIPTED_PROVIDER_ENABLED=true PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8021`
  - frontend: `(cd main/frontend-modern && AGENT_CORE_REAL_BACKEND_E2E=1 VITE_API_PROXY_TARGET=http://127.0.0.1:8021 npm run test:e2e -- tests/e2e/agent-chat-real-backend-long-task.spec.ts --reporter=line)` -> `2 passed`
  - cleanup: `lsof -nP -iTCP:8021 -sTCP:LISTEN` returned no listener after stopping the test backend.

## Result

| Row | Before | After |
| --- | --- | --- |
| URL-pool source after submit | Candidate submission was visible, but not carried back into writing. | Follow-up can read submission artifacts and append a writing paragraph. |
| Evidence status | Risk of treating queued collection as verified. | Inserted text marks the source as pending until ingest completion. |
| Real UI path | Source-card approval stopped at task boundary. | E2E covers approval, reload recovery, artifact read, and writing workbench insertion. |

## Remaining Gap

This is still not a full external-source closure. Remaining work:

- configure and validate at least one non-DDG provider or external-search MCP service;
- poll or subscribe to actual URL-pool task completion and replace pending writing evidence with verified extracted evidence;
- add source-candidate history controls across sessions.
