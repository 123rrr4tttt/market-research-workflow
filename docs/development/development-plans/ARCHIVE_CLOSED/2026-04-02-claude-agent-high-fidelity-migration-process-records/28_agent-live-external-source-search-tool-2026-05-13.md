<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/28_agent-live-external-source-search-tool-2026-05-13.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/28_agent-live-external-source-search-tool-2026-05-13.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Live External Source Search Tool - 2026-05-13

Status: `no_closure_claim`

This pass closes the next implementation gap after `27_agent-material-supplement-writing-source-semantics-2026-05-13.md`: AgentCore now has a concrete external candidate search tool in the model-owned loop, not only a no-fetch discovery plan.

2026-05-14 sync: [`41_agent-high-fidelity-migration-closure-audit-2026-05-14.md`](./41_agent-high-fidelity-migration-closure-audit-2026-05-14.md) adds R3 Matrix Capability Execution. This document proves the existence and boundary of `source.web.search`; it does not authorize one search query as the default research workflow. Broad source discovery must use keyword/query matrices, internal/external tool branches, provider diagnostics, candidate deduplication, and ranked review before final answer or ingest.

## What Changed

- Added AgentCore tool `source.web.search`.
- The tool reuses the existing project search stack: `app.services.search.web.search_sources`.
- It returns candidate titles, URLs, snippets, provider metadata, and trust assessments.
- It does not fetch article bodies, ingest sources, or write project data.
- It evaluates candidate URLs through the existing source candidate trust gate before the model decides whether to continue into governed source-library/url-pool ingestion.
- It is exposed in:
  - external source discovery profile;
  - general material collection;
  - long-task investigation/writing;
  - writing workbench external material flows;
  - user-facing Agent tool pool metadata.

## Tool Boundary

`source.discovery.plan` remains the no-fetch/no-write planning gate.

`source.web.search` is the bounded external search step:

- network/search-provider I/O: yes;
- project writes: no;
- article body fetch: no;
- source ingestion: no;
- next gate: review candidates, then run governed source-library/url-pool ingestion if needed.

For matrix workflows, one `source.web.search` call is only one branch. The model should vary query terms, language, entity names, source classes, and provider route when the task asks for breadth or high confidence, then merge candidates before review.

`ingest.source_library.run` remains the governed collection/write boundary.

## Verification

- Focused backend:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_agent_core_unittest.py -q -k "source_web_search or tool_window_keeps_general_chat_empty or capability_material_categories"` -> `3 passed, 3 warnings`
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/integration/test_agent_chat_api_unittest.py -q -k "capabilities_route"` -> `2 passed, 11 warnings`
- Backend Agent matrix:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_interactive_agent_runtime_unittest.py main/backend/tests/unit/test_agent_run_loop_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q` -> `104 passed, 11 warnings`
- Frontend:
  - `npm run lint -- tests/e2e/agent-chat-real-backend-long-task.spec.ts` -> passed
- Real backend browser E2E:
  - backend: `AGENT_CORE_E2E_SCRIPTED_PROVIDER_ENABLED=true PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8021`
  - frontend: `AGENT_CORE_REAL_BACKEND_E2E=1 VITE_API_PROXY_TARGET=http://127.0.0.1:8021 npm run test:e2e -- tests/e2e/agent-chat-real-backend-long-task.spec.ts --reporter=line` -> `2 passed`

## Remaining Limits

- The browser E2E uses the default-off scripted provider and deterministic candidate payload for repeatability.
- Live search quality still depends on local provider configuration (`SERPER_API_KEY`, Google CSE, Serpstack, SerpAPI, or DDG availability/rate limits).
- The next acceptance gap is quality evaluation against real provider output plus candidate-to-ingest review UX, not the absence of an AgentCore search tool.
- The R3 acceptance gap is matrix execution: traceable keyword/provider/evidence branching plus deduped candidate ranking, not merely a successful single live query.
