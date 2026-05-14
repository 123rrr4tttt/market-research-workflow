# Expanded Agent And Writing Scenario Matrix

Run time: 2026-05-11 18:06 PDT

Scope: extend the previous Agent Core live matrix to cover the missing user-facing paths: writing workbench creation/edit/review, approval rejection, long-task/session replay, artifact replay, project/source-library contracts, and frontend mobile layout.

## Matrix Result

| Scenario | Result | Evidence |
| --- | --- | --- |
| Casual chat | PASS | Agent Chat e2e free conversation returned a streamed model answer with `0 tools` and no execution chrome |
| Project awareness | PASS | Agent Chat e2e `项目里有什么数据` used read-only project/source tools and did not request approval |
| Governed source execution | PASS | Agent Chat e2e explicit source-library execution produced `agent_core.permission_requested`, showed the approval card, and rejected it through `/agent-approvals/{id}/resolve` |
| Writing creation/edit/preview | PASS | New Writing Workbench e2e created a document through the UI, saved it through the live backend, switched to split mode, and verified preview text |
| Agent writing review | PASS | New Writing Workbench e2e seeded `metadata_json.agent_updates`, opened the Agent panel, located the inserted paragraph by textarea selection, accepted it, and verified persisted `review_status=accepted` |
| Writing mobile layout | PASS | New Writing Workbench mobile e2e verified toolbar, canvas, stage, and editor do not horizontally overflow |
| Agent Chat mobile layout | PASS | Existing Agent Chat mobile scenario passed after a live chat turn |
| Long task and control replay | PASS | `test_agent_runtime_scenario_replay_unittest.py`, `test_agent_control_tools_unittest.py` passed |
| Artifact replay and idle status | PASS | `test_agent_runtime_artifact_idle_replay_unittest.py` passed after narrowing idle-status expectation to the actual fast status path |
| Source-library and project-key contracts | PASS | Source-library core, URL pool adapter, and project-key policy suites passed |

## Fixes Added

- Added strict tool-argument normalization for `item_key -> items` so aliased source-library calls no longer fail schema validation.
- Added regression coverage for project tool argument normalization with request-sourced `project_key` and stripped contextual extras.
- Made Agent Chat frontend request high-risk approval by default for user-facing chat turns, preserving ordinary free chat while gating write/external tools.
- Added stable Writing Workbench selectors for the page shell, toolbar, title, editor, panels, mode buttons, save/export/refresh controls, document cards, and Agent update controls.
- Added Writing Workbench e2e coverage for create/save/preview, Agent update locate/accept, and mobile layout.
- Extended Agent Chat e2e so the source-library approval card is not only visible but also rejectable.
- Removed remaining frontend lint warnings in Agent Chat by stabilizing refetch dependencies and memoizing task/artifact arrays.

## Verification Commands

- `/Users/wangyiliang/.local/bin/python3.11 -m pytest -q tests/unit/test_agent_core_unittest.py tests/integration/test_agent_chat_api_unittest.py`
  - `41 passed`
- `/Users/wangyiliang/.local/bin/python3.11 -m pytest -q tests/integration/test_agent_runtime_scenario_replay_unittest.py tests/integration/test_agent_runtime_artifact_idle_replay_unittest.py tests/integration/test_writing_api_unittest.py tests/integration/test_writing_llm_actions_api_unittest.py tests/unit/test_agent_control_tools_unittest.py tests/unit/test_source_candidate_trust_unittest.py`
  - `30 passed, 5 subtests passed`
- `/Users/wangyiliang/.local/bin/python3.11 -m pytest -q tests/core_business/test_source_library_core_contract.py tests/unit/test_source_library_url_pool_adapter_unittest.py tests/integration/test_project_key_policy_unittest.py`
  - `70 passed`
- `npm run test:e2e -- tests/e2e/agent-chat.spec.ts tests/e2e/writing-workbench.spec.ts --reporter=list`
  - `7 passed`
- `npm run lint`
  - passed with no warnings
- `npm run build`
  - production build succeeded
- Browser verification on `http://127.0.0.1:5174`
  - Agent Chat exposed `agent-chat-input` and runtime panel
  - Writing Workbench exposed `writing-workbench-page`, `writing-workbench-toolbar`, and `writing-markdown-editor`

## Risk Resolution Pass

Run time: 2026-05-11 18:36 PDT

