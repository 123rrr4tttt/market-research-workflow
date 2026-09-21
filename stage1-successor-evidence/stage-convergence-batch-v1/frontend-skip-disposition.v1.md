# Frontend Static-Skip Disposition v1

## Status and authority boundary

- Audit date: `2026-09-07`
- Scope: the ten static skips in `main/frontend-modern/tests/e2e/agent-chat.spec.ts`.
- Verdict: `10 CURRENT_FUNCTIONALITY_GAP_OR_MIGRATION_GAP`, `0 PASS`, `0 AUTHORIZED_RETIRED`.
- A skipped test is not a passing test. None of the ten observations is counted in a passing denominator.
- The working tree currently routes `flowAgentChat` to `CodexAgentPage`, but the route replacement and the two `describe.skip` edits are uncommitted working-tree changes. They are observable implementation state, not a formal product-retirement decision.
- The scoped search found no current AgentChat/Codex R100, successor decision, or additive retirement contract authorizing removal of the ten behavioral claims.
- The current authority ceiling remains `NO_LEGACY_RETIREMENT`. The deployment plan says any retirement requires a separate task, evidence, and authorization. Therefore this audit does not infer retirement from route visibility, a passing host shell test, or a stubbed iframe.

## Exact source and decision identities

| Artifact | SHA-256 | Relevance |
| --- | --- | --- |
| `main/frontend-modern/tests/e2e/agent-chat.spec.ts` | `50faef14d037fd63c82cef0dd10dacddbf9e5c9b1d4f97e4a805b498fff44140` | Contains all ten static skips and the one active host-only route test. |
| `main/frontend-modern/src/app/kernel/moduleManifest.ts` | `451510c3ed78fd263b32442c61b6b5b0ad487a9013f15368c66fc264cccfb1c1` | Defines `flowAgentChat` at `/workbench/agent` and preserves legacy hash identity. |
| `main/frontend-modern/src/app/kernel/legacyHashAdapter.ts` | `c79a3f4f24c6fbbae9ac4fdb17ca651dde4cf0a5717f680e8b484fa5a909df3e` | Maps `agent-chat.html` and `agent.html` to `flowAgentChat`. |
| `main/frontend-modern/src/app/kernel/renderKernelModuleContent.tsx` | `05976605ac0c94cba470441e80c8defd2cae94950069b474fe54801eb2e167a7` | Current working-tree projection `flowAgentChat -> CodexAgentPage`. |
| `main/frontend-modern/src/pages/CodexAgentPage.tsx` | `c0d4eab0bed40bef3a277af6825d42e665defebd3c6b286e21803d928b17cf1a` | Current host status/bootstrap/iframe surface; it does not implement the ten legacy observations. |
| `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/06_production-deployment-stage-progress.v1.md` | `2f13a5402620f59433cb63168e6d7de558a81e29da8423da857c68ea2525497b` | Records the skips as `legacy_agent_chat_migrated_or_real_backend_bypassed`; the file explicitly has no retirement authority. |
| `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/16_stage-convergence-execution-amendment.v1.md` | `316339cdfa538f66272802e31dd236c0838f1fcd093169d79408b81e816ded6f` | Preserves `NO_LEGACY_RETIREMENT` at line 63. |
| `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/04_production-deployment-stage-plan.v1.md` | `d04ae870b5d2a13afacdc7a07e9d5a89b7ab77e7b6c2d6cdd4bd2101151f76fa` | Requires separate task, evidence, and authorization for retirement at line 353. |
| `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/41_agent-high-fidelity-migration-closure-audit-2026-05-14.md` | `930f347cc8f5b4634741ebf344a3c20f0354c5e45f241f65827729d7603751b1` | Historical closure record that treated the affected AgentChat behavior as covered; it is lineage, not current retirement authority. |

## Replacement-test inventory

