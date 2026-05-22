# Agent Architecture Deepening: Writing, Investigation, Data/Graph Tools

Date: 2026-05-11
Status: implemented baseline; future polish separated from this closure scope
Mainline: Claude Code level AgentCore reconstruction, after `17_claude-code-core-reconstruction-spec-2026-05-11.md`

2026-05-11 update: approval is frozen as a default interaction feature. Keep the approval protocol, event types, store, and continue route for compatibility, but do not use approval pauses as the main safety mechanism. Execution safety now comes from explicit tool choice, schema validation, project isolation, version locks, budgets, trust gates, and hard deny boundaries.

2026-05-13 update: the formal-tool gap identified by user-side testing has been closed for the AgentCore mainline. Model-visible tools now either have a real handler or are not registered; `workflow_graph.run`, `report.generate`, `agent_batch.nl_command.submit`, `agent_batch.submit`, `skill.search`, `skill.load`, `mcp.tools.list`, and `mcp.tool.call` are available through typed AgentCore tools. The frontend no longer renders backend failure fallback as a normal assistant answer, no longer seeds fake chat history as real history, and renders capability entries as read-only catalogue cards.

2026-05-13 follow-up: AgentChat interaction boundaries have been tightened from user-side test evidence. Clearing a conversation now detaches the backend session instead of continuing stale context; retries are scoped to the original frontend session; internal backend/session/mode metadata is hidden unless debug mode is explicitly enabled; the capability catalogue filters out disabled/unimplemented/not-mounted tools; `/turn/stream` emits `agent_core.stream_opened` before heavier setup; and `tool_window.py` now uses declarative profile definitions rather than an imperative branch chain.

2026-05-13 backend closure update: the highest-risk backend tool-loop gaps now have executable closure tests. `skill.search -> skill.load -> skill.<id>` is covered as a single discovery/load/invocation chain; `mcp.tools.list -> mcp.tool.call` is covered with a mounted MCP-compatible test tool plus structured not-configured failure; and `agent_task.plan.append -> partial task completion -> agent_session.resume_bundle` is covered for long-task resume. Remaining MCP/browser/search work is now about real external server hardening rather than a missing AgentCore call contract.

2026-05-13 crossflow closure update: the source-discovery/investigation/writing gap now has one executable AgentCore chain. A model turn can plan candidate sources with no network fetch, store followed leads and pending questions in the investigation artifact trail, create a writing workbench draft from an approved paragraph insertion with a clear title, preserve source refs/provenance in Agent writing metadata, and read the resume bundle with the new artifacts visible.

2026-05-13 AgentChat progressive UI update: the user-facing AgentChat workbench now preserves the current turn's streamed events across backend session rebinding, exposes split long-task cards in a `tasks` tab, and renders progressive tool events, source-quality cards, and writing-diff summaries. This closes the immediate gap where backend tool chains existed but user-visible progress and provenance were too thin.

2026-05-13 writing workbench diff-review update: Agent writebacks now have an expandable diff-review panel in the writing workbench. The panel shows version transition, locator, inserted text, source refs, provenance keys, and call id before the user locates, accepts, or rejects the change.

2026-05-13 external boundary visibility update: AgentChat now separates unavailable tools from callable capabilities. Disabled, not-mounted, and unimplemented external/MCP/browser/search capabilities are visible in an `external boundary` section with state and reason, but remain unavailable as executable tool cards.

2026-05-13 R17 update: multi-hop investigation is now a first-class AgentCore tool instead of an implicit artifact dump. `agent_investigation.trace.read` reads stored clue nodes/edges, expands a bounded trace from a focus node, returns pending questions/followed leads/citations/next steps, and is exposed in long-task and writing tool windows. The full chain `source.discovery.plan -> agent_investigation.leads.append -> agent_investigation.trace.read -> writing.document.insert_paragraph -> agent_session.resume_bundle` is covered both as a unit chain and through `/api/v1/agent-chat/turn`. External MCP/browser/search visibility now comes from `agent_runtime.external_tool_status`, shared by MCP catalog/call, tool_pool, and AgentChat boundary cards with `configured`, `reachable`, `auth_ok`, `server_error`, and `mounted_tool_count`.

