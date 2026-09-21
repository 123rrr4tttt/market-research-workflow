# Frontend Control Coverage Addendum v1

## Evidence boundary

- Audit date: `2026-09-07`.
- Parent disposition: `stage1-successor-evidence/stage-convergence-batch-v1/frontend-skip-disposition.v1.md`, SHA-256 `221d393dbfdd4086b7ebbd5e93828949c25779e6bf806ab947cd2c4baf3fca71`.
- This addendum does not modify or supersede the parent disposition.
- Method: read-only review of current test and implementation source.
- Execution state: `NOT_EXECUTED_IN_THIS_ADDENDUM`.
- Claim ceiling: existing backend/API tests reduce duplicate gap accounting; they do not establish an embedded-Codex WebUI PASS and do not authorize product retirement.

## Exact reviewed identities

| Artifact | SHA-256 |
| --- | --- |
| `main/backend/tests/unit/test_agent_control_tools_unittest.py` | `dd8ac1a2138040011c68d78b6fa32ec6df6b7791fcec15373779c8ec0b76d57b` |
| `main/backend/tests/integration/test_agent_runtime_scenario_replay_unittest.py` | `91cd0a941b263553007ca0fff67428a4724e317f7eedb700522e51deae00a7f8` |
| `main/backend/tests/integration/test_agent_chat_api_unittest.py` | `d98507a55c5472fc9b8de57451ad4510d98789f5057ba0771eeadd1ae3fe75aa` |
| `main/backend/tests/unit/test_interactive_agent_runtime_unittest.py` | `0f82ea712eb922918ffa71d6907b30b19746ba283075cd4ca7bde535daf609f5` |
| `main/backend/app/api/agent_chat.py` | `0b1639a2701e05ff56676ffa769e72ad9518b8581340f07cce5eb02227d5f781` |
| `main/frontend-modern/src/pages/AgentChatPage.tsx` | `db815684899533c5544bebf4fd2cc7a75fc07b6deb5fdfb3270b428083a41b8a` |

## FE-AGENT-SKIP-05 through FE-AGENT-SKIP-07

The backend control semantics are already materially covered and must not be counted again as wholly absent frontend gaps.

### Natural-language capability selection

`main/backend/tests/unit/test_agent_control_tools_unittest.py::AgentControlToolsUnitTest::test_control_capability_selection`

- `继续上一步` is classified as `control` and selects capability `task.continue`.
- `重试失败任务` is classified as `control` and selects capability `task.retry`.
- `取消当前会话` is classified as `control` and selects capability `task.cancel`.

### Direct control effects

`main/backend/tests/unit/test_agent_control_tools_unittest.py::AgentControlToolsUnitTest::test_task_cancel_cancels_session`

- A direct `task.cancel` runtime call completes.
- The stored session becomes `canceled`.

`main/backend/tests/unit/test_agent_control_tools_unittest.py::AgentControlToolsUnitTest::test_task_continue_runs_coordinator_pass`

- A direct `task.continue` runtime call completes.
- The coordinator is invoked exactly once with the same session ID.

`main/backend/tests/unit/test_agent_control_tools_unittest.py::AgentControlToolsUnitTest::test_task_retry_uses_latest_failed_task_when_task_id_omitted`

- An omitted task ID selects the latest failed task.
- The selected failed task returns to `pending`.

### Natural-turn and scenario integration

`main/backend/tests/unit/test_agent_control_tools_unittest.py::AgentControlToolsUnitTest::test_interactive_turn_can_dispatch_retry_as_control_tool`

- A natural retry turn uses control mode.
- `task.retry` completes.
- Started and result events are emitted.
- `agent_batch.nl_command.submit` is absent.

`main/backend/tests/integration/test_agent_runtime_scenario_replay_unittest.py::AgentRuntimeScenarioReplayIntegrationTest::test_s07_cancel_then_continue_preserves_recoverable_session_state`

- Natural cancel changes the session to `canceled` and completes `task.cancel`.
- Natural `继续` completes `task.continue` and resumes the canceled session to a recoverable non-canceled state.
- The scenario emits `task.continue_resumed_canceled` and restores a wait-for-approval coordinator decision.

`main/backend/tests/integration/test_agent_chat_api_unittest.py::AgentChatApiIntegrationTestCase::test_agent_core_control_tools_cancel_continue_retry_in_one_session`

