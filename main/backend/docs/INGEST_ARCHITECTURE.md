# 数据摄取架构

## 1. 文档定位

本文件整合摄取流程图与流程深度分析，作为数据摄取架构的主文档。


**相关文档**：信息资源库（item/channel、来源字段、URL→Channel 路由）见 `RESOURCE_LIBRARY_DEFINITION.md`。

## 2. 架构分层

```
API 层 (app/api/ingest.py) — 需 project_key，绑定项目 schema
  ↓
服务层 (app/services/ingest/) — 部分流程委托 subprojects/<key>/ 领域服务
  ↓
适配器层 (app/services/ingest/adapters/)
  ↓
数据模型层 (app/models/entities.py / PostgreSQL)
  ↓
索引层 (Elasticsearch, 部分流程)
```

## 3. 核心职责

### 3.1 现役 URL 与来源获取组合

直接 URL 的原入口 `ingest/url_pool.py::_run_source_library_frontdoor_ingress` 准备 `FrontDoorExecutionProtocol`、有效渠道和请求选项，然后调用 `source_library/orchestrators/url_execution.py::fetch_routed_targets`。正式来源入口仍由 resolver 解析条目与来源策略，再调用同一个获取核；直接 URL 不再创建 `*.single_url_compat` 伪来源条目。

获取核复用具名渠道叶子，保持 URL 展开、静态／渲染／crawler 选择、参数注入、回退及 collect-only 结果。直接 URL 完成获取后仍只调用一次原 postprocess；Material 写入、去重及项目事务归原 writer。候选、已取得正文、队列 ACK 与已入库 Material 分开观察。

站内搜索的 frontdoor 与 handler-cluster adapter 共用 `fold_search_observations` 聚合候选、diagnostics、review queue 和错误。frontdoor 去重错误消息并显式 fetch；adapter 保留重复错误及原 pool／auto-ingest 尾部。两条交付链的权限和失败并未合并。

耐久 URL 操作沿 installed operation 与 RuntimeNode 执行。URL 工具读回调用 `composition/url_pool_readback.py::read_url_pool_evidence`，使用 capability 的精确版本关联核对 request、outcome 与 Material 的实际来源 URL；UNKNOWN 结果和已保存版本保留只读观察。Cell、Runtime journal、领域 writer 各自拥有原身份与事实，读回组合没有写权限。

### 3.2 市场数据流程职责

- API 层：参数校验、同步/异步执行选择、任务响应包装
- 服务层：采集流程编排、去重/匹配、入库与任务日志
- 适配器层：访问外部网站/API，解析 HTML/JSON，输出标准记录
- 数据模型层：持久化 `MarketStat` / `Document` / `EtlJobRun`
- 索引层：政策文档等进入搜索索引（按流程触发）

## 4. 市场数据摄取流程（核心链路）

1. 接收请求（`state/game/source_hint/limit`）
2. 选择适配器（按州/游戏/来源）
3. 调用 `adapter.fetch_records()`
4. 遍历 `MarketRecord`
5. 校验日期（无日期记录跳过）
6. `_get_existing()` 去重/匹配
7. `_update_existing()` 或新建记录
8. 提交事务并记录任务状态

## 5. 适配器选择逻辑（概要）

- `source_hint` 优先（例如 `legiscan`）
- 否则按 `state` 选择州级适配器
- 如指定 `game`，再过滤到特定游戏适配器

适配器类型：

- 网页抓取适配器（官网/页面抓取）
- API 适配器（结构化接口、通常更稳定）

## 6. 市场数据匹配与更新策略

### 6.1 当前原则

- 尽量按 `state + game + date` 匹配
- 兼容 `game=None` 的数据源输出
- 更新时优先“补空不覆盖”
- 元数据字段（来源、URI 等）可更新

### 6.2 主要风险

- `game=None` 在同日多游戏场景可能误匹配
- 某些适配器字段稀疏（仅日期/部分指标）
- 不同来源 `game` 命名口径不一致

### 6.3 改进方向

- 加入 `source_name/source_uri` 辅助匹配
- 基于 `jackpot/revenue` 等字段做相似度校验
- 给适配器增加数据完整度评分

## 7. 政策文档摄取流程（概要）

1. 选择政策适配器
2. 拉取文档列表
3. 按内容哈希（SHA256）去重
4. 创建/复用 `Source`
5. 插入 `Document`
6. 触发索引（按流程）

优点：

- 内容哈希去重可跨 URL 识别重复内容

限制：

- 对“内容相似但不完全相同”场景识别能力有限

## 8. 参数合并顺序（run_item_by_key）

当通过 `run_item_by_key` 执行来源采集时，最终请求参数按以下顺序合并（后者覆盖前者）：

1. `channel.default_params` — 通道默认参数
2. `item.params` — 来源项参数
3. `ingest_config` — 项目摄取配置（如 `social_forum` 的 payload）
4. `override_params` — 采集页传入的运行时覆盖参数

合并后传入 channel 适配器执行。

## 9. 同步/异步执行模式

- 同步：直接执行服务函数，适合小批量调试
- 异步：通过 `Celery` 任务执行，返回 `task_id`

建议生产环境默认优先异步，便于稳定性与可观测性。

## 10. 数据质量与可观测性建议

建议记录：

- 适配器成功率 / 失败率
- 抓取数 / 入库数 / 更新数 / 跳过数
- 缺失字段分布
- 数据新鲜度
- 多源冲突次数
