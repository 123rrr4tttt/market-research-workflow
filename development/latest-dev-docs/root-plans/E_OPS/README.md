# 市场情报（market-intel）项目说明

> 最后更新：2026-03-01  
> 当前版本：`v0.9-rc2.0`（预发布，团队联调）
> 合并校对清单：见 `MERGED_PLAN_REVIEW.md`（含保留/合并/疑似过时与链接校验结论）

本仓库实现一体化信息工作流：多来源采集 -> 结构化处理 -> 索引检索 -> 可视化与运维管理。  
适用于政策、市场、新闻、社媒等主题的数据采集与分析。

## 文档分层

- `root-plans` 四层结构说明：见 [DIR_MAP.md](./DIR_MAP.md)

## 1. 项目总览

- 后端：`FastAPI + SQLAlchemy + Alembic + Celery + Redis + Elasticsearch`
- 数据库：`PostgreSQL + pgvector`
- 前端：
  - `main/frontend`：旧版模板前端（Jinja/静态页面）
  - `main/frontend-modern`：新版 React + Vite + TypeScript
- 首选运行方式：Docker（首选脚本：`./scripts/docker-deploy.sh`）
- 多项目隔离：按 `project_<key>` schema 进行业务数据隔离

## 1.1 依赖一览

### Docker 模式（推荐）

| 依赖 | 说明 |
|------|------|
| **Docker** | 含 Docker Compose，用于运行全栈服务 |
| **Git** | 克隆与版本管理 |

### 本地开发模式（`local-start`）

