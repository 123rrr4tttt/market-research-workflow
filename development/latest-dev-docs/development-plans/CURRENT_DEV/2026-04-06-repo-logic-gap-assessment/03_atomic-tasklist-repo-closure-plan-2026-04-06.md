# Atomic Task List: Repo Closure Plan (2026-04-06)

## Execution Status Snapshot

- `AT-RCL-01`: pending, freeze scope / owner / compatibility inventory.
- `AT-RCL-02`: pending, workflow graph durable runtime and closure contract.
- `AT-RCL-03`: pending, workflow graph integrity and replay verification.
- `AT-RCL-04`: pending, agent session runtime canonical-path convergence.
- `AT-RCL-05`: pending, project key hardening and hard-gate rollout.
- `AT-RCL-06`: pending, LLM capability truthfulness and naming split.
- `AT-RCL-07`: pending, source-library authority vs compat contract split.
- `AT-RCL-08`: pending, frontend render/shell ownership convergence.
- `AT-RCL-09`: pending, legacy hash adapter and B-layer shell closure.
- `AT-RCL-10`: pending, required checks / PR evidence / docs closure.
- `AT-RCL-11`: pending, final regression pack and closure note.

## Reference Pack

- [01_repo-logic-gap-assessment-2026-04-06.md](./01_repo-logic-gap-assessment-2026-04-06.md)
- [02_repo-closure-plan-aligned-with-latest-direction-2026-04-06.md](./02_repo-closure-plan-aligned-with-latest-direction-2026-04-06.md)
- [01_claude-agent-high-fidelity-migration-mapping-2026-04-02.md](../2026-04-02-claude-agent-high-fidelity-migration/01_claude-agent-high-fidelity-migration-mapping-2026-04-02.md)
- [03_frontend-three-layer-rewrite-closure-gap-assessment-and-rollout-2026-04-02.md](../2026-03-15-frontend-three-layer-rewrite/03_frontend-three-layer-rewrite-closure-gap-assessment-and-rollout-2026-04-02.md)
- [01_source-library-ingest-minimal-migration-plan-2026-03-25.md](../2026-03-25-source-library-ingest-minimal-migration/01_source-library-ingest-minimal-migration-plan-2026-03-25.md)
- [05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md](../2026-03-25-source-library-ingest-minimal-migration/05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md)
- [PULL_REQUEST_TEMPLATE.md](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/.github/PULL_REQUEST_TEMPLATE.md)
- [branch-protection-required-checks.json](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/.github/branch-protection-required-checks.json)
- [backend-tests.yml](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/.github/workflows/backend-tests.yml)
- [check_api_layer_imports.py](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/scripts/check_api_layer_imports.py)

## Serial-Parallel Rules

- L0 serial bootstrap:
  - `AT-RCL-01`
- L1 parallel runtime foundation split:
  - `AT-RCL-02`
  - `AT-RCL-04`
  - `AT-RCL-05`
  - `AT-RCL-06`
- L2 serial runtime convergence:
  - `AT-RCL-03`
  - `AT-RCL-07`
- L3 parallel frontend and governance:
  - `AT-RCL-08`
  - `AT-RCL-09`
  - `AT-RCL-10`
- L4 serial closure:
  - `AT-RCL-11`

## Global Acceptance Contract

- `workflow graph` 必须从进程内编译态收口到可恢复、可回取、可验证的 runtime。
- `agent_batch`、`workflow_graph`、`skill_runtime` 可暂保留 compat 入口，但 session/task/event ledger 必须明确为主核。
- `project_key` 必须从默认软约束收紧到目标环境可用的硬约束。
- LLM 相关能力必须区分“真实模型路径”和“模板/规则 fallback 路径”。
- source-library 的兼容输出可以保留，但必须显式区分权威输出和 compat projection。
- frontend 只能存在一个模块/路由事实源；legacy hash 只能存在于显式 adapter 边界。
- 收口任务必须带最小验证命令、回退方式、以及文档索引更新。
- 收口完成前，不得以“后续再补文档/验证”为理由把主题从 `CURRENT_DEV` 提前归档。

