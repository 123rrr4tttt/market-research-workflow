# MERGED_BACKEND_DOCS

> Scope: Consolidated draft for `development/latest-dev-docs/backend-docs`  
> Updated: 2026-03-01

## 0. 使用说明

本文件将当前后端分散文档归并为四个主视角：
- 架构（Architecture）
- API（Contract + Route + Frontend Integration）
- 采集（Ingest + Resource Library + Data Quality）
- 路线图（Roadmap + Phase + 验收证据）

阅读建议：
1. 新成员先读「架构」和「API」。
2. 研发改造采集链路时重点读「采集」。
3. 评估近期交付状态与下一阶段时读「路线图」。

## 1. 架构（Architecture）

### 1.1 系统分层

后端主链路可抽象为：
- API 层：`app/api/*.py` 暴露 `/api/v1/*`，承担参数校验、租户上下文、同步/异步入口。
- 服务层：`app/services/*` 组织领域流程（ingest、graph、discovery、policy 等）。
- 适配器层：对接外部网站/API 与平台特化逻辑。
- 数据层：PostgreSQL（项目 schema + shared/public）与 pgvector；部分链路接 Elasticsearch。

对应文档主证据：
- `INGEST_ARCHITECTURE.md`
- `接口层调查文档.md`
- `数据库说明文档.md`

### 1.2 多租户与项目隔离

当前核心隔离机制：
- `project_key` 作为项目上下文，支持 header/query 传递。
- 运行时存在 `warn | require` 两阶段约束（缺失 key 时容错/强制）。
- 请求与回退可观测性通过响应头透传（`X-Project-Key-*`）。

对应文档主证据：
- `INGEST_CHAIN_EVIDENCE_MATRIX_2026-03-01.md`
- `INGEST_CHAIN_TASKBOARD_2026-03-01.md`
- `FRONTEND_MODERNIZATION_API_MAP_2026-02-27.md`

### 1.3 图谱与结构化协同

图谱与结构化抽取并行存在，关键点：
- 图谱系统覆盖社交图谱与市场图谱两条构图链路。
- 结构化字段与图谱适配器之间已有对齐说明与修复记录。
- 仍需持续处理跨平台字段不齐导致的归一化失败问题（尤其 social 非 reddit 来源）。

对应文档主证据：
- `社交平台图谱生成标准文档.md`
- `社交平台内容图谱API.md`
- `STRUCTURED_VS_GRAPH_ALIGNMENT.md`
- `政策数据结构说明.md`

### 1.4 架构边界与解耦方向

架构治理的两个明确方向：
- 统一采集骨架：`collect_runtime` 作为主干执行协议。
- 领域解耦：彩票特化逻辑逐步下沉到子项目，主干保留通用能力。

对应文档主证据：
- `UNIFIED_COLLECT_ARCHITECTURE.md`
- `COLLECT_RUNTIME_SOCIAL_PHASE2_NOTE.md`
- `LOTTERY_DECOUPLING_INVENTORY.md`

## 2. API

### 2.1 契约标准

统一约定包括：
- 响应 envelope：`status/data/error/meta`
- 错误码与 HTTP 状态码映射
- 分页统一放置于 `meta.pagination`
- 失败不得伪装成 `HTTP 200`

对应文档：`API_CONTRACT_STANDARD.md`

### 2.2 路由盘点与分层

当前自动解析路由库存量：
- `API_ROUTE_INVENTORY_2026-02-27.md` 标注总计 135 条路由。
- 接口层调查文档提供了 API 文件、应用级路由、前端调用封装与内部 contracts 的分层视图。

对应文档：
- `API_ROUTE_INVENTORY_2026-02-27.md`
- `接口层调查文档.md`

### 2.3 前端换栈 API 最小契约

前端现代化阶段优先绑定：
- 基础/项目接口
- ingest 工作台接口
- source library / resource pool 前置接口
- process 任务监控接口
- dashboard 核心指标接口

对应文档：`FRONTEND_MODERNIZATION_API_MAP_2026-02-27.md`

### 2.4 数据模型 API 语义锚点

API 的主要数据承载对象：
- `documents` / `market_stats` / `etl_job_runs` 等核心表。
- `extracted_data`（JSONB）承载政策、市场、社交等结构化负载。