| Previously Open Risk | Resolution | Evidence |
| --- | --- | --- |
| Agent Chat live latency had no local acceleration path beyond waiting on the model. | Added targeted local reductions and observability: structured-data targeted search skips per-dataset `count(*)`, source-library agent context uses a short TTL cache, and the persistent Codex core reports start/reuse/invoke timing. | Backend status showed the Codex core mounted once with `start_count=1`, `reuse_count=4`, `invoke_count=5`, idle TTL `300`, and last invoke timing captured. Focused backend regression suite passed. |
| No browser-level Chat -> Writing same-scenario coverage. | Added `agent-chat-writing-crossflow.spec.ts`, covering Agent Chat context persistence, same-project navigation into Writing Workbench, live document save, backend readback, and return to Chat. | `npm run test:e2e -- tests/e2e/agent-chat-writing-crossflow.spec.ts tests/e2e/writing-workbench.spec.ts tests/e2e/agent-chat.spec.ts --reporter=list` returned `8 passed`. |
| Live e2e wrote durable test data to `demo_proj`. | Added isolated e2e project helpers, per-run project creation, writing-document soft delete, and final hard project cleanup. Writing Workbench e2e no longer uses `demo_proj`. | Cleanup probe created an `e2e_probe_*` project, saved a writing document, soft-deleted the document, hard-deleted the project, and confirmed no `e2e_*` project residue remained. |
| Newly created projects could fail Writing Workbench saves because project schemas lacked writing tables. | Added writing workbench tables to new-project table provisioning and locked it with a core contract test. | `test_create_project_table_set_includes_writing_workbench_tables` passed; the crossflow and writing e2e suites now create isolated projects and save documents successfully. |
| Source execution approval needed to stay governed while preserving free chat. | Agent Chat streaming requests now enable high-risk approval by default and expose stable approval test hooks. The source execution e2e verifies permission request display and rejection resolution. | Agent Chat e2e observed `agent_core.permission_requested`, displayed the approval card, rejected through `/api/v1/agent-approvals/{id}/resolve`, and showed the rejection result. |

## Follow-up Verification Commands

- `/Users/wangyiliang/.local/bin/python3.11 -m pytest -q tests/unit/test_agent_core_unittest.py tests/integration/test_agent_chat_api_unittest.py tests/integration/test_agent_runtime_artifact_idle_replay_unittest.py tests/integration/test_writing_api_unittest.py tests/core_business/test_projects_core_contract.py tests/unit/test_structured_data_search_unittest.py tests/unit/test_codex_cli_llm_fallback_unittest.py`
  - `73 passed, 11 warnings in 5.90s`
- `/Users/wangyiliang/.local/bin/python3.11 -m pytest -q tests/core_business/test_projects_core_contract.py tests/integration/test_writing_api_unittest.py tests/unit/test_structured_data_search_unittest.py tests/unit/test_codex_cli_llm_fallback_unittest.py`
  - `29 passed`
- `/Users/wangyiliang/.local/bin/python3.11 -m pytest -q tests/integration/test_writing_api_unittest.py tests/integration/test_agent_chat_api_unittest.py`
  - `25 passed`
- `npm run lint`
  - passed with no warnings
- `npm run build`
  - production build succeeded
- `npm run test:e2e -- tests/e2e/agent-chat-writing-crossflow.spec.ts tests/e2e/writing-workbench.spec.ts tests/e2e/agent-chat.spec.ts --reporter=list`
  - `8 passed`
- Browser verification on `http://127.0.0.1:5174`
  - Agent Chat exposed `agent-chat-page`, `agent-chat-input`, `agent-chat-send-button`, and the runtime panel.
  - Writing Workbench exposed `writing-workbench-page`, `writing-workbench-toolbar`, `writing-markdown-editor`, and `writing-save`.

## Residual Boundary

- Upstream model reasoning time is still external to this project. The local system now reduces avoidable pre/post-model latency and exposes persistent-core reuse metrics, but absolute answer time will still vary with Codex/OpenAI core response latency and requested task complexity.

## Runtime State

- Backend restarted with latest code on `127.0.0.1:8000` in detached screen session `mrw-backend-8000`.
- Persistent Codex core remounted after the post-restart source-library approval probe; idle TTL remains 300 seconds.
- Frontend restarted with latest code on `127.0.0.1:5174` in detached screen session `mrw-frontend-5174`.
