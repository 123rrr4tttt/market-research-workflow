# Agent Runtime V2 Model Final Answer And Agent Batch Governed Fallback

Date: 2026-05-10 PST
Source plan: `02_claude-code-level-agent-interaction-todo-2026-05-10.md`

## Scope Completed

This pass closes the remaining open TODOs in the Claude Code level interaction plan.

Implemented:

- Tool execution now returns to the run-loop planner after read-only tools complete, so final answers can be generated from the current context and tool results instead of stopping at a template-only dispatch summary.
- The heuristic planner now produces a tool-result-grounded final answer when no model planner is configured.
- The JSON model planner path is covered by tests where the model selects a tool outside the keyword-selected capability hint set, proving selected capabilities are hints rather than a hard routing boundary.
- `agent_batch.nl_command.submit` is now approval-gated when it is the generic fallback execution path and no more specific high-risk capability has matched.
- Project-specific write/external paths keep precedence: source-library execution, workflow execution, and report generation request their own scoped approvals instead of also creating duplicate `agent_batch` approvals.
- `/agent-chat/turn` now defaults `require_high_risk_approval=true`, matching the frontend workbench path and preventing generic execution from bypassing approval by default.

## Main Files

- `main/backend/app/services/agent_runtime/run_loop.py`
- `main/backend/app/services/agent_runtime/interactive_agent.py`
- `main/backend/app/api/agent_chat.py`
- `main/backend/tests/unit/test_agent_run_loop_unittest.py`
- `main/backend/tests/unit/test_interactive_agent_runtime_unittest.py`
- `main/backend/tests/integration/test_agent_chat_api_unittest.py`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-04-02-claude-agent-high-fidelity-migration/02_claude-code-level-agent-interaction-todo-2026-05-10.md`

## Validation

Backend:

```bash
cd main/backend
./.venv311/bin/python -m py_compile app/api/agent_chat.py app/services/agent_runtime/tool_execution.py app/services/agent_runtime/tool_pool.py app/services/agent_runtime/read_only_tools.py app/services/agent_runtime/capability_registry.py app/services/agent_runtime/interactive_agent.py app/services/agent_runtime/run_loop.py app/services/agent_runtime/session_memory.py
./.venv311/bin/python -m pytest -q tests/integration/test_agent_chat_api_unittest.py tests/unit/test_agent_run_loop_unittest.py tests/unit/test_interactive_agent_runtime_unittest.py tests/unit/test_agent_session_memory_unittest.py tests/integration/test_agent_runtime_scenario_replay_unittest.py tests/integration/test_agent_runtime_artifact_idle_replay_unittest.py tests/unit/test_agent_control_tools_unittest.py
```

Result: `50 passed, 11 warnings`.

Focused unit validation:

```bash
cd main/backend
./.venv311/bin/python -m pytest -q tests/unit/test_agent_run_loop_unittest.py tests/unit/test_interactive_agent_runtime_unittest.py
```

Result: `24 passed`.

## Mainline Satisfaction Update

- P0-04 is satisfied by returning to the planner after tool execution and preserving model-generated final answers in `run_loop.model_final_answer`.
- P0-05 is satisfied by the JSON planner test where model tool calls can select `source_library.item.list` even when the initial selected capability hint only includes `agent_session.context.read`.
- P5-03 is satisfied by approval-gating the generic `agent_batch.nl_command.submit` fallback while keeping scoped source-library, workflow, and report approvals as the preferred execution paths.

With this pass, all checklist rows in `02_claude-code-level-agent-interaction-todo-2026-05-10.md` are checked.

## Frontend Interaction Debug Follow-up

After exercising the actual Agent Chat UI through Playwright, one user-facing gap remained: capability and read-only answers were still opening with runtime-template language. This was fixed by making the heuristic final-answer synthesis produce direct, user-oriented summaries for capability, tool-pool, source-library, project, artifact, workflow, and ingest read-only results, and by removing the `运行时依据` block from the normal conversational answer.

Validated UI paths:

- Desktop initial shell and mobile initial shell render with conversation, workbench, composer, and tabs visible.
- Capability question `你能做什么工具？` returns a natural answer, exposes tool traces, and does not submit `agent_batch`.
- Source-library fact question stays read-only and shows `source_library.item.list`.
- Generic execution request creates an approval card for `agent_batch.nl_command.submit` with editable JSON, approve, and reject controls.
- Approval rejection feeds back into the conversation.
- Artifact drawer and tool timeline remain inspectable after interactions.
- Source-library execution request creates scoped `ingest.source_library.run` approval instead of a generic batch approval.
- Desktop/mobile and post-interaction states have no horizontal overflow.
- No browser console errors or page errors were observed.

Playwright result: `34 passed, 0 failed`.

Observed visible-answer latencies:

- Capability answer: `488ms`.
- Source-library read-only answer: `3051ms`.
- Generic approval card: `3796ms`.
- Source-library scoped approval: `289ms`.

Screenshots captured during debug:

- `/tmp/agent-ui-debug-desktop-initial.png`
- `/tmp/agent-ui-debug-mobile-initial.png`
- `/tmp/agent-ui-debug-interaction.png`
- `/tmp/agent-ui-debug-source-approval.png`

## Local Recovery Follow-up

A later foreground check found the frontend on `127.0.0.1:5173` still serving while backend port `8000` was not listening. The immediate cause was process lifecycle rather than API code: a shell-detached uvicorn process could answer one smoke request and then be reaped with the command session. The backend was relaunched through user service label `com.codex.market-research-workflow.backend`, and `/api/v1/agent-chat/capabilities` returned `200`.

The recovery replay then exposed a smaller UI-state issue: the Agent Chat page could keep showing `实时运行` / the thinking bubble after a completed turn because SSE remained open. The frontend now treats terminal session status (`completed`, `failed`, `canceled`, `cancelled`) as authoritative over stream liveness for the run signal and thinking indicator.

Recovery validation:

- `npm run build` passed.
- Real Agent Chat Playwright turn `你能做什么工具？` returned the natural capability answer in `2138ms`.
- Post-turn workbench showed `TASKS=3`, `TOOLS=9`, `phase=verification`.
- No thinking ghost, no live-running ghost, no failed requests, and no console/page errors were observed.
- Screenshot: `/tmp/agent-ui-recovered-fixed.png`.

## Free Chat Regression Follow-up

A user screenshot showed `你好` still routing to `agent_batch.nl_command.submit` and producing a high-risk approval card. The root cause was an overly aggressive fallback in the goal classifier: short greetings and general questions that did not match a known read-only surface defaulted to `execute`.

This also reopens the architectural item that had been marked complete in the source TODO: keyword/rule routing is still too dominant. The corrective target is model-first routing. The model/planner should make most semantic decisions: answer directly, call read-only tools, ask a clarifying question, request approval, or execute a governed tool. Rule code such as `classify_goal` should only emit hints and enforce safety/approval/budget vetoes; it must not be the primary interpreter of user intent.

Fixes:

- Greeting/social turns (`你好`, `hello`, `hi`, etc.) now classify as `conversation`.
- General non-action questions using read-only phrasing such as `是什么` / `why` / `what` no longer default to project execution when no explicit project action token is present.
- Pure social turns select no project execution capability and no read-only tool calls; they return a plain assistant answer.
- Frontend no longer appends `parsed: (empty)` for turns without a parsed payload.
- Frontend hides technical message metadata, tool chips, and suggested next-action buttons for plain conversation turns with no tool calls.

Validation:

- Backend API smoke: `你好` returned `agent_mode=conversation`, `approval_requests=0`, `capability_calls=[]`.
- Real Agent Chat Playwright turn `你好` returned in `2033ms`.
- The final assistant message had no approval text, no `agent_batch.nl_command.submit`, no `parsed:` block, no thinking ghost, no metadata chips, no next-action buttons, and no tool chips.
- Full agent runtime target suite: `52 passed, 11 warnings`.
- Frontend `npm run build` passed.
- Screenshot: `/tmp/agent-ui-hello-general-answer.png`.

## Reopened Item: Model-first Routing

P0-05R is now tracked in `02_claude-code-level-agent-interaction-todo-2026-05-10.md`.

Implementation direction:

- Introduce a model decision schema before capability selection: `answer_direct`, `call_tools`, `ask_clarification`, `request_approval`, `decline_or_safe_complete`.
- Pass the model a compact project-aware tool pool, risk policy, session summary, and recent tool results.
- Convert `classify_goal` output into optional `RoutingHints`, not a hard route.
- Make direct answer / clarification the default for low-confidence input; never default unknown text to `agent_batch`.
- Keep deterministic rules as guardrails only: approval, write/external risk, budget, timeout, concurrency, and explicit hard veto.
- Gate the regression suite on plain user messages such as `你好`, `hello`, `你是谁`, `为什么这么慢`, and `当前有什么能力`.

The `你好` fix is therefore only a symptom repair. The remaining work is to remove classifier-first routing from the main path.

## 2026-05-11 Closure: Model-first Turn Decision

P0-05R is now implemented in the main agent-chat route.

- Added `interactive_agent.turn_decision.v1` before capability selection. It emits `answer_direct`, `call_tools`, `ask_clarification`, `request_approval`, or `decline_or_safe_complete` with confidence and reason.
- `classify_goal` and `select_capabilities_for_goal` now feed `RoutingHints` inside the plan artifact; they no longer directly decide the entry path in `InteractiveAgentRuntime`.
- The turn decision receives the project-aware tool pool summary before selecting capabilities. The JSON model planner path can also drive the same schema when `enable_model_tool_loop=true`.
- Unknown or low-confidence text defaults to direct answer or clarification, not `agent_batch`.
- Regression gates now cover `你好`, `你是谁`, `这个系统现在能干什么`, `为什么这么慢`, `当前有什么能力`, `这个项目有什么数据`, `请总结当前项目进展`, and `搜索来源库里新能源相关条目`.
- Frontend `AgentChatPage` now sends through `/agent-chat/turn/stream`, consumes the final SSE result, and no longer treats a long-lived session SSE `open` state as a thinking bubble.
- User-side Playwright E2E now covers plain chat, read-only project/source-library fact questions, governed source-library approval, and mobile no-overflow layout.

Validation:

- Backend target suite: `37 passed, 11 warnings, 4 subtests passed`.
- Frontend build: `npm run build` passed.
- AgentChat E2E: `4 passed`.

## 2026-05-11 Follow-up Closure: Free Conversation Is Model-Generated

The previous P0-05R closure still allowed ordinary non-tool questions to fall back to template text or clarification. This is now corrected.

- Added `ModelConversationAnswerer` for plain `conversation / answer_direct` turns. Ordinary facts and open conversation now call the configured LLM fallback and return a natural answer with no tool chrome.
- Fixed Codex CLI fallback discovery for launchd services by resolving `/Applications/Codex.app/Contents/Resources/codex` explicitly instead of relying on `PATH`.
- Added `GuardedModelTurnDecisionPlanner`: model routing remains available, but obvious read-only/control/approval/direct-safe paths are decided by fast guardrails before any expensive routing-model call. This keeps project data reads and approval cards responsive.
- Frontend AgentChat now sends `enable_model_tool_loop: true`; backend keeps read-only tool execution on the fast heuristic run-loop to avoid slow JSON planner calls for every tool scenario.
- User-facing E2E now verifies a non-canned free fact question (`解释一下 CAPM 的核心假设`), parses `interactive_agent.final_answer` from SSE, and asserts that the final stream result matches the visible assistant message.

Live HTTP replay after restart:

- `中国的首都是哪里？`: `conversation / answer_direct`, no capabilities, no approvals, model answer `中国的首都是北京。`, elapsed `12.84s`.
- `解释一下 CAPM 的核心假设` with model loop enabled: `conversation / answer_direct`, no capabilities, no approvals, model-generated CAPM answer, elapsed `13.96s`.
- `这个项目有什么数据` with model loop enabled: `read_only / call_tools`, capabilities `agent_session.context.read`, `project.summary.read`, `source_library.item.list`, no approvals, elapsed `0.71s`.
- `用来源库 demo.news 补一轮证据` with model loop enabled: `execute / request_approval`, capabilities `source_library.item.list`, `ingest.status.read`, `ingest.source_library.run`, one approval, elapsed `0.38s`.

Validation after this follow-up:

- Backend target suite: `39 passed, 11 warnings, 5 subtests passed`.
- Frontend build: `npm run build` passed.
- AgentChat Playwright E2E: `4 passed` in `21.2s`.
- Browser smoke against `http://127.0.0.1:5173/#agent-chat.html`: `中国的首都是哪里？` rendered `中国的首都是北京。`; stream final event was present; no `agent_batch`, approval, `parsed`, metadata chips, tool chips, console errors, or page errors.

