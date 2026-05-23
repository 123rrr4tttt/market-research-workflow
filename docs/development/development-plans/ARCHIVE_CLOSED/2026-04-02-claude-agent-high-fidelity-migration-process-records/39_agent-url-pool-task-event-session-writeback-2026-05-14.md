<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/39_agent-url-pool-task-event-session-writeback-2026-05-14.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/39_agent-url-pool-task-event-session-writeback-2026-05-14.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent URL-Pool Task Event Session Writeback

Date: 2026-05-14
Status: active gap reduction, no closure claim

## Scope

This pass addresses the remaining gap from `38_agent-source-history-read-tool-and-ui-recovery-2026-05-14.md`: URL-pool submissions were visible in Agent session artifacts, but asynchronous task completion/failure was still not written back into the same session automatically.

The target behavior is:

- `ingest.url_pool.submit` passes a session marker into queued URL-pool work;
- the Celery URL-pool task records completed/failed task events back into the originating Agent session;
- `ingest.url_pool.status` reads those task events before deciding whether evidence is pending, failed, completed-without-record, or verified;
- `source.history.read` includes URL-pool task events for resumed investigations.

## Implementation

- Updated `ingest.url_pool.submit`:
  - creates a deterministic `agent-url-pool-*` task id;
  - submits async URL-pool work through `apply_async(..., task_id=...)`;
  - injects `_agent_core_url_pool_submission` into `search_options` with session id, artifact name, idempotency key, candidate review key, project key, URL, task id, and source call id.
- Updated `task_ingest_url_via_source_library`:
  - extracts the Agent submission marker from `search_options`;
  - records `completed` events after successful frontdoor execution;
  - records `failed` events before re-raising failures.
- Added session writeback helper:
  - writes/updates `ingest.url_pool_task_events.json`;
  - updates the matching `ingest.url_pool_submissions.json` submission with `task_events`, `latest_task_status`, timestamps, task result, or task error;
  - appends `ingest.url_pool.task.completed` / `ingest.url_pool.task.failed` events to the Agent session event stream.
- Updated `ingest.url_pool.status`:
  - reads `ingest.url_pool_task_events.json`;
  - exposes `task_events`, `latest_task_event`, and `task_event_artifact_found`;
  - distinguishes `verified_evidence_ready_for_writing`, `wait_for_ingest_completion_or_retry_status`, `ingest_completed_without_verified_project_record`, and `url_pool_ingest_failed_review_error_or_retry`.
- Updated `source.history.read`:
  - reads URL-pool task event artifacts;
  - returns per-session and total task event counts.
- Updated AgentChat source decision recovery:
  - displays latest URL-pool task status from submission `task_events` when available.
  - merges nested submit responses, source history task events, and task-event artifacts without letting older review `next_gate` text overwrite terminal URL-pool status.

## Validation

- Focused backend tests:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q -k "url_pool or source_history or capabilities_route_marks_core or material_categories_are_shared or tool_window"` -> `9 passed, 67 deselected, 11 warnings`
- Compile check:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m py_compile main/backend/app/services/tasks.py main/backend/app/services/agent_core/project_tools.py` -> passed
- Frontend lint:
  - `(cd main/frontend-modern && npm run lint -- src/pages/AgentChatPage.tsx src/pages/agent-chat.css)` -> `0 errors, 1 existing CSS ignored warning`
- Backend Agent matrix:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_interactive_agent_runtime_unittest.py main/backend/tests/unit/test_agent_run_loop_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q` -> `113 passed, 11 warnings`
- Frontend build:
  - `(cd main/frontend-modern && npm run build)` -> passed
- Browser-level real-backend AgentChat E2E:
  - `AGENT_CORE_E2E_SCRIPTED_PROVIDER_ENABLED=true PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8021`
  - `(cd main/frontend-modern && AGENT_CORE_REAL_BACKEND_E2E=1 VITE_API_PROXY_TARGET=http://127.0.0.1:8021 npm run test:e2e -- tests/e2e/agent-chat-real-backend-long-task.spec.ts --reporter=line)` -> `2 passed`
- Follow-up focused checks after browser E2E wiring:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q -k "url_pool or source_history"` -> `6 passed, 67 deselected, 11 warnings`
  - `(cd main/frontend-modern && npm run lint -- tests/e2e/agent-chat-real-backend-long-task.spec.ts src/pages/AgentChatPage.tsx src/pages/agent-chat.css)` -> `0 errors, 1 existing CSS ignored warning`

## Result

| Row | Before | After |
| --- | --- | --- |
| Async URL-pool task id | Submit returned Celery id, but task had no session marker. | Submit uses deterministic task id and passes an Agent session marker. |
| Background completion | Completion/failure stayed in task/job layer. | Task writes completed/failed events into Agent session artifacts and events. |
| Status gate | Status reconciled submission, jobs, and stored evidence. | Status also reads task events and can distinguish completed-without-record and failed states. |
| Resume/history | Source history had reviews/submissions only. | Source history includes URL-pool task events for resumed investigations. |
| Browser recovery | Candidate card showed task id, but could keep the old review `next_gate`. | Candidate card recovers `URL-pool completed` from task events after refresh and status follow-up. |

## Remaining Gap

This does not prove live external provider quality. Remaining work:

- configure at least one non-DDG provider or external-search MCP and rerun a live candidate search;
- rerun the same writeback path against a non-scripted provider once live provider credentials or an external-search MCP are configured.
