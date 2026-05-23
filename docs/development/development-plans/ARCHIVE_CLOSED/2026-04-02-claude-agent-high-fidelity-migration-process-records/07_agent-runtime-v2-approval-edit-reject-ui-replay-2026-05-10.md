<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/07_agent-runtime-v2-approval-edit-reject-ui-replay-2026-05-10.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/07_agent-runtime-v2-approval-edit-reject-ui-replay-2026-05-10.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Runtime V2 Approval Edit Reject UI Replay

Date: 2026-05-10 PST
Source plan: `02_claude-code-level-agent-interaction-todo-2026-05-10.md`

## Scope Completed

This pass closes the next P2/P4 gap after project tool adapters: approvals are no longer approve-only.

Implemented:

- Backend approval continuation accepts `binding_payload_overrides`.
- Approval overrides merge into the original binding payload before execution; nested `inputs`, `input`, and `override_params` maps merge instead of replacing unrelated fields.
- Updated approval audit state:
  - emits `approval.binding_overridden`
  - appends `binding_overridden` to the approval audit log
  - refreshes `binding_hash` after override merge
- `/agent-chat/approvals/{approval_id}/continue` now passes override payloads to the runtime.
- Frontend approval card supports:
  - JSON parameter edit before approve
  - client-side invalid JSON guard
  - approve-and-continue with edited payload
  - reject from the primary pending approval card
  - reject from secondary pending approval rows
- Frontend API typing now treats `resolveAgentApproval` as returning an `AgentApprovalItem`.
- Timeline metadata now wraps long event names so the workbench no longer overflows horizontally.

## Main Files

- `main/backend/app/services/agent_runtime/interactive_agent.py`
- `main/backend/app/api/agent_chat.py`
- `main/backend/tests/unit/test_interactive_agent_runtime_unittest.py`
- `main/backend/tests/integration/test_agent_chat_api_unittest.py`
- `main/frontend-modern/src/lib/api.ts`
- `main/frontend-modern/src/lib/types.ts`
- `main/frontend-modern/src/pages/AgentChatPage.tsx`
- `main/frontend-modern/src/pages/agent-chat.css`

## Validation

Commands run:

```bash
cd main/backend
./.venv311/bin/python -m pytest -q tests/unit/test_interactive_agent_runtime_unittest.py tests/integration/test_agent_chat_api_unittest.py
```

Result: `13 passed, 11 warnings`.

```bash
cd main/backend
./.venv311/bin/python -m pytest -q tests/unit/test_agent_sessions_service_unittest.py tests/integration/test_agent_sessions_api_unittest.py tests/unit/test_agent_run_loop_unittest.py tests/unit/test_interactive_agent_runtime_unittest.py tests/integration/test_agent_chat_api_unittest.py
```

Result: `37 passed, 11 warnings`.

```bash
cd main/frontend-modern
npm run build
```

Result: passed.

Browser replay:

- Recompiled `demo_graph_agent_smoke` through `POST /api/v1/workflow-graph/compile`.
- Opened `http://127.0.0.1:5173/#agent-chat.html`.
- Submitted `运行 workflow graph demo_graph_agent_smoke`.
- Confirmed pending approval card exposes both `批准并继续` and `拒绝`.
- Entered invalid JSON override `{bad}`; UI showed `JSON 参数无效` and did not approve.
- Entered valid override `{"inputs":{"smoke":true}}`; approval continued and UI showed `审批已处理`.
- Submitted the same workflow again; clicked `拒绝`; UI showed `审批已拒绝`.
- Verified workbench, timeline, tool section, and artifact section remain present.
- Verified no console/page errors and no horizontal overflow.

Replay metrics:

```json
{
  "hasWorkbench": true,
  "hasTimeline": true,
  "hasToolSection": true,
  "hasArtifactSection": true,
  "hasApprovalCallout": false,
  "hasRejectText": true,
  "invalidJsonWasVisible": true,
  "overflowingElements": 0,
  "bodyOverflowX": false
}
```

In-app browser check:

```json
{
  "hasWorkbench": true,
  "errorCount": 0
}
```

## Mainline Satisfaction Update

- P2-04 is now materially covered for the current high-risk approval path: approval wait state can be approved, rejected, or edited before approval.
- P4-04 is covered for the current workbench card: approval card supports approve, reject, and modified-parameter approve.
- P6-04 has first replay evidence for approval-card interaction and workbench layout stability.
- S-05 workflow execution is stronger: user can inspect, edit approval payload, continue, and see execution feedback.

## Remaining Gap

Still open before Claude Code-level parity:

- P2-03 abort signal/cancel is not yet model-callable and tool-cooperative.
- P2-05 impact diff is not synthesized before high-risk execution.
- P2-06 external/cost budgets are not fully enforced across source-library and ingest execution.
- P2-07 failure result feedback and parameter correction are still partial.
- T-16/T-17/T-18 `task.cancel`, `task.retry`, and `task.continue` are still API actions, not runtime tools.
- P6 fixed scenario replay exists only as ad hoc browser smoke, not as a repo-owned replay artifact.

## Next Mainline Slice

Proceed to P6 first, then P2/P5:

1. Add repo-owned scenario replay coverage for S-01, S-02, S-05, and one failure-recovery path.
2. Save scenario replay output into this development topic after each run.
3. Convert `task.cancel`, `task.retry`, and `task.continue` into governed tools.
4. Continue demoting `agent_batch` so it remains a compatibility tool instead of the default execution spine.