2026-05-13 R18 update: AgentChat now treats investigation traces as user-facing evidence, not just tool metadata. The tools workbench extracts `agent_investigation.trace.v1` payloads and renders focus node, node/edge counts, trace summary, and unresolved question cards in the long-task scenario.

2026-05-13 R19 update: the external service matrix now has a configured-but-unreachable regression test. A browser MCP service can report `server_error` with `configured=true` and `reachable=false`, and the same state is visible through both `mcp.service.catalog` and `tool_pool` disabled grouping.

2026-05-13 R31/contentfulness update: the writing workbench now has side-by-side Agent paragraph anchors with locate/accept/reject/diff actions, and post-tool answers are guarded by a live contentfulness gate. The gate initially failed source-library continue and writing writeback because they were too status-like; after provider prompt and tool-summary fixes, the live rerun requires concrete object/data names, useful result IDs or snippets, and next inspectable state.

2026-05-13 R33 update: stored structured-data quality is now model-callable through `project.structured_data.quality_audit`. The lane scans documents and graph nodes for script/CSS/navigation shell noise, returns affected counts/samples/recommended actions, and is exposed through a narrow `data-quality-audit` tool window so real quality-cleaning prompts do not fall back to generic project search.

2026-05-14 R46 update: the remaining local-data answer substance gap has been closed by manifest-first context and demand-read tools. `project.structured_data.search` and `project.context.bundle` now expose `model_evidence_manifest`; AgentCore preserves items/evidence/read handles in the second model step; `project.structured_data.item.read`, `project.structured_data.items.read`, `project.context.resource.read`, and `writing.document.section.read` provide concrete follow-up reads; and normal `project-context` turns return to the model for synthesis instead of using the template fallback. Closure evidence is recorded in [`46_agent-context-manifest-and-demand-read-synthesis-2026-05-14.md`](./46_agent-context-manifest-and-demand-read-synthesis-2026-05-14.md).

## Goal

Restart the Agent architecture deepening lane as docs-driven development. The target is an interactive project agent that can:

- answer normal conversational turns without mechanical classification or unnecessary tool calls;
- autonomously choose project tools when project data, graph data, source-library state, writing documents, tasks, or artifacts are relevant;
- split long tasks into durable subtasks and resume them across turns;
- run multi-round investigation and clue tracing through local structured data, graph nodes, source-library items, and eventually external search/ingest;
- work with the writing workbench like a Canvas-style collaborator: read the current draft, propose edits, and write paragraphs or sections through optimistic locking and visible provenance;
- keep Codex/Core replaceable while retaining Claude Code style contracts around query loop, tool schemas, permission context, task tools, compact memory, and stream events.

## Reference Anchors

Local Claude Code source remains the primary reference, with `Claude-Code-main` treated as the fuller baseline and `claude-code` as the lighter comparison.

- `src/query.ts`: model-owned query loop, turn state, tool result feedback, max-turn stop reasons.
- `src/Tool.ts` and `src/tools.ts`: typed tool contract, registry factory, read-only/concurrency/permission filtering.
- `src/tools/TaskCreateTool`, `TaskGetTool`, `TaskUpdateTool`, `TaskListTool`: Task V2 as tool surface, not an outside planner.
- `src/hooks/toolPermission/*` and `src/utils/permissions/*`: unified permission context and interactive approval.
- `src/tools/FileEditTool`, `FileWriteTool`, `src/utils/diff.ts`: writeback as validate -> diff -> apply -> return auditable result.
- `src/services/compact/*` and `src/services/SessionMemory/*`: micro/auto/reactive compact and session memory.
- `src/utils/messages.ts` and `src/screens/REPL.tsx`: standard stream state for text, tool use, thinking, and tool-end events.

## Current Gap

The current project already has `agent_core_v3`, persistent Codex fallback, tool windows, read-only project tools, source-library execution tools, structured-data search, session memory, and writing workbench CRUD.

The remaining user-visible gap is no longer the basic AgentCore tool surface; that surface now exists and has targeted regression coverage. The backend closure for skill discovery/load/invocation, mounted MCP-compatible calls, long-task resume, the source-discovery/investigation/writing crossflow, and local-data demand-read synthesis is covered. The remaining items below are product polish or provider-capacity lanes, not blockers for the high-fidelity migration objective:

