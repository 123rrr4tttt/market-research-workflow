<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/09_runtime-smoke-reproduction-repo-closure-plan-2026-04-07.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/09_runtime-smoke-reproduction-repo-closure-plan-2026-04-07.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Runtime Smoke Reproduction: Repo Closure Plan (2026-04-07)

> 日期：2026-04-07
> 主题：repo-level live runtime smoke reproduction
> 范围：`AT-RCL-02 ~ AT-RCL-09` 的真实运行链路
> 结论：`./scripts/run_repo_runtime_smoke.sh` 已可重复执行，并在本地开发栈下实跑通过

## 1. Purpose

本文件用于把本轮“真实运行功能测试”从聊天结论沉淀为可复跑入口与证据记录。

这里关注的不是 unit/integration mock 绿，而是：

1. live backend API 是否可直接对外工作；
2. `agent-batch -> celery worker -> agent_sessions` 是否能形成真实闭环；
3. frontend 是否能通过真实 backend 加载首页与图谱页；
4. `project_key` require-mode 是否可被单独复现。

## 2. Runtime Entry

统一入口：

```bash
./scripts/run_repo_runtime_smoke.sh
```

脚本结构：

1. backend live API smoke：
   - [main/backend/scripts/repo_runtime_smoke.py](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/scripts/repo_runtime_smoke.py)
2. frontend live browser smoke：
   - [runtime-smoke.spec.ts](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/tests/e2e/runtime-smoke.spec.ts)
3. wrapper：
   - [run_repo_runtime_smoke.sh](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/scripts/run_repo_runtime_smoke.sh)

## 3. Preconditions

默认前提：

1. 本机主开发栈已启动，backend 主入口为 `http://127.0.0.1:8000`。
2. Redis / PostgreSQL / scrapyd / celery worker 已随本地开发环境就绪。
3. frontend 不要求预先启动；Playwright 会临时拉起 `4173` 端口的 Vite dev server，并把 `/api/*` 代理到当前 backend。
4. require-mode backend 由 wrapper 临时起在 `18001`，用于验证 `PROJECT_KEY_REQUIRE_IN_NON_DEV=true`。

推荐启动方式：

```bash
cd main/backend && ./start-local.sh
```

## 4. Coverage Matrix

| 主题 | live smoke coverage |
|---|---|
| `AT-RCL-02` / `AT-RCL-03` | `workflow_graph` compile -> run -> status -> events -> compiled |
| `AT-RCL-04` | `agent-batch/jobs` submit -> poll -> items -> events -> `agent_sessions/{id}` |
| `AT-RCL-05` | normal-mode header telemetry + require-mode `PROJECT_KEY_REQUIRED` gate |
| `AT-RCL-06` | `POST /api/v1/llm-report/generate` + `POST /api/v1/writing/llm-actions` capability-truth |
| `AT-RCL-07` | `source-library/sync` + `source-library/run` + `graph/structured-search` |
| `AT-RCL-08` / `AT-RCL-09` | homepage runtime load + graph page live backend load + backend legacy redirects |

## 5. Executed Result

执行命令：

```bash
./scripts/run_repo_runtime_smoke.sh
```

本轮实际结果：

1. backend live API smoke 通过：
   - `/health`
   - `/health/deep`
   - `/projects`
   - `workflow_graph`
   - `llm-report`
   - `writing`
   - `ingest/market`
   - `source-library/sync`
   - `graph/structured-search`
   - `source-library/run`
   - `agent-batch/jobs`
   - `agent-sessions/{session_id}`
2. legacy redirect smoke 通过：
   - `/` -> `http://127.0.0.1:5173/`
   - `/app` -> `http://127.0.0.1:5173/`
   - `/graph.html?type=market` -> `http://127.0.0.1:5173/#graph.html%3Ftype%3Dmarket`
3. require-mode smoke 通过：
   - `GET /api/v1/health`
   - `POST /api/v1/ingest/source-library/run` missing project_key -> `400 / PROJECT_KEY_REQUIRED`
4. frontend browser smoke 通过：
   - `homepage runtime smoke uses live backend`
   - `graph runtime smoke loads against live graph endpoints`
   - Playwright 结果：`2 passed`

## 6. Interpretation

这轮 runtime smoke 说明 repo-closure 主题当前不只是“测试替身层面成立”，而是最关键的 live 入口已经具备可重复复验性：

1. `agent-batch` 真实经过 worker 消费并收敛回 session ledger。
2. frontend graph 页面不再只靠 mock graph API 才能证明可用。
3. `project_key` 的 dev/warn 与 non-dev/require 两条策略都能在本地复现。

## 7. Residual Boundary

本 smoke pack 不替代以下门禁：

1. `npm run lint`
2. `check_api_layer_imports.py`
3. `./scripts/test-standardize.sh ci-pr`

这些仍属于治理门禁，不属于 live runtime smoke 的职责。