| 依赖 | 说明 | 自动安装 |
|------|------|----------|
| **Homebrew** | **必装**，用于安装 PostgreSQL、Redis；macOS 本地模式核心依赖 | 需[手动安装](https://brew.sh) |
| **Python 3.11+** | 后端运行时 | 否 |
| **PostgreSQL** | 数据库（端口 5432） | 是，通过 Homebrew |
| **Redis** | 消息队列（端口 6379） | 是，通过 Homebrew |
| **Elasticsearch** | 全文检索（端口 9200） | 否，需 `--with-docker-deps` 或手动启动 |
| **Node.js / npm** | 前端构建（modern 前端） | 否 |
| **Git** | 版本管理 | 否 |

> **重要**：本地模式依赖 **Homebrew**。若未安装，请先执行：
> ```bash
> /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
> ```
> 安装后按提示将 `brew` 加入 PATH。

## 2. 快速开始（首选 Docker）

### 2.1 首次准备

```bash
cp main/backend/.env.example main/backend/.env
```

### 2.2 可部署性检查（推荐先执行）

```bash
./scripts/docker-deploy.sh preflight
```

### 2.3 一键启动（首选）

```bash
./scripts/docker-deploy.sh start
```

### 2.4 常用运维命令（首选）

```bash
./scripts/docker-deploy.sh stop
./scripts/docker-deploy.sh restart
```

### 2.5 常用访问地址

- OpenAPI：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/api/v1/health`
- 深度健康检查：`http://localhost:8000/api/v1/health/deep`
- 管理入口：`http://localhost:8000/resource-pool-management.html`

本地（非 Docker）模式仅用于开发调试，生产与联调默认按 Docker 链路执行。

### 2.6 本地首次启动（macOS）

若使用本机 PostgreSQL/Redis（非 Docker），首次启动步骤：

```bash
# 1. 复制配置（若尚未存在）
cp main/backend/.env.example main/backend/.env

# 2. 一键启动（自动安装依赖、迁移、导入演示数据）
./scripts/platform-macos.sh local-start
```

脚本会自动：安装 Python 依赖、PostgreSQL/Redis（Homebrew）、pgvector、Node.js，执行数据库迁移，无演示数据时导入 demo_proj。若 Homebrew PostgreSQL 无 `postgres` 用户，会尝试自动创建。

### 2.7 平台封装脚本（每个平台一个入口）

说明：平台脚本的 `start` / `stop` / `restart` 会统一转发到 `./scripts/docker-deploy.sh` 对应命令。`local-start` 调用 `main/backend/start-local.sh`。

统一子命令：
- `start`：Docker 启动全服务
- `stop`：Docker 停止全服务
- `restart`：Docker 重启全服务
- `local-start`：本地后端启动（依赖 `main/backend/start-local.sh`）
- `local-stop`：本地后端停止（依赖 `main/backend/stop-local.sh`）

macOS：

```bash
./scripts/platform-macos.sh start
./scripts/platform-macos.sh stop
./scripts/platform-macos.sh restart
./scripts/platform-macos.sh local-start
./scripts/platform-macos.sh local-stop
```

Linux：

```bash
./scripts/platform-linux.sh start
./scripts/platform-linux.sh stop
./scripts/platform-linux.sh restart
./scripts/platform-linux.sh local-start
./scripts/platform-linux.sh local-stop
```

Windows（PowerShell，自动尝试 Git Bash/WSL）：

```powershell
.\scripts\platform-windows.ps1 start
.\scripts\platform-windows.ps1 stop
.\scripts\platform-windows.ps1 restart
.\scripts\platform-windows.ps1 local-start
.\scripts\platform-windows.ps1 local-stop
```

## 3. 运行拓扑

默认容器服务（`main/ops/docker-compose.yml`）：

- `db`（PostgreSQL）:`5432`
- `es`（Elasticsearch）:`9200`
- `redis`:`6379`
- `backend`（FastAPI）:`8000`
- `celery-worker`（异步任务）
- `frontend-modern`（可选 profile：`modern-ui`）:`5174`

后端核心环境变量：

- `DATABASE_URL`
- `ES_URL`
- `REDIS_URL`
- `MODERN_FRONTEND_URL`（启用新前端重定向）

## 4. 前端入口与迁移关系

- 默认情况下，若配置了 `MODERN_FRONTEND_URL`，访问 `/`、`/app`、`/app.html` 会重定向到新版前端。
- 旧版页面可通过 `?legacy=1` 回退访问。
- 本地开发新版前端：

```bash
cd main/frontend-modern
npm install
VITE_API_PROXY_TARGET=http://localhost:8000 npm run dev
```

- 访问：`http://localhost:5173`

## 5. 仓库结构与职责

```text
<repo-root>/
├── README.md                     # 项目主说明
├── GIT_WORKFLOW.md               # 协作规范
├── 信息源库/                     # 运行时来源配置库（global + projects）
├── 信息流优化/                   # 优化路线与阶段规划
├── reference_pool/               # 调研与参考资料库
└── main/
    ├── QUICKSTART.md             # 快速启动
    ├── ops/                      # Docker 编排与运维脚本
    ├── backend/                  # FastAPI 服务、模型、迁移、测试
    ├── frontend/                 # 旧版模板前端
    └── frontend-modern/          # 新版 React 前端
```

## 6. 后端架构（`main/backend`）

### 6.1 API 层

统一前缀：`/api/v1`。主要分组：

- `ingest`：采集与配置
- `search`：检索与索引初始化
- `resource_pool`：资源池抽取、站点入口、统一搜索
- `source_library`：来源库条目与执行
- `projects` / `project-customization`：项目管理与定制
- `dashboard` / `admin` / `process`：运营与任务管理

### 6.2 服务层

`main/backend/app/services` 关键模块：

- `ingest/`：政策、市场、新闻、社媒等采集
- `search/`：Web 检索、ES 检索、混合检索
- `resource_pool/`：URL 提取、站点入口发现、候选写回
- `source_library/`：来源条目解析、路由、执行、同步
- `collect_runtime/`：统一采集运行时与适配器执行
- `indexer/`：文本处理与索引写入
- `tasks.py`：Celery 异步任务

### 6.3 数据层与迁移

- ORM：`main/backend/app/models/entities.py`
- 迁移：`main/backend/migrations/versions/*`
- 策略：
  - `public`：共享与控制平面（如 shared_*、部分全局配置）
  - `project_<key>`：项目隔离业务数据
- 启动时会自动执行：`alembic upgrade head`

## 7. 核心数据流

### 7.1 采集流（Ingest）

输入任务 -> `ingest/*` / `collect_runtime/*` -> 落库 -> `indexer/*` -> 可检索。

### 7.2 检索流（Search）

`search` API -> ES/DB（bm25/vector/hybrid）-> 返回标准化结果。

### 7.3 来源库流（Source Library）

条目配置（global/project）-> handler 路由与适配器执行 -> 采集结果落库/索引。

### 7.4 资源池流（Resource Pool）

从文档/任务提取 URL -> 发现 site entries -> 统一搜索扩展候选 -> 写回资源池 -> 可触发后续入库。

## 8. API 快速验证

```bash
BASE=http://localhost:8000/api/v1

curl "$BASE/health"
curl "$BASE/health/deep"
curl "$BASE/search?q=lottery&top_k=5"
curl "$BASE/projects"
```

带项目上下文示例：

```bash
curl "$BASE/source_library/items?project_key=demo_proj&scope=effective"
curl "$BASE/resource_pool/urls?project_key=demo_proj&scope=effective&page=1&page_size=20"
```

说明：部分接口要求 `project_key` 参数或 `X-Project-Key` 请求头。

## 9. 测试分层与 CI 门禁

后端测试目录：`main/backend/tests`，按分层组织为：

- `unit`：纯逻辑测试，快速反馈
- `integration`：模块装配与协作测试
- `contract`：API Envelope / OpenAPI 契约稳定性测试
- `e2e`：关键链路冒烟测试

`pytest` 已启用 `--strict-markers`，marker 定义见 `main/backend/pytest.ini`。

本地执行（仓库根目录）：

```bash
cp main/backend/.env.example main/backend/.env
cd main/backend
.venv311/bin/python -m pytest -m unit -q
.venv311/bin/python -m pytest -m integration -q
.venv311/bin/python -m pytest -m contract -q
.venv311/bin/python -m pytest -m e2e -q
```

CI 门禁（`.github/workflows/backend-tests.yml`）：

- `pull_request`：`unit-check + integration-check + docker-check`
- `main` 分支 `push` / `schedule` / `workflow_dispatch`：`unit-check + integration-check + contract-check + e2e-check + docker-check`

当前 `e2e` 冒烟已覆盖：

- `/api/v1/health`
- `/api/v1/health/deep`
- `X-Project-Key` 请求头解析与 header/query 优先级

## 10. 运维与排障

常用命令：

```bash
cd main/ops
docker-compose ps
docker-compose logs -f backend
docker-compose logs -f celery-worker
```

端口排查：

```bash
lsof -i :8000
lsof -i :5432
lsof -i :9200
lsof -i :6379
```

快速自检：

```bash
cd main/ops
./test-docker-startup.sh
```

## 11. 演示数据

- SQL 数据包：`main/backend/seed_data/project_demo_proj_v0.9-rc2.0.sql`
- 导入脚本：`main/backend/scripts/load_demo_proj_seed.sh`
- 前端静态下载：
  - `/static/demo/project_demo_proj_v0.9-rc2.0.sql`
  - `/static/demo/load_demo_proj_seed.sh`

## 12. 文档导航

- 快速启动：`main/QUICKSTART.md`
- Docker 运维：`main/ops/README.md`
- 后端说明：`main/backend/README.md`
- 本地开发：`main/backend/README.local.md`
- API 总文档：`main/backend/API接口文档.md`
- API 路由清单：`main/backend/docs/API_ROUTE_INVENTORY_2026-02-27.md`
- 后端文档索引：`main/backend/docs/README.md`
- 资源库定义：`main/backend/docs/RESOURCE_LIBRARY_DEFINITION.md`
- 资源池 API：`main/backend/docs/RESOURCE_POOL_EXTRACTION_API.md`
- 前端迁移契约：`main/backend/docs/FRONTEND_MODERNIZATION_API_MAP_2026-02-27.md`
- 后端测试分层说明：`main/backend/tests/README.md`
- 迭代计划：`plans/status-8x-2026-02-27.md`
- 版本说明：`RELEASE_NOTES_pre-release-0.9-rc2.0.md`

## 13. 8.x 进一步开发规划（状态同步）

以下状态同步自预发布说明第 8 节，并结合当前仓库落地情况更新（截至 `2026-03-01`）：

| 路线 | 当前状态 | 说明 / 下一步 |
|---|---|---|
| `8.1` 来源池自动提取与整合 | 已完成 | 主链路可用，继续做稳定性回归。 |
| `8.2` 工作流平台化 | 已完成最小闭环 | 已具备模板读取/保存/运行，下一步补更细粒度编排能力。 |
| `8.3` Perplexity 集成 | 未开始 | 进入实现前先完成 provider 接口与配额策略设计。 |
| `8.4` 时间轴与事件/实体演化 | 进行中 | 统一时间线模型与展示口径。 |
| `8.5` RAG + LLM 对话与分析报告 | 部分完成 | 检索能力已具备，需补报告与对话闭环 API。 |
| `8.6` 公司/商品/电商对象化采集 | 部分完成 | 已有专题能力，需统一采集入口与对象模型。 |
| `8.7` 数据类型优化 | 进行中 | 继续提升提取质量与类型一致性。 |
| `8.8` 其他迭代（质量与工程化） | 进行中（基线已落地） | 已完成测试分层与 CI 门禁基线，下一步扩展关键业务 e2e。 |

本轮已完成的 `8.8` 基线项：

- 后端测试分层：`unit / integration / contract / e2e`
- `pytest` 严格 marker：`--strict-markers`
- CI 并行门禁：`unit-check`、`integration-check`、`contract-check`、`e2e-check`、`docker-check`

详见：

- 版本说明：`RELEASE_NOTES_pre-release-0.9-rc2.0.md`
- 迭代计划：`plans/status-8x-2026-02-27.md`

## 14. 当前已知风险（供联调参考）

- 新旧前端并行，功能存在重叠，迁移仍在进行中。
- `resource_pool` 路由存在下划线/连字符兼容写法，建议逐步统一。
- 部分接口仍处于响应风格过渡期（Envelope 统一尚未完全收口）。
- 异步任务依赖 Celery/Redis，排查问题需结合 worker 日志。
- 外部搜索/社媒/LLM 供应商能力受 API Key 与配额影响。

## 15. 协作规范

代码协作与分支策略见：`GIT_WORKFLOW.md`
