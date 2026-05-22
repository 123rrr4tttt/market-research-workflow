# Wave6-7 Writing Workbench Evolution Status Evidence and Minimum Plan (2026-05-21)

> Scope: evidence pass for `2026-03-07-writing-workbench-evolution`.
> Output mode: topic-local evidence only; no shared index edits.
> Result: do not archive the topic yet. Core loop and backend contracts are mostly sealed, but artifact/refactor/export-adapter work remains open.

## 1. Status Judgment

The two original documents in this directory are now partially outdated as status records:

- `01_writing-workbench-evolution-plan-2026-03-07.md` is still useful as the product boundary document.
- `02_atomic-tasklist-writing-workbench-evolution-2026-03-07.md` still says `E1-E9` are pending, but repo evidence now shows several tasks are implemented or bounded by contract tests.

Current status:

| Item | Status | Evidence | Minimum follow-up |
| --- | --- | --- | --- |
| `E1` baseline and delta matrix | sealed | `main/backend/app/services/writing/primary_loop_service.py` exposes `build_wave_a_baseline_matrix`; `main/backend/tests/unit/test_writing_primary_loop_service_unittest.py` asserts implemented vs deferred capability split. | Keep as evidence-backed; no rebuild-from-zero plan. |
| `E2` primary writing loop | sealed | `evaluate_primary_loop_state` defines document-ready -> editing -> saved -> context-loaded -> citation-applied -> action-executed -> write-back-ready; unit tests cover no-graph completion and ordering violations. | Preserve this loop as the future workbench invariant. |
| `E3` evidence vs graph context boundary | sealed, with frontend contract update needed | Backend schema has `WritingContextEnvelope`, `context_boundary`, and `dependency_gate`; keyword-card service already returns boundary metadata. | Land frontend type parity and a small contract check. Done in this branch. |
| `E4` templates and intermediate artifacts | partially sealed | Template list/validate paths and `TemplateLibraryPanel` exist; agent update review UI exists in `WritingWorkbenchPage.tsx`. There is no independent reusable generated-artifact model yet. | Keep generated artifacts as future work; do not call the topic fully closed. |
| `E5` canonical source and export staging | sealed for Markdown, open for non-Markdown adapters | `/api/v1/writing/export/markdown` rebuilds citations before returning Markdown; contract test keeps it as explicit non-JSON export. | Keep `docx`/`latex` adapters deferred and separate from authoring model. |
| `E6` LLM action and audit contract | sealed, with frontend contract update needed | Backend request/response schema has `target_scope`, `capability_truth`, `action_boundary`, and `dependency_gate`; API tests assert capability truth is returned. | Land frontend type parity and static check. Done in this branch. |
| `E7` surface refactor boundary | not sealed | Workbench still centralizes broad state in `WritingWorkbenchPage.tsx`, even though stories and E2E tests protect behavior. | Future refactor should split page coordination from templates, evidence/citations, LLM action audit, and agent-update review state. |
| `E8` cross-theme dependency contracts | sealed | `evaluate_primary_loop_state` returns `writing.cross_theme_gate.e8.v1` for graph, LLM, and frontend consume-only boundaries; tests cover invalid graph handoff blocking. | Keep dependency ownership outside this topic except for writing-side adapters. |
| `E9` minimum regression gate | partially sealed and updated | Backend unit/contract/integration tests exist; frontend E2E and Storybook fixtures exist. This branch adds `npm run check:writing-workbench-contract` for route/manifest/type parity. | Live Playwright writing E2E remains the broader gate when backend/browser prerequisites are available. |

## 2. Minimum Plan Landed in This Branch

This pass lands the smallest deterministic development plan:

1. Add a topic-local status evidence document instead of editing shared docs indexes.
2. Align frontend writing API types with backend E3/E6/E8 boundary fields:
   - keyword-card request: `context`, `graph_context`
   - keyword-card response: `context_boundary`, `dependency_gate`
   - LLM action payload: `target_scope`
   - LLM action response: `capability_truth`, `action_boundary`, `dependency_gate`
3. Add a static writing-workbench contract check:
   - verifies `flowWriting` remains reachable through module manifest, kernel renderer, hash resolver, and Storybook shell fixture
   - verifies frontend writing endpoint keys stay present
   - verifies frontend writing types expose backend boundary fields
   - verifies backend writing schema/API still contain the expected boundary fields and endpoints

## 3. Closure Decision

The topic should remain in `CURRENT_DEV`.

Closed enough to treat as baseline:

- `E1`, `E2`, `E3`, `E5` Markdown-only path, `E6`, `E8`

Still open:

- reusable generated artifacts after LLM output
- refactor split out of `WritingWorkbenchPage.tsx`
- non-Markdown export adapters
- full live frontend writing E2E gate in an environment with the backend/browser prerequisites running

## 4. Validation Commands

Run after this patch:

```bash
cd main/frontend-modern
npm run check:writing-workbench-contract
npm run check:topology-platform
npm run lint

cd ../backend
/Users/wangyiliang/.local/bin/python3.11 -m pytest tests/unit/test_writing_primary_loop_service_unittest.py tests/integration/test_writing_llm_actions_api_unittest.py tests/integration/test_writing_keyword_cards_api_unittest.py tests/contract/test_api_schema_writing_search_small_contract_unittest.py
```
