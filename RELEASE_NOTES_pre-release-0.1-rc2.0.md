# 预发布说明：v0.1-rc2.0（2026-03-02）

- 版本类型：`预发布（Pre-release）`
- 版本名称：`v0.1-rc2.0`
- 适用场景：开发联调、端到端流程验证、发布前回归

## 摘要

本版本聚焦“单 URL 优先采集 + 有意义内容门禁 + 图谱标准化输出 + 前后端联动补齐”。目标是将采集、处理、图谱、运维页面打通为可验证的开发版本闭环。

## 本次重点更新

### 1) Ingest 链路增强（单 URL 优先）

- 新增单 URL 采集相关能力，完善 ingest 入口分流与处理流程。
- 引入轻量过滤、脏数据复核与有意义内容门禁，降低低价值文档入库概率。
- URL 池策略与来源解析逻辑同步调整，提升可控性与可解释性。

### 2) 图谱能力升级（标准化与投影）

- 新增图谱映射与投影模块，统一节点展示语义与导出接口口径。
- 图谱导出器与文档类型映射更新，支持更稳定的结构化输出。
- 管理接口补充图谱标准化相关能力，便于批量治理与回放验证。

### 3) 后端 API 与任务编排补齐

- `admin / ingest / process / projects` 等接口扩展，覆盖新链路运行与运营场景。
- 任务服务与启动钩子更新，保证新能力在主流程中可调度、可观测。
- discovery/store 与 source library resolver 协同增强，减少链路分叉行为差异。

### 4) 前端联动更新（modern）

- `Ingest / Graph / Ops / Process / CrawlerManage` 页面适配新接口与新状态。
- 新增图谱节点卡片与扩展展示组件，提升图谱调试与运营可读性。
- API types/endpoints 与交互 hooks 同步更新，降低前后端契约偏差。

### 5) 测试与质量保障

- 新增与扩展单元、集成、核心业务测试，覆盖 meaningful gate、single URL、graph projection 等关键模块。
- 增加前端 e2e 用例（single URL ingest 方向），补齐主链路自动化检查。
- 标准化测试入口 `scripts/test-standardize.sh` 新增：
  - `external-smoke`（后端外部链路冒烟，docker compose）
  - `frontend-e2e`（前端 Playwright 回归）
- 本版本建议在合并前执行分层测试与关键页面冒烟。

### 6) development 文档同步（2026-03-02）

本次预发布说明与 `development/latest-dev-docs` 已对齐，重点纳入以下开发计划：

- 单 URL 优先采集分配方案（`CURRENT_DEV/2026-03-02-single-url-first-ingest-allocation-plan`）
- Source Time Window + Smart Timestamp 三段方案（`CURRENT_DEV/2026-03-02-source-time-window-smart-timestamp-plan`）
- 图谱节点 A→B 标准化方案（`CURRENT_DEV/2026-03-02-graph-node-standardization-a-then-b-plan`）
- 全局向量化通用基础方案（`CURRENT_DEV/2026-03-02-global-vectorization-general-foundation`）
- 标准化 ingest workflows 文档（`backend-core/main/STANDARD_INGEST_WORKFLOWS_2026-03-02.md`）

文档入口建议：

- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`
- `development/latest-dev-docs/development-plans/INDEX.md`

## 兼容性与注意事项

- 本版本为开发预发布，优先保证“闭环可验证”，不承诺长期稳定 API 形态。
- 个别实验性脚本与运行产物不纳入发布内容，发布时应保持工作区清洁。
- 若与旧文档口径冲突，以本说明与当前代码行为为准。

## 推荐回归清单（v0.1-rc2.0）

1. 单 URL 采集任务从提交到落库是否可完整跑通。
2. meaningless/dirty 内容是否被门禁策略正确拦截或标记。
3. 图谱页面是否可稳定展示新投影结果与节点信息卡片。
4. process/ops 页面是否能正确呈现新任务状态与统计信息。
5. 后端分层测试与前端关键 e2e 是否通过。

## 说明

- 本说明对应当前开发版本快照，不等同正式发布公告。
- 历史版本说明保留：
  - `RELEASE_NOTES_pre-release-0.md`
  - `RELEASE_NOTES_pre-release-0.9-rc2.0.md`
