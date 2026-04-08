# Validation Closure: Repo Closure Plan (2026-04-07)

> 日期：2026-04-07
> 主题：`AT-RCL-11`
> 范围：repo-level closure validation for `AT-RCL-02 ~ AT-RCL-10`
> 结论：validation pack green; after same-day `AT-RCL-04` runtime convergence closure, the repo-closure topic is archive-ready

## 1. Purpose

本文件用于给 2026-04-06 仓库级收口计划留下一轮真实回归证据，并据此给出是否归档的判断。

本轮 closure 的目标不是把所有 topic 都口头宣布“做完”，而是回答三件事：

1. 当前 additive/switchable 收口实现是否仍能通过最小真实回归包。
2. 哪些 topic 已经有足够证据支撑“实现已落地并可标记 completed”。
3. 当前主题是否可以从 `CURRENT_DEV` 归档。

## 2. Executed Regression Pack

### 2.1 Backend broad regression lane

```bash
./scripts/test-standardize.sh ci-pr
```

结果：

1. `554 passed`
2. `4 skipped`
3. `133 deselected`

解释：

1. 这条 lane 覆盖了 repo closure 当前最关键的 unit / integration / core business 组合。
2. `test_info_ingest_script_unittest.py`、`test_api_group_a_core_contract.py`、`test_crawler_management_core_contract.py` 的稳定性修正已经纳入这轮绿色结果。

### 2.2 Backend targeted closure pack

```bash
cd main/backend && .venv311/bin/python -m pytest -q \
  tests/integration/test_workflow_graph_api_unittest.py \
  tests/integration/test_project_key_policy_unittest.py \
  tests/integration/test_llm_report_api_unittest.py \
  tests/integration/test_writing_llm_actions_api_unittest.py \
  tests/core_business/test_source_library_core_contract.py
```

结果：

1. `55 passed`

覆盖主题：

1. `AT-RCL-02` / `AT-RCL-03`: workflow graph durability and integrity path
2. `AT-RCL-05`: project-key enforcement and fallback telemetry
3. `AT-RCL-06`: llm capability-truth contract
4. `AT-RCL-07`: source-library authority / compat contract

### 2.3 Frontend closure pack

```bash
cd main/frontend-modern && npm run lint
cd main/frontend-modern && npm run build
cd main/frontend-modern && npm run test:e2e -- tests/e2e/homepage.spec.ts
```

结果：

1. `npm run lint` 通过，保留仓库存量 `19 warnings`，无新增 error
2. `npm run build` 通过
3. `homepage.spec.ts` -> `2 passed`

覆盖主题：

1. `AT-RCL-08`: render ownership closure remains buildable and reachable
2. `AT-RCL-09`: shell / route / hash compatibility closure still preserves homepage entry

### 2.4 Agent runtime convergence pack

```bash
cd main/backend && .venv311/bin/python -m pytest -q \
  tests/unit/test_agent_batch_api_unittest.py \
  tests/unit/test_agent_sessions_service_unittest.py
cd main/backend && .venv311/bin/python -m pytest -q \
  tests/integration/test_agent_batch_workflow_closure_unittest.py \
  tests/integration/test_agent_sessions_api_unittest.py
```

结果：

1. `44 passed`
2. `5 passed`

覆盖主题：

1. `AT-RCL-04`: direct `/agent-batch/jobs` submit path now projects into the session/task/event ledger

### 2.5 Live runtime smoke pack

```bash
./scripts/run_repo_runtime_smoke.sh
```

结果：

1. backend live API smoke 通过
2. legacy redirect smoke 通过
3. require-mode `project_key` smoke 通过
4. frontend live browser smoke 通过
5. Playwright runtime pack -> `2 passed`

补充入口：

1. backend script: [main/backend/scripts/repo_runtime_smoke.py](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/scripts/repo_runtime_smoke.py)
2. wrapper: [scripts/run_repo_runtime_smoke.sh](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/scripts/run_repo_runtime_smoke.sh)
3. frontend runtime spec: [runtime-smoke.spec.ts](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/tests/e2e/runtime-smoke.spec.ts)

覆盖主题：

1. `AT-RCL-02` / `AT-RCL-03`: workflow graph live compile-run chain
2. `AT-RCL-04`: agent-batch worker consumption and session-ledger projection
3. `AT-RCL-05`: dev/warn and non-dev/require project-key behavior
4. `AT-RCL-06`: llm-report and writing capability-truth live response
5. `AT-RCL-07`: source-library sync/run and structured-search live path
6. `AT-RCL-08` / `AT-RCL-09`: homepage + graph page live backend rendering and legacy redirect compatibility

## 3. Closure Evidence Summary

| Topic | Evidence status | Current judgement |
|---|---|---|
| `AT-RCL-02` workflow graph durability | targeted backend pack green | additive implementation landed; needs final archive decision only after topic-wide closure |
| `AT-RCL-03` workflow graph integrity | targeted backend pack green | integrity signal path landed and regression-stable |
| `AT-RCL-04` agent runtime canonical path | agent runtime convergence pack green | direct job submit now has additive session-ledger projection and stable compat boundary |
| `AT-RCL-05` project hard gate | targeted backend pack green | policy switch remains controllable and validated |
| `AT-RCL-06` llm truthfulness | targeted backend pack green | capability-truth contract is regression-stable |
| `AT-RCL-07` source-library authority split | targeted backend pack green + ci-pr green | authority/compat split is stable under current callers |
| `AT-RCL-08` frontend single source | frontend lint/build/homepage green + live runtime smoke green | render ownership收口未破坏入口和真实 backend 渲染 |
| `AT-RCL-09` legacy hash boundary | frontend pack green + live redirect/runtime smoke green | compat boundary remains intact in both browser and redirect path |
| `AT-RCL-10` governance default gate | gate scripts + unit/integration/contract already green | governance baseline is evidence-backed |

## 4. Exit Recommendation

推荐：`archive-ready`

原因：

1. `AT-RCL-11` 作为“最终回归与 closure 留痕”已经完成。
2. topic-level closure matrix 已补齐，`AT-RCL-02 ~ AT-RCL-10` 都已有足够证据进入 `completed`。
3. `AT-RCL-04` 的 additive runtime convergence 已在同日落地并通过 targeted validation，不再构成继续留在 `CURRENT_DEV` 的理由。

## 5. Residual Risk

1. `workflow graph` durable compiled artifact 目前已经可验证，但是否要把 `_compiled` fallback 从 retained compat 继续下调，还需要单独的迁移决策。
2. `project_key` 虽然 non-dev require path 已验证，但生产/非开发环境最终默认值切换仍依赖明确 rollout 决策。
3. frontend 和 agent runtime 仍保留 retained compat surface；这符合当前策略，但后续动作应进入 archive / destructive-cleanup 决策，而不是继续把本主题视为未封口。

## 6. Closure Output

本轮 `AT-RCL-11` 实际输出：

1. 一轮 repo-level final regression pack 绿色结果
2. `AT-RCL-04` convergence evidence 已由 [08_agent-runtime-canonical-path-closure-2026-04-07.md](./08_agent-runtime-canonical-path-closure-2026-04-07.md) 补齐
3. live runtime smoke reproduction 已由 [09_runtime-smoke-reproduction-repo-closure-plan-2026-04-07.md](./09_runtime-smoke-reproduction-repo-closure-plan-2026-04-07.md) 补齐
4. 当前主题进入 archive-ready 状态的证据化建议
5. 顶层和分层索引同步到本 closure 文档