对应文档：
- `数据库说明文档.md`
- `政策数据结构说明.md`
- `社交平台内容图谱API.md`

### 2.5 第三方 API 接入约束

已明确的平台接入要点：
- Reddit：setup 与 limit 上限、调用方式与限制。
- Twitter/X：账号、权限、限额与 SDK 示例。

对应文档：
- `REDDIT_API_SETUP.md`
- `REDDIT_API_LIMITS.md`
- `TWITTER_API_SETUP.md`

## 3. 采集（Collection / Ingest）

### 3.1 采集主流程

主流程覆盖：
- 市场/政策/社交等入口接收
- 适配器选路
- 去重匹配与更新/插入
- 同步或异步任务化执行
- 任务历史与状态可追踪

对应文档：
- `INGEST_ARCHITECTURE.md`
- `UNIFIED_COLLECT_ARCHITECTURE.md`
- `INGEST_CHAIN_EVIDENCE_MATRIX_2026-03-01.md`

### 3.2 数据源与资源库

采集前置能力由来源库驱动：
- Item 负责“来源集合”定义。
- Channel 负责“可访问性适配”。
- Resource pool 负责 URL 资源沉淀、提取与捕获。

对应文档：
- `INGEST_DATA_SOURCES.md`
- `RESOURCE_LIBRARY_DEFINITION.md`
- `RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md`
- `RESOURCE_POOL_EXTRACTION_API.md`

### 3.3 质量与可追溯机制

采集质量关键保障点：
- 文档去重：URI 优先，text_hash 兜底。
- 日期提取：URL/HTML/Header/Text 多层策略。
- 政策可视化统计口径与实时性校验。

对应文档：
- `文档去重逻辑说明.md`
- `日期提取与修复总览.md`
- `政策可视化数据校验与实时性说明.md`

### 3.4 社交流程迁移状态

当前状态结论：
- `social.py` 尚未完全进入统一 `collect_runtime` 骨架。
- 已有 display_meta 兼容与任务展示过渡，但不等于迁移完成。
- 后续 Phase 6 需以“协议统一、平台差异留在适配器层”为原则。

对应文档：`COLLECT_RUNTIME_SOCIAL_PHASE2_NOTE.md`

### 3.5 采集任务范式参考

`数据摄取内容.md` 提供了跨社交、政策、竞品、投资、伦理等任务模板（草稿级），可作为采集编排参考输入，不应直接视作已产品化接口契约。

## 4. 路线图（Roadmap）

### 4.1 已有阶段材料

当前阶段化文档覆盖：
- Phase 2：Docker 环境最小验收（ingest config）
- Phase 5：LLM+符号化最小可行方案
- Ingest Chain：project_key 策略、可观测性、基线测试、租户初始化修复

对应文档：
- `PHASE2_VERIFICATION.md`
- `PHASE5_LLM_SYMBOLIZATION_MVP.md`
- `INGEST_CHAIN_TASKBOARD_2026-03-01.md`
- `INGEST_CHAIN_EVIDENCE_MATRIX_2026-03-01.md`

### 4.2 中长期技术改造轨道

已定义的重点演进方向：
- Unified Search 最小增强（URL 过滤、RSS 解析、sitemap 递归、source_ref 写回）。
- 数字数据同构化（Core NumericFact + 子项目扩展）。
- 彩票领域耦合下沉与主干通用化。

对应文档：
- `UNIFIED_SEARCH_ENHANCEMENT_PLAN.md`
- `NUMERIC_DATA_HOMOGENIZATION_ROADMAP.md`
- `LOTTERY_DECOUPLING_INVENTORY.md`

### 4.3 文档治理状态

文档侧已经形成：
- 主文档 + archive 分主题归档
- 已有合并计划与执行记录
- 但仍存在分散入口较多的问题（本合并稿用于降低阅读成本）

对应文档：
- `DOC_MERGE_PLAN.md`
- `README.md`
- `index.md`

## 5. 当前综合结论

