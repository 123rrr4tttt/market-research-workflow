# 预发行版 Release Notes：v0.1.0-rc.1（2026-02-26）

- 版本类型：`Release Candidate（预发行）`
- 版本目标：为 `v0.1.0` 正式版做整合与稳定性验证
- 适用场景：内部联调、迁移验证、验收回归
- 不建议：作为长期稳定生产基线

## 摘要（一句话）

本 RC 聚焦把“资源池（Resource Pool）+ 统一搜索（Unified Search）+ 采集运行时（Collect Runtime）+ 来源库适配器（Source Library）”串成可验证闭环，并配套迁移与管理页面，进入缺陷收敛阶段。

## 亮点（你应该关心的）

- 资源池主链路进入可验证状态（URL 抽取 → `site_entries` 发现 → 去重 → 候选写回 → `url_pool` 抓取入库）。
- 采集运行时模块落地，为后续工作流平台化与可视化执行打基础。
- 来源库改为适配器化（handler registry / url router），新增来源类型的接入方式更统一。
- 前端新增资源池管理页面模板，用于联调与验收。

## 交付内容（按落地物）

- 资源池 API：`main/backend/app/api/resource_pool.py`
- 资源池服务：`main/backend/app/services/resource_pool/`
- 采集运行时：`main/backend/app/services/collect_runtime/`
- 来源库适配器：`main/backend/app/services/source_library/adapters/`
- 资源池管理页：`main/frontend/templates/resource-pool-management.html`
- 设计与验证文档：`main/backend/docs/`

## 功能介绍（团队试用版）

本 RC 适合团队按“主链路闭环”来试用，重点是验证：资源池能否把发现、沉淀与抓取入库串起来，并且在多项目隔离下可控可复现。

### 资源池（Resource Pool）

- 目标：沉淀“项目可用的信息来源 URL”，并对 URL 做去重、归因与后续抓取入库衔接。

可试用功能：

- 从已有文档中抽取 URL 写入资源池（支持同步或 Celery 异步）。
- 从任务记录中抽取 URL 写入资源池（适合把历史采集任务反哺成资源池资产）。
- 浏览与筛选资源池 URL（按 scope/source/domain 分页查看）。

### 站点入口（Site Entries）

- 目标：把资源池 URL 进一步归纳成可执行的“站点入口”（domain_root/rss/sitemap/search_template 等），用于后续统一搜索与自动发现。

可试用功能：

- 从资源池 URL 自动探测并生成 `site_entries`（可选是否探测 link alternate、RSS/sitemap 常见路径）。
- 手工新增或更新某个站点入口（例如补一个 RSS 或 sitemap）。
- 对站点入口做规则优先的分类推荐（必要时可启用 LLM 兜底）。

### 统一搜索（Unified Search by Item）

- 目标：基于 `item_key + query_terms + site_entries` 做站内/站点级搜索，产出候选 URL，并可选择写回资源池与自动入库。

可试用功能：

- 对某个 `item_key` 生成候选 URL（并返回使用的 `site_entries` 与错误信息）。
- 选择将候选写回资源池（去重）。
- 选择 `auto_ingest=true` 触发抓取入库（限制 `ingest_limit`，用于 RC 快速验证闭环）。

### 多项目隔离（Project Key）

- 目标：同一套能力在不同项目 schema 下互不影响。

试用要点：

- 所有资源池相关 API 都需要项目上下文，使用 `X-Project-Key` Header 或 `project_key` 查询参数。
- 示例项目 key 通常为 `online_lottery`（以你仓库当前默认迁移/绑定为准）。

## 试用路径（推荐，30-60 分钟跑通）

1. 启动服务（见“升级与启动”），打开 OpenAPI：`http://localhost:8000/docs`。
2. 打开管理页面：`http://localhost:8000/resource-pool-management.html`（来源库入口也会重定向到这里）。
3. 确定项目 key，并在 API 请求里设置 `X-Project-Key`（或 `project_key` 参数）。
4. 抽取 URL 入资源池：`POST /api/v1/resource_pool/extract/from-documents`（或 `POST /api/v1/resource_pool/capture/from-tasks`）。
5. 确认 URL 入池：`GET /api/v1/resource_pool/urls`。
6. 自动发现站点入口：`POST /api/v1/resource_pool/discover/site-entries`。
7. 校验站点入口：`GET /api/v1/resource_pool/site_entries`（类型与 domain 是否合理）。
8. 统一搜索验证闭环：`POST /api/v1/resource_pool/unified-search`，先产出候选，再打开 `write_to_pool/auto_ingest` 小流量验证。

## 关键接口速查（试用常用）

