# 消费侧模块化专项评估与推进方案（2026-03-14）

## 1. 目标

在 `frontdoor -> unified structured extraction -> normalizer -> compat -> writer` 主干已经开始落地之后，单独评估消费侧模块化问题，避免把“写入侧标准化”误判为“读取侧已经自然收敛”。

本专项只回答三件事：

1. 当前哪些消费模块仍直接依赖 `Document.extracted_data`
2. 哪些读取可通过 `document_views` facade 收口
3. 哪些读取本质上属于 SQL JSON 查询层，不能简单用 facade 代替

## 2. 结论

消费侧必须单独立项，不应继续附属于 ingest/frontdoor 计划。

当前消费侧不是单一问题，而是两类问题并存：

1. `Python 读取层`：在 API / graph / indexer / stats 中直接 `dict` 读取 `doc.extracted_data`
2. `SQL JSON 查询层`：在查询条件、排序、日期表达式中直接写 `Document.extracted_data["..."]`

这两层的治理方法不同：

1. `Python 读取层`
   - 适合通过 `main/backend/app/services/document_views/` 收口
   - 目标是减少散落读取、集中 fallback、稳定兼容字段
2. `SQL JSON 查询层`
   - 短期不能靠 facade 解决
   - 更合理的方向是单独抽成 query helpers / predicate builders

## 3. 调查范围

本次调查覆盖：

1. `main/backend/app/api`
2. `main/backend/app/services/graph`
3. `main/backend/app/services/indexer`
4. `main/backend/app/services/stats`

重点核查：

1. 是否直接读取 `doc.extracted_data`
2. 是否直接使用 `Document.extracted_data["..."]` 参与 SQL 过滤/排序
3. 是否已经接入 `document_views`

## 4. 当前状态

### 4.1 已开始走 facade 的模块

以下模块已经部分或大体完成“读取 facade 化”：

1. [main/backend/app/services/graph/adapters/policy.py](../../../../../main/backend/app/services/graph/adapters/policy.py)
2. [main/backend/app/services/graph/adapters/market.py](../../../../../main/backend/app/services/graph/adapters/market.py)
3. [main/backend/app/services/graph/adapters/reddit.py](../../../../../main/backend/app/services/graph/adapters/reddit.py)
4. [main/backend/app/services/graph/adapters/generic.py](../../../../../main/backend/app/services/graph/adapters/generic.py)
5. [main/backend/app/services/graph/adapters/__init__.py](../../../../../main/backend/app/services/graph/adapters/__init__.py)
6. [main/backend/app/services/indexer/policy.py](../../../../../main/backend/app/services/indexer/policy.py)
7. [main/backend/app/api/policies.py](../../../../../main/backend/app/api/policies.py)

现状判断：

1. graph adapters 已主要通过 `document_views` 或同类读取函数消费结构化数据
2. policy indexer 已把主要 Python 读取收敛到 `get_extracted_data(...)`
3. `api/policies.py` 已把响应组装部分迁到 facade，但 SQL JSON 查询仍保留原样

### 4.2 仍高度依赖原始 JSON 的模块

高风险模块：

1. [main/backend/app/api/admin.py](../../../../../main/backend/app/api/admin.py)
2. [main/backend/app/api/dashboard.py](../../../../../main/backend/app/api/dashboard.py)

中风险模块：

1. [main/backend/app/services/stats/prompt_time_density.py](../../../../../main/backend/app/services/stats/prompt_time_density.py)
2. [main/backend/app/api/policies.py](../../../../../main/backend/app/api/policies.py)

低风险模块：

1. [main/backend/app/services/graph/backfill_graph_nodes.py](../../../../../main/backend/app/services/graph/backfill_graph_nodes.py)
2. graph adapters
3. policy indexer

## 5. 读取点分类

### 5.1 可通过 facade 收口的 Python 读取

这类读取发生在查询结果返回后，对 `doc.extracted_data` 做字典访问、fallback、聚合、响应组装。

典型模块：

1. [main/backend/app/api/dashboard.py](../../../../../main/backend/app/api/dashboard.py)
   - 情感分布
   - 平台分布
   - trend 聚合前的数据提取
   - keyword / topic / sentiment_tags 汇总
2. [main/backend/app/api/admin.py](../../../../../main/backend/app/api/admin.py)
   - 列表项字段组装
   - topic / relation / graph 相关计算输入
   - 文档详情的结构化字段回显
