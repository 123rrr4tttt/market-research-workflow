# Agent Writing Material Scope Ontology Refinement

Date: 2026-05-14
Status: implemented, not final closure

## Problem

The Agent already separated project material from source-library entries, but the material scope vocabulary was still too narrow for writing workflows:

- generic "supplement material" should be treated as material gathering, not just a read-only inventory request;
- writing-context material requests should start from internal project data, graph, artifacts, and writing documents;
- explicit outside/web/new/source/reference wording should expose external discovery and search;
- already collected/stored/ingested material should remain internal existing evidence, even if it originally came from an external source;
- writing gaps such as "existing material is insufficient, find more references" should be allowed to escalate to external discovery.

## Implementation

- Extended shared material ontology vocabulary in `main/backend/app/services/agent_runtime/material_ontology.py`:
  - external/new/reference terms: `新的资料`, `更多来源`, `额外来源`, `参考来源`, `引用来源`, `参考文献`, `再找来源`;
  - internal/existing terms: `既有`, `已经存储`, `项目库中`, `已归档`;
  - material terms: `来源`, `引用`, `出处`, `source(s)`, `citation(s)`, `reference(s)`;
  - writing gap terms: `不足`, `不够`, `缺口`, `需要更多`, `insufficient`, `gap`, `missing`.
- Refined classification order:
  - explicit source-library/catalog terms still route to source catalog tools;
  - writing requests with explicit existing/project-local material route to `internal_existing`;
  - writing requests with a material gap route to `external_discovery` with mixed scope;
  - explicit external/web/new/reference terms route to external discovery/ingest.
- Mirrored the same vocabulary in `main/backend/app/services/agent_core/tool_window.py` so tool-window slicing exposes the right candidate tools while leaving final tool choice to the model.
- Updated deterministic real-backend E2E scripted provider so writing-gap material requests use the external-writing path.
- Added backend regression coverage for generic reference supplementation, project-local existing reference sources, and writing-gap escalation.
- Added browser E2E coverage for writing-gap reference search in AgentChat.

## Validation

- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_agent_core_unittest.py -q -k "material_ontology or tool_window_keeps_general_chat_empty"` -> `4 passed, 50 deselected, 3 warnings`.
- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_interactive_agent_runtime_unittest.py main/backend/tests/unit/test_agent_run_loop_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q` -> `113 passed, 11 warnings`.
- `cd main/frontend-modern && npm run lint -- src/pages/AgentChatPage.tsx src/pages/agent-chat.css tests/e2e/agent-chat-real-backend-long-task.spec.ts` -> `0 errors, 1 existing CSS ignored warning`.
- `cd main/frontend-modern && npm run build` -> passed.
- With scripted real backend on `127.0.0.1:8021`: `AGENT_CORE_REAL_BACKEND_E2E=1 VITE_API_PROXY_TARGET=http://127.0.0.1:8021 npm run test:e2e -- tests/e2e/agent-chat-real-backend-long-task.spec.ts --reporter=line` -> `2 passed`.

## Remaining Notes

- This is a semantic routing refinement, not a closure claim for the whole Claude-Code-level Agent migration.
- The intended behavior is model-owned: the ontology narrows the visible tool set and prompt semantics, but the model still decides whether to call internal project tools, external search, or collection tools based on current user wording and tool results.
- Synchronized with R3 in `41_agent-high-fidelity-migration-closure-audit-2026-05-14.md`: material scope classification is only the first dimension of the capability matrix. Writing/material supplementation should branch across internal existing materials, generated artifacts, source catalog/history, external query variants, provider readiness, and candidate review before concluding coverage or performing ingest.
