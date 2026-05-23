<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/32_agent-url-pool-ingest-submit-tool-2026-05-13.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/32_agent-url-pool-ingest-submit-tool-2026-05-13.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent URL-Pool Ingest Submit Tool

Date: 2026-05-13
Status: active gap reduction, no closure claim

## Scope

This pass closes the concrete gap left by `31_agent-source-candidate-review-decision-loop-2026-05-13.md`: approved external URL candidates produced a `url_pool` payload, but AgentCore did not have a first-class tool to submit that payload into the existing URL-pool/source-library ingestion frontdoor.

The target behavior is:

- external candidates stay distinct from already ingested project evidence;
- a reviewed and approved URL candidate can enter a real collection boundary;
- the boundary is model-visible and inspectable as an AgentCore tool call;
- interactive chat returns quickly by queuing ingestion and exposing the task/status boundary.

## Implementation

- Added AgentCore tool `ingest.url_pool.submit`.
  - Accepts either direct URL arguments or the `url_pool` `ingest_payload` returned by `source.candidate.review`.
  - Defaults to `async_mode=true` for chat use.
  - Queues existing `task_ingest_url_via_source_library` for async collection.
  - Uses existing `services.ingest.url_pool.ingest_url_via_source_library_frontdoor` for sync execution when explicitly requested.
  - Records submissions in a session artifact named `ingest.url_pool_submissions.json` with URL, project key, query terms, dispatch result, task id, idempotency key, and counts.
  - Replays duplicate idempotency keys without re-queuing the URL.
- Updated `source.candidate.review` next gate for approved URLs to `run_ingest.url_pool.submit_with_payload`.
- Exposed `ingest.url_pool.submit` in AgentCore tool windows for source discovery, material collection, long-task investigation, and writing workbench contexts.
- Added tool-pool and capability metadata so `/agent-chat/capabilities` lists `ingest.url_pool.submit` as an implemented core tool.
- Updated native and JSON provider guidance:
  - after `source.candidate.review` returns an approved URL-pool payload and the user chose collection, call `ingest.url_pool.submit`;
  - report task id or the next inspectable ingest state rather than a purely formal completion line.
- Updated the deterministic real-backend E2E provider so the source-card `采集` action executes:
  - `source.candidate.review`
  - `ingest.url_pool.submit`
  - final answer with the inspectable collection boundary.

## Validation

- Focused backend tests:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q -k "source_candidate_review or ingest_url_pool_submit or material_categories_are_shared or capabilities_route_marks_core or tool_window"` -> `5 passed, 65 deselected, 11 warnings`
- Backend Agent matrix:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_interactive_agent_runtime_unittest.py main/backend/tests/unit/test_agent_run_loop_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q` -> `107 passed, 11 warnings`
- Frontend lint:
  - `(cd main/frontend-modern && npm run lint -- src/pages/AgentChatPage.tsx src/pages/agent-chat.css tests/e2e/agent-chat-real-backend-long-task.spec.ts)` -> `0 errors, 1 existing CSS ignored warning`
- Real-backend AgentChat E2E:
  - backend: `AGENT_CORE_E2E_SCRIPTED_PROVIDER_ENABLED=true PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8021`
  - frontend: `(cd main/frontend-modern && AGENT_CORE_REAL_BACKEND_E2E=1 VITE_API_PROXY_TARGET=http://127.0.0.1:8021 npm run test:e2e -- tests/e2e/agent-chat-real-backend-long-task.spec.ts --reporter=line)` -> `2 passed`
  - cleanup: `lsof -nP -iTCP:8021 -sTCP:LISTEN` returned no listener after stopping the test backend.

## Result

| Row | Before | After |
| --- | --- | --- |
| Approved URL candidate | `source.candidate.review` returned a payload but no first-class AgentCore ingest execution tool existed. | `ingest.url_pool.submit` accepts the payload and queues existing URL-pool ingestion. |
| User-facing turn | The final answer could only say a payload was ready. | The final answer can cite a submitted URL-pool boundary and task/status inspection path. |
| Auditability | Candidate decision artifact existed, but collection submission was not persisted in the Agent session. | `ingest.url_pool_submissions.json` records dispatch result and idempotency. |
| E2E evidence | Candidate approval E2E stopped at payload generation. | Real-backend E2E now asserts both `source.candidate.review` and `ingest.url_pool.submit` in the stream. |

## Remaining Gap

This is still not a full external-source closure. Remaining work:

- persist per-candidate decision state in the UI after reload, not only through latest run details/artifacts;
- validate the same candidate-to-ingest loop against a live non-E2E external search provider with network variability and trust gating;
- connect submitted URL-pool task completion back into writing/workbench evidence insertion so newly collected material can be cited or inserted in the same long task.