1. 后端主干已具备统一 API 契约、多租户上下文治理与可观测增强基础。
2. 采集链路在资源库化、统一运行时、质量治理上已有清晰方向，但社交统一执行通道尚在过渡期。
3. 路线图材料齐全，当前瓶颈主要在跨文档认知成本与阶段改造落地节奏，而非缺少方案。

## 6. 源文件映射表（Source Mapping）

| Source File | Section | Usage in This Merge |
|---|---|---|
| `README.md` | 路线图/文档治理 | 目录分组与阅读路径基线 |
| `index.md` | 路线图/文档治理 | 文件来源索引基线 |
| `DOC_MERGE_PLAN.md` | 路线图/文档治理 | 合并与归档策略依据 |
| `接口层调查文档.md` | 架构/API | 接口分层、模块职责与路由结构 |
| `API_CONTRACT_STANDARD.md` | API | 统一响应与错误契约 |
| `API_ROUTE_INVENTORY_2026-02-27.md` | API | 路由总量与模块分布依据 |
| `FRONTEND_MODERNIZATION_API_MAP_2026-02-27.md` | API | 前端换栈最小接口集合 |
| `INGEST_ARCHITECTURE.md` | 架构/采集 | 摄取分层与主流程骨架 |
| `UNIFIED_COLLECT_ARCHITECTURE.md` | 架构/采集 | 横向/纵向统一采集设计 |
| `COLLECT_RUNTIME_SOCIAL_PHASE2_NOTE.md` | 架构/采集 | social 通道迁移边界与验收条件 |
| `INGEST_DATA_SOURCES.md` | 采集 | 数据源分类与选型建议 |
| `RESOURCE_LIBRARY_DEFINITION.md` | 采集 | item/channel/source_collection 定义 |
| `RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md` | 采集/路线图 | 资源库分 phase 实施计划 |
| `RESOURCE_POOL_EXTRACTION_API.md` | 采集/API | resource pool 提取/捕获接口设计 |
| `文档去重逻辑说明.md` | 采集 | URI/text_hash 去重策略说明 |
| `日期提取与修复总览.md` | 采集 | 发布日期提取策略与效果 |
| `政策可视化数据校验与实时性说明.md` | 采集 | 政策统计一致性与实时性结论 |
| `数据摄取内容.md` | 采集 | 任务清单草稿与采集维度参考 |
| `数据库说明文档.md` | 架构/API | PostgreSQL 表结构与 JSONB 模型 |
| `政策数据结构说明.md` | 架构/API | 政策结构化字段规范 |
| `社交平台图谱生成标准文档.md` | 架构 | 图谱系统标准与架构 |
| `社交平台内容图谱API.md` | API/架构 | 社交图谱接口、模型、导出能力 |
| `STRUCTURED_VS_GRAPH_ALIGNMENT.md` | 架构 | 结构化与图谱字段对齐差异 |
| `REDDIT_API_SETUP.md` | API/采集 | Reddit 接入方式与配置 |
| `REDDIT_API_LIMITS.md` | API/采集 | Reddit 端点与参数限制 |
| `TWITTER_API_SETUP.md` | API/采集 | Twitter/X 接入流程 |
| `INGEST_CHAIN_TASKBOARD_2026-03-01.md` | 路线图 | ingest 链路任务状态与 follow-up |
| `INGEST_CHAIN_EVIDENCE_MATRIX_2026-03-01.md` | 路线图 | 变更证据、测试、隔离验证 |
| `PHASE2_VERIFICATION.md` | 路线图 | Phase 2 验收步骤 |
| `PHASE5_LLM_SYMBOLIZATION_MVP.md` | 路线图 | LLM+规则化 MVP 设计 |
| `UNIFIED_SEARCH_ENHANCEMENT_PLAN.md` | 路线图 | unified-search 增强顺序 |
| `NUMERIC_DATA_HOMOGENIZATION_ROADMAP.md` | 路线图 | 数字事实同构化中长期计划 |
| `LOTTERY_DECOUPLING_INVENTORY.md` | 架构/路线图 | 彩票特化耦合点与迁移目标 |

---

如需继续收敛，可在下一轮将本文件拆成：
- `backend-architecture.md`
- `backend-api-baseline.md`
- `backend-ingest-operations.md`
- `backend-roadmap-status.md`

并将本文件保留为 1 页总览。
