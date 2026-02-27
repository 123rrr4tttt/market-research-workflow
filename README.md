# 市场情报（market-intel）项目说明

> 最后更新：2026-02-27

当前版本：`v0.1.7-rc1`（预发布，团队联调）

本版本附带可导入的 `demo_proj` 演示数据包。项目部署后可在页面点击“注入初始项目”一键恢复演示数据。

数据包（仓库路径：`main/backend/seed_data/project_demo_proj_v0.1.7-rc1.sql`；前端下载：`/static/demo/project_demo_proj_v0.1.7-rc1.sql`），可配合导入脚本（仓库路径：`main/backend/scripts/load_demo_proj_seed.sh`；前端下载：`/static/demo/load_demo_proj_seed.sh`）快速恢复联调数据。

本文档为项目主说明，涵盖定位、快速开始、架构与文档入口。所有路径均为**相对仓库根目录**。

版本管理与协作建议见：`GIT_WORKFLOW.md`（轻量 Git 工作流）

预发布说明（团队联调）：`RELEASE_NOTES_pre-release-1.7.md`（v0.1.7-rc1）

试用入口：
- 管理页面：`http://localhost:8000/resource-pool-management.html`
- OpenAPI：`http://localhost:8000/docs`

---

## 1. 项目概述

本仓库实现**多来源信息采集 → 结构化处理 → 可检索查询 → 可视化与运维**的一体化工作流。

**技术栈**：FastAPI、Celery + Redis、SQLAlchemy + PostgreSQL、Elasticsearch、Jinja2 模板前端

**核心能力**：政策/市场/新闻/社媒采集、LLM 结构化提取、ES 检索、仪表盘与图谱可视化、多项目数据隔离

---

## 2. 快速开始

### 2.1 Docker 一键启动（推荐）

```bash
export PROJECT_DIR="main"
cd "$PROJECT_DIR/ops"
./start-all.sh
```

停止：`./stop-all.sh`

**首次运行**：复制 `main/backend/.env.example` 为 `main/backend/.env`（可选，有默认值）。

**访问**：OpenAPI `http://localhost:8000/docs` | 健康检查 `http://localhost:8000/api/v1/health`

**试用入口**：管理页面 `http://localhost:8000/resource-pool-management.html`（资源池/来源库） | Release Notes `RELEASE_NOTES_pre-release-1.7.md`

**项目上下文**：部分接口（尤其资源池相关）需要 `X-Project-Key` Header 或 `project_key` 参数。

### 2.2 本地开发（后端）

```bash
cd main/backend
./start-local.sh
```

依赖服务（PostgreSQL、ES、Redis）可单独用 `docker-compose up -d db es redis` 启动。详见 `main/backend/README.local.md`。

---

## 3. 仓库结构

```text
<repo-root>/
├── README.md              # 本文档
├── 信息源库/              # 信息源配置（channels/items）
├── 信息流优化/            # A/B/C 阶段优化路线
├── reference_pool/        # 参考资料（gitignore）
└── main/
    ├── QUICKSTART.md
    ├── backend/           # FastAPI 应用、服务、迁移、脚本
    ├── frontend/          # 模板与静态资源
    └── ops/               # docker-compose、start-all.sh、stop-all.sh
```

---

## 4. 后端架构

### 4.1 API 分层

`app/api` 按领域拆分，挂载于 `/api/v1`：

| 模块 | 职责 |
|------|------|
| policies, market, search, reports | 政策/市场/检索/报表 |
| ingest, discovery, indexer | 采集、发现搜索、索引 |
| dashboard, admin, process | 仪表盘、管理台、任务 |
| projects, topics, products, governance | 项目/主题/商品/治理 |
| llm_config, config, source_library, project_customization | 配置与定制 |
| resource_pool | 资源池与统一搜索（来源沉淀/站点入口/候选写回/自动入库） |

### 4.2 服务层

- `ingest/` + `adapters/`：政策、市场、新闻、社媒、商品、电商采集
- `resource_pool/`：资源池、站点入口发现、统一搜索、候选写回与 `url_pool` 衔接
- `collect_runtime/`：采集运行时（适配器化执行骨架）
- `source_library/`：来源库（adapter/registry/router）
- `search/`：检索、索引、历史、智能搜索
- `llm/` + `extraction/`：结构化提取与模型调用
- `graph/`：图谱构建与导出
- `aggregator/`：项目库汇总同步
- `governance/`：数据保留与治理
- `projects/`：多项目上下文与 schema 绑定