- `POST /api/v1/resource_pool/extract/from-documents`：从 Documents 抽取 URL 入资源池（支持 `async_mode`）。
- `POST /api/v1/resource_pool/capture/enable`：启用/禁用对指定任务类型的资源池捕获。
- `POST /api/v1/resource_pool/capture/from-tasks`：从 Tasks 抽取 URL 入资源池（支持 `async_mode`）。
- `GET /api/v1/resource_pool/urls`：分页查看资源池 URL（scope/source/domain）。
- `POST /api/v1/resource_pool/discover/site-entries`：从 URL 探测并生成 `site_entries`（可写入 shared 或 project）。
- `GET /api/v1/resource_pool/site_entries`：分页查看站点入口（domain/entry_type/enabled）。
- `POST /api/v1/resource_pool/site_entries`：手工 upsert 站点入口（支持 `search_template` 等）。
- `POST /api/v1/resource_pool/site_entries/recommend`：对站点入口做分类推荐（规则优先，`use_llm=true` 可兜底）。
- `POST /api/v1/resource_pool/unified-search`：按 `item_key` 做统一搜索，产出候选 URL，可写回与自动入库。

## 快速请求示例（可直接改）

```bash
curl -sS -H 'Content-Type: application/json' -H 'X-Project-Key: online_lottery' \
  -X POST 'http://localhost:8000/api/v1/resource_pool/extract/from-documents' \
  -d '{"scope":"project","filters":{"limit":200},"async_mode":false}' | jq
```

```bash
curl -sS -H 'Content-Type: application/json' -H 'X-Project-Key: online_lottery' \
  -X POST 'http://localhost:8000/api/v1/resource_pool/discover/site-entries' \
  -d '{"url_scope":"effective","target_scope":"project","limit_domains":50,"probe_timeout":8.0}' | jq
```

```bash
curl -sS -H 'Content-Type: application/json' -H 'X-Project-Key: online_lottery' \
  -X POST 'http://localhost:8000/api/v1/resource_pool/unified-search' \
  -d '{"item_key":"<your_item_key>","query_terms":["<term1>","<term2>"],"write_to_pool":true,"auto_ingest":false,"max_candidates":200}' | jq
```

## 数据库迁移（必做）

本 RC 引入资源池与采集配置相关表/配置，升级前请先备份数据库。

- `main/backend/migrations/versions/20260226_000001_add_resource_pool_tables.py`
- `main/backend/migrations/versions/20260226_000002_add_resource_pool_capture_config.py`
- `main/backend/migrations/versions/20260226_000003_add_ingest_config.py`
- `main/backend/migrations/versions/20260226_000004_add_resource_pool_site_entries.py`

## 升级与启动（推荐路径）

- 升级前备份数据库。
- 使用仓库运维脚本启动（会处理依赖健康检查与迁移）：

```bash
export PROJECT_DIR="main"
cd "$PROJECT_DIR/ops"
./start-all.sh
```

- 确认服务可用：OpenAPI `http://localhost:8000/docs`；健康检查 `http://localhost:8000/api/v1/health`。

说明：`start-all.sh` 启动流程包含 `alembic upgrade head`。

## 验证清单（RC Gate，建议按顺序）

- 迁移可在“全新 DB”与“现有 DB 快照”上正常执行。
- 资源池闭环跑通：抽取 URL、发现 `site_entries`、去重、统一搜索写回、`url_pool` 抓取入库。
- 项目隔离仍正确（schema `project_<key>`），并且 `X-Project-Key` 切换行为符合预期。
- Celery 任务链稳定运行，失败日志足够定位问题。
- 前端资源池管理页能驱动预期的后端接口完成联调。

可选脚本验证（更偏 E2E）：

- `main/backend/scripts/test_resource_library_e2e.py`
- `main/backend/scripts/test_search_to_document_chain.py`

## 已知风险（RC 期）

- 迁移与服务逻辑耦合较高，环境差异是主要风险来源。
- adapter 在复杂站点上仍可能不稳定（限流、反爬、页面结构变化）。
- UI 与 API 的字段/交互细节可能仍需一轮联调收敛。
- 测试覆盖目前不足以作为生产稳定性信号。

## 下一步（走向 v0.1.0 的必做项）

- 跑完“验证清单”，收敛所有阻塞发布的问题（数据正确性、任务失败、迁移问题）。
- 做一份可重复执行的最小回归清单：ingest 主流程、项目切换、资源池闭环。
- 补充迁移回滚说明与“已知可用环境矩阵”（依赖版本与启动方式）。

## 路线图（v0.1.0 之后，来自 README）

- 来源池自动提取与整合增强（分级、融合、冲突处理）。
- 工作流平台化（项目模板、工作流可编辑、看板可编辑、无 LLM 模式）。
- 搜索与发现增强（Perplexity 集成与多源融合）。
- 时间轴与事件/实体演化建模与可视化。
- RAG 对话与结构化分析报告。
- 公司/商品/电商对象化信息收集能力。
- 数据类型规范化与图谱 schema 扩展。
