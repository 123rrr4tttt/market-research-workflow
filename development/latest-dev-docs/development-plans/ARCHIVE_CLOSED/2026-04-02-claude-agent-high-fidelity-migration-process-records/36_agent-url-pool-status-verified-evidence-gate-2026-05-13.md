# Agent URL-Pool Status Verified Evidence Gate

Date: 2026-05-13
Status: active gap reduction, no closure claim

## Scope

This pass addresses the next gap left by `35_agent-url-pool-candidate-to-writing-workbench-2026-05-13.md`: URL-pool candidates could be submitted and written as pending sources, but AgentCore had no first-class way to check whether the submitted URL had become stored project evidence before replacing pending writing language.

The target behavior is:

- read the current session's URL-pool submission artifact;
- reconcile submission URL/task id with recent ingest jobs when available;
- search already-stored project documents/sources for the submitted URL;
- return an explicit next gate:
  - `verified_evidence_ready_for_writing`
  - `wait_for_ingest_completion_or_retry_status`

## Implementation

- Added AgentCore tool `ingest.url_pool.status`.
  - Reads `ingest.url_pool_submissions.json`.
  - Resolves latest or explicit URL/task id.
  - Scans recent ingest jobs for matching URL or task id.
  - Searches project `documents` and `sources` through the existing structured-data search boundary.
  - Returns `verified`, `pending`, `evidence_items`, `job_matches`, `submission`, and `writing_guidance`.
- Exposed `ingest.url_pool.status` in source-discovery, material-collection, long-task, and writing tool windows.
- Added capability/tool-pool metadata so `/agent-chat/capabilities` shows it as an implemented core read-only tool.
- Updated native and JSON provider guidance:
  - call `ingest.url_pool.status` before replacing pending writing evidence;
  - only replace pending language with verified citations when project evidence exists;
  - keep pending language when the submitted source is still queued or missing stored evidence.

## Validation

- Focused backend tests:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q -k "ingest_url_pool_status or ingest_url_pool_submit or capabilities_route_marks_core or material_categories_are_shared or tool_window"` -> `5 passed, 67 deselected, 11 warnings`
- Backend Agent matrix:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_interactive_agent_runtime_unittest.py main/backend/tests/unit/test_agent_run_loop_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q` -> `109 passed, 11 warnings`

## Result

| Row | Before | After |
| --- | --- | --- |
| Pending URL-pool evidence | Agent could only read the submission artifact or generic ingest status separately. | `ingest.url_pool.status` reconciles submission, jobs, and stored project evidence. |
| Writing replacement gate | No first-class verified/pending decision. | Tool returns `verified_evidence_ready_for_writing` or `wait_for_ingest_completion_or_retry_status`. |
| Data boundary | Writing chain risked relying on queued task state. | Writing guidance now requires stored documents/sources before verified citation replacement. |

## Remaining Gap

This is still not a full external-source closure. Remaining work:

- configure and validate at least one non-DDG external provider or external-search MCP service;
- wire actual Celery/task completion events into session artifacts automatically, instead of requiring status reconciliation by URL/task id;
- add UI affordances for candidate/source history across sessions.