- long-task planning/resume is model-callable and has backend recovery coverage; AgentChat now exposes split-task cards, continue/retry controls, progressive events, source-quality cards, writing diffs, and investigation trace cards, while deeper artifact review flows remain a polish lane;
- structured data and graph data have combined query tools, a quality-audit lane for noisy stored records, and multi-hop clue tracing now has a model-callable trace reader plus unit/API/live coverage; remaining work is richer source-quality scoring and larger live-project scenario coverage;
- writing workbench paragraph insertion is tool-callable with version locks and approved title-based draft creation; AgentChat shows writing diff summaries, and the writing workbench now has an expandable per-update diff-review panel plus side-by-side paragraph anchors. A richer full-canvas editing surface remains a product polish lane;
- source discovery has a no-fetch trust planning tool, a tested handoff into investigation artifacts, a trace-read step, writing metadata, and AgentChat source-quality cards, while autonomous external search/ingest still requires hardened external MCP/browser boundaries before broad enablement;
- external MCP/browser/search capabilities now use a shared runtime status matrix for configured/reachable/auth/server-error/mounted fields; real external server hardening and live configured-server scenario matrices remain future work;
- UI streams now preserve progressive tool events in AgentChat; remaining writing collaboration work is now full-canvas polish rather than basic review visibility.

## Non-Negotiable Red Lines

These are merge blockers for this lane:

1. One execution boundary: all runtime variants must share the same schema, project isolation, version lock, budget, trust-gate, and hard-deny behavior for write, external, or privileged tools. Approval pauses remain frozen compatibility, not the default boundary.
2. Project isolation: every data/search/source/write operation must carry `project_key` and bind to the target project context.
3. External input is untrusted: URL/search ingestion needs allowlist, private-network blocking, redirect checks, content-type limits, checksum, and rollback logs before broad autonomous use.
4. Long-task resume must be idempotent: task-plan tools need idempotency keys and must skip duplicate task creation on replay.
5. Writing writeback must be versioned: document mutation tools require optimistic lock data or an explicit `allow_latest` flag, and must return a diff/summary.
6. Tool outputs must be schema-like: model-visible results need contract version, status, compact evidence, and error semantics.
7. Final answers must be contentful: after tools run, the model must not return only a formal status; it must name the concrete object/data affected, include useful counts/snippets/result IDs where available, and point to the next inspectable state.

## Architecture Shape

The target architecture is:

```text
User turn
  -> AgentCore query loop
  -> model chooses: final answer or tool calls
  -> unified permission gate
  -> typed project tools / skills / MCP surfaces
  -> tool result fed back to model
  -> final answer / durable task state / workbench writeback
```

Tool placement:

- Core tools: low-latency project/session/writing/data reads and session-local planning.
- Skill tools: policy-heavy project workflows such as source-library dispatch and workflow graph orchestration.
- MCP services: external or separately hosted services such as browser/search automation once the boundary is configured.
- Writing tools: initially backend project tools with optimistic locks; later synced to the workbench UI as live diff events.

## Phase Matrix

### P0: First Vertical Slice

- [x] Add `agent_task.plan.append` as a model-callable Task V2 style tool.
  - Writes only to the session ledger.
  - Uses idempotency key and duplicate suppression.
  - Auto-allowed only for session-local planning metadata.
- [x] Add `agent_session.resume_bundle`.
  - Returns active tasks, recent messages, recent artifacts, approvals, and compact session metadata.
  - Used for "continue", "long task", and multi-turn investigation recovery.
- [x] Add `project.graph.search`.
  - Focuses `project.structured_data.search` on `graph_nodes`.
  - Returns compact graph-node evidence and query metadata.
- [x] Add `project.structured_graph.query`.
  - Combines stored documents, graph nodes, sources, resource-pool entries, and keyword memory into a single read-only investigation view.
- [x] Add writing workbench tools.
  - `writing.document.list`
  - `writing.document.read`
  - `writing.document.insert_paragraph`
  - The write tool uses version/etag checks or explicit `allow_latest`, returns line-count diff, and executes through tool-level write boundaries while approval stays frozen.
