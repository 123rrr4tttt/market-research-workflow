# Source Library 搜索参数修复计划（2026-03-12）

## 1. 目标

统一来源库搜索参数语义，覆盖四类关键参数并保证在三分入口下行为一致：

1. 最大搜索数目（`max_items/limit/per_keyword_limit/max_candidates/ingest_limit`）
2. 页数（`page/page_size/max_pages`）
3. 时间窗（`days_back/date_from/date_to/start_offset`）
4. 关键词记录（`query_terms` 历史落库一致性）

## 2. 当前缺口

1. `max_items` 未在来源库主链统一映射，部分链路只识别 `limit`。
2. `site_search` 的 search template 实际固定 `page=1`，缺少多页抓取策略。
3. 时间窗参数主要在 `search.market` 生效，`protocol_search/site_search` 基本未统一承接。
4. 关键词历史虽可记录，但 reddit 等链路记录的是 `subreddit`，与用户搜索词不一致。

## 3. 统一参数契约（修复后）

约定统一运行时参数结构（入口可兼容旧字段）：

- `query_terms: string[]`
- `max_items: int`（全局目标产出上限）
- `per_keyword_limit: int`（每关键词候选上限）
- `max_candidates: int`（候选 URL 上限）
- `ingest_limit: int`（落库上限）
- `page: int`
- `page_size: int`
- `max_pages: int`
- `days_back: int | null`
- `date_from: YYYY-MM-DD | null`
- `date_to: YYYY-MM-DD | null`
- `start_offset: int | null`

优先级（高 -> 低）：

1. 用户运行时 `override_params`
2. `ItemResolver` 推导值
3. item.params
4. channel.default_params

## 4. 原子任务清单（04）

### AT-01 参数归一层（已完成）

- 目标：在 `ItemResolver` 增加 `_normalize_search_params(...)`，统一别名参数。
- 输入：`run_item_payload` 合并后的 `params`。
- 输出：标准字段（`query_terms/max_items/ingest_limit/page/page_size/max_pages/days_back/date_*`）。
- 验收：`execution_request.params` 可见归一后的快照。

### AT-02 三分入口映射（已完成）

- 目标：归一参数在 `protocol_search/provider_harvest/site_search/url_execution` 统一可见。
- 输入：`resolver.run_item_payload` 的 `params`。
- 输出：前门协议与执行请求快照同步标准参数。
- 验收：四类入口不再依赖单一别名（仅 `limit`/`keywords`）。

### AT-03 page/max_pages 生效（已完成）

- 目标：`search_template` 支持从 `page` 开始抓取 `max_pages` 页。
- 输入：`item.params/override_params` 中的 `page/max_pages/page_size`。
- 输出：多页候选合并去重后再进入 `select_search_candidates`。
- 验收：`site_search` 不再固定 `page=1`。

### AT-04 market 适配器补参（已完成）

- 目标：`market` adapter 透传时间与分页参数。
- 输入：`max_items/provider/language/start_offset/days_back`。
- 输出：`collect_market_info(...)` 接收并执行对应参数。
- 验收：市场链路可观测 `days_back/start_offset` 生效。

### AT-05 关键词历史语义修复（已完成）

- 目标：关键词历史统一记录用户搜索词，不混淆来源标识。
- 输入：各入口 `query_terms` 与落库元数据。
- 输出：`keyword_history` 语义一致。
- 验收：reddit 等来源不再以 `subreddit` 代替用户搜索词。

### AT-06 契约校验与回归（已完成本轮最小集）

- 目标：为本轮改动补充最小回归测试。
- 输入：`resolver`、`unified_search`、`market adapter`。
- 输出：新增/更新单测覆盖关键参数行为。
- 验收：新增单测通过，现有相关单测不回归。

## 5. 验收标准

1. 同一请求在不同入口不会因别名字段导致行为漂移。
2. `site_search` 支持 `max_pages>1` 的多页候选合并。
3. `market` 链路可观察到 `days_back/start_offset` 生效。
4. 关键词历史中 `keyword` 字段与用户输入搜索词一致。

## 6. 涉及文件

- `main/backend/app/services/source_library/resolver.py`
- `main/backend/app/services/resource_pool/unified_search.py`
- `main/backend/app/services/source_library/adapters/market.py`
- `main/backend/app/services/ingest/news.py`
- `main/backend/app/services/ingest/single_url.py`
- `main/backend/tests/unit/test_source_library_resolver_unittest.py`
- `main/backend/tests/unit/test_ingest_source_search_contract_unittest.py`
- `main/backend/tests/core_business/test_source_library_core_contract.py`

## 6.1 本轮已改动文件（AT-01/02/03/04/06）

- `main/backend/app/services/source_library/resolver.py`
- `main/backend/app/services/resource_pool/unified_search.py`
- `main/backend/app/services/source_library/adapters/market.py`
- `main/backend/tests/unit/test_source_library_resolver_unittest.py`
- `main/backend/tests/unit/test_resource_pool_unified_search_unittest.py`
- `main/backend/tests/unit/test_source_library_market_adapter_unittest.py`
- `main/backend/app/services/ingest/news.py`
- `main/backend/tests/unit/test_ingest_news_reddit_terms_unittest.py`

