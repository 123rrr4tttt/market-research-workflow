<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/24_agent-long-task-stage-ui-recovery-2026-05-13.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/24_agent-long-task-stage-ui-recovery-2026-05-13.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Long Task Stage UI Recovery - 2026-05-13

## Scope

This note closes the next `21_agent-goal-gap-and-optimization-direction-2026-05-13.md` gap around long-task stage visibility and browser-level recovery evidence. It does not claim full Claude Code level closure; it records one concrete slice: durable long-task stage state is now visible in AgentChat and survives the tested browser reload path.

## Implemented

- Backend long-task stage tools are registered in AgentCore:
  - `agent_long_task.stage.update`
  - `agent_long_task.stage.read`
- The stage contract stores `agent_long_task.stage.v1` state in the session artifact `agent_long_task.state.json`.
- Stage state includes:
  - `current_stage`
  - `completed_stages`
  - per-stage summaries and counters
  - evidence refs, gap list, discovery/source intake/clue/draft refs
  - `next_actions`
  - idempotent replay keys
- `agent_session.resume_bundle` includes compact `long_task_states`.
- AgentChat now extracts long-task stage state from tool results, stream events, session artifacts, and task payload/metadata.
- AgentChat task panel now displays a `long task stages` section with:
  - current stage
  - completed stage chain
  - latest stage summary
  - accumulated evidence/gap/discovery/intake/clue/draft counters
  - next action
- The AgentChat E2E long-task scenario now verifies that stage state remains visible after browser reload.

## Browser Behavior Matrix

| Scenario | Expected behavior | Evidence |
|---|---|---|
| Long investigation/writing task | User sees split tasks, progressive tool events, source quality, investigation trace, writing diff, and long-task stage state. | `tests/e2e/agent-chat.spec.ts` long-task scenario |
| Stage state from model-owned tool loop | `agent_long_task.stage.update` appears in stream/tool details and feeds the UI stage card. | E2E asserts stream text and run details contain `agent_long_task.stage.update` |
| Internal evidence and gaps remain visible | UI card shows accumulated `evidence 2 · gaps 2`, not only the last tool result. | E2E asserts stage card text |
| Refresh/reopen recovery | Reloaded AgentChat restores the session and still shows `draft_output` plus next action. | E2E reload assertion |

## Verification

- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_interactive_agent_runtime_unittest.py main/backend/tests/unit/test_agent_run_loop_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q` -> `102 passed, 11 warnings`
- `npm run lint -- src/pages/AgentChatPage.tsx src/pages/agent-chat.css tests/e2e/agent-chat.spec.ts` -> `0 errors, 1 existing CSS ignored warning`
- `npm run build` -> passed
- `npm run test:e2e -- tests/e2e/agent-chat.spec.ts -g "long task"` -> `1 passed`
- `npm run test:e2e -- tests/e2e/agent-chat.spec.ts` -> `10 passed`

## Remaining Gaps From 21

- Source intake and trust-gated external collection stage states exist in the contract but need a browser scenario that exercises actual source intake results, not only candidate discovery.
- Full closure still requires an audit that every acceptance-matrix row in `21_agent-goal-gap-and-optimization-direction-2026-05-13.md` passes from the browser with real backend services where feasible.