- [x] Update tool-window profiles.
  - Expose writing tools for writing/report/workbench turns.
  - Expose task/data/graph/source tools for long-task, multi-round investigation, clue tracing, and project-data questions.
- [x] Update JSON provider protocol hints.
  - Make the model prefer graph/data tools for stored project knowledge.
  - Make the model prefer task-plan append for long-running goals instead of asking generic clarification.

### P1: Investigation And Source Discovery

- [x] Add autonomous source-candidate planning.
  - Generate search queries and candidate source-library items without immediate external writes.
- [x] Add trust pipeline before external ingestion.
  - URL normalization, SSRF/private-IP blocking, redirect chain validation, content limits, checksum, source score, dedupe.
- [x] Add source-quality gates.
  - Minimum credibility score, stale-source handling, duplicate detection, source conflict notes.
- [x] Add multi-round investigation artifacts.
  - Store clue graph, pending questions, followed leads, rejected leads, and citation trail.

### P2: Writing Workbench Deep Integration

- [x] Add paragraph IDs or block anchors to writing documents.
- [x] Add insert/replace/accept/reject operations in the frontend workbench.
- [x] Stream agent edit proposals into the workbench panel.
- [x] Refresh the current document after successful agent writeback.
  - First slice: writing workbench document list refetches every 10s and the active document refetches every 5s/on focus, so backend AgentCore edits become visible without a manual reload.
- [x] Add provenance side panel for inserted paragraphs.

### P3: Claude Code Level Runtime Parity

- [x] Query loop parity: explicit state machine for turn count, pending tool summary, transition reason, blocking limit.
- [x] Compact parity: micro compact, auto compact, reactive compact, and session memory extraction.
- [x] Stream parity: standardized event blocks for assistant delta, tool start, tool progress, tool result, approval, final answer.
- [x] Permission parity: classifier-assisted but policy-owned execution boundaries with approval compatibility frozen by default.
- [x] Tool schema parity: validate args before execution and return recoverable tool errors.

## Acceptance Scenarios

1. Free conversation:
   - User asks "你好" or a general fact.
   - Agent answers directly without invoking project tools.

2. Project-data question:
   - User asks "项目里有什么机器人相关数据".
   - Agent calls project structured/graph tools and answers from stored records.

3. Long writing task:
   - User asks for a long-form report using local materials and follow-up research.
   - Agent appends a durable task plan, reads project data, searches source-library items, and produces resumable task state.

4. Writing workbench edit:
   - User asks "把这段补到当前文稿的研究背景后面".
   - Agent reads the target writing document, calls `writing.document.insert_paragraph`, writes with version lock or explicit `allow_latest`, and returns diff/provenance.

5. Multi-round investigation:
   - User asks to trace a lead across stored graph nodes and source-library records.
   - Agent calls graph/data/source tools, summarizes evidence, and creates follow-up tasks instead of losing state in prose.

6. Frozen approval consistency:
   - The same source-library execution or writing mutation request must not create an approval pause by default, no matter which provider/runtime path is used. Existing approval resume remains compatible for historical pending approvals.

## First Implementation Commitment

This document authorizes the first vertical slice immediately:

- session-local long-task tools;
- project structured/graph query tools;
- writing document read/list/paragraph insert tools;
- tool-window and provider prompt updates;
- focused unit tests for registry exposure, permission behavior, task-plan idempotency, graph query, writing writeback lock behavior, and tool-window routing.

Later phases must remain tied to this document and update it or append a numbered implementation status record before claiming closure.

## Implementation Log

### 2026-05-11 P0 Vertical Slice

Landed in code:

- `main/backend/app/services/agent_core/project_tools.py`
  - `agent_task.plan.append`
  - `agent_session.resume_bundle`
  - `project.graph.search`
  - `project.structured_graph.query`
  - `writing.document.list`
  - `writing.document.read`
  - `writing.document.insert_paragraph`
- `main/backend/app/services/agent_core/core.py`
  - Approval is now frozen by default; write/external tools rely on schema validation, project isolation, version locks, budget/trust gates, and hard deny boundaries instead of a generic pause.
- `main/backend/app/services/agent_core/tool_window.py`
  - Adds long-task/investigation and writing-workbench profiles.
  - Expands project-context profile with graph and structured+graph tools.