## Topology-Risk Confirmation

以下任务当前最容易因为“对现有结构拓扑理解不完整”而导致改动失败，必须先按护栏模式执行，不能直接改默认行为：

- 高风险：
  - `AT-RCL-04`
  - `AT-RCL-07`
  - `AT-RCL-08`
  - `AT-RCL-09`
- 中风险：
  - `AT-RCL-02`
  - `AT-RCL-05`
- 低到中风险：
  - `AT-RCL-06`
  - `AT-RCL-10`

确认依据：

1. `workflow graph` 当前编译记录仍保存在进程内 `_compiled` registry，`run()` 先回取内存态，再投给 runtime；虽然 run store 与 handoff store 已经存在，但它们还没有覆盖 compiled artifact registry，所以如果在未冻结 graph id / version / store 语义前直接改执行主链，仍然容易把现有运行路径打断。
2. source-library 当前明确同时暴露 `terminal_output`、`frontdoor_ingress`、`postprocess_frontdoor`、`legacy_result`；如果在未完成 caller matrix 之前直接删减或改写默认输出，最容易破坏现有兼容调用方。
3. frontend 当前真实存在双中心：
   - `AppShell` 自己维护页面分发和 hash 同步
   - `ModuleRenderer` 再维护一份页面分发
   - `FrontendKernelApp` 对 unknown route 仍回退旧 `AppShell`
   - `moduleManifest -> contracts -> registry` 已形成派生链，但真正未收敛的是 render ownership 与 compat fallback
4. `project_key` fallback 是当前真实运行策略，不是偶然漏网；如果在未区分环境和 caller 之前直接把默认策略切成 `require`，高概率影响现有功能流。

因此，本轮实现必须额外遵守下面这些“不会影响当前功能”的护栏：

1. 先补 mapping、store、metadata、parity test，再切默认路径。
2. 先保留 compat 输出和旧入口，再做 authority path 和 canonical path。
3. 所有高风险任务第一阶段只允许 additive change，不允许 destructive change。
4. 所有默认行为切换都必须由显式 knob / feature flag / env 开关控制。
5. 在 parity checklist 跑通前，不允许移除旧路由、旧 hash、旧 response 字段、旧 adapter 入口。

## Functional-Safety Policy

为确保修改计划不影响当前功能，本轮收口统一采用三档改动策略：

- `freeze-only`
  - 只允许补文档、补 mapping、补 caller matrix、补验证，不改任何默认运行路径。
- `additive-only`
  - 只允许新增 store、metadata、guard、验证、双写/双读、显式 adapter，不允许删字段、不允许切默认值。
- `switchable`
  - 允许通过显式开关切换新行为，但必须保留一键回退路径。

任务对应策略：

- `AT-RCL-01`: `freeze-only`
- `AT-RCL-02`: `additive-only`
- `AT-RCL-03`: `additive-only`
- `AT-RCL-04`: `freeze-only -> additive-only -> switchable`
- `AT-RCL-05`: `additive-only -> switchable`
- `AT-RCL-06`: `additive-only`
- `AT-RCL-07`: `freeze-only -> additive-only -> switchable`
- `AT-RCL-08`: `freeze-only -> additive-only`
- `AT-RCL-09`: `freeze-only -> additive-only -> switchable`
- `AT-RCL-10`: `additive-only`
- `AT-RCL-11`: `switchable`

## Task AT-RCL-01: Freeze Closure Scope, Owner Map, and Compatibility Inventory

- Goal: 冻结本轮收口的范围、owner、兼容面与退出标准，避免后续任务发生口径漂移。
- Status: pending
- Depends_on: `[]`
- Blocks: `["AT-RCL-02","AT-RCL-04","AT-RCL-05","AT-RCL-06","AT-RCL-08","AT-RCL-10"]`
- Input:
  - [01_repo-logic-gap-assessment-2026-04-06.md](./01_repo-logic-gap-assessment-2026-04-06.md)
  - [02_repo-closure-plan-aligned-with-latest-direction-2026-04-06.md](./02_repo-closure-plan-aligned-with-latest-direction-2026-04-06.md)
