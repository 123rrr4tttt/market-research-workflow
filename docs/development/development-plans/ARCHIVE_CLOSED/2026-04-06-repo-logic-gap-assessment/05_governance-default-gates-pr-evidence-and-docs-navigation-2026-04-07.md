<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/05_governance-default-gates-pr-evidence-and-docs-navigation-2026-04-07.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/05_governance-default-gates-pr-evidence-and-docs-navigation-2026-04-07.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Governance Default Gates, PR Evidence, and Docs Navigation (2026-04-07)

> 日期：2026-04-07
> 主题：`AT-RCL-10`
> 范围：`.github/*`、`main/backend/tests/README.md`、`development/latest-dev-docs/*`
> 状态：completed, governance baseline aligned to current workflow reality and verified by the local gate pack

## 1. Purpose

本文件用于把本轮仓库收口的治理要求，从“分散在文档和历史记忆中的建议”收成默认可执行基线。

本轮不追求一次性重写全部 CI，而是做三件更关键的事情：

1. 明确 branch protection 当前真实依赖哪些 required checks。
2. 明确 PR 默认必须留下哪些 scope / risk / evidence / rollback / docs 证据。
3. 明确 `development/latest-dev-docs` 在新增和收口时必须同步哪些索引入口。

## 2. Current Workflow Reality

### 2.1 Branch protection required checks

当前 `main` 的 required checks 以 [branch-protection-required-checks.json](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/.github/branch-protection-required-checks.json) 为准：

1. `backend-tests`
2. `r9_ef_required_check`

解释：

1. `backend-tests` 对应 [backend-tests.yml](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/.github/workflows/backend-tests.yml) 工作流套件。
2. `r9_ef_required_check` 对应 [r9-ef-required-check.yml](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/.github/workflows/r9-ef-required-check.yml) 中的独立 job。

### 2.2 backend-tests current lane split

`pull_request` 默认 deterministic blocking lane：

1. `standards-check`
2. `r81-a-min-verify-check`
3. `r81-b-min-verify-check`
4. `unit-check`
5. `llm-report-must-check`
6. `integration-check`
7. `schema-guard-check`
8. `coverage-check`
9. `security-check`
10. `docker-check`

`pull_request` observation lane：

1. `flaky-observe`

`push(main)` / `schedule` / `workflow_dispatch` 在上述基础上额外包含：

1. `contract-check`
2. `e2e-check`
3. `contracts-governance-observe`

## 3. Default PR Evidence

默认 PR 证据模板以 [PULL_REQUEST_TEMPLATE.md](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/.github/PULL_REQUEST_TEMPLATE.md) 为准。

必须保留的 section：

1. `Scope`
2. `Risk`
3. `Test Evidence`
4. `Rollback Strategy`
5. `Docs And Closure`

解释：

1. `Scope` 用于固定这次改动到底收哪一条 topic / task。
2. `Risk` 用于显式说明 failure mode 与 retained compat guard。
3. `Test Evidence` 用于绑定实际命令和结果，而不是口头说“已验证”。
4. `Rollback Strategy` 用于说明回退方法、窗口与 owner/module。
5. `Docs And Closure` 用于把文档更新与 closure 留痕变成默认动作，而不是可选动作。

## 4. Docs Navigation Maintenance Checklist

当 `CURRENT_DEV` 主题新增文档、验证文档或 closure note 时，默认至少同步下面这些路径：

1. [development/latest-dev-docs/README.md](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/development/latest-dev-docs/README.md)
2. [development/latest-dev-docs/MERGED_OVERVIEW.md](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/development/latest-dev-docs/MERGED_OVERVIEW.md)
3. [development/latest-dev-docs/development-plans/INDEX.md](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/development/latest-dev-docs/development-plans/INDEX.md)
4. [development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md)

维护规则：

1. 顶层 `README.md` 记录“最新补充”。
2. `MERGED_OVERVIEW.md` 记录“最近新增”。
3. `development-plans/INDEX.md` 维护主入口导航。
4. `CURRENT_DEV/INDEX.md` 维护当前未封口主题入口。

## 5. Minimum Local Validation For AT-RCL-10

本主题最小验证命令保持与任务单一致：

```bash
main/backend/.venv311/bin/python main/backend/scripts/check_api_layer_imports.py
./scripts/test-standardize.sh unit
./scripts/test-standardize.sh integration
./scripts/test-standardize.sh contract
```

### 5.1 Executed validation result

本轮已实际执行并通过：

1. `main/backend/.venv311/bin/python main/backend/scripts/check_api_layer_imports.py`
2. `./scripts/test-standardize.sh unit` -> `443 passed, 4 skipped, 244 deselected`
3. `./scripts/test-standardize.sh integration` -> `111 passed`
4. `./scripts/test-standardize.sh contract` -> `90 passed, 601 deselected`

为让这组命令在当前仓库真实可跑，本轮同时补了三处治理稳定性修正：

1. [信息采集测试.py](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/scripts/信息采集测试.py) 改成懒加载旧 ingest 依赖，避免 unit lane 在 import 阶段被历史模块删除打断。
2. [test_crawler_management_core_contract.py](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/tests/core_business/test_crawler_management_core_contract.py) 对齐当前 async payload，纳入 `workflow_run_id` / `trace_id` 缺省字段。
3. [test_api_group_a_core_contract.py](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/tests/core_business/test_api_group_a_core_contract.py) 改为对象级 patch，消除 alias-level patch 在整包 contract lane 中的漂移；同时 [API_LAYER_HTTP_EXCEPTION_DETAIL_ALLOWLIST.txt](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/docs/API_LAYER_HTTP_EXCEPTION_DETAIL_ALLOWLIST.txt) 已刷新到当前 baseline。

## 6. Closure Interpretation

`AT-RCL-10` 在当前阶段的 closure 判断标准不是“所有治理要求都彻底自动化”，而是：

1. required check matrix 与实际 workflow 不再冲突。
2. PR 默认模板已经显式要求 scope / risk / test / rollback / docs 证据。
3. docs navigation 的默认同步入口已经写清并进入顶层索引。
4. 最小本地验证包可以真实执行。