- `main/backend/app/services/agent_core/json_provider.py`
  - Adds model protocol guidance for graph/data tools, long-task planning, and writing workbench reads/writes.
- `main/backend/tests/unit/test_agent_core_unittest.py`
  - Adds regression coverage for new tool exposure, task-plan idempotency, structured/graph routing, writing version-lock behavior, and tool-window routing.
- `main/frontend-modern/src/pages/WritingWorkbenchPage.tsx`
  - Adds periodic/focus refetch for the writing document list and active document so AgentCore writeback can surface in the workbench.

Validation:

- `main/backend/.venv311/bin/python -m pytest -q tests/unit/test_agent_core_unittest.py`
  - Result: 15 passed, 3 warnings.
- `main/backend/.venv311/bin/python -m py_compile main/backend/app/services/agent_core/project_tools.py main/backend/app/services/agent_core/tool_window.py main/backend/app/services/agent_core/json_provider.py main/backend/app/services/agent_core/core.py main/backend/tests/unit/test_agent_core_unittest.py`
  - Result: passed.
- `npm run lint -- src/pages/WritingWorkbenchPage.tsx` from `main/frontend-modern`
  - Result: passed with 0 errors; existing warnings remain in `AgentChatPage.tsx` hook dependencies.

### 2026-05-11 P1-P3 Deepening Slice

Landed in code:

- `main/backend/app/services/source_library/source_candidate_trust.py`
  - Adds no-fetch/no-write source candidate planning, URL unwrap/canonicalization, public-host validation, trust score, duplicate detection, source-quality notes, and required pre-ingest checks.
- `main/backend/app/services/source_library/adapters/url_pool.py`
  - Rejects non-http/private/local explicit URLs before fetch and avoids falling back to pool URLs when all explicit URLs are rejected.
- `main/backend/app/services/agent_core/project_tools.py`
  - Wires `source.discovery.plan` to the trust planner.
  - Adds `agent_investigation.leads.append` for clue graph, pending questions, followed/rejected leads, citations, and idempotent session artifact storage.
  - Adds writing block anchors in `writing.document.read`.
  - Extends Agent writing writeback metadata with `agent_updates`, locator, diff, source refs, and provenance.
- `main/backend/app/services/agent_core/core.py`
  - Adds schema validation before execution, recoverable tool errors, reactive compaction, and optional `turn_state` loop-state events.
- `main/backend/app/api/writing.py`
  - Allows workbench updates to persist reviewed Agent writeback metadata.
- `main/frontend-modern/src/pages/WritingWorkbenchPage.tsx`
  - Adds Agent update panel, visible provenance/status, locate, accept, reject/revert, manual refresh, and document-list Agent markers.
- `main/frontend-modern/src/components/writing/writing-workbench.css`
  - Adds the Agent update panel and card styling.

Validation:

- `main/backend/.venv311/bin/python -m pytest -q tests/unit/test_agent_core_unittest.py tests/unit/test_source_candidate_trust_unittest.py tests/unit/test_source_library_url_pool_adapter_unittest.py`
  - Result: 30 passed, 3 warnings.
- `main/backend/.venv311/bin/python -m py_compile app/services/agent_core/contracts.py app/services/agent_core/core.py app/services/agent_core/project_tools.py app/services/agent_core/tool_window.py app/services/agent_core/json_provider.py app/services/source_library/source_candidate_trust.py app/services/source_library/adapters/url_pool.py app/api/agent_chat.py app/api/writing.py tests/unit/test_agent_core_unittest.py tests/unit/test_source_candidate_trust_unittest.py tests/unit/test_source_library_url_pool_adapter_unittest.py`
  - Result: passed.
- `npm run lint -- src/pages/WritingWorkbenchPage.tsx src/components/writing/writing-workbench.css` from `main/frontend-modern`
  - Result: 0 errors; existing `AgentChatPage.tsx` hook warnings remain, CSS is ignored by the current ESLint config.
- `npm run build` from `main/frontend-modern`
  - Result: passed.
- Browser smoke on `http://127.0.0.1:5174/#writing-workbench.html`
  - Result: workbench renders, Agent button is visible, Agent update panel opens, and locate/empty-state/accept-reject affordances are present.

### 2026-05-13 AgentChat Interaction And Tool-Window Closure

