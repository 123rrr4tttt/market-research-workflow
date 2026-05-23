<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/27_agent-material-supplement-writing-source-semantics-2026-05-13.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/27_agent-material-supplement-writing-source-semantics-2026-05-13.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Material Supplement And Writing Source Semantics - 2026-05-13

Status: `no_closure_claim`

This pass tightens the material-intent boundary from the user-facing scenario:

- General material supplementation should mean gathering useful material, not mechanically mapping every "资料" request to source-library.
- Writing-context material requests should prefer internal project material first: structured data, graph data, artifacts, writing documents, and session outputs.
- Writing-context external requests should still be able to search external material and continue into governed collection when the user asks for external/web/new material.
- Source-library remains a catalog/collection-entrypoint category, not a synonym for already stored project material.

## Code Changes

- `material_ontology` now covers broader abstract collection wording such as search/gather/find expressions instead of only exact "补充资料" phrases.
- `select_core_tool_window` now consumes the shared material intent result for collection detection, so "搜集一些资料" and similar expressions enter the material-collection profile.
- The material ontology now treats source decisions as dimensions instead of one-off phrases:
  - origin: internal project material, source-library/catalog entrypoint, external/web source;
  - state: existing/stored/ingested/generated, catalog-only, or to-collect;
  - context: writing/text/draft/report, investigation, project read, or general conversation.
- Abstract phrasing such as "已入库资料", "采集到的资料", "站外公开来源", "选区/这段文字" now routes through those dimensions instead of source-library string matching.
- General material collection exposes `project.context.bundle`, internal project search, `source.discovery.plan`, source-library search/list, and governed `ingest.source_library.run` when the model chooses to continue collection.
- Writing workbench tool windows keep both internal material tools and external discovery/collection tools visible, while model guidance says internal first unless explicit external/web/new material or an internal gap.
- The E2E scripted provider now uses `classify_material_intent` for supplement routing and preserves long-task routing priority.
- Native and JSON AgentCore providers now share the same prompt contract: general supplement means gather context, writing supplement starts internal-first, already collected/ingested material is internal evidence, and source-library remains an entrypoint.

## Browser Acceptance Matrix

`agent-chat-real-backend-long-task.spec.ts` now covers a real backend SSE matrix:

1. Normal fact question: no tool call.
2. Existing project material question: `project.context.bundle`, not source-library as the primary answer.
3. Source-library catalog question: `source_library.item.list`.
4. General "搜集资料" request: internal context first, then `source.discovery.plan`.
5. Writing "搜索资料" request: internal context and writing document list, no source-library ingest.
6. Writing "已入库资料" request: internal context and writing document list, no source-library ingest.
7. Writing "站外公开来源" request: internal context, `source.discovery.plan`, `source.web.search`, and governed `ingest.source_library.run`.
8. Long writing investigation: internal context, stage updates, discovery, source intake, investigation trace, and writing document insertion.

## Verification

- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_agent_core_unittest.py -q -k "material_ontology or tool_window_keeps_general_chat_empty"` -> `4 passed, 3 warnings`
- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_interactive_agent_runtime_unittest.py main/backend/tests/unit/test_agent_run_loop_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q` -> `103 passed, 11 warnings`
- `npm run lint -- tests/e2e/agent-chat-real-backend-long-task.spec.ts` -> passed
- `AGENT_CORE_REAL_BACKEND_E2E=1 VITE_API_PROXY_TARGET=http://127.0.0.1:8021 npm run test:e2e -- tests/e2e/agent-chat-real-backend-long-task.spec.ts --reporter=line` with backend started as `AGENT_CORE_E2E_SCRIPTED_PROVIDER_ENABLED=true ... uvicorn ... --port 8021` -> `2 passed`

Additional verification after abstract source-state/context expansion:

- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/unit/test_interactive_agent_runtime_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q -k "material_ontology or tool_window_keeps_general_chat_empty or native_tool_calling_provider_maps_safe_names_to_canonical_tools or writing_material_supplement or text_writing or agent_core"` -> `61 passed, 32 deselected, 11 warnings`
- `npm run lint -- tests/e2e/agent-chat-real-backend-long-task.spec.ts` -> passed
- `AGENT_CORE_REAL_BACKEND_E2E=1 VITE_API_PROXY_TARGET=http://127.0.0.1:8021 npm run test:e2e -- tests/e2e/agent-chat-real-backend-long-task.spec.ts --reporter=line` with backend started as `AGENT_CORE_E2E_SCRIPTED_PROVIDER_ENABLED=true ... uvicorn ... --port 8021` -> `2 passed`

## Remaining Limits

- This is still deterministic browser evidence for the AgentCore/tool boundary. It does not prove live web search quality or live external source fetching.
- The next gap is to connect live external search/MCP-backed discovery into the same model-owned loop while preserving the internal-first writing behavior.