| Test artifact | SHA-256 | Actual coverage boundary |
| --- | --- | --- |
| `main/frontend-modern/tests/e2e/agent-chat-real-backend-long-task.spec.ts` | `fd0628a587815d6fb65282b4104cfadf1cc0d1655d8151359dbac26d94127148` | Real backend scripted AgentCore semantics, persistent session readback, Codex host mount, and Writing Workbench output. No embedded Codex child-UI assertion. |
| `main/frontend-modern/tests/e2e/agent-chat-writing-crossflow.spec.ts` | `605ab3ae1cd136323a8de007a1e8bea46e6a7aed3986f128897d154ba7d06e5e` | Codex host availability plus writing document create/readback. No chat behavior. |
| `main/frontend-modern/tests/e2e/writing-workbench.spec.ts` | `d6c88629102a00e55146734d73f7f506b1de2845baa068436678275a301f60a2` | Writing create/edit/review/search/rewrite/rollback/mobile behavior. No AgentChat or Codex conversation behavior. |
| `main/frontend-modern/tests/e2e/graph-clue-chain.spec.ts` | `d63ba98e769926068aa1b72ba05b3198d3856be459ad207beac242112e5934f3` | Graph clue-chain, blocked-provider, evidence drawer, and reviewed-candidate UI. No AgentChat progressive cards. |
| `main/frontend-modern/tests/e2e/successor-runtime-client.spec.ts` | `f3d423b6be77b4578682c224d04d27f4d82b44bc0c2dc0fa94295f6bbd7c7065` | Successor envelope, identity, projection-clock, retry, and rollback client laws. Not chat control behavior. |
| `main/frontend-modern/tests/e2e/successor-runtime-observation.spec.ts` | `0c822a1b1e6f5cee6cd87bd3e3bc51f7170cf8a32de41b649a67544d1322810d` | Successor observation vocabulary and derivation. Not chat cancel/continue/retry behavior. |
| `main/frontend-modern/src/pages/AgentChatPage.stories.tsx` | `874f90e0882a3f5d306bec1b427334653b07e27694b548f46a090e507b6725d7` | Default component render only; it has no `play` function and is not a behavioral replacement. |

## Ten-item disposition

### FE-AGENT-SKIP-01

- Test ID: `free conversation returns a streamed model answer without execution chrome` (`agent-chat.spec.ts:390`).
- Old observation claim: a substantive streamed CAPM answer appears; no batch fallback, approval/debug residue, message metadata, run details, or tool chrome appears; runtime summary reports zero tools.
- Current route: `flowAgentChat -> CodexAgentPage -> /codex/` under the exact route hashes above.
- Available replacement: the first real-backend long-task test asserts CAPM content and absence of `agent_core.tool_call_requested`; the active host test asserts only host and iframe mount.
- Decision: `PARTIAL_CURRENT_COVERAGE`, `UI_OBSERVATION_GAP`, `NOT_RETIRED`.
- Minimal restoration: retain the semantic no-tool assertion at the AgentCore API boundary; add a stable embedded-WebUI child contract for final answer and absence of execution chrome. A host iframe or stub marker is insufficient.

### FE-AGENT-SKIP-02

- Test ID: `project and source-library fact questions use read-only project tools` (`agent-chat.spec.ts:406`).
- Old observation claim: the stream selects `project.summary.read` and `source_library.item.list`; message-local tool details render both; no timeout, fallback, batch submission, debug detail, or approval pause appears.
- Current route: the same embedded Codex route; no formal retirement decision exists.
- Available replacement: the first real-backend long-task test covers `project.context.bundle`, `source_library.item.list`, and the internal-material/source-catalog distinction.
- Decision: `PARTIAL_CURRENT_COVERAGE`, `TOOL_RENDERING_GAP`, `NOT_RETIRED`.
- Minimal restoration: preserve structured API tool-selection assertions, then add a child-WebUI tool-result rendering assertion when a stable browser contract exists.

### FE-AGENT-SKIP-03

- Test ID: `explicit source-library execution stays on the frozen mainline without approval pause` (`agent-chat.spec.ts:423`).
- Old observation claim: the stream contains tool request/result for `ingest.source_library.run`, contains no permission request, renders tool detail, and presents no approval callout or waiting text.
- Current route: the same embedded Codex route; no formal retirement decision exists.
- Available replacement: real-backend material/source flows exercise `ingest.source_library.run`, but do not preserve the complete no-permission and UI no-pause observation.
- Decision: `PARTIAL_CURRENT_COVERAGE`, `APPROVAL_OBSERVATION_GAP`, `NOT_RETIRED`.
- Minimal restoration: add structured API assertions for request/result and absence of permission events; add the corresponding current-surface approval-state check.