Landed in code:

- `main/frontend-modern/src/pages/AgentChatPage.tsx`
  - Clear current session now resets the backend session id, root task id, phase, compat/projection state, stream events, selected artifact, and draft.
  - Retry stores the originating frontend session id and reuses that session binding.
  - Runtime metadata chips are hidden by default and only render with `agent_debug=1` / `debug_agent=1`.
  - Capability cards filter to enabled and implemented tools.
- `main/frontend-modern/tests/e2e/agent-chat.spec.ts`
  - Adds deterministic user-scenario coverage for free conversation, project-data tool use, frozen source-library execution, mobile overflow, backend failure, and clear-session backend detachment.
  - Asserts source-library execution turns send `require_high_risk_approval=false` on the mainline.
- `main/backend/app/api/agent_chat.py`
  - Emits `agent_core.stream_opened` before entering heavier AgentCore stream setup.
- `main/backend/app/services/agent_core/tool_window.py`
  - Moves tool-window selection to declarative profile definitions and signal extraction while preserving model-owned tool selection.
- `main/backend/tests/integration/test_agent_chat_api_unittest.py`
  - Asserts `agent_core.stream_opened` precedes `agent_core.stream_started`.

Validation:

- `PYTHONPATH=main/backend pytest main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/unit/test_source_candidate_trust_unittest.py -q`
  - Result: 28 passed, 3 warnings.
- `PYTHONPATH=main/backend pytest main/backend/tests/integration/test_agent_chat_api_unittest.py -q`
  - Result: 19 passed, 11 warnings.
- `npm run lint -- src/pages/AgentChatPage.tsx tests/e2e/agent-chat.spec.ts` from `main/frontend-modern`
  - Result: passed.
- `npm run test:e2e -- tests/e2e/agent-chat.spec.ts --reporter=line` from `main/frontend-modern`
  - Result: 6 passed.

### 2026-05-13 Backend Tool-Loop Closure

Landed in code:

- `main/backend/app/services/agent_core/project_tools.py`
  - Adds `register_agent_core_mcp_tool` and `clear_agent_core_mcp_tools` as the mounted MCP-compatible call boundary.
  - `mcp.tools.list` includes mounted tools.
  - `mcp.tool.call` executes mounted handlers and returns structured success, not-configured, service-mismatch, and handler-failure results.
  - Compact resume tasks now include `result_summary` and compact `result_payload`.
- `main/backend/tests/unit/test_agent_core_unittest.py`
  - Adds `skill.search -> skill.load -> skill.workflow_graph.get_run` chain coverage.
  - Adds `mcp.tools.list -> mcp.tool.call` success and not-configured failure coverage.
  - Adds `agent_task.plan.append -> partial completion -> agent_session.resume_bundle` long-task recovery coverage.

Validation:

- `PYTHONPATH=main/backend pytest main/backend/tests/unit/test_agent_core_unittest.py -q`
  - Result: 29 passed, 3 warnings.
- `PYTHONPATH=main/backend pytest main/backend/tests/unit/test_source_candidate_trust_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q`
  - Result: 21 passed, 11 warnings.
- `PYTHONPATH=main/backend pytest main/backend/tests/unit/test_skill_runtime_unittest.py main/backend/tests/unit/test_codex_cli_llm_fallback_unittest.py -q`
  - Result: 20 passed.
- `PYTHONPATH=main/backend python3 -m py_compile main/backend/app/services/agent_core/project_tools.py main/backend/tests/unit/test_agent_core_unittest.py`
  - Result: passed.

### 2026-05-13 Source Discovery / Investigation / Writing Crossflow Closure

Landed in code:

- `main/backend/app/services/agent_core/project_tools.py`
  - `writing.document.insert_paragraph` now allows an approved call with no `doc_id` but a clear `title` to create a new workbench draft.
  - Calls without `doc_id` and without `title` still fail, keeping accidental unnamed document creation blocked.
  - The model-facing tool description explicitly documents the title-based creation path.
- `main/backend/tests/unit/test_agent_core_unittest.py`
  - Adds one model-owned chain for `source.discovery.plan -> agent_investigation.leads.append -> writing.document.insert_paragraph -> agent_session.resume_bundle`.
  - Verifies no-fetch/no-write source discovery gates, investigation artifact creation, writing draft creation, source refs/provenance metadata, resume-bundle artifact visibility, and transcript feedback into the next model step.

