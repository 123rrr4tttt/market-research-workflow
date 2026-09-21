# Frontend Zero-Skip Disposition v2

## Status and authority boundary

- Audit date: `2026-09-08`.
- Supersedes: `stage1-successor-evidence/stage-convergence-batch-v1/frontend-skip-disposition.v1.md`, SHA-256 `c2249218da6c040b8a4103652422f642e8412a2f01ac8811a68d74b076c53f4b`.
- Scope: the ten cases formerly recorded as static skips in `main/frontend-modern/tests/e2e/agent-chat.spec.ts`.
- Current source disposition: `10 ACTIVE_TESTS`, `112 MAIN_TESTS`, `0 STATIC_SKIPS`.
- Main-suite collection observation: `112 tests in 15 files`; under the full-suite environment contract, all 112 are expected to remain active and the executed report must contain zero skips.
- Execution state: `FRESH_PREVIEW_NOT_EXECUTED`.
- Verdict: the v1 static-skip current-state classification and exclusion of the ten cases from the runnable denominator are historical and are superseded by this document. Collection does not establish `PASS`, `PASS_COMPLETE_NO_SKIPS`, embedded-Codex behavior, or production authority.
- Authority ceiling: `INTERNAL_REHEARSAL_ONLY`, `NO_LEGACY_RETIREMENT`, `PRODUCTION_RELEASE_NOT_AUTHORIZED`.

## Exact current-byte identities

| Artifact | SHA-256 | Binding relevance |
| --- | --- | --- |
| `main/frontend-modern/tests/e2e/agent-chat.spec.ts` | `6986e4dcfae81f68c1d283b9fe142cdc93f25bbed85406a938ce391410f93cb2` | Contains the ten active tests, their mocks and assertions, plus the separate canonical Codex-host mount test. |
| `main/frontend-modern/src/pages/AgentChatPage.tsx` | `27ce4053ea66feb6df90be3586a783a92b5a8b431c8abff880660e1b961d4795` | Implements the in-process compatibility surface exercised by the ten tests. |
| `main/frontend-modern/src/app/kernel/renderKernelModuleContent.tsx` | `0f1fa23e8731712247e5576e1c1dd5326032ecb90a0f15ca83d4f138041f3452` | Selects `AgentChatPage` only for `agent-chat-compat`; otherwise selects `CodexAgentPage`. |
| `main/frontend-modern/src/app/kernel/routes.ts` | `e118600339161c0b88d1c5cb4d0197570c23469ebb7bf0c3225b7c0be0cc4aac` | Resolves `/agent-chat-compat.html` to the compatibility render variant. |
| `main/frontend-modern/src/app/kernel/types.ts` | `0f1587211b74f9b484444dddd46768bd0321c6c9937bf0f7ec21e6190900887e` | Declares the `agent-chat-compat` render variant. |
| `main/frontend-modern/src/app/kernel/moduleManifest.ts` | `118aef45204d0063ef34478376c4bca693718f3f60d05c7ad85d1a2aa2fda2d5` | Registers `#agent-chat-compat.html` as an alias of `flowAgentChat`. |
| `main/frontend-modern/src/app/kernel/legacyHashAdapter.ts` | `b7a1c40da6269862b1c154fdc7f2f9a7a7525d3236efbee4ff590534c8387436` | Maps the compatibility hash to `flowAgentChat`. |
| `main/frontend-modern/src/pages/CodexAgentPage.tsx` | `974de9ef847d7fc1e8fd5ba8c1a05c30c59d1bb6646e8ff39bca80a49c1dd802` | Implements the canonical `/workbench/agent` host and embedded `/codex/` iframe, which is not the child surface exercised by the ten compatibility tests. |

These hashes bind the disposition to the current working-tree bytes. Any change to a bound artifact requires re-collection and a successor disposition rather than silent reuse of this record.

## Collection evidence and limit

The source was collected with:

```text
AGENT_CORE_REAL_BACKEND_E2E=1 FRONTEND_E2E_ISOLATED=1 \
  node_modules/.bin/playwright test --config playwright.config.ts --list
```

Observed terminal summary:

```text
Total: 112 tests in 15 files
```

The ten formerly skipped cases are ordinary `test(...)` declarations at their current source locations. Here, `0 STATIC_SKIPS` means that no main-suite case is permanently excluded from the full-mode collection. Conditional `test.skip(...)` guards remain for environment-dependent cases, but the full-suite contract sets `AGENT_CORE_REAL_BACKEND_E2E=1` and removes the backend-bypass input so those guards must not skip at execution time. The executed report is still required to contain zero skips. The collection observation does not launch the preview, backend, Codex stub, browser test bodies, shared services, or database-dependent flows. It is therefore not an execution receipt.

## Ten-case active-source disposition

| ID | Active test | Current source assertion boundary |
| --- | --- | --- |
| FE-AGENT-SKIP-01 | `free conversation returns a streamed model answer without execution chrome` | Compatibility UI renders a mocked streamed answer without execution residue. |
| FE-AGENT-SKIP-02 | `project and source-library fact questions use read-only project tools` | Compatibility UI and mocked SSE expose the two read-only tools without fallback or approval residue. |
| FE-AGENT-SKIP-03 | `explicit source-library execution stays on the frozen mainline without approval pause` | Compatibility UI and mocked SSE expose the execution tool without a permission event or approval callout. |
| FE-AGENT-SKIP-04 | `long task shows split tasks, progressive tool events, source quality, and writing diff` | Compatibility UI renders mocked task, event, quality, trace, diff, and reload-recovery state. |
| FE-AGENT-SKIP-05 | `natural cancel renders the AgentCore control tool` | Compatibility UI renders mocked `task.cancel`, feedback, and negative-residue assertions. |
| FE-AGENT-SKIP-06 | `natural continue renders the AgentCore control tool` | Compatibility UI renders mocked `task.continue`, feedback, and negative-residue assertions. |
| FE-AGENT-SKIP-07 | `natural retry renders the AgentCore control tool` | Compatibility UI renders mocked `task.retry`, feedback, and negative-residue assertions. |
| FE-AGENT-SKIP-08 | `mobile layout has no horizontal overflow after a chat turn` | Compatibility page, layout, thread, and message body are checked at `390x844` after a mocked turn. |
| FE-AGENT-SKIP-09 | `keeps default chat empty, renders capabilities as read-only, and surfaces backend failure as retryable error` | Compatibility UI checks clean default state, read-only capability display, explicit retry, and absence of fake success/debug leakage. |
| FE-AGENT-SKIP-10 | `clear session detaches backend session before the next turn` | Compatibility UI clears visible history and the next mocked request sends no old `session_id`. |

The active tests restore a deterministic browser contract for `AgentChatPage` through the explicit compatibility route. They do not claim that the embedded `/codex/` child WebUI implements the same controls, that mocked SSE is live provider evidence, or that collection is a passing run.

## Full-suite acceptance rule

The disposition can contribute to a full frontend PASS only when the hash-bound fresh preview is executed by the full-suite runner and its report exact-matches all of the following:

1. exactly 112 main-suite tests;
2. zero skipped tests, including zero conditional or environmental skips;
3. zero failures and zero errors;
4. unchanged source and candidate-surface identities; and
5. the admitted fresh image, internal network, backend lifecycle, database target, and exclusive database lease.

Until that receipt exists, the accurate state is `ACTIVE_COLLECTION_NOT_EXECUTED`, not `PASS` and not `SKIPPED`.