### FE-AGENT-SKIP-04

- Test ID: `long task shows split tasks, progressive tool events, source quality, and writing diff` (`agent-chat.spec.ts:435`).
- Old observation claim: two planned tasks, durable long-task stages, evidence/gap counts, nine progressive tool events, source score, investigation trace, writing diff, and reload recovery are visible in the agent surface.
- Current route: the same embedded Codex route; no formal retirement decision exists.
- Available replacement: the second real-backend long-task test covers AgentCore events, structured persistent session/task/event/artifact readback, source review/status, and Writing Workbench output. Graph tests cover related trace/candidate UI on another route.
- Decision: `PARTIAL_CURRENT_COVERAGE`, `CANONICAL_AGENT_UI_GAP`, `NOT_RETIRED`.
- Minimal restoration: test the equivalent cards/recovery in the embedded WebUI. If `AgentChatPage` remains a supported noncanonical component, its component test may be restored separately and explicitly labelled `LEGACY_COMPONENT_NOT_CANONICAL`; it cannot close the production-route claim.

### FE-AGENT-SKIP-05

- Test ID: `natural cancel renders the AgentCore control tool` (`agent-chat.spec.ts:473`).
- Old observation claim: a natural-language cancel utterance selects and renders `task.cancel`, returns canceled feedback, and avoids batch/fallback residue.
- Current route: the same embedded Codex route; no formal retirement decision exists.
- Available replacement: no frontend replacement. Successor retry/rollback laws are a different contract. Historical control contract `09_agent-runtime-v2-session-control-tools-2026-05-10.md` SHA-256 `b743dc477dc73b552005e1680114a5b9a6627542bd824dcdd5933a5abf9c7a35` preserves lineage only.
- Decision: `CURRENT_FUNCTIONALITY_GAP`, `NOT_RETIRED`.
- Minimal restoration: deterministic AgentCore turn plus session-status/event readback for `task.cancel`, followed by current embedded-WebUI rendering coverage.

### FE-AGENT-SKIP-06

- Test ID: `natural continue renders the AgentCore control tool` (`agent-chat.spec.ts:484`).
- Old observation claim: a natural-language continue utterance selects and renders `task.continue`, returns continued feedback, and avoids batch/fallback residue.
- Current route and available lineage: same as FE-AGENT-SKIP-05.
- Decision: `CURRENT_FUNCTIONALITY_GAP`, `NOT_RETIRED`.
- Minimal restoration: deterministic AgentCore turn plus session/event readback for `task.continue`, followed by current embedded-WebUI rendering coverage.

### FE-AGENT-SKIP-07

- Test ID: `natural retry renders the AgentCore control tool` (`agent-chat.spec.ts:495`).
- Old observation claim: a natural-language retry utterance selects and renders `task.retry`, returns retry feedback, and avoids batch/fallback residue.
- Current route and available lineage: same as FE-AGENT-SKIP-05.
- Decision: `CURRENT_FUNCTIONALITY_GAP`, `NOT_RETIRED`.
- Minimal restoration: deterministic AgentCore turn plus failed-task/session/event readback for `task.retry`, followed by current embedded-WebUI rendering coverage.

### FE-AGENT-SKIP-08

- Test ID: `mobile layout has no horizontal overflow after a chat turn` (`agent-chat.spec.ts:506`).
- Old observation claim: after a real chat turn at `390x844`, the page, layout, thread, and message body do not overflow horizontally.
- Current route: the host page now owns an iframe, while child layout is owned by the embedded WebUI.
- Available replacement: none. The AgentChat Storybook default has no play function. Writing Workbench mobile coverage concerns another page.
- Decision: `CURRENT_FUNCTIONALITY_GAP`, `NOT_RETIRED`.
- Minimal restoration: split the claim into host iframe containment/overflow and child-WebUI conversation overflow. The former cannot imply the latter.

