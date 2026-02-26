# 市场情报（market-intel）项目说明

> 最后更新：2026-02-26

当前版本：`v0.1.5-rc1`（预发布，团队联调）

本版本附带可导入的 `demo_proj` 演示数据包（仓库路径：`main/backend/seed_data/project_demo_proj_v0.1.5-rc1.sql`；前端下载：`/static/demo/project_demo_proj_v0.1.5-rc1.sql`），可配合导入脚本（仓库路径：`main/backend/scripts/load_demo_proj_seed.sh`；前端下载：`/static/demo/load_demo_proj_seed.sh`）快速恢复联调数据。

本文档为项目主说明，涵盖定位、快速开始、架构与文档入口。所有路径均为**相对仓库根目录**。

版本管理与协作建议见：`GIT_WORKFLOW.md`（轻量 Git 工作流）

预发布说明（团队联调）：`RELEASE_NOTES_pre-release-1.5.md`（v0.1.5-rc1）

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

**试用入口**：管理页面 `http://localhost:8000/resource-pool-management.html`（资源池/来源库） | Release Notes `RELEASE_NOTES_pre-release-1.5.md`

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
| `RELEASE_NOTES_pre-release-1.5.md` | 预发布 1.5 说明（资源库稳定化、任务展示、结构化补齐、图谱页修复） |
| `GIT_WORKFLOW.md` | Git 工作流（轻量版） |

### 7.5 已实现能力：来源池与统一搜索

以下能力已落地，详见 `main/backend/docs/RESOURCE_LIBRARY_DEFINITION.md`、`main/backend/docs/RESOURCE_POOL_EXTRACTION_API.md`：

- **自动提取**：从文档/任务提取 URL 写入 `resource_pool_urls`；从 URL 自动发现站点入口（`site_entries`：domain_root、RSS、sitemap、link_alternate）
- **去重**：`resource_pool_urls` 唯一约束；统一搜索写回时按 URL 去重
- **进一步收集**：统一搜索（query_terms + item 绑定的 site_entries）→ 候选 URL 写回池 → `url_pool` 抓取入库；支持 `auto_ingest` 一条龙完成
- **多项目隔离**：resource_pool、site_entries、documents 均按 `project_<key>` schema 隔离
- **管理入口**：`http://localhost:8000/resource-pool-management.html`

---

## 8. 进一步开发规划

### 8.1 来源池的自动提取与整合（待完成）

- **分级**：按可信度、更新频率、覆盖范围对来源分级
- **整合**：跨来源合并、冲突消解（去重已实现）

### 8.2 完善工作流平台化

- **项目模板创建**：支持从模板创建新项目，预置工作流、看板、信息源配置
- **工作流可编辑**：在 UI 中配置采集流程、触发条件、依赖关系
- **看板可编辑**：自定义看板布局、指标、筛选与视图
- **无 LLM 模式**：基于完善的来源池与符号化处理流程，支持纯规则/模板驱动的采集与结构化，不依赖 LLM

### 8.3 集成 Perplexity

- 接入 Perplexity API，作为搜索/发现与问答的补充能力
- 与现有 Serper/DDG/Google 等形成多源搜索与结果融合

### 8.4 时间轴与事件/实体演化

- **时间轴**：对事件、实体按时间顺序建模与可视化
- **演化数据**：追踪实体（公司、商品、政策等）随时间的变化、版本与关联关系

### 8.5 RAG + LLM 对话与分析报告

- **RAG 对话**：基于已入库文档的检索增强生成，支持多轮问答
- **分析报告**：基于 RAG 上下文生成结构化分析报告（政策解读、市场趋势、竞品分析等）

### 8.6 以公司、商品、电商为对象的信息收集

- **公司**：以公司为对象的信息采集（舆情、动态、关联数据）
- **商品**：以商品为对象的信息采集（商品库、价格追踪、竞品对比）
- **电商**：以电商/售卖为对象的信息采集（销售渠道、价格观测、库存与促销）

### 8.7 数据类型优化

- 扩展 `doc_type` 与 `extracted_data` 结构，支持更多业务类型
- 统一时间、金额、枚举等字段的格式与校验
- 图谱节点/边类型的规范化与扩展

### 8.8 其他迭代

- 完善 adapter 稳定性（重试、限流、站点兼容）
- 补齐 ingest、dashboard、project 切换等关键链路测试
- 图谱与治理能力增加操作面与可视化联动
- 清理历史脚本，沉淀为可复用运维命令
