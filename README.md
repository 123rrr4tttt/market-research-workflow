# 市场研究工作流

> 最后更新：`2026-04-07`
> 当前状态：持续开发中，默认按 Docker 链路运行

这是一个面向市场研究 / 情报采集 / 结构化分析的全栈工作流仓库。仓库核心目标不是只提供一个 API 服务，而是把采集、抽取、索引、检索、项目隔离、异步任务、运维入口和现代化操作前端放在一套统一工程里。

这个仓库也不只是“应用代码”。其中同时包含开发计划、归档文档、参考资料、验证脚本和运行时来源配置。第一次进入仓库时，建议先看本文档的启动入口、目录地图和文档索引，而不是直接在大目录里盲搜。

## 项目定位

- 后端：`FastAPI + SQLAlchemy + Alembic + Celery + Redis`
- 存储与检索：`PostgreSQL + pgvector + Elasticsearch`
- 前端：`main/frontend-modern`，当前唯一活跃前端
- 运行方式：Docker-first，本地模式用于开发调试
- 作用范围：多来源采集、结构化处理、资源池/来源库管理、检索与分析、任务编排与运维

## 当前能力概览

### 已落地的核心模块

- `ingest`：市场、政策、报告、社交、数据 API 等采集链路
- `discovery` / `search`：发现、检索、索引访问
- `resource_pool`：资源池与候选入口管理
- `source_library`：来源库条目、解析、执行与项目定制
- `collect_runtime` / `indexer`：采集运行时与索引写入
- `graph` / `workflow_graph` / `writing` / `agent_runtime` / `typed_knowledge`：图谱、工作流、写作与 agent 相关服务能力

### 技术栈

- 后端：`Python 3.11+`, `FastAPI`, `SQLAlchemy`, `Alembic`, `Celery`
- 前端：`React 19`, `Vite`, `TypeScript`, `React Query`, `Storybook`
- 测试：`pytest`, Playwright
- 工程门禁：GitHub Actions + 仓库内自定义 verification / smoke 脚本

## 运行拓扑

默认容器编排定义在 [`main/ops/docker-compose.yml`](./main/ops/docker-compose.yml)：

- `db`：PostgreSQL，端口 `5432`
- `es`：Elasticsearch，端口 `9200`
- `redis`：Redis，端口 `6379`
- `backend`：FastAPI，端口 `8000`
- `celery-worker`：异步任务 worker
- `frontend-modern`：可选 profile，端口 `5174`
- `scrapyd`：可选 profile，端口 `6800`

## 快速开始

### 推荐方式：Docker

1. 准备环境文件：

```bash
cp main/backend/.env.example main/backend/.env
```

2. 先做部署前检查：

```bash
./scripts/docker-deploy.sh preflight
./scripts/docker-deploy.sh preflight --profile scrapyd
```

3. 启动服务：

```bash
./scripts/docker-deploy.sh start
```

4. 常用操作：

```bash
./scripts/docker-deploy.sh status
./scripts/docker-deploy.sh logs
./scripts/docker-deploy.sh health
./scripts/docker-deploy.sh stop
```

### 常用访问地址