Validation:

- `PYTHONPATH=main/backend pytest main/backend/tests/unit/test_agent_core_unittest.py -q`
  - Result: 30 passed, 3 warnings.
- `PYTHONPATH=main/backend pytest main/backend/tests/unit/test_source_candidate_trust_unittest.py main/backend/tests/integration/test_writing_api_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q`
  - Result: 29 passed, 11 warnings.
- `PYTHONPATH=main/backend python3.11 -m py_compile main/backend/app/services/agent_core/project_tools.py main/backend/tests/unit/test_agent_core_unittest.py`
  - Result: passed.

### 2026-05-13 AgentChat Long-Task And Progressive Event UI

Landed in code:

- `main/frontend-modern/src/pages/AgentChatPage.tsx`
  - Stores current-turn streamed AgentCore events on the assistant message so events remain visible after backend session rebinding.
  - Adds a `tasks` workbench tab with split-task cards, status, dependencies, read/write sets, and continue/retry actions.
  - Adds progressive tool-event cards, source-quality cards, and writing-diff cards to the tool workbench.
- `main/frontend-modern/src/pages/agent-chat.css`
  - Adds responsive task/progressive/source/diff card styling.
- `main/frontend-modern/tests/e2e/agent-chat.spec.ts`
  - Adds a long-task scenario asserting split-task UI, progressive events, source quality, and writing diff visibility.

Validation:

- `npm run lint -- src/pages/AgentChatPage.tsx tests/e2e/agent-chat.spec.ts` from `main/frontend-modern`
  - Result: passed.
- `npm run test:e2e -- tests/e2e/agent-chat.spec.ts --reporter=line` from `main/frontend-modern`
  - Result: 7 passed.
- In-app browser verification on `http://127.0.0.1:5174/#agent-chat.html`
  - Result: runtime details show `tasks`, progressive event, source-quality, and writing-diff sections after reload.

### 2026-05-13 Writing Workbench Agent Diff Review

Landed in code:

- `main/frontend-modern/src/pages/WritingWorkbenchPage.tsx`
  - Adds an expandable Agent update diff-review panel with version transition, locator, inserted text, source refs, provenance keys, and call id.
  - Keeps locate, accept, and reject controls in the same Agent update card so review and action share one interaction context.
- `main/frontend-modern/src/components/writing/writing-workbench.css`
  - Adds responsive diff-review panel styling.
- `main/frontend-modern/tests/e2e/writing-workbench.spec.ts`
  - Verifies the diff panel before locate and accept controls.

Validation:

- `npm run lint -- src/pages/WritingWorkbenchPage.tsx src/components/writing/writing-workbench.css tests/e2e/writing-workbench.spec.ts` from `main/frontend-modern`
  - Result: passed with the existing CSS ignored-by-ESLint warning.
- `VITE_API_PROXY_TARGET=http://127.0.0.1:8017 npm run test:e2e -- tests/e2e/writing-workbench.spec.ts --reporter=line` from `main/frontend-modern`
  - Result: 3 passed.
- Environment note:
  - The default backend listener on `127.0.0.1:8000` was present but `/api/v1/health` timed out. A temporary healthy backend on `127.0.0.1:8017` was used for this writing-workbench verification and stopped afterward.

### 2026-05-13 External Boundary Visibility

Landed in code:

- `main/frontend-modern/src/pages/AgentChatPage.tsx`
  - Separates unavailable capabilities from executable core/governed cards.
  - Renders disabled, not-mounted, and unimplemented capabilities in an `external boundary` section with state and reason.
- `main/frontend-modern/tests/e2e/agent-chat.spec.ts`
  - Verifies that `mcp.placeholder.echo` appears in the boundary section as `not_mounted` instead of as an executable capability.

Validation:

- `npm run lint -- src/pages/AgentChatPage.tsx tests/e2e/agent-chat.spec.ts` from `main/frontend-modern`
  - Result: passed.
- `npm run test:e2e -- tests/e2e/agent-chat.spec.ts --reporter=line` from `main/frontend-modern`
  - Result: 7 passed.
