# Frontend Control Coverage Addendum v2

## Evidence boundary

- Audit date: `2026-09-08`.
- Current parent disposition: `stage1-successor-evidence/stage-convergence-batch-v1/frontend-skip-disposition.v2.md`, SHA-256 `fb047583078cfeb0e0b33ad34e340b37a76e90147cdb175ef5e8be9ad6712dd4`.
- Superseded parent record: `stage1-successor-evidence/stage-convergence-batch-v1/frontend-skip-disposition.v1.md`, current SHA-256 `c2249218da6c040b8a4103652422f642e8412a2f01ac8811a68d74b076c53f4b`. This corrects the stale `221d393d...` parent hash recorded by addendum v1.
- Supersedes: `stage1-successor-evidence/stage-convergence-batch-v1/frontend-control-coverage-addendum.v1.md`, SHA-256 `65a1206938bc32fcb57c86c1f08e7187b66bec67e434cf0a0899552793c889c2`.
- Method: current-byte source review plus main Playwright `--list` collection; no test body, preview, backend, embedded Codex child, or live provider was executed for this addendum.
- Execution state: `ACTIVE_COLLECTION_NOT_EXECUTED_ON_FRESH_PREVIEW`.
- Claim ceiling: source coverage is partitioned by owner and observation surface. Backend/API tests, compatibility-page browser tests, and embedded-Codex WebUI behavior are not interchangeable evidence.

## Exact reviewed identities

| Artifact | SHA-256 |
| --- | --- |
| `main/frontend-modern/tests/e2e/agent-chat.spec.ts` | `6986e4dcfae81f68c1d283b9fe142cdc93f25bbed85406a938ce391410f93cb2` |
| `main/frontend-modern/src/pages/AgentChatPage.tsx` | `27ce4053ea66feb6df90be3586a783a92b5a8b431c8abff880660e1b961d4795` |
| `main/frontend-modern/src/app/kernel/renderKernelModuleContent.tsx` | `0f1fa23e8731712247e5576e1c1dd5326032ecb90a0f15ca83d4f138041f3452` |
| `main/frontend-modern/src/app/kernel/routes.ts` | `e118600339161c0b88d1c5cb4d0197570c23469ebb7bf0c3225b7c0be0cc4aac` |
| `main/frontend-modern/src/pages/CodexAgentPage.tsx` | `974de9ef847d7fc1e8fd5ba8c1a05c30c59d1bb6646e8ff39bca80a49c1dd802` |
| `main/backend/tests/unit/test_agent_control_tools_unittest.py` | `dd8ac1a2138040011c68d78b6fa32ec6df6b7791fcec15373779c8ec0b76d57b` |
| `main/backend/tests/integration/test_agent_runtime_scenario_replay_unittest.py` | `91cd0a941b263553007ca0fff67428a4724e317f7eedb700522e51deae00a7f8` |
| `main/backend/tests/integration/test_agent_chat_api_unittest.py` | `d98507a55c5472fc9b8de57451ad4510d98789f5057ba0771eeadd1ae3fe75aa` |
| `main/backend/tests/unit/test_interactive_agent_runtime_unittest.py` | `0f82ea712eb922918ffa71d6907b30b19746ba283075cd4ca7bde535daf609f5` |
| `main/backend/app/api/agent_chat.py` | `0b1639a2701e05ff56676ffa769e72ad9518b8581340f07cce5eb02227d5f781` |

Any byte change in these artifacts invalidates the corresponding source-coverage statement until re-reviewed.

## Backend and API semantic coverage

Existing source materially covers the control semantics and must not be described as wholly absent:

- `test_control_capability_selection` maps natural-language continue, retry, and cancel utterances to `task.continue`, `task.retry`, and `task.cancel`.
- `test_task_cancel_cancels_session`, `test_task_continue_runs_coordinator_pass`, and `test_task_retry_uses_latest_failed_task_when_task_id_omitted` assert their direct state effects.
- `test_interactive_turn_can_dispatch_retry_as_control_tool` asserts retry dispatch, start/result events, and absence of batch submission.
- `test_s07_cancel_then_continue_preserves_recoverable_session_state` asserts cancel followed by recoverable continue behavior.
- `test_agent_core_control_tools_cancel_continue_retry_in_one_session` transports all three controls through `/api/v1/agent-chat/turn` and asserts API/store state. Its `FakeCoreProvider` fixtures prove deterministic integration, not live-model selection.
- Agent runtime create/reuse tests and `_prepare_agent_core_session` cover the server distinction between an omitted `session_id` and an explicit existing session.

This addendum did not execute those backend/API tests. Their source coverage does not prove compatibility-page rendering, embedded-Codex rendering, or live `/turn/stream` serialization.

## Active compatibility-page browser coverage

The current `agent-chat.spec.ts` restores the four control/clear cases as active tests on `/#agent-chat-compat.html`:

| Legacy ID | Active compatibility-source coverage | Remaining evidence limit |
| --- | --- | --- |
| FE-AGENT-SKIP-05 cancel | Sends the natural utterance, observes mocked SSE naming `task.cancel`, renders cancel feedback/tool detail, and rejects batch/fallback residue. | Not executed on the fresh preview; route-mocked SSE is not a live backend serialization receipt. |
| FE-AGENT-SKIP-06 continue | Sends the natural utterance, observes mocked SSE naming `task.continue`, renders continue feedback/tool detail, and rejects batch/fallback residue. | Not executed on the fresh preview; route-mocked SSE is not a live backend serialization receipt. |
| FE-AGENT-SKIP-07 retry | Sends the natural utterance, observes mocked SSE naming `task.retry`, renders retry feedback/tool detail, and rejects batch/fallback residue. | Not executed on the fresh preview; route-mocked SSE is not a live backend serialization receipt. |
| FE-AGENT-SKIP-10 clear | Clears visible assistant history and asserts the next mocked turn request omits the prior `session_id`. | Not executed on the fresh preview; it proves the compatibility client-to-wire binding only after the browser test runs. |

These declarations close the old static-skip classification at source level. They do not yet establish a passing browser result.

## WebUI observation boundary

The ten active tests exercise `AgentChatPage` through the explicit compatibility render variant. The canonical `/workbench/agent` route instead renders `CodexAgentPage`, which hosts `/codex/` in an iframe. Therefore:

- compatibility-page assertions may establish the in-process legacy/successor compatibility contract after execution;
- backend/API tests establish server classification, state, and transport contracts only within their assertions;
- neither source class establishes the embedded `/codex/` child WebUI's cancel, continue, retry, clear/new-chat, message-local tool rendering, or child layout behavior;
- the separate canonical-host test proves only the host and iframe `src`, not the child WebUI behavior; and
- mocked compatibility SSE cannot substitute for a focused real `/turn/stream` serialization check.

The embedded-WebUI observation boundary remains an explicit coverage boundary, not a reason to classify the active compatibility tests as skipped.

## Correction of addendum v1 line 121

Addendum v1 line 121 said that the four browser observations remained skipped. That statement is superseded. The accurate current-byte statement is:

> FE-AGENT-SKIP-05, FE-AGENT-SKIP-06, FE-AGENT-SKIP-07, and FE-AGENT-SKIP-10 are active compatibility-route Playwright tests. They were collected as part of the 112-test main inventory but have not been executed against the required fresh preview. No entry is promoted to PASS by source review or collection alone.

The full-suite runner must execute exactly 112 tests and report zero skips, failures, and errors before `PASS_COMPLETE_NO_SKIPS` can be asserted. The fresh preview, image, internal network, lifecycle admission, database target, and exclusive lease requirements remain unchanged.