- `/api/v1/agent-chat/turn` transports cancel, continue, and retry messages through one session.
- It asserts the three control tool names and completed statuses.
- It asserts response/store cancellation, resumed-task state, and failed-task retry to `pending`.
- The tool choice is supplied by sequential `FakeCoreProvider` fixtures. This test proves API/state integration, not independent live model selection.

### Remaining exact gaps

- `WEBUI_CONTROL_INTERACTION_UNCOVERED`: the current embedded WebUI must accept the utterance and render the correct message-local tool and feedback.
- `WEBUI_NEGATIVE_RESIDUE_UNCOVERED`: the current surface must show no batch/fallback residue.
- `CONTROL_STREAM_SERIALIZATION_NOT_FOCUSED`: the strongest combined API test uses non-stream `/turn`; no reviewed focused test individually asserts `/turn/stream` SSE serialization for all three controls.

The last item is a narrow transport-observation gap. It must not be restated as absent backend control semantics.

## FE-AGENT-SKIP-10

Legacy clear-session behavior is client-owned. `AgentChatPage.clearCurrentSession` clears visible history and draft state and sets the stored `backendSessionId`, root task ID, phase, compatibility mode, and projection version to null. The backend does not expose a separate `clear session` action.

### Existing server-side branch coverage

`main/backend/tests/unit/test_interactive_agent_runtime_unittest.py::InteractiveAgentRuntimeUnitTest::test_run_turn_creates_session_tasks_events_and_final_answer`

- A turn without an input session creates a session bundle with tasks, events, and final answer.

`main/backend/tests/unit/test_interactive_agent_runtime_unittest.py::InteractiveAgentRuntimeUnitTest::test_run_turn_appends_to_existing_session`

- A turn with an explicit session ID preserves that ID and appends messages/tasks.

`main/backend/tests/integration/test_agent_chat_api_unittest.py::AgentChatApiIntegrationTestCase::test_agent_chat_turn_defaults_to_agent_core_v3`

- An API turn without a session ID reaches AgentCore v3 and returns a complete turn.

`main/backend/tests/integration/test_agent_chat_api_unittest.py::AgentChatApiIntegrationTestCase::test_agent_core_turn_uses_prior_session_transcript_for_followup`

- An explicit reused session supplies prior transcript and context to the follow-up turn.

The implementation branch in `main/backend/app/api/agent_chat.py::_prepare_agent_core_session` reuses a supplied `session_id` and creates a new session when it is omitted.

### Remaining exact gap

`WEBUI_CLEAR_TO_WIRE_BINDING_UNCOVERED`: the current embedded WebUI must clear or start a new chat, remove the visible prior messages, and omit the old `session_id` on the next request. The resulting session should be observably distinct from the detached session.

There is no reviewed focused backend/API test that performs two turns separated by a client clear because clear is not a backend operation. The paired create/reuse tests establish server branch semantics but do not close the client-to-wire binding.

## Consolidated disposition refinement

| Legacy item | Backend/API semantic state | Remaining accountable gap |
| --- | --- | --- |
| FE-AGENT-SKIP-05 cancel | `COVERED_BY_EXISTING_TEST_SOURCE_NOT_EXECUTED_HERE` | Embedded-WebUI utterance, rendering, negative residue, and focused stream observation. |
| FE-AGENT-SKIP-06 continue | `COVERED_BY_EXISTING_TEST_SOURCE_NOT_EXECUTED_HERE` | Embedded-WebUI utterance, rendering, negative residue, and focused stream observation. |
| FE-AGENT-SKIP-07 retry | `COVERED_BY_EXISTING_TEST_SOURCE_NOT_EXECUTED_HERE` | Embedded-WebUI utterance, rendering, negative residue, and focused stream observation. |
| FE-AGENT-SKIP-10 clear | `SERVER_CREATE_AND_REUSE_BRANCHES_COVERED_BY_EXISTING_TEST_SOURCE_NOT_EXECUTED_HERE` | Embedded-WebUI clear/new-chat state and next-request session identity binding. |

No entry is promoted to PASS by this read-only source review. The original four skipped browser observations remain skipped until a current-surface replacement test runs or an authorized additive successor/retirement decision is recorded.