- OpenAPI: [http://localhost:8000/docs](http://localhost:8000/docs)
- 健康检查: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
- 深度健康检查: [http://localhost:8000/api/v1/health/deep](http://localhost:8000/api/v1/health/deep)
- modern 前端（启用对应 profile 时）: [http://localhost:5174](http://localhost:5174)

## 本地开发

当你需要快速迭代后端和前端，而不想整套容器都拉起时，使用本地模式。

### 一键本地启动

```bash
cp main/backend/.env.example main/backend/.env
./scripts/local-deploy.sh start
```

这个入口会转发到 [`main/backend/start-local.sh`](./main/backend/start-local.sh)，通常会启动：

- 本地 backend：`8000`
- modern 前端 dev server：`5173`
- 本地 Celery worker
- 本地 PostgreSQL / Redis（按脚本检测与配置决定）
- 本地 Elasticsearch 或 Docker 托管依赖（取决于参数与环境）

### 本地常用命令

```bash
./scripts/local-deploy.sh status
./scripts/local-deploy.sh health
./scripts/local-deploy.sh stop
```

### 平台封装脚本

- [`scripts/platform-macos.sh`](./scripts/platform-macos.sh)
- [`scripts/platform-linux.sh`](./scripts/platform-linux.sh)
- [`scripts/platform-windows.ps1`](./scripts/platform-windows.ps1)

### 前端单独开发

```bash
cd main/frontend-modern
npm install
VITE_API_PROXY_TARGET=http://localhost:8000 npm run dev
```

`main/frontend-modern` 常用脚本见 [`main/frontend-modern/package.json`](./main/frontend-modern/package.json)：

- `npm run dev`
- `npm run build`
- `npm run lint`
- `npm run storybook`
- `npm run test:e2e`

## 仓库地图

```text
.
├── main/
│   ├── backend/            # FastAPI 应用、服务层、迁移、测试、后端脚本
│   ├── frontend-modern/    # 当前活跃的 React + Vite 前端
│   ├── ops/                # Docker 编排、启停脚本、运维说明
│   └── QUICKSTART.md       # 较短的快速启动说明
├── scripts/                # 仓库级部署、验证、冒烟、自检脚本
├── development/            # 开发文档与合并索引
├── docs/                   # 运维、安全、契约、实现类文档
├── plans/                  # 规划与执行计划
├── 信息源库/               # 来源库运行时配置
├── 信息流优化/             # 工作流优化方向与规划
├── reference-pool/         # 参考资料与 OSS 参考代码
└── tmp/                    # 临时导入或研究材料
```

### 后端重点目录

[`main/backend/app/services`](./main/backend/app/services) 下目前可以优先关注这些域：

- `ingest`
- `discovery`
- `search`
- `resource_pool`
- `source_library`
- `collect_runtime`
- `indexer`
- `graph`
- `workflow_graph`
- `writing`
- `agent_runtime`
- `typed_knowledge`

### 测试分层

后端测试位于 [`main/backend/tests`](./main/backend/tests)：

- `unit`
- `integration`
- `contract`
- `e2e`
- `core_business`

## 测试与质量门禁

### 本地测试入口

后端常用执行方式：

```bash
cp main/backend/.env.example main/backend/.env
cd main/backend
pytest -m "unit and not external and not flaky" -q
pytest -m "integration and not external and not flaky" -q
pytest -m "contract and not external and not flaky" -q
```

统一脚本入口：

```bash
./scripts/test-standardize.sh unit
./scripts/test-standardize.sh integration
./scripts/test-standardize.sh contract
./scripts/test-standardize.sh coverage
./scripts/test-standardize.sh ci-pr
```

其他常用检查：

- [`scripts/run_repo_runtime_smoke.sh`](./scripts/run_repo_runtime_smoke.sh)
- [`scripts/local-smoke-all-stages.sh`](./scripts/local-smoke-all-stages.sh)
- [`scripts/verify/`](./scripts/verify)

### 仓库内现有 GitHub Actions

- [`backend-tests.yml`](./.github/workflows/backend-tests.yml)
- [`r3-must-gates.yml`](./.github/workflows/r3-must-gates.yml)
- [`r84-f-required-check.yml`](./.github/workflows/r84-f-required-check.yml)
- [`r9-ef-required-check.yml`](./.github/workflows/r9-ef-required-check.yml)

这些工作流覆盖了后端分层测试、依赖与安全门禁、必过校验切片，以及特定报告链路的质量检查。

## 文档入口

如果你要理解当前实现状态、开发背景或历史计划，不要从零散文件开始，优先走下面这些入口：

- 开发文档第一入口：[`development/latest-dev-docs/README.md`](./development/latest-dev-docs/README.md)
- 开发文档总览：[`development/latest-dev-docs/MERGED_OVERVIEW.md`](./development/latest-dev-docs/MERGED_OVERVIEW.md)
- 开发计划索引：[`development/latest-dev-docs/development-plans/INDEX.md`](./development/latest-dev-docs/development-plans/INDEX.md)
- 后端文档索引：[`main/backend/docs/README.md`](./main/backend/docs/README.md)
- 后端本地开发说明：[`main/backend/README.local.md`](./main/backend/README.local.md)
- 运维说明：[`main/ops/README.md`](./main/ops/README.md)
- modern 前端说明：[`main/frontend-modern/README.md`](./main/frontend-modern/README.md)

## 使用前需要知道的事实

- Docker 是团队协作和可复现运行的默认路径。
- `main/frontend-modern` 是当前唯一活跃前端，旧模板前端不是主开发目标。
- 仓库里包含大量规划、归档、参考资料目录，其中不少不是运行时路径。
- 部分采集 / 搜索 / LLM 能力依赖 `main/backend/.env` 中的外部 API Key。

## 协作约定

- Git / 分支规范见 [`GIT_WORKFLOW.md`](./GIT_WORKFLOW.md)
- 开发说明类文档应统一纳入 [`development/latest-dev-docs/`](./development/latest-dev-docs) 索引体系