- Output:
  - closure owner map
  - compatibility inventory
  - topic exit criteria
  - touched-module execution sheet
- Likely files:
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-04-06-repo-logic-gap-assessment/02_repo-closure-plan-aligned-with-latest-direction-2026-04-06.md`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-04-06-repo-logic-gap-assessment/03_atomic-tasklist-repo-closure-plan-2026-04-06.md`
- Acceptance:
  - 每个收口对象都有 owner、compat status、最低验收项和回退路径。
- Minimum validation:
  - `rg -n "workflow graph|agent runtime|project_key|LLM|source-library|frontend|required checks|compat" development/latest-dev-docs/development-plans/CURRENT_DEV/2026-04-06-repo-logic-gap-assessment -S`

## Task AT-RCL-02: Land Durable Workflow Graph Runtime Contract

- Goal: 将 workflow graph 从单进程 `_compiled` 句柄收口到 durable compiled artifact store / registry 驱动的 runtime，并与现有 run store / handoff store 持久化边界对齐。
- Status: pending
- Depends_on: `["AT-RCL-01"]`
- Blocks: `["AT-RCL-03","AT-RCL-11"]`
- Input:
  - `main/backend/app/services/workflow_graph/__init__.py`
  - `main/backend/app/services/workflow_graph/compiler.py`
  - `main/backend/app/services/workflow_graph/runtime.py`
  - `main/backend/app/services/workflow_graph/store.py`
  - `main/backend/app/services/workflow_graph/handoff_store.py`
  - `main/backend/app/api/workflow_graph.py`
- Output:
  - durable compiled artifact contract
  - explicit graph id / version / resume semantics
  - runtime handoff storage alignment note
- Likely files:
  - `main/backend/app/services/workflow_graph/__init__.py`
  - `main/backend/app/services/workflow_graph/store.py`
  - `main/backend/app/services/workflow_graph/runtime.py`
  - `main/backend/app/api/workflow_graph.py`
- Acceptance:
  - compile -> persist -> reload -> run 不再依赖同一进程内存态。
  - graph id 语义不再等同于 session-local temporary handle。
  - 不重复实现已有 run-event / handoff persistence，而是与其 contract 对齐。
  - 在默认执行链切换前，现有 compile/run API 仍保持可用。
- Safety mode:
  - `additive-only`
- Do not do first:
  - 不先删除 `_compiled` registry。
  - 不先改 `run()` 的请求/响应外形。
- Minimum validation:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit/test_workflow_graph_compiler_unittest.py tests/unit/test_workflow_graph_runtime_unittest.py tests/unit/test_workflow_graph_handoff_store_unittest.py`
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/integration/test_workflow_graph_api_unittest.py`

## Task AT-RCL-03: Add Workflow Graph Integrity and Replay Closure Checks

- Goal: 在 workflow graph durable runtime 之上补完整性校验、回放一致性和 closure boundary 门禁。
- Status: pending
- Depends_on: `["AT-RCL-02"]`
- Blocks: `["AT-RCL-11"]`
- Input:
  - `main/backend/app/services/workflow_graph/contracts.py`
  - `main/backend/app/services/workflow_graph/schema.py`
  - `main/backend/app/services/workflow_graph/edit_contract.py`
  - `main/backend/app/services/workflow_graph/observability.py`
- Output:
  - graph integrity checks
  - replay consistency checks
  - failure diagnostics for invalid closure state
- Likely files:
  - `main/backend/app/services/workflow_graph/contracts.py`
  - `main/backend/app/services/workflow_graph/schema.py`
  - `main/backend/app/services/workflow_graph/edit_contract.py`
  - `main/backend/tests/unit/test_workflow_graph_edit_contract_unittest.py`
- Acceptance:
  - orphan/cycle/reference drift/replay inconsistency 有明确失败信号，而不是静默容忍。