3. [main/backend/app/services/stats/prompt_time_density.py](../../../../../main/backend/app/services/stats/prompt_time_density.py)
   - `prompt_group`
   - `source_domain`
   - 一部分策略输入字段读取
4. [main/backend/app/api/policies.py](../../../../../main/backend/app/api/policies.py)
   - 已部分迁移，仍可继续扩展 facade 覆盖面

这一类问题的治理方式：

1. 统一新增 `policy_view / market_view / social_view / common_view`
2. 所有 Python 层读取尽量不再直接写 `doc.extracted_data.get(...)`
3. 把 fallback 规则固定在 facade 内，而不是散落在消费逻辑里

### 5.2 暂不能由 facade 解决的 SQL JSON 查询

这类读取发生在数据库查询表达式中，本质上是 JSONB predicate / sort / cast 问题。

典型模块：

1. [main/backend/app/api/admin.py](../../../../../main/backend/app/api/admin.py)
   - `platform`
   - `sentiment.sentiment_orientation`
   - `policy.state`
   - `policy.policy_type`
   - `market.state`
   - `market.game`
   - `market.report_date`
   - `company_structured/product_structured/operation_structured`
   - `entities_relations`
2. [main/backend/app/api/dashboard.py](../../../../../main/backend/app/api/dashboard.py)
   - `Document.extracted_data.isnot(None)` 等存在性判断
3. [main/backend/app/api/policies.py](../../../../../main/backend/app/api/policies.py)
   - `policy.state`
   - `policy.policy_type`
   - `policy.effective_date`
4. [main/backend/app/services/stats/prompt_time_density.py](../../../../../main/backend/app/services/stats/prompt_time_density.py)
   - `_policy_effective_date_expr`
   - JSON 文本转日期的 cast / regex 逻辑

这一类问题的治理方式：

1. 不要强行塞进 facade
2. 后续单独提取成 `query_builders` / `predicate_helpers`
3. 保持数据库侧过滤能力与性能语义不变

## 6. 当前消费侧结构风险

### 6.1 风险一：读取和查询层耦合

当前很多文件同时包含：

1. SQL 条件构建
2. `doc.extracted_data` 的 Python 读取
3. API 输出结构拼装

结果是同一文件同时承担“查询层”和“视图层”，难以局部标准化。

### 6.2 风险二：fallback 规则散落

同一种业务语义在不同文件中常有不同 fallback 规则。例如：

1. `platform` 有时取 `extracted_data.platform`
2. `state` 有时取 `doc.state`，有时取 `extracted_data.policy.state`
3. `entities` 有时读 `entities_relations.entities`，有时读顶层 `entities`

这种差异会导致：

1. 兼容行为不稳定
2. 相同文档在不同消费端展示不同结果
3. 后续 contract 升级时无法统一替换

### 6.3 风险三：admin 兼具“治理入口”和“消费入口”

[main/backend/app/api/admin.py](../../../../../main/backend/app/api/admin.py) 既提供结构化数据回填/覆盖能力，也承担大量读取与查询功能。

因此它不是普通消费方：

1. 一部分路径是治理工具，不应完全 facade 化
2. 一部分路径是读取接口，适合 facade 化

这里需要显式拆开，而不是一次性整文件重构。

## 7. 推荐模块边界

### 7.1 读取 facade 层

建议继续扩展：

1. `main/backend/app/services/document_views/common_view.py`
2. `main/backend/app/services/document_views/policy_view.py`
3. `main/backend/app/services/document_views/market_view.py`
4. `main/backend/app/services/document_views/social_view.py`

职责：

1. 统一从 `doc.extracted_data` 提取业务字段
2. 统一 fallback
3. 统一兼容字段读取
4. 仅做“读”，不承担写入、回填、DB predicate

### 7.2 查询 helper 层

建议后续新增：

1. `main/backend/app/services/document_queries/policy_filters.py`
2. `main/backend/app/services/document_queries/market_filters.py`
3. `main/backend/app/services/document_queries/social_filters.py`

职责：

1. 统一 SQL JSON path
2. 统一存在性判断
3. 统一日期 cast / 文本规范化表达式
4. 避免在 `api/admin.py`、`api/dashboard.py`、`api/policies.py` 中继续散写 SQL JSON 片段

## 8. 推荐迁移顺序

### Phase C-1：冻结消费者读取契约

