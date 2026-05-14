# Agent Workbench UI And Mainline Satisfaction

Date: 2026-05-10 PST
Source plan: `02_claude-code-level-agent-interaction-todo-2026-05-10.md`

## Scope Completed

This pass finishes the first M4 frontend workbench slice and records the current satisfaction state of the full mainline TODO, not just the UI section.

Implemented:

- Reworked `AgentChatPage` right-side inspector into an agent workbench with a compact run signal, phase/tool/task/approval metrics, approval callout, tool-call section, artifact section, and live timeline section.
- Kept the conversation as the primary surface: left session rail, central chat stream, right workbench for execution state.
- Moved high-risk pending approval into a prominent callout with `批准并继续`, while keeping the full approval list for audit context.
- Replaced the previous combined `events / artifacts` stack with separate artifact and timeline views.
- Added timeline items synthesized from session events and tasks so users can see tool/task movement without reading raw event payloads.
- Tightened React keys for message metadata and suggested actions to avoid duplicate-key warnings during repeated agent replies.
- Preserved the existing session/task actions as secondary controls.

## Mainline Satisfaction Matrix

Legend: `done` means this pass or earlier passes satisfy the row at current scope; `partial` means a usable slice exists but the source TODO still has open requirements; `pending` means not yet materially implemented.

| TODO section | Status | Evidence | Remaining gap |
|---|---|---|---|
| P0 interaction loop and fast chat | partial | `AgentRunLoop`, read-only fast path, stream-style events, session ledger sink, model-planner final-answer preservation, and idle latency replay are implemented. | Keyword hints still influence routing before the model planner; full model-native answer synthesis is not the only path yet. |
| P1 tool protocol and dynamic tool pool | partial | Tool definition contract and read-only tools exist for capabilities/session/project/source-library/artifact. | Dynamic project-aware tool assembly, delayed tool search, `ToolExecutionContext`, dry-run and per-tool examples are incomplete. |
| P2 concurrency, permission, approval, interrupt | partial | High-risk approval wait and approved continuation exist for `workflow_graph.run` and source-library compat run. | Reject/edit approval, write-set locking, abort signal, impact diff, retry-as-tool-result, and hook points are still open. |
| P3 memory, context, compression | pending | No durable session memory or context compaction layer was added in this pass. | Needs session memory, project context builder, tool-use summary, and context-budget policy. |
| P4 frontend workbench | partial | Conversation-first layout, tool timeline, approval callout, approval edit/reject, artifact preview panel, capability panel, and responsive no-overflow smoke are implemented. | Token streaming bubble, per-tool retry, and explicit narrow-screen tab switching remain open. |
| P5 compatibility migration | partial | `/agent-chat/turn` now uses the new runtime surface while keeping legacy response compatibility; runtime feature flags are exposed. | `agent_batch` is still a fallback path and still needs caller-by-caller demotion into a governed compatibility tool. |
| P6 tests, metrics, acceptance gates | partial | Backend unit/integration tests, fixed S-01 through S-10 replay gates, run-loop metrics, frontend build, HTTP smoke, and UI approval smoke passed. | Full frontend E2E and broader performance thresholds remain open. |
| Required scenarios S-01-S-10 | done | All fixed backend replay scenarios are green across `test_agent_runtime_scenario_replay_unittest.py` and `test_agent_runtime_artifact_idle_replay_unittest.py`. | UI-level replay for artifact drawer/mobile/per-tool controls still belongs to P4/P6, not the backend scenario gate. |

## Validation

Commands run:

```bash
cd main/frontend-modern
npm run build
```

Result: TypeScript build and Vite production build passed.

In-app browser smoke against local Vite:

- Opened `http://127.0.0.1:5173/#agent-chat.html`.
- Confirmed the new `agent workbench`, composer, `tool calls`, `artifacts`, and `live timeline` regions render.
- Submitted `运行 workflow graph demo_graph_agent_smoke`.
- Confirmed one pending `批准并继续` approval appears.
- Continued the approval from the UI.
- Confirmed `审批已处理` appears, no pending approval button remains, and browser console errors are empty.

Headless Playwright layout smoke:

```json
{
  "metrics": {
    "hasWorkbench": true,
    "hasTimeline": true,
    "hasToolSection": true,
    "hasArtifactSection": true,
    "hasApprovalCalloutAfterContinue": false,
    "handledText": true,
    "pendingApprovalButtons": 0,
    "bodyOverflowX": false,
    "overflowingElements": 0,
    "pageHeight": 814
  },
  "errors": []
}
```

## Current Closure Boundary

This is not a full M4 closure. It is a usable workbench baseline that satisfies the first half of P4:

- P4-01 is materially satisfied for desktop.
- P4-03 is partially satisfied with timeline summaries.
- P4-04 is partially satisfied for approve-and-continue only.
- P4-05 is partially satisfied with artifact listing but no preview drawer.
- P4-06 is satisfied in direction: task state is secondary, not the main flow.
- P4-07 is partially satisfied: approval is close to current run state; retry/cancel are still global.
- P4-08, P4-09, and P4-10 remain open beyond the current basic empty/error and responsive checks.

## Next Mainline Slice

Continue with the non-UI gaps from the same source TODO:

1. P1/P2: implement richer governed tool adapters for `workflow_graph.list`, `workflow_graph.inspect`, `ingest.status.read`, `task.cancel`, `task.retry`, and `task.continue`.
2. P2: add approval rejection and edit-before-approve payload flow.
3. P6: add fixed scenario replay for S-01, S-02, S-05, and one failure-recovery path.
4. P3/P5: only after the above, add session memory/context compaction and demote `agent_batch` behind a governed compatibility tool.