- Minimum validation:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit/test_workflow_graph_edit_contract_unittest.py tests/unit/test_workflow_graph_curated_service_unittest.py`

## Task AT-RCL-04: Converge Agent Runtime to Session/Task/Event Canonical Path

- Goal: 把 agent runtime 主执行链收敛到 session/task/event 核心，旧 `agent_batch` 等入口降为 adapter。
- Status: pending
- Depends_on: `["AT-RCL-01"]`
- Blocks: `["AT-RCL-11"]`
- Input:
  - `main/backend/app/services/agent_runtime/coordinator.py`
  - `main/backend/app/services/agent_runtime/task_bus.py`
  - `main/backend/app/services/agent_runtime/watchers.py`
  - `main/backend/app/services/agent_runtime/memory.py`
  - `main/backend/app/services/agent_batch/*`
  - `main/backend/app/api/agent_batch.py`
  - [01_claude-agent-high-fidelity-migration-mapping-2026-04-02.md](../2026-04-02-claude-agent-high-fidelity-migration/01_claude-agent-high-fidelity-migration-mapping-2026-04-02.md)
- Output:
  - canonical runtime path note
  - compat adapter map for old entrypoints
  - session migration / resume contract
- Likely files:
  - `main/backend/app/services/agent_runtime/coordinator.py`
  - `main/backend/app/services/agent_runtime/task_bus.py`
  - `main/backend/app/services/agent_batch/task_contract.py`
  - `main/backend/app/services/agent_batch/approval_binding.py`
  - `main/backend/app/api/agent_batch.py`
- Acceptance:
  - “真实入口”与“compat 入口”边界明确，且 session lifecycle 可以被画成单一主链。
- Safety mode:
  - `freeze-only -> additive-only -> switchable`
- Do not do first:
  - 不先把 `agent_batch`、`workflow_graph`、`skill_runtime` 当成可直接下线的旧入口。
  - 不先改变现有 task manifest / retry / approval contract 默认语义。
- Minimum validation:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit/test_agent_batch_api_unittest.py tests/unit/test_agent_batch_loop_unittest.py tests/unit/test_agent_batch_approval_binding_unittest.py tests/integration/test_agent_batch_workflow_closure_unittest.py`

## Task AT-RCL-05: Harden Project Key to Environment-Ready Hard Gate

- Goal: 把 `project_key` 从默认软约束收敛为目标环境可启用的硬门禁。
- Status: pending
- Depends_on: `["AT-RCL-01"]`
- Blocks: `["AT-RCL-11"]`
- Input:
  - `main/backend/app/settings/config.py`
  - `main/backend/app/main.py`
  - `main/backend/app/web_ui_routes.py`
  - `main/backend/tests/integration/test_project_key_policy_unittest.py`
- Output:
  - hardened enforcement policy
  - fallback telemetry rules
  - rollout note for dev vs non-dev environments
- Likely files:
  - `main/backend/app/settings/config.py`
  - `main/backend/app/main.py`
  - `main/backend/tests/integration/test_project_key_policy_unittest.py`
- Acceptance:
  - 非开发环境可切 `require`，并保持明确失败行为与告警头/日志。
- Safety mode:
  - `additive-only -> switchable`
- Do not do first:
  - 不先把当前默认配置直接改成全环境 `require`。
  - 不先删除 fallback telemetry 和 warning header。
- Minimum validation:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/integration/test_project_key_policy_unittest.py`
  - `cd main/backend && .venv311/bin/python -m pytest -m "integration and not external" tests/integration/test_project_schema_guard_unittest.py -q`

## Task AT-RCL-06: Split Real LLM Capability From Template/Rule Fallback

- Goal: 收紧 LLM 相关能力语义，避免“命名像成品、实现仍是 fallback”。
- Status: pending
- Depends_on: `["AT-RCL-01"]`
- Blocks: `["AT-RCL-11"]`
- Input:
  - `main/backend/app/services/llm_report_generator.py`
  - `main/backend/app/services/llm_report_source_enrichment.py`
  - `main/backend/app/services/writing/llm_action_service.py`
  - `main/backend/app/api/llm_report.py`
  - `main/backend/app/api/writing.py`
- Output:
  - capability naming split
  - response metadata for real vs fallback path
  - updated docs / API wording
- Likely files:
  - `main/backend/app/services/llm_report_generator.py`
  - `main/backend/app/services/writing/llm_action_service.py`
  - `main/backend/app/api/llm_report.py`
  - `main/backend/app/api/writing.py`
- Acceptance:
  - 上层调用方和文档能明确区分真实模型路径与模板/规则路径。
- Minimum validation:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit/test_llm_report_generator_unittest.py tests/unit/test_llm_report_api_unittest.py tests/unit/test_writing_llm_action_service_unittest.py`
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/integration/test_llm_report_api_unittest.py tests/integration/test_writing_llm_actions_api_unittest.py`

## Task AT-RCL-07: Separate Source-Library Authority Output From Compat Projection

- Goal: 保留 source-library compat 输出，但明确 authority output、compat projection 和优先级。
- Status: pending
- Depends_on: `["AT-RCL-02","AT-RCL-03","AT-RCL-06"]`
- Blocks: `["AT-RCL-11"]`
- Input:
  - `main/backend/app/services/collect_runtime/adapters/source_library.py`
  - `main/backend/app/services/source_library/terminal_output.py`
  - `main/backend/app/services/source_library/resolver.py`
  - `main/backend/app/services/ingest/frontdoor_ingress.py`
  - `main/backend/app/services/ingest/postprocess_frontdoor.py`
- Output:
  - authority output contract
  - compat projection note
  - deprecation conditions for retained legacy fields
- Likely files:
  - `main/backend/app/services/collect_runtime/adapters/source_library.py`
  - `main/backend/app/services/source_library/terminal_output.py`
  - `main/backend/app/services/source_library/resolver.py`
  - `main/backend/tests/core_business/test_source_library_core_contract.py`
- Acceptance:
  - 调用方不再把 `legacy_result` 和权威输出混为一谈。
  - compat 字段保留状态和下线条件可追溯。
- Safety mode:
  - `freeze-only -> additive-only -> switchable`
- Do not do first:
  - 不先移除 `legacy_result`、`terminal_output`、`frontdoor_ingress`、`postprocess_frontdoor`。
  - 不先改 `to_source_library_response(...)` 的默认返回字段集合。
- Minimum validation:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit/test_source_library_terminal_output_unittest.py tests/unit/test_collect_runtime_source_library_adapter_unittest.py tests/unit/test_postprocess_frontdoor_unittest.py`
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/core_business/test_source_library_core_contract.py tests/integration/test_t22_source_library_scrapy_collect_runtime_integration_unittest.py`

## Task AT-RCL-08: Unify Frontend Render Ownership and Shell Facts

- Goal: 将 frontend 的 render ownership、route dispatch、surface、shell 关系收敛为单一事实源，同时保持模块 metadata 继续从 manifest 派生。
- Status: pending
- Depends_on: `["AT-RCL-01"]`
- Blocks: `["AT-RCL-09","AT-RCL-11"]`
- Input:
  - `main/frontend-modern/src/app/kernel/moduleManifest.ts`
  - `main/frontend-modern/src/app/platform/modules/registry.ts`
  - `main/frontend-modern/src/app/kernel/contracts.ts`
  - `main/frontend-modern/src/app/kernel/routes.ts`
  - `main/frontend-modern/src/app/kernel/ModuleRenderer.tsx`
  - `main/frontend-modern/src/app/shell/AppShell.tsx`
- Output:
  - render/shell single source of truth
  - route/module mapping closure note
  - parity checklist for module metadata -> route -> render -> shell -> nav
- Likely files:
  - `main/frontend-modern/src/app/kernel/moduleManifest.ts`
  - `main/frontend-modern/src/app/platform/modules/registry.ts`
  - `main/frontend-modern/src/app/kernel/contracts.ts`
  - `main/frontend-modern/src/app/kernel/routes.ts`
  - `main/frontend-modern/src/app/kernel/ModuleRenderer.tsx`
  - `main/frontend-modern/src/app/shell/AppShell.tsx`
- Acceptance:
  - 页面渲染与 shell dispatch 只剩一份权威来源。
  - `moduleManifest` 继续作为模块 metadata 的权威来源。
  - `AppShell` 与 `ModuleRenderer` 不再分别维护双份事实。
- Safety mode:
  - `freeze-only -> additive-only`
- Do not do first:
  - 不先删 `AppShell` 内的旧分发。
  - 不先把 metadata registry 的收敛误当成 render ownership 已经收敛。
  - 不先假定 `moduleManifest` 已经天然覆盖全部 nav / route / shell 事实。
- Minimum validation:
  - `cd main/frontend-modern && npm run lint`
  - `cd main/frontend-modern && npm run build`
  - `cd main/frontend-modern && npm run test:e2e -- tests/e2e/homepage.spec.ts`

## Task AT-RCL-09: Close Legacy Hash Adapter Boundary and B-Layer Shell Coverage

- Goal: 将 legacy hash 兼容下沉到显式 adapter，并补齐 B 层 shell 与导航可见性。
- Status: pending
- Depends_on: `["AT-RCL-08"]`
- Blocks: `["AT-RCL-11"]`
- Input:
  - `main/frontend-modern/src/app/kernel/legacyHashAdapter.ts`
  - `main/frontend-modern/src/app/navigation/index.ts`
  - `main/frontend-modern/src/app/kernel/FrontendKernelApp.tsx`
  - `main/frontend-modern/src/app/kernel/VisualizationLayerShell.tsx`
  - `main/frontend-modern/src/components/FigmaSideNav.tsx`
  - `main/backend/app/web_ui_routes.py`
- Output:
  - supported legacy hash matrix
  - canonical modern hash output rules
  - B-layer shell / nav parity closure note
- Likely files:
  - `main/frontend-modern/src/app/kernel/legacyHashAdapter.ts`
  - `main/frontend-modern/src/app/navigation/index.ts`
  - `main/frontend-modern/src/app/kernel/FrontendKernelApp.tsx`
  - `main/frontend-modern/src/app/kernel/VisualizationLayerShell.tsx`
  - `main/frontend-modern/src/components/FigmaSideNav.tsx`
  - `main/backend/app/web_ui_routes.py`
- Acceptance:
  - legacy hash 只在 adapter 层承载兼容语义。
  - 所有 `LayerId='B'` 模块具备 route / shell / nav 一致性。
- Safety mode:
  - `freeze-only -> additive-only -> switchable`
- Do not do first:
  - 不先修改 legacy hash 的默认解析规则。
  - 不先改 backend `/graph.html`、`/dashboard.html`、`/topic-dashboard.html` 等跳转目标。
  - 不先把 unknown route fallback 从 `FrontendKernelApp` 中移除。
- Minimum validation:
  - `cd main/frontend-modern && npm run lint`
  - `cd main/frontend-modern && npm run test:e2e -- tests/e2e/graphpage.spec.ts`
  - `cd main/frontend-modern && npm run test:ingest-smoke`

## Task AT-RCL-10: Turn Required Checks, PR Evidence, and Docs Navigation Into Default Gates

- Goal: 把治理要求从“文档建议”收紧为默认门禁和默认留痕。
- Status: pending
- Depends_on: `["AT-RCL-01"]`
- Blocks: `["AT-RCL-11"]`
- Input:
  - `.github/branch-protection-required-checks.json`
  - `.github/workflows/backend-tests.yml`
  - `.github/PULL_REQUEST_TEMPLATE.md`
  - `main/backend/tests/README.md`
  - `development/latest-dev-docs/README.md`
  - `development/latest-dev-docs/MERGED_OVERVIEW.md`
- Output:
  - required check matrix alignment note
  - PR evidence expectations
  - docs navigation maintenance checklist
- Likely files:
  - `.github/branch-protection-required-checks.json`
  - `.github/workflows/backend-tests.yml`
  - `.github/PULL_REQUEST_TEMPLATE.md`
  - `main/backend/tests/README.md`
  - `development/latest-dev-docs/README.md`
  - `development/latest-dev-docs/MERGED_OVERVIEW.md`
- Acceptance:
  - required checks 与实际 workflow 不冲突。
  - PR evidence 至少包含 scope / risk / test evidence / rollback。
  - 文档新增与 closure note 默认同步索引。
- Minimum validation:
  - `python main/backend/scripts/check_api_layer_imports.py`
  - `./scripts/test-standardize.sh unit`
  - `./scripts/test-standardize.sh integration`
  - `./scripts/test-standardize.sh contract`

## Task AT-RCL-11: Run Final Regression Pack and Documentation Closure

- Goal: 以一组最小但真实的回归包结束本轮收口，并同步文档与状态。
- Status: pending
- Depends_on: `["AT-RCL-02","AT-RCL-03","AT-RCL-04","AT-RCL-05","AT-RCL-06","AT-RCL-07","AT-RCL-08","AT-RCL-09","AT-RCL-10"]`
- Blocks: `[]`
- Input:
  - all outputs from `AT-RCL-01 ~ AT-RCL-10`
- Output:
  - final closure report
  - updated status snapshot
  - updated indexes and merged overview
  - exit recommendation: remain in `CURRENT_DEV` or archive
- Likely files:
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-04-06-repo-logic-gap-assessment/03_atomic-tasklist-repo-closure-plan-2026-04-06.md`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-04-06-repo-logic-gap-assessment/04_validation-closure-repo-closure-plan-2026-04-06.md`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
  - `development/latest-dev-docs/development-plans/INDEX.md`
  - `development/latest-dev-docs/README.md`
  - `development/latest-dev-docs/MERGED_OVERVIEW.md`
- Acceptance:
  - 至少一轮真实 regression pack 跑通并留痕。
  - 文档、验证、回退、compat status 四条线都闭环。
  - 是否归档的判断基于证据，不基于主观完成感。
- Minimum validation:
  - `./scripts/test-standardize.sh ci-pr`
  - `cd main/frontend-modern && npm run lint && npm run build && npm run test:e2e -- tests/e2e/homepage.spec.ts`
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/integration/test_workflow_graph_api_unittest.py tests/integration/test_project_key_policy_unittest.py tests/integration/test_llm_report_api_unittest.py tests/integration/test_writing_llm_actions_api_unittest.py tests/core_business/test_source_library_core_contract.py`

## Minimum Regression Pack Summary

- Backend runtime:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit/test_workflow_graph_compiler_unittest.py tests/unit/test_workflow_graph_runtime_unittest.py tests/unit/test_workflow_graph_handoff_store_unittest.py`
- Backend policy / capability:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/integration/test_project_key_policy_unittest.py tests/integration/test_llm_report_api_unittest.py tests/integration/test_writing_llm_actions_api_unittest.py`
- Source-library / ingest:
  - `cd main/backend && .venv311/bin/python -m pytest -q tests/unit/test_collect_runtime_source_library_adapter_unittest.py tests/unit/test_source_library_terminal_output_unittest.py tests/core_business/test_source_library_core_contract.py`
- Frontend:
  - `cd main/frontend-modern && npm run lint`
  - `cd main/frontend-modern && npm run build`
  - `cd main/frontend-modern && npm run test:e2e -- tests/e2e/homepage.spec.ts`
  - `cd main/frontend-modern && npm run test:e2e -- tests/e2e/graphpage.spec.ts`

## Residual Risk Notes

- `workflow graph` durable store 若没有版本和 replay contract，容易把“可恢复”做成“可写但不可验证”。
- agent runtime 若只补 adapter、不明确 canonical path，会继续保留“双入口都像主入口”的问题。
- `project_key` 强化若没有 rollout 区分，可能误伤本地和历史调用链。
- source-library 若只加字段、不标权威优先级，会继续维持多合同歧义。
- frontend 若只改 route，或只整理 registry metadata，而不收 render / shell / nav 三处事实源，双中心问题不会真正消失。
- required checks 和 PR evidence 若不转成默认执行，收口计划仍会停留在文档层。