## 2026-05-11 Follow-up: Codex Core Latency and Model-owned Tool Routing

The user clarified that project-data questions must remain model-core, not a mechanical semantic bypass. The previous fast semantic probe was removed from the main path.

- `GuardedModelTurnDecisionPlanner` now only skips the routing model for safety/control/direct-safe guardrails. Read-only project/source-library questions go through `JsonModelTurnDecisionPlanner`; timeout fallback remains safety-only.
- The Codex CLI fallback is now tuned for embedded agent-chat turns: explicit `model_reasoning_effort=none`, isolated light workdir, `--ignore-user-config`, and disabled global plugin/browser/memory/multi-agent prewarm. This preserves Codex as the LLM core while removing unrelated global Codex startup cost from ordinary turns.
- Model-selected read-only project-data tools are normalized to `read_only`; capability/status-only tool reads can still present as `conversation`.
- User-facing final answers no longer mention `fast path` or internal job wording.

Live HTTP replay after restart:

- `项目里有什么数据`: `call_tools / read_only`, `model_path=json_model_turn_decision`, selected `project.summary.read`, `source_library.item.list`, `agent_session.context.read`, no model error, elapsed `5.064s`.
- `中国的首都是哪里？`: `answer_direct / conversation`, `model_path=json_model_turn_decision`, no tools, no model error, answer `中国的首都是北京。`, elapsed `5.314s`.
- One replay of `现在有哪些数据可以用` still hit the 8s Codex CLI turn-decision timeout and used the safety fallback. This confirms the next latency milestone must be a persistent Codex app-server/session bridge, not more rules.

Validation:

- Backend target suite: `45 passed, 11 warnings, 5 subtests passed`.
- Frontend build: `npm run build` passed.
- AgentChat Playwright E2E: `4 passed`.
