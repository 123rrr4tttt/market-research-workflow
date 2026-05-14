# Agent Core Live Scenario Matrix

Run time: 2026-05-11 17:53 PDT

Scope: validate the current Agent Chat system from actual user-facing scenarios, then fix issues that block free conversation, project-aware tool use, governed tool execution, and visible frontend interaction.

## Matrix Result

| Scenario | Expected behavior | Result | Evidence |
| --- | --- | --- | --- |
| Free conversation | User can ask a normal question without mechanical routing or approval fallback | PASS | Browser UI smoke returned `可以，现在可以自由对话。` in about 3s after page reload; API probe returned HTTP 200 in 9.44s |
| Project data question | Model can understand a broad project-data question and call project/source tools as needed | PASS | Live stream completed in 14.96s with `project.summary.read`, `project.structured_data.search`, `source_library.item.list`, `ingest.status.read`, and `agent_session.context.read` |
| Source library execution | High-risk source-library execution becomes a governed approval, not a fake answer or silent failure | PASS | Live stream returned `permission_requested` for `ingest.source_library.run` in 5.68s; frontend e2e verified visible approval controls |
| Frontend interaction | Chat page has stable input, visible run details, and approval state | PASS | Browser reload on `http://127.0.0.1:5174/#agent-chat.html` found `agent-chat-input`, placeholder `输入问题或任务`, and runtime panel |
| Mobile layout | Chat interface does not overflow on mobile viewport | PASS | `npm run test:e2e -- tests/e2e/agent-chat.spec.ts --reporter=list`: mobile scenario passed |

## Fixes Applied During Matrix

- Normalized model tool-call arguments before schema validation and execution.
- Injected request `project_key` into project-scoped tools when the model omits it.
- Stripped unsupported contextual arguments from strict tool schemas when the model over-supplies session context.
- Normalized `item_key` to `items` for source-library execution.
- Held the persistent Codex app-server mount lock through endpoint readiness, preventing duplicate first-call mounts.
- Added a compact no-tools JSON prompt path for ordinary conversation.
- Updated Agent Chat frontend selectors, input copy, pending-approval visibility, and e2e expectations.

## Verification

- `/Users/wangyiliang/.local/bin/python3.11 -m pytest -q tests/unit/test_agent_core_unittest.py tests/integration/test_agent_chat_api_unittest.py tests/unit/test_codex_cli_llm_fallback_unittest.py`
  - `42 passed, 11 warnings`
- `/Users/wangyiliang/.local/bin/python3.11 -m pytest -q tests/unit/test_source_candidate_trust_unittest.py tests/unit/test_source_library_url_pool_adapter_unittest.py tests/integration/test_writing_api_unittest.py tests/unit/test_writing_document_service_unittest.py`
  - `20 passed, 11 warnings`
- `npm run test:e2e -- tests/e2e/agent-chat.spec.ts --reporter=list`
  - `4 passed`
- `npm run lint`
  - `0 errors, 3 existing warnings in AgentChatPage.tsx`
- `npm run build`
  - production build succeeded

## Remaining Gaps

- Latency is functional but not yet Claude Code level: free chat is roughly 3s in warmed browser UI, 9s by direct API probe, and project-aware tool answers are roughly 15-17s.
- Writing workbench has backend writing coverage, but there is still no dedicated frontend e2e covering canvas-style paragraph insertion and revision.
- Default system Python is still not the right test runtime for this repo; use `/Users/wangyiliang/.local/bin/python3.11` or `main/backend/.venv311`.