### FE-AGENT-SKIP-09

- Test ID: `keeps default chat empty, renders capabilities as read-only, and surfaces backend failure as retryable error` (`agent-chat.spec.ts:529`).
- Old observation claim: the default session is clean; capability/external-boundary groups are read-only and accurately labelled; stream/turn failure yields an explicit retryable error with no fake assistant success or debug leakage.
- Current route: `CodexAgentPage` exposes only status/bootstrap/iframe host behavior; it does not expose these controls directly.
- Available replacement: none. Existing status mocks and the synthetic stub do not test capability or retry behavior.
- Decision: `CURRENT_FUNCTIONALITY_GAP_REQUIRING_PRODUCT_OWNER_DECISION`, `NOT_RETIRED`.
- Minimal restoration: decide the current owner of capability-boundary presentation; test it there. Preserve fail-closed/retry behavior in the embedded-WebUI browser contract. A synthetic error page is diagnostic only.

### FE-AGENT-SKIP-10

- Test ID: `clear session detaches backend session before the next turn` (`agent-chat.spec.ts:630`).
- Old observation claim: clearing removes assistant messages and the next turn sends `session_id: null`, rather than retaining the previous backend session.
- Current route: the embedded WebUI owns new-chat/clear interaction. The real-backend helper intentionally preserves one session across its conversation.
- Available replacement: none.
- Decision: `CURRENT_FUNCTIONALITY_GAP`, `NOT_RETIRED`.
- Minimal restoration: expose and test the embedded WebUI new-chat/clear contract, including outgoing next-turn session identity, or obtain an explicit additive retirement/successor decision.

## Synthetic Codex stub 18379 protocol

Implementation: `stage1-successor-evidence/stage-convergence-batch-v1/codex-stub18379.mjs`, SHA-256 `92b702d8a56d59e0b97cf173f8b29faff444bc101c1ded320ebca7d11c69e7b7`.

- Listen only on `127.0.0.1:18379` by default.
- `GET|HEAD /healthz`: `204`, `Cache-Control: no-store`, `X-Codex-E2E-Stub: 1`.
- `GET|HEAD /`: static no-script HTML containing `data-testid="codex-stub-root"` and fixture-boundary metadata.
- `GET|HEAD /api/auth/bootstrap`: synthetic JSON with `e2e-codex-stub-noncredential`; this exercises only the current bootstrap/localStorage/remount path and is not user or native Codex authentication.
- `/socket.io/**` and HTTP Upgrade: explicit `501 WEBSOCKET_NOT_IMPLEMENTED`.
- Unknown routes: `404`; state-changing or unsupported methods: `405` with `Allow: GET, HEAD`.
- JSON-lines log retains method, path, status, and allowlisted proxy headers. Authorization and Cookie values are never logged; only their presence is recorded.
- The stub performs no external request, user-auth lookup, native Codex call, or database operation.
- Intended wiring: `VITE_CODEX_PROXY_TARGET=http://127.0.0.1:18379` in the isolated preview only.
- Passing scope: proxy rewrite, forwarded prefix observation, bootstrap response handling, and iframe materialization. It does not claim Codex chat, user authentication, WebSocket, tool rendering, session control, or any of the ten skipped behaviors.

## Follow-up gate

The ten skips remain outside PASS. A later candidate may close an item only with either:

1. a replacement test that preserves the old semantic and observable claim on its current owner; or
2. an explicit additive successor/retirement decision identifying what is preserved, changed, and lost.

Homepage visibility, iframe `src`, Storybook default rendering, static stub readiness, backend-only semantics, and unrelated successor-client laws must not be substituted for the missing browser observations.

## Current-byte disposition (2026-09-08)

All ten named cases above are now active Playwright tests in
`main/frontend-modern/tests/e2e/agent-chat.spec.ts`. The current collection
inventory is 112 main-suite tests and zero static skips. This closes only the
old static-skip classification: execution still requires the fresh preview,
image, service admission, and database lease defined by the full-suite plan.
