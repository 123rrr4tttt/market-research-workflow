# Wave5 Clue Chain Implementation Evidence

Date: 2026-05-22
Status: `wave5_merged` / `verification_passed`

This file is the supervisor evidence record for the Wave5 Clue Chain implementation. It updates the earlier planning placeholders after the implementation worktrees were merged into `codex/devdocs-wave5-integration-2026-05-22`.

## Integrated Branches

| Lane | Branch | Commit | Result |
|---|---|---:|---|
| A | `codex/devdocs-wave5-clue-chain-core-storage` | `3fe910e` | core `ClueChainService`, store, contracts, alias dedupe, decision state |
| B | `codex/devdocs-wave5-clue-chain-api-contract` | `378b2b3` | typed `/api/v1/clue-chains` create/list/detail/expand/decision/close API |
| C | `codex/devdocs-wave5-clue-chain-source-hop` | `e47465a` | deterministic source-library expansion hop |
| D | `codex/devdocs-wave5-clue-chain-external-hop` | `ab13626` | fixture-gated external-search expansion hop |
| E | `codex/devdocs-wave5-clue-chain-graph-integration` | `5846c61` | evidence-backed graph mutation/handoff payload builder |
| F | `codex/devdocs-wave5-clue-chain-agent-tool` | `d325760` | agent `chain.expand` tool with no-silent-promote guard |
| G | `codex/devdocs-wave5-clue-chain-frontend-api` | `edb9cba` | frontend Clue Chain API domain/types |
| H | `codex/devdocs-wave5-clue-chain-graph-ui` | `98fda79` | GraphPage create-chain action, inspector, evidence drawer, candidate queue |
| I | `codex/devdocs-wave5-clue-chain-docs-status` | `2a4cc03` | docs/index/status sync |
| J | `codex/devdocs-wave5-clue-chain-integration-review` | `98dc562` | integration risk review |
| Supervisor | `codex/devdocs-wave5-integration-2026-05-22` | `22fb5e8`, `315751f`, `b70a746` | API wired to core service; Graph UI merged; frontend contract aligned |

## Acceptance Evidence

| Requirement | Evidence |
|---|---|
| Create Chain from graph nodes | `POST /api/v1/clue-chains` integration test plus GraphPage e2e create-chain action |
| Source-library hop stores replayable evidence/candidates | `tests/unit/test_clue_chain_source_library_expansion_unittest.py`; API expand path records source hop into `ClueChainService` |
| External-search hop is fixture-gated by default | `tests/unit/test_clue_chain_external_search_expansion_unittest.py`; API default uses injected/fixture-gated results, not public network |
| Every promoted graph payload references ChainEvidence/ChainDecision | `tests/unit/test_clue_chain_graph_integration_unittest.py` rejects missing evidence and emits provenance fields |
| Agent can request expansion but cannot silently promote | `tests/unit/test_agent_core_clue_chain_tool_unittest.py`; handler returns `requires_review` and `graph_mutation_performed: false` |
| Duplicate aliases merge before new nodes | core service and source-library expansion unit tests cover alias dedupe |
| UI exposes frontier/hops/evidence/blockers/review queue | `tests/e2e/graph-clue-chain.spec.ts`; `ClueChainInspector` component |
| API schema remains typed | `tests/contract/test_api_schema_inventory_contract_unittest.py`; Clue Chain source summary has zero untyped 200 responses |

## Verification Commands

```text
cd main/backend && ./.venv311/bin/python -m pytest tests/unit/test_clue_chain_service_unittest.py tests/unit/test_clue_chain_source_library_expansion_unittest.py tests/unit/test_clue_chain_external_search_expansion_unittest.py tests/unit/test_clue_chain_graph_integration_unittest.py tests/unit/test_agent_core_clue_chain_tool_unittest.py tests/unit/test_agent_core_unittest.py tests/integration/test_clue_chains_api_unittest.py tests/contract/test_api_schema_inventory_contract_unittest.py -q
```

Result: `101 passed, 13 warnings, 6 subtests passed`.

```text
cd main/backend && ./.venv311/bin/python -m py_compile app/api/clue_chains.py app/contracts/schemas/clue_chains.py app/services/clue_chains/__init__.py app/services/clue_chains/contracts.py app/services/clue_chains/store.py app/services/clue_chains/service.py app/services/clue_chains/source_library_expansion.py app/services/clue_chains/external_search_expansion.py app/services/clue_chains/graph_integration.py
```

Result: passed.

```text
cd main/frontend-modern && npm run lint -- --max-warnings=0
```

Result: passed.

```text
cd main/frontend-modern && npx playwright test tests/e2e/graph-clue-chain.spec.ts --reporter=line
```

Result: `1 passed`.

```text
cd main/frontend-modern && npm run check:topology-platform
```

Result: passed with `status: ok`.

```text
cd main/frontend-modern && npm run build
```

Result: passed.

```text
changed Markdown link check for files changed since f04d9e9
```

Result: `CHANGED_DOC_LINKS_OK files=10`.

```text
git diff --check
```

Result: passed.

## Residual Scope

Wave5 closes the planned first implementation slice. The following are not claimed as closed by this evidence file:

- live public external-search provider reliability; default remains fixture-gated and opt-in;
- production graph submit conflict handling beyond evidence-backed payload generation;
- broader visual regression coverage outside the mocked GraphPage Clue Chain e2e;
- full repository-wide test suite.

The Clue Chain documents remain under `CURRENT_DEV` as the canonical feature entry, but the Wave5 implementation plan is no longer a placeholder.