### 4.3 数据与隔离

- `public`：项目元数据（`projects`、`project_sync_state`）
- `project_<key>`：按项目隔离业务数据（如 `project_online_lottery`）
- `aggregator`：跨项目聚合

启动时会将历史 `default` 迁移为 `online_lottery`。请求通过 `X-Project-Key` / `project_key` 或当前激活项目绑定上下文。

### 4.4 异步任务

主要采集任务已 Celery 化。大部分 ingest 接口支持 `async_mode=true` 触发后台任务。

---

## 5. 前端与页面

模板由 `main/frontend/templates` 提供，入口在 `main.py`。

**主要页面**：index、app、settings、admin、dashboard、resource-pool-management（资源池/来源库）、process-management、project-management、policy-*、social-media-*、market-data-visualization 等。

---

## 6. 运行与部署

**推荐**：`main/ops/start-all.sh` 统一启动，不建议分散手动启动。

**核心服务**：Backend `:8000`、PostgreSQL `:5432`、Elasticsearch `:9200`、Redis `:6379`

**启动流程**：依赖健康检查 → `alembic upgrade head` → FastAPI 启动

---

## 7. 文档入口

| 文档 | 说明 |
|------|------|
| `main/QUICKSTART.md` | 快速启动 |
| `main/ops/README.md` | Docker 运维与排障 |
| `main/backend/README.md` | 后端配置与抓取能力 |
| `main/backend/README.local.md` | 本地开发配置 |
| `main/backend/API接口文档.md` | API 完整参考 |
| `main/backend/docs/README.md` | 后端文档索引 |
| `信息流优化/README.md` | 优化路线 |
| `RELEASE_NOTES_v0.1.0-rc.1.md` | 历史 RC 版本说明（v0.1.0-rc.1） |
| `RELEASE_NOTES_pre-release-1.7.md` | 预发布 1.7 说明（资源库稳定化、任务展示、结构化补齐、图谱页修复） |
| `GIT_WORKFLOW.md` | Git 工作流（轻量版） |

### 7.5 已实现能力：来源池与统一搜索

以下能力已落地，详见 `main/backend/docs/RESOURCE_LIBRARY_DEFINITION.md`、`main/backend/docs/RESOURCE_POOL_EXTRACTION_API.md`：

- **自动提取**：从文档/任务提取 URL 写入 `resource_pool_urls`；从 URL 自动发现站点入口（`site_entries`：domain_root、RSS、sitemap、link_alternate）
- **去重**：`resource_pool_urls` 唯一约束；统一搜索写回时按 URL 去重
- **进一步收集**：统一搜索（query_terms + item 绑定的 site_entries）→ 候选 URL 写回池 → `url_pool` 抓取入库；支持 `auto_ingest` 一条龙完成
- **多项目隔离**：resource_pool、site_entries、documents 均按 `project_<key>` schema 隔离
- **管理入口**：`http://localhost:8000/resource-pool-management.html`

### 7.6 与第 8 节规划的偏差说明（核验时间：2026-02-27）

- 第8节为工作区实际实现状态：`8.1` 已形成稳定增量；`8.2 / 8.4 / 8.7 / 8.8` 进行中偏差收口；`8.3` 尚未开始；`8.5 / 8.6` 处于部分完成状态。
- 说明：`8.2` 已完成“模板读写与运行”最小闭环，仍未达到完整“可编辑模板/看板编辑器”闭环。
- 由于近期迭代集中在 `resource_pool` 与主干采集稳定性，未与第8节保持 1:1 实时同步，本文档后续条目已按“真实状态”重写为：
  - `状态 / 完成度`：`已完成 / 部分完成 / 进行中 / 未开始`
  - `证据`：对应服务层或 API 路径
  - `下步动作`：本轮可执行闭环任务

---

## 8. 进一步开发规划

> 最近核验：`2026-02-27`
> 可执行清单：`plans/status-8x-2026-02-27.md`
> 多智能体执行记录：`plans/8x-multi-agent-kickoff-2026-02-27.md`、`plans/8x-round-1-2026-02-27.md`
> 决策记录：`plans/decision-log-2026-02-27.md`
> 第2轮执行：`plans/8x-round-2-2026-02-27.md`、`plans/8x-round-2-2026-02-27-taskboard.md`

### 8.1 来源池的自动提取与整合（已完成）

