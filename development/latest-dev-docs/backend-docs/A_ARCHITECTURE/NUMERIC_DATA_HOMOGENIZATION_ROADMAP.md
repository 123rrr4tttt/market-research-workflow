# 数字数据同构化实施路线图（通用主干 + 子项目特型）

> 目标：把“数字信息”从散落字段升级为全流程可复用、可追溯、可治理的统一事实资产。

## 1. 背景与现状问题
- 当前项目已具备文档抽取、结构化落库、检索、可视化链路，但数字字段在不同路径中口径不统一。
- 关键痛点：
  - 同一指标在不同模块有不同字段语义（如增长率的 `ratio` vs `percent` 展示）。
  - 主干流程与子项目指标耦合过紧，专场景字段难以横向复用。
  - 数值缺少统一单位、时间、置信度、来源片段回溯元信息。
  - 抽取与搜索的候选质量控制不足，导致数字噪音和误差传播。

## 2. 设计目标（双层同构）

### 2.1 主干一般数据类（Core）
构建统一事实层 `NumericFact`，作为所有业务的通用数字主数据：
- 指标域：销售额/利润/成本/订单量/用户数/转化率/客单价/库存周转率/同比/环比等通用指标。
- 强制字段：
  - `metric_code`
  - `subject_id`（主体标识）
  - `period_start/period_end`（时间窗口）
  - `value`（标准化数值）
  - `unit` + `scale`（单位及倍数）
  - `source_ref`（文档/链接）
  - `confidence`（抽取置信度）
  - `raw_excerpt`（可溯源片段）

### 2.2 子项目特型数据类（Project Extension）
保留每个子项目的行业专属指标，不侵入主干：
- 每个子项目使用 `metric_code` 命名空间（如 `lottery.jackpot`, `supply.inventory_health`）。
- 通过映射规则向主干输出可转换字段（若存在对应映射）。
- 只在该子项目视图中默认展示，主干对齐时可按需选择是否透出。

## 3. 里程碑与阶段目标

### 3.0 Phase 0（第 1 周）：统一定义与一致性修复
1. 建立“数字事实主模型”草案（字段、单位、时间、质量字段）。
2. 统一增长率等高风险口径问题（`ratio` 与 `%`）。
3. 在现有 API 中明确“主干字段优先策略”，先做只读一致性修复。

#### 交付
- `NUMERIC_FACT_SCHEMA.md`（草案，后续可嵌入现有文档）
- 增长率展示与入库口径一致说明
- 一份“字段兼容映射清单”（现有字段 -> `metric_code`）

### 3.1 Phase 1（第 2-3 周）：数字事实层落地（最小可用）
1. 抽取器输出标准数字对象（至少包含 value/unit/period/metric_code/confidence）。
2. 为现有市场/通用信息链路引入字段标准化器（单位清洗、百分比、中文量词）。
3. 在关键链路并行保留旧字段，新增标准字段用于双轨兼容。
4. 在图表与报表侧改造为主干数字视图读取。

#### 交付
- 标准化抽取器模块
- `numeric_fact`（或等价视图）读写链路
- 旧字段兼容映射 + 回归风险清单

### 3.2 Phase 2（第 4-6 周）：搜索与采集质量工程化
1. 候选 URL 增加数字价值评分（关键词、可信域名、结构化信号、去噪）。
2. 抽取失败与低置信度样本重试机制（规则/模板优先，必要时 LLM fallback）。
3. 指标级异常检测（突变、单位异常、时间序列空洞）自动告警。

#### 交付
- 数字采集质量得分规则
- 失败重试与人工复核入口
- 数字异常告警机制（日报/周报）

### 3.3 Phase 3（第 7-10 周）：子项目特型并行扩展
1. 为每个子项目定义 `scope=project` 指标扩展模型。
2. 提供“主干<->特型”映射规则版本化管理。
3. 子项目新增指标先走扩展层，确认稳定后再评估是否上主干。

#### 交付
- 子项目指标清单与映射规则
- 项目层扩展数据展示页（追加卡片，不影响主干看板）
- 映射与冲突仲裁规则文档