## 7. 时间参数适配（对齐 2026-03-12 文档 05/06）

本节用于对齐：

1. `2026-03-12-time-semantics-density-merged-plan/05_*`（时间语义与密度主报告）
2. `2026-03-12-time-semantics-density-merged-plan/06_*`（原子任务单）
3. 当前来源库三分入口与参数修复现状（2026-03-12）

### 7.1 时间参数统一口径

运行时统一时间参数（入口可兼容别名）：

- `time_window: Nd | null`（如 `7d/30d/90d`，优先用于统计与调度）
- `start_time: YYYY-MM-DD | null`
- `end_time: YYYY-MM-DD | null`
- `days_back: int | null`
- `date_from: YYYY-MM-DD | null`
- `date_to: YYYY-MM-DD | null`
- `start_offset: int | null`（搜索分页起点，不等同时间）

归一规则：

1. 若 `start_time/end_time` 给定，则优先使用绝对时间范围。
2. 否则若 `time_window` 给定，按锚点时间推导绝对范围。
3. 否则若 `days_back` 给定，推导 `date_from/date_to`。
4. 若三者均缺失，则走入口默认时间策略（保留当前行为）。

### 7.2 三分入口映射（时间维）

1. `protocol_search`
- 入参接收：`time_window/start_time/end_time/days_back/date_from/date_to/start_offset`
- 透传目标：协议适配器（market/news/reddit 等）
- 说明：`start_offset` 仅用于搜索分页；时间过滤由 `time_window/date_*` 决定

2. `provider_harvest`
- 入参接收：`time_window/start_time/end_time/days_back/date_from/date_to`
- 透传目标：固定刷新提供商采集器
- 说明：provider 不支持绝对时间时，降级为 `days_back` 或 provider 默认窗口

3. `site_search`
- 入参接收：`time_window/start_time/end_time/days_back/date_from/date_to/page/page_size/max_pages`
- 透传目标：`handler.cluster -> unified_search -> crawler/url_execution`
- 说明：site_search 必须支持“多页 + 时间窗”联合约束，避免只跑 `page=1`

4. `url_execution`
- 入参接收：`time_window/start_time/end_time`（可选）
- 透传目标：单 URL 抓取与写入元数据
- 说明：不做搜索过滤，但写入 `source_time/effective_time` 相关元信息

### 7.3 与 05/06 的对齐点（本期必须）

1. 对齐 `05` 的统一时间语义目标：
- 采集侧统一可接收 `time_window/start/end`，并可回溯到 `effective_time` 口径。

2. 对齐 `06` 的原子任务拆解：
- 在参数层先完成“时间参数可传、可观测、可回放”；
- 算法层（density cloud / overlap / shift）后续在 stats 与调度侧逐步接入。

3. 现阶段边界：
- 本文档先落“时间参数适配”与“采集链透传”；
- 不在本任务内要求完成 `density_cloud` 算法上线。

### 7.4 服务链路（时间参数）

1. 用户请求
- `api/ingest` 或 `api/source_library` 接收 `override_params`

2. 来源库前门
- `source_library.resolver._resolve_execution_request(...)`
- 归一 `time_window/start/end/days_back/date_*`

3. 三分执行
- `protocol_search -> run_channel(adapter)`
- `provider_harvest -> run_channel(provider adapter)`
- `site_search -> handler.cluster -> unified_search -> crawler/url_execution`

4. 入库与统计
- 文档写入 `publish_date/source_time/effective_time`（按现有能力逐步补齐）
- `stats/prompt-time-density*` 继续消费时间范围；后续扩展 cloud/priority 参数

### 7.5 当前实现状态（2026-03-12）

1. 已接入
- `days_back/start_offset` 在 market 搜索链可生效

2. 半接入
- `site_search` 已经通过 `handler.cluster + unified_search` 使用爬虫层，但时间参数未统一贯穿

3. 待接入
- `time_window/start_time/end_time` 在来源库三分入口的统一归一与透传
- `date_from/date_to` 到 site_search/crawler 的执行过滤
- 时间参数与 density 调度结果的闭环（策略回放）

### 7.6 验收补充（时间参数）

1. 相同 `time_window/start/end` 在 `protocol_search` 与 `site_search` 行为一致（允许 provider 能力差异导致结果量不同）。
2. `days_back` 与 `date_from/date_to` 互斥/优先级规则稳定且可追踪。
3. 调用结果回传 `execution_request` 必含最终生效的时间参数快照。
4. 关键回归场景：
- 仅 `days_back`
- 仅 `start_time/end_time`
- `time_window + max_pages`
- `start_offset + days_back`（分页与时间并存）

## 8. 完成状态（2026-03-12）

1. 已完成：`AT-01/AT-02/AT-03/AT-04/AT-05/AT-06`。
2. 待后续：无（本轮 04 范围内已闭环）。