目标：

1. 固化 `policy/market/social/common` 四类 view 暴露字段
2. 明确哪些字段仍是 compat 字段
3. 明确哪些字段只允许在 facade 内解析

### Phase C-2：先迁 Python 读取层

优先级：

1. [main/backend/app/api/dashboard.py](../../../../../main/backend/app/api/dashboard.py)
2. [main/backend/app/api/admin.py](../../../../../main/backend/app/api/admin.py)
3. [main/backend/app/services/stats/prompt_time_density.py](../../../../../main/backend/app/services/stats/prompt_time_density.py)

策略：

1. 先不碰 SQL where / order by
2. 先把响应组装、聚合输入、topic/entity/sentiment 读取迁到 facade
3. 保证接口响应不变

### Phase C-3：抽 SQL JSON 查询 helper

优先级：

1. `policy`
2. `social`
3. `market`

策略：

1. 提取复用的 predicate builders
2. 收敛重复 JSON path
3. 保持 SQL 语义与现有行为一致

### Phase C-4：收口 admin 特殊路径

专门拆分：

1. `治理类接口`
   - 手动回填
   - 批量合并
   - 重跑抽取
2. `消费类接口`
   - 列表
   - 筛选
   - 图谱读取
   - 统计读取

只有消费类接口进入 facade / query helper 主线。

## 9. 原子任务建议

### AT-C-01 冻结 consumer read contract

- 目标：固化 `document_views` 的对外读取字段
- 输入：当前 graph/indexer/api/stats 的读取口径
- 输出：`common/policy/market/social` view 字段清单
- 验收：新增消费逻辑不再直接发明新的顶层 JSON 读取路径

### AT-C-02 dashboard Python 读取 facade 化

- 目标：收口 `dashboard.py` 中逐文档 JSON 读取
- 输入：情感、平台、关键词、topic 统计逻辑
- 输出：dashboard 改走 `document_views`
- 验收：接口返回结构和统计结果保持一致

### AT-C-03 admin 消费读取 facade 化

- 目标：只迁移 `admin.py` 中消费类读取逻辑
- 输入：列表、详情、图谱输入、topic/relations 读取
- 输出：消费读取与响应组装不再散落直读 JSON
- 验收：治理类接口不受影响

### AT-C-04 stats Python 读取 facade 化

- 目标：收口 `prompt_time_density.py` 的 Python 层字段读取
- 输入：`source_domain`、`prompt_group` 等逻辑
- 输出：stats 读取兼容规则集中化
- 验收：策略输出与当前一致

### AT-C-05 query helper 抽离

- 目标：统一 SQL JSON 查询表达式
- 输入：`admin.py`、`policies.py`、`prompt_time_density.py`
- 输出：`document_queries/*`
- 验收：查询行为不变，重复 JSON path 显著下降

## 10. 测试建议

### 10.1 facade 单测

覆盖：

1. `policy_view`
2. `market_view`
3. `social_view`
4. `common_view`

断言：

1. compat fallback 正常
2. `entities_relations -> entities/relations` 映射稳定
3. 缺失字段时返回值稳定

### 10.2 consumer regression tests

最小集合：

1. `dashboard` 统计接口
2. `admin` 列表/详情接口
3. `policies` 列表/详情接口
4. `prompt_time_density` 时间窗口统计

### 10.3 SQL predicate regression tests

重点断言：

1. 缺失字段
2. 空 JSON
3. 嵌套空对象
4. 非法日期字符串
5. `policy/market/sentiment` 混合存在时的筛选行为

## 11. 与 frontdoor/ingest 主线的关系

消费侧专项与前面的 frontdoor/ingest 改造是串联关系，不是同一层工作。

关系应定义为：

1. 写入侧主线
   - `ingress adapters`
   - `postprocess frontdoor`
   - `unified structured extraction`
   - `terminal normalizer`
   - `terminal_compat`
   - `terminal_writer`
2. 消费侧主线
   - `document_views`
   - `document_queries`
   - `graph/indexer/api/stats`

也就是说：

1. 写入侧负责“写得一致”
2. 消费侧负责“读得一致”

两者都做完，结构化服务模块化才算闭环。

## 12. 一句话结论

当前消费侧最该做的不是继续扩 writer，而是把 `dashboard/admin/stats` 的 Python 读取层先 facade 化，再把 SQL JSON 查询层独立抽象。