## 4. 并行协作分工（多人并行）
- 架构代理
  - 负责模型边界、schema、指标目录治理。
  - 交付：`Metric Catalog`、数据流定义、映射规范。
- 执行代理 A（采集）
  - 负责搜索候选评分、抓取元信息、失败重试。
  - 交付：候选评分规则、数据源信誉表。
- 执行代理 B（抽取）
  - 负责标准化器与抽取后校验。
  - 交付：数值单位/比例标准化实现、抽取验证规则。
- 执行代理 C（存储/API）
  - 负责 `NumericFact` 落库/API 兼容。
  - 交付：事实层读写接口、兼容视图。
- 审核代理
  - 负责口径一致性、指标对账、验收标准。
  - 交付：验收报告与回归风险清单。

## 5. 文件级改造清单（建议）

### 数据模型与规范
- `main/backend/app/models/entities.py`
- `main/backend/app/services/extraction/models.py`
- `main/backend/docs/政策数据结构说明.md`

### 抽取与标准化
- `main/backend/app/services/extraction/extract.py`
- `main/backend/app/services/extraction/application.py`
- `main/backend/app/services/ingest/market_web.py`
- `main/backend/app/services/ingest/market.py`
- `main/backend/app/services/ingest/market adapters/*`

### 发现/搜索质量控制
- `main/backend/app/services/search/web.py`
- `main/backend/app/services/search/smart.py`
- `main/backend/app/services/search/hybrid.py`

### API 与展示统一
- `main/backend/app/api/market.py`
- `main/backend/app/api/dashboard.py`
- `main/backend/app/api/reports.py`
- `main/backend/app/api/search.py`
- `main/frontend/templates/market-data-visualization.html`
- `main/frontend/templates/data-dashboard.html`

## 6. 验收指标（建议）
- 统一指标可追溯率：`core` 事实层返回中 `source_ref + raw_excerpt` 覆盖率 100%。
- 数字一致性：同一 KPI 在主干展示与明细接口偏差 < 1%。
- 口径正确率：`ratio` 到 `%` 展示换算错差率为 0。
- 抽取质量：核心指标抽取成功率（含单位和时间）提升至少 20%。
- 告警覆盖：异常波动与单位异常触发率达到预设阈值并自动记录。

## 7. 风险与对策
- 风险：一次性改动过多导致下游接口震荡。
  - 对策：双轨发布（旧字段保留），以 `metric_code` 与 `scope` 做兼容。
- 风险：不同来源单位口径冲突。
  - 对策：`unit + scale + is_percent` 强约束，无法确定时降级人工复核。
- 风险：子项目扩展指标无法统一归一。
  - 对策：项目层独立命名空间与版本化映射表，逐步迁移。

## 9. 本次执行（主干 + 特型双轨）
- 已完成主干能力层：`main/backend/app/services/extraction/numeric.py`
  - 统一数值口径解析（支持单位/百分比/人民币/美元/中文量词）
  - 加入 `scope` + `data_class` 元数据（`core` / `project_extension`）
- 已完成主干链路接入：
  - 抽取：`main/backend/app/services/extraction/extract.py`
  - 采集：`main/backend/app/services/ingest/market_web.py`
  - 入库：`main/backend/app/services/ingest/market.py`（入库前标准化 + 质量归并）
  - 检索：`main/backend/app/services/search/web.py`（去 tracking + 数字相关度重排）
  - 图谱适配：`main/backend/app/services/graph/adapters/market.py`
- 子项目特型落地方式：以 `lottery.market` 作为 project scope，沿用同一口径，但独立打标签，不影响 core 通用字段。

## 8. 本周可执行最小计划（Sprint 0）
1. 修复增长率展示口径（ratio↔percent）并建立回归检查项。  
2. 定义 `NumericFact` 字段字典（含 `scope` 和 `metric_code`）。  
3. 在一个核心链路中完成标准化器接入（金额、比例、时间窗口）。  
4. 输出本路线图配套的“字段兼容映射表 v1.0”。  
