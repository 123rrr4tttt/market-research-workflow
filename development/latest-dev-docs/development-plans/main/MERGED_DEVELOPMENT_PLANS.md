# MERGED DEVELOPMENT PLANS

更新时间：2026-03-01 07:31:19 PST  
合并范围：`01`-`11` 号计划文档（含 `Ingest` 双份证据/看板的增量信息）

## 1. 合并原则与口径

- 本文作为执行主稿，按「阶段 -> 里程碑 -> 依赖」组织。
- `03/04` 与 `09/10` 属同主题，采用“以 `09/10` 为最新基线，补充 `03/04` 一致项”的方式合并。
- “状态同步/方向性文档”与“已落地证据文档”并存：状态用于排期，证据用于验收。

## 2. 阶段计划（Phase）

### Phase 0：基线与治理冻结（Week 1）

目标：先统一标准和交付边界，再推进功能改造。  
来源：`01` `02` `05` `08`

关键交付：
- 8.x 状态基线与 P0/P1/P2 任务映射（含 owner、验收口径）。
- 标准化主线（架构/API 契约/测试/配置迁移/可观测性/交付流程）落文档并进入 PR 模板。
- 文档体系收敛：主干文档 + archive 分层，减少重复报告。

退出标准：
- 标准文档可引用、评审模板可执行、后续变更有统一证据字段。

### Phase 1：Ingest 链路治理与项目隔离（Week 1-2）

目标：完成 `project_key` 策略化治理与可验证隔离。  
来源：`03` `04` `09` `10`

关键交付（当前已大部分完成）：
- 写路径策略：`warn -> require`（`ingest` + `source_library`）。
- 中间件观测：`X-Request-Id` / `X-Project-Key-*` 头与 fallback 告警日志。
- 合同扩展：`PROJECT_KEY_REQUIRED` 错误码与配置开关 `project_key_enforcement_mode`。
- 测试基线：
  - `test_project_key_policy_unittest.py`
  - `test_ingest_baseline_matrix_unittest.py`
  - `test_frontend_modern_entry_baseline_unittest.py`
- 实库验证：`demo_proj` 与 `iso_proj` 写隔离验证；新建项目初始化修复（本地 sequence 绑定）。

退出标准：
- 核心 ingest 入口在 `require` 模式下缺失 key 必失败、显式 key 必可通。
- DB 层无跨项目污染，且新租户初始化后可完成 raw import。

### Phase 2：资源库与统一搜索增强（Week 2-3）

目标：提高来源管理清晰度与 unified search 质量/可追溯性。  
来源：`06` `07`

关键交付：
- Resource Library 简化：Item 仅保留“来源 + 访问适配”，运行时参数统一下沉采集页或 ingest config。
- 新增/完善 `ingest_config`（结构配置 + API + 运行时注入）。
- Unified Search 最小增强四件套：
  - 候选 URL 过滤（同域、去 tracking、deny domains）
  - RSS/Atom 解析稳健化（namespace/CDATA/fallback）
  - sitemapindex 递归（深度/数量/去重限制）
  - `source_ref` 细粒度写回（`site_entry_url`、`entry_type`、`domain`）

退出标准：
- 来源配置、运行参数、搜索写回链路职责清晰且可回归验证。

### Phase 3：数字数据同构化（Week 2-6）

目标：建立 Core 与 Project Extension 双层数字事实体系。  
来源：`11`（并与 `01` 的 8.7 数据类型优化对齐）

关键交付：
- `NumericFact` 统一字段（`metric_code/subject/period/value/unit/scale/source_ref/confidence/raw_excerpt`）。
- 主链路双轨兼容（旧字段保留 + 新标准字段并行）。
- 质量工程：候选评分、低置信度重试、指标异常检测告警。
- 子项目扩展：命名空间 + 映射规则版本化，避免侵入主干。

退出标准：
- 核心 KPI 口径一致、可追溯字段覆盖率达标、子项目扩展与主干解耦。

### Phase 4：8.x 业务能力扩展闭环（Week 3+ 持续）

目标：推进 8.2-8.8 未闭环项，按最小可用逐步收口。  
来源：`01` `02`（并吸收前述 Phase 1-3 成果）

重点方向：
- 平台化工作流（模板/看板配置保存-读取-运行闭环）。
- 多源集成（含 Perplexity）与归因输出。
- 时间轴/实体演化查询与前端过滤。
- RAG + 报告生成最小闭环。
- 公司/商品/电商对象化采集-提取-看板联通。

退出标准：
- 每条 8.x 任务具备可重复验收动作与最小回归检查。

## 3. 里程碑（Milestones）

## M0（已完成）：计划与标准基线
- 完成状态盘点、并行分工、标准化方向、文档归档策略。

## M1（已完成）：Ingest Stage-1 治理
- `project_key` warn 策略、中间件观测、核心单测/矩阵测试落地。

## M2（进行中）：Ingest Stage-2 就绪
- 条件：客户端切换完成 + 存量库序列问题修复。
- 验收：`project_key_enforcement_mode=require` 可安全启用。

## M3（进行中）：资源库/统一搜索增强
- 完成 `ingest_config`、搜索过滤/解析/追溯增强并回归。

## M4（进行中）：数字事实层最小可用
- 完成核心链路标准化接入与兼容映射表。

## M5（待启动）：8.x 业务能力全面闭环
- 以 8.2-8.8 为主线完成平台化、多源、时间轴、RAG、对象化采集。

## 4. 依赖图（Dependencies）

`D1` 标准先行：`Phase 0 -> Phase 1/2/3/4`  
`D2` Ingest 强依赖：`M2(require)` 依赖客户端升级与历史序列修复。  
`D3` 搜索写回依赖：`source_ref` 扩展依赖 URL 过滤/RSS/sitemap 先稳定。  
`D4` 数字同构依赖：抽取标准化依赖搜索/采集质量提升，展示统一依赖 API 契约稳定。  
`D5` 业务扩展依赖：8.x 闭环依赖 Phase 1-3 的合同、隔离、质量基座。  

## 5. 当前执行优先级（合并后建议）

1. 完成 M2 前置：修复 `demo_proj` 序列/PK 状态，准备切 `require`。
2. 并行推进 M3（资源库+搜索增强）与 M4（数字事实层最小链路）。
3. 将 8.2/8.5/8.6 作为 M5 首批闭环对象，复用前述标准化成果。

## 6. 源文档映射

- `01_plans_status-8x-2026-02-27.md`
- `02_plans_8x-multi-agent-kickoff-2026-02-27.md`
- `03_plans_ingest-chain-evidence-matrix-2026-03-01.md`
- `04_plans_ingest-chain-taskboard-2026-03-01.md`
- `05_plans_project-standardization-development-directions-2026-03-01.md`
- `06_main_backend_docs_RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md`
- `07_main_backend_docs_UNIFIED_SEARCH_ENHANCEMENT_PLAN.md`
- `08_main_backend_docs_DOC_MERGE_PLAN.md`
- `09_main_backend_docs_INGEST_CHAIN_EVIDENCE_MATRIX_2026-03-01.md`
- `10_main_backend_docs_INGEST_CHAIN_TASKBOARD_2026-03-01.md`
- `11_main_backend_docs_NUMERIC_DATA_HOMOGENIZATION_ROADMAP.md`