**状态**：`已完成`  
**完成度**：已实现核心链路，覆盖源抽取、站点入口发现、统一搜索并发执行与写回逻辑。  
**证据**：
- `main/backend/app/services/resource_pool/unified_search.py`
- `main/backend/app/api/resource_pool.py`
- `RELEASE_NOTES_pre-release-1.7.md`
**下步动作**：
- 将分级、跨源整合策略沉淀为可配置阈值（信任度、频率、覆盖率）并加入回归验收项。
- 形成 8.1 的验收文档：每条写回 URL 的来源可追溯 `source_ref.site_entry_url`。

### 8.2 完善工作流平台化
 
**状态**：`部分完成`  
**完成度**：已在项目定制 API 与 dashboard 落地“读取模板 / 保存模板 / 触发运行”的最小闭环。  
**证据**：
- `main/backend/app/api/project_customization.py`
- `main/backend/app/services/projects/workflow.py`
- `main/frontend/templates/dashboard.html`
**下步动作**：
- 以 `template_id + board_layout + trigger_rules` 做 schema 约束，补齐前端校验与回显一致性。
- 增加模板列表/历史版本与编辑器友好化（字段注释、字段类型、最小输入校验）。

### 8.3 集成 Perplexity
 
**状态**：`未开始`  
**完成度**：当前未发现 Perplexity 接口或适配器实现。  
**证据**：未检索到 `perplexity` 适配/API 代码路径  
**下步动作**：
- 先定义 provider 适配层（`search` 与 `discover` 双通道）。
- 新增密钥/限流配置与 `source_priority` 聚合策略。
- 增加聚合结果可复现对比测试。

### 8.4 时间轴与事件/实体演化
 
**状态**：`进行中`  
**完成度**：已有时间线展示能力，但未形成统一事件-实体版本模型。  
**证据**：
- `main/frontend/templates/policy-tracking.html`
- `main/frontend/templates/policy-state-detail.html`
**下步动作**：
- 设计统一事件与实体版本 schema（事件来源、时间、实体关系、版本字段）。
- 增加“实体沿时间线”后端查询接口与前端切换视图。

### 8.5 RAG + LLM 对话与分析报告
 
**状态**：`部分完成`  
**完成度**：已有混合检索/向量入库能力，但未形成对话与报告 API 闭环。  
**证据**：
- `main/backend/app/services/search/hybrid.py`
- `main/backend/app/services/indexer/policy.py`
- `main/backend/app/api/search.py`（备注为统一检索入口，尚无 chat/report 专属路由）
**下步动作**：
- 在 `api/search` 下补充 `POST /chat` 与 `POST /analysis-report` 任务链路。
- 在前端补齐会话状态（上下文、引用展示、报告下载）。

### 8.6 以公司、商品、电商为对象的信息收集
 
**状态**：`部分完成`  
**完成度**：已具备专题抽取、图谱/看板展示基础，但未完成统一的对象型采集闭环。  
**证据**：
- `main/backend/app/api/admin.py`
- `main/backend/app/api/products.py`
- `main/frontend/templates/graph.html`
**下步动作**：
- 建立对象型采集任务（company/product/operation）编排模板和项目级配置。
- 把实体对象、价格观测、竞品对比打通到统一任务/报表链路。

### 8.7 数据类型优化
 
**状态**：`进行中`  
**完成度**：继续在提取与归一化中扩展 `extracted_data` 字段与时间提取准确性，但全局规范仍未完全统一。  
**证据**：
- `main/backend/app/services/discovery/store.py`
- `main/backend/app/services/extraction/extract.py`
**下步动作**：
- 固化 `doc_type` 与 `extracted_data` JSON schema 版本化约束。
- 补齐全量日期、金额、枚举校验与历史记录回放脚本。

### 8.8 其他迭代
 
**状态**：`进行中`  
**完成度**：核心稳定性在持续修复，但“占位页/历史脚本治理”等事项待收口。  
**证据**：
- `main/backend/app/services/collect_runtime/adapters/source_library.py`
- `main/backend/app/services/collect_runtime/adapters/url_pool.py`
- `main/frontend/templates/resource-pool-management.html`（存在“占位”文案）
**下步动作**：
- 列出 adapter 可靠性清单并对接统一重试/限流策略。
- 完成关键链路测试清单与历史脚本整理，新增“可复用运维命令”归档。

**交付状态总览文件**：`plans/status-8x-2026-02-27.md`
