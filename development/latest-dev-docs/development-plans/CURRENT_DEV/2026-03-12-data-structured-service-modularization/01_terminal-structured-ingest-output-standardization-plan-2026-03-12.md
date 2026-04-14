# 末端结构化入库输出标准化方案（2026-03-12）

## 1. 目标

在“来源库三分入口”已收口到 `POST /api/v1/ingest/source-library/run` 的基础上，统一**送入结构化入库末端**的数据契约，避免不同来源链路各写一套 `Document.extracted_data` 形态。

本方案聚焦：

1. 统一写库末端契约（`Document` + `extracted_data` 最小字段集）
2. 统一链路行为（news/market/social/policy 四类来源）
3. 统一验收门禁（contract + integration + DB 抽样）

## 2. 现状结论（代码事实）

当前为“**部分标准化**”，不是“全量标准化”。

### 2.1 已标准化末端

`single_url` 末端写库已具备较稳定的统一字段：

- `structured_extraction_status`
- `structured_extraction_reason`（可选）
- `quality_score`
- `degradation_flags`
- `capability_profile`
- `http_status`
- `light_filter`

对应代码：`main/backend/app/services/ingest/single_url.py` 的 `_persist_single_url_document`。

### 2.2 未统一末端（绕开 single_url writer）

1. `market_web` 仍有直接 `Document(...)` 入库路径
2. `social`（reddit sentiment）仍直接 `Document(...)` 入库
3. `policy` 仍直接 `Document(...)` 入库（且结构化字段较少）

这三条路径导致 `extracted_data` 顶层 key 分布差异明显。

## 3. 统一目标契约（Terminal Ingest Contract v1）

## 3.1 适用范围

- 所有写入 `documents` 表的新记录（不区分来源入口）
- 包含：`source-library/run` 触发链路、直接 ingest 任务链路

### 3.2 Document 层最小约束

1. `doc_type` 必须通过 `normalize_doc_type` 归一
2. `uri` 必须为规范化 URL（可去 fragment）
3. 去重策略必须明确（`uri` 或 `text_hash` 至少一项）

### 3.3 extracted_data 层最小字段集

所有新写入文档必须包含以下字段（允许扩展，不允许缺失）：

1. `schema_version`（固定 `terminal.ingest.v1`）
2. `platform`（来源执行平台，如 `single_url`、`reddit`）
3. `source_ref`（最小含 `url` 或等价可追溯 locator）
4. `structured_extraction_status`（`ok|failed|skipped`）
5. `quality_score`（`0~100`）
6. `degradation_flags`（数组）
7. `ingestion_entrypoint`（如 `source_library.run`）
8. `source_mode`（`protocol_search|provider_harvest|site_search|url_execution`）

可选字段：

- `structured_extraction_reason`
- `http_status`
- `capability_profile`
- `light_filter`
- 业务扩展字段（如 `market/policy/sentiment/entities`）

## 4. 链路收敛策略

### 4.1 推荐主线

采用“单 writer”策略：

- 提取公共写库函数 `terminal_document_writer`（可先复用 `single_url` 逻辑）
- `market_web/social/policy` 改为调用统一 writer
- 对保留直写路径增加“补齐标准字段”适配层（过渡）

### 4.2 兼容策略

1. 历史记录不强制立即回填全量字段
2. 新写入必须满足 v1
3. 提供离线回填脚本，按批次补 `schema_version` 与核心字段

## 5. 原子任务清单（Doc-first）

### AT-11 统一契约定义

- 目标：固化 Terminal Ingest Contract v1
- 输入：本方案文档 + 当前 `single_url` 字段集
- 输出：契约文档 + 常量定义（后续代码）
- 验收：contract 测试可识别必填字段缺失

### AT-12 抽象统一 writer

- 目标：新增公共 writer 服务
- 输入：`single_url` 当前写库逻辑
- 输出：`Document` 统一写库入口（函数/服务）
- 验收：`single_url` 与至少 1 条其他链路共用该 writer

### AT-13 market/social/policy 迁移

- 目标：三条直写链路改走统一 writer
- 输入：现有链路写库点
- 输出：三链路末端字段口径一致
- 验收：DB 抽样 `structured_extraction_status` 缺失率显著下降

### AT-14 历史数据回填脚本

- 目标：为历史记录补齐最低契约字段
- 输入：`documents` 历史行
- 输出：幂等回填脚本
- 验收：重复执行结果稳定，无破坏性覆盖

### AT-15 门禁与观测

- 目标：新增测试与观测指标
- 输入：contract + integration + SQL 抽样
- 输出：闭环验证报告
- 验收：
  - 新写入样本中必填字段完整率 = 100%
  - 关键链路测试通过

## 6. 验收标准（封口口径）

满足以下条件可判定“末端结构化入库标准化完成（v1）”：

1. `source-library/run` 主链路写入全部满足 Terminal Ingest Contract v1
2. `market/social/policy/news` 四类来源至少各 1 条集成测试覆盖并通过
3. DB 抽样检查中，新写入记录的必填字段完整率 100%
4. 文档、索引、测试门禁已同步

## 7. 风险与边界

1. 不同来源天然字段差异较大，统一应限定在“最小公共契约”，避免过拟合
2. 历史数据回填需要批量节流，避免影响线上写入
3. 若后续引入 `NormalizedIngestEnvelope` 作为强约束，应在 v2 升级并保留 v1 兼容

## 7.1 关键策略补充：先冻结消费侧字段，对内先标准化

本轮改造建议采用“双速治理”：

1. 对外/对消费侧：冻结现有读取字段口径，短期不要求业务方跟着改 JSON 路径
2. 对内/对写入侧：先完成统一 contract、统一 writer、统一状态机
3. 对中间层：增加内部 facade/adapter，把内部标准结构映射回当前消费侧字段形态

这样做的原因很直接：

- 当前 API、indexer、graph、stats 对 `extracted_data` 的历史路径依赖较深
- 如果写入侧和消费侧同时重构，风险会显著放大
- 先把“新增不一致”止住，再逐步清理“历史不一致”，整体更稳

## 8. 深化判断：当前问题不只是“字段不一致”，而是“末端职责耦合”

结合现有代码，当前末端不一致主要来自 4 类耦合：

### 8.1 写库与抽取结果拼装耦合

- `single_url` 在 `_persist_single_url_document` 中补齐：
  - `structured_extraction_status`
  - `structured_extraction_reason`
  - `quality_score`
  - `degradation_flags`
  - `capability_profile`
  - `http_status`
  - `light_filter`
- `market_web/social` 则在各自流程内直接拼接：
  - `extraction_status`
  - `extraction_reason`
  - `extraction_error`
- `policy.py` 甚至仍存在仅写 `Document` 基础字段、不写 `extracted_data` 的路径

这意味着“抽取结果如何表达”与“文档如何落库”被绑在了各来源服务里，无法形成统一末端。

### 8.2 公共元数据与业务域数据耦合

当前 `extracted_data` 同时承载三类信息：

1. 末端公共元数据：如 `platform`、`quality_score`
2. 结构化抽取状态：如 `structured_extraction_status` / `extraction_status`
3. 业务域数据：如 `policy`、`market`、`sentiment`

由于没有命名分层，不同链路很容易把“公共元数据”和“业务域对象”混写在顶层。

### 8.3 入口上下文与末端契约耦合不足

仓库里已经存在 `NormalizedIngestEnvelope`，可表达：

- `ingestion_entrypoint`
- `source_locator`
- `input_kind`
- `content_format`
- `lineage_ref`
- `task_window`

但它当前主要停留在 digestion/scaffold 语义，尚未稳定进入 `Document.extracted_data` 的统一持久化流程。因此“入口信息已部分标准化，末端持久化却没有共用 contract”。

### 8.4 消费侧已隐式依赖历史字段形态

统一末端时不能只看写入侧，还要考虑读取侧：

- graph adapters 依赖 `extracted_data.platform`
- policy indexer 依赖 `source_domain/effective_time/keep_for_vectorization`
- 多个 API/统计逻辑直接读取 `extracted_data.policy.*`
- 市场/社媒适配器依赖 `market` / `sentiment`

因此不能简单“改成一个全新 JSON 结构”；必须采取“公共字段标准化 + 业务域对象保留兼容”的分层方案。

### 8.5 LLM 结构化能力已存在，但尚未被显式模块化

当前仓库里已经有一套独立的 LLM 结构化抽取链路：

- `services/extraction/application.py`
  - `ExtractionApplicationService`
  - 统一编排 `entities_relations/policy/market/sentiment/company/product/operation`
- `services/ingest/structured_extraction.py`
  - `extract_structured_enriched_safe`
  - 统一包装异常、空结果、抽取状态
- `services/extraction/service.py`、`services/extraction/extract.py`、`services/extraction/topic_extract.py`
  - 实现各类 domain extractor
- `services/llm/config_loader.py`、`services/llm/provider.py`
  - 负责 prompt/config/provider/model 装配

当前问题不在“缺少 LLM 抽取”，而在于：

1. 它还没有被放进 terminal 模块化架构中的正式层级
2. 抽取结果仍直接散落混入 `extracted_data`
3. 抽取版本、模型配置、prompt 配置没有成为稳定 contract
4. 不同入口对 include flags 和抽取调用时机仍是分散控制

因此这次方案里需要把 Unified Structured Extraction 明确纳入设计。

## 9. 推荐的模块化目标：三层末端架构

建议把“末端结构化”拆成 3 个可独立演进的服务层，而不是继续由各入口服务自行组装 `Document(...)`。

### 9.1 Layer A: Source Terminal Adapter

职责：

- 接住各来源链路的原始结果
- 只做来源特定字段映射
- 产出统一的“末端输入 DTO”

输入示例：

- `single_url` 页面抓取结果
- `market_web` 搜索/正文抓取结果
- `social` Reddit post
- `policy` provider item
- `raw_import` 原始导入记录

输出建议：`TerminalIngestPayload`

核心字段：

- `source_name`
- `source_kind`
- `doc_type`
- `title`
- `summary`
- `content`
- `uri`
- `publish_date`
- `text_hash`
- `source_metadata`
- `domain_payload`
- `extraction_outcome`
- `envelope`

注意：这一层不直接写 DB。

### 9.1B Layer A-2: Unified Structured Extraction Service

职责：

- 对 `TerminalIngestPayload` 中可抽取文本执行统一结构化抽取
- 编排 ER / policy / market / sentiment / company / product / operation 等子能力
- 统一抽取错误、空结果、fallback、抽取摘要
- 输出标准化的 `extraction_outcome`

建议它独立成层，而不是留在各入口里的原因：

- 它本质上不是来源 adapter，也不是 writer
- 它是“领域抽取能力编排层”
- 后续无论写入侧还是消费侧模块化，都需要复用它

建议输出模型：`TerminalExtractionOutcome`

核心字段：

- `status`
- `reason`
- `error`
- `extractor_version`
- `model_profile`
- `prompt_profile`
- `domains`
- `summary`

### 9.1C 2026-03-14 修正：Unified Structured 已与当前架构重叠

结合当前实现，这一层已经不是“未来独立层”的纯规划状态，而是已经部分落在现有 frontdoor 编排里：

- [unified_structured_extraction_service.py](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/ingest/unified_structured_extraction_service.py)
- [postprocess_frontdoor.py](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/ingest/postprocess_frontdoor.py)

代码事实是：

1. `postprocess_frontdoor` 已直接调用 `run_unified_structured_extraction()`
2. `run_unified_structured_extraction()` 只是对 `ExtractionApplicationService + structured_extraction.py` 的一层薄包装
3. 因此它与当前 frontdoor 编排在职责上已经出现重叠

据此，后续方向不应再是“继续把 Unified Structured 规划成长期并列模块”，而应改成：

1. 先迁移所有结构化调用入口到 frontdoor
2. 再修剪历史链路里的重复结构化调用
3. 等调用口径稳定后，再决定把这层并回 frontdoor 还是并回 extraction 主服务

### 9.2 Layer B: Terminal Contract Normalizer

职责：

- 将不同入口的 `TerminalIngestPayload` 规范化为统一 contract
- 补齐默认字段
- 统一状态枚举、字段名、版本号
- 保证 `extracted_data` 至少满足 v1/v2 契约

这一层应解决的关键问题：

1. `structured_extraction_status` 与 `extraction_status` 统一为一套字段
2. `source_library.run`、direct ingest、raw import 等入口统一 `ingestion_entrypoint`
3. 公共元数据与业务域对象分层
4. 历史消费者需要的字段保留兼容映射
5. 将 LLM 抽取结果稳定映射到 contract，而不是让上游自由决定最终 JSON 形态

### 9.3 Layer C: Terminal Document Writer

职责：

- `Source` 获取/创建
- `doc_type` 归一
- 去重策略执行
- `Document` 持久化
- 返回统一写库结果（`inserted/skipped/doc_id/reason`）

这一层只负责“写什么、怎么去重、如何落库”，不负责解释各来源的业务字段。

## 10. 建议的数据模型：不要继续平铺顶层 key

如果继续把所有字段平铺在 `extracted_data` 顶层，后续每增加一类来源都会继续污染契约。更稳妥的做法是引入固定命名分区。

### 10.1 推荐结构

```json
{
  "schema_version": "terminal.ingest.v2",
  "platform": "reddit",
  "source_ref": {
    "url": "https://example.com/x",
    "locator": "https://example.com/x"
  },
  "terminal": {
    "ingestion_entrypoint": "source_library.run",
    "source_mode": "provider_harvest",
    "input_kind": "url_driven_external",
    "content_format": "html",
    "lineage_ref": "job:123"
  },
  "extraction": {
    "status": "ok",
    "reason": null,
    "extractor_version": "llm.structured.v1",
    "model_profile": {
      "provider": "default",
      "model": "gpt-4o-mini"
    },
    "quality_score": 86,
    "degradation_flags": [],
    "http_status": 200,
    "capability_profile": {},
    "light_filter": {}
  },
  "domains": {
    "policy": {},
    "market": {},
    "sentiment": {}
  },
  "compat": {
    "policy": {},
    "market": {},
    "sentiment": {}
  }
}
```

### 10.2 为什么建议保留 `compat`

短期内，大量读取逻辑仍从顶层读取 `policy`/`market`/`sentiment`。因此过渡期建议：

1. `domains.*` 作为未来主结构
2. 顶层 `policy/market/sentiment` 继续保留或由 writer 自动镜像
3. 等消费侧改造完成后，再逐步废弃顶层兼容字段

这里再补一个更严格的原则：

- `compat` 不是给新业务继续直接依赖的长期主结构
- `compat` 的职责是“冻结对外字段，屏蔽内部重构”
- 所有新增写入逻辑应优先面向内部标准结构，再由 facade/mapper 生成兼容字段

如果当前不想上 v2 结构，也至少应在 v1 内先把如下顶层公共字段固定：

- `schema_version`
- `platform`
- `source_ref`
- `ingestion_entrypoint`
- `source_mode`
- `structured_extraction_status`
- `structured_extraction_reason`
- `quality_score`
- `degradation_flags`

并禁止再新增 `extraction_status` 这类平行命名。

### 10.3 LLM 元数据也需要进入标准层

当前 LLM 抽取服务已经具备配置驱动能力：

- prompt 可来自 `LlmServiceConfig`
- model/provider 可通过 `get_chat_model()` 动态解析
- 某些 extractor 支持 structured output，失败后 fallback 到 JSON 提取

这些信息如果不进入统一 contract，后续会出现几个问题：

1. 无法追溯一条结构化结果是哪个 extractor / model / prompt 版本生成的
2. prompt 调整后，历史结果与新结果难以区分
3. 消费侧看到结构变化时，难以判断是 contract 变更还是 extractor 漂移

因此建议在 `extraction` 分层中至少固定：

- `extractor_version`
- `model_profile`
- `prompt_profile`
- `structured_output_mode`

如果短期不想全量写入，也至少要写 `extractor_version` 与 `model_profile.model`。

## 11. 统一状态机建议

当前各链路出现了：

- `ok`
- `failed`
- `fallback`
- `skipped`

但字段名和语义并不完全一致。建议统一成：

### 11.1 抽取状态

- `ok`: 成功产出可用结构化结果
- `partial`: 有结构化结果，但依赖 fallback/规则补全
- `failed`: 已执行抽取但没有可用结果
- `skipped`: 因配置/内容门禁未执行抽取

### 11.2 落库状态

- `inserted`
- `skipped_exists`
- `updated`
- `failed`

这样可以避免把“抽取是否成功”和“是否成功写库”混成一个状态字段。

## 12. 服务拆分建议（代码落点）

建议新增而不是继续扩张已有入口服务，避免 `single_url.py` 继续成为事实上的“大一统实现”。

### 12.1 建议新增模块

- `main/backend/app/services/ingest/terminal_contract.py`
  - 定义 `TerminalIngestPayload`
  - 定义 `TerminalExtractionOutcome`
  - 定义 `TerminalWriteResult`
  - 定义 contract validator

- `main/backend/app/services/ingest/unified_structured_extraction_service.py`
  - 统一封装 `ExtractionApplicationService`
  - 统一 include flags 策略
  - 统一抽取结果状态、版本、摘要、异常
  - 对接 `terminal_normalizer`

- `main/backend/app/services/ingest/terminal_normalizer.py`
  - 统一 `schema_version`
  - 统一字段名
  - 统一 extracted_data 分层
  - 兼容映射旧字段

- `main/backend/app/services/ingest/terminal_writer.py`
  - `get_or_create_source`
  - 去重策略
  - `Document` 持久化
  - 通用 commit/flush/result

- `main/backend/app/services/ingest/terminal_compat.py`
  - 从内部标准结构生成当前消费侧可读字段
  - 统一保留顶层 `policy/market/sentiment/platform/...`
  - 冻结消费侧 contract

- `main/backend/app/services/ingest/terminal_adapters/`
  - `single_url_adapter.py`
  - `market_web_adapter.py`
  - `social_adapter.py`
  - `policy_adapter.py`
  - `raw_import_adapter.py`

### 12.2 现有文件的推荐收敛方式

- `single_url.py`
  - 保留抓取、质量判定、light filter、structured extraction
  - 去掉最终 `Document(...)` 细节，改调 adapter + unified structured extraction service + writer

- `market_web.py`
  - 保留搜索/抓正文/market normalize
  - 去掉直写 `Document(...)`
  - 抽取调用改走 unified structured extraction service

- `social.py`
  - Reddit sentiment 与 policy 搜索两条链路都改用 adapter
  - 去掉各自的 extracted_data 顶层拼装
  - sentiment/policy 抽取统一通过 unified structured extraction service 触发

- `policy.py`
  - 作为最需要纳入统一 writer 的路径
  - 至少补齐 `schema_version/platform/source_ref/structured_extraction_status`
  - 若后续补 LLM policy extraction，也通过 unified structured extraction service 进入

- `discovery/store.py`、`raw_import.py`
  - 当前也存在直写入口，应视为第二批治理对象
  - 若先只治理 source-library/run 主链路，需在文档中明确“阶段性例外”

### 12.3 消费侧模块化建议

你提到“这些消费侧业务将来也需要模块化”，这点应提前反映在设计里，但不应和当前末端标准化同时硬绑上线。

建议消费侧后续按“读取 facade”方式模块化，而不是继续在 API / indexer / graph 中散落直接读取 `extracted_data`：

- `main/backend/app/services/document_views/`
  - `policy_view.py`
  - `market_view.py`
  - `social_view.py`
  - `common_view.py`

这些 view/facade 的职责：

- 从 `Document` 中读取内部标准结构
- 在需要时回退到旧顶层兼容字段
- 为 API / indexer / graph 提供稳定读取接口

这样后续消费侧模块化时，就不需要每个业务模块都自己处理 JSON 细节。

## 13. 迁移策略建议：先统一 writer，再统一 JSON 结构

建议分两阶段推进，而不是一次性同时重做所有来源和所有消费侧。

### 阶段 A：Writer 收口

目标：

- 先显式收口 unified structured extraction 调用入口
- 所有新链路先共用 `terminal_writer`
- 先统一基础公共字段
- 业务域对象暂不重构

验收：

- `single_url/market/social` 抽取调用统一经过 `unified_structured_extraction_service`
- `single_url/market/social/policy` 四链路共用一个 writer
- 不再新增新的 `Document(...)` 直写末端
- 消费侧字段对外保持不变
- 新老写入链路都通过 `terminal_compat` 生成冻结字段

### 阶段 B：Contract 分层

目标：

- 引入 `terminal/extraction/domains` 分层
- 兼容保留顶层 `policy/market/sentiment`
- 消费侧逐步迁移到新路径

验收：

- 新增 contract validator
- 新消费者默认读取新层级
- 旧消费者保持兼容

### 阶段 C：消费侧模块化

目标：

- API / graph / indexer / stats 不再散落直接读取 `extracted_data`
- 收敛到统一 facade/view service
- 为最终移除顶层兼容字段做准备

验收：

- 新增消费侧 facade 测试
- 关键业务模块改为调用 view service
- 顶层兼容字段只作为 fallback，不再作为首选读取路径

## 14. 最小门禁建议：不只测“写进去了”，要测“形态一致”

### 14.1 Contract tests

对 `terminal_normalizer` 做纯函数级测试：

- 输入 minimal payload，输出必须补齐公共字段
- `extraction_status` 必须被收敛/映射，不允许裸写进入最终 contract
- 缺失 `source_ref` / `schema_version` 直接失败

再补一类测试：

- 冻结字段测试：给定内部标准结构，`terminal_compat` 输出的顶层 `policy/market/sentiment/platform` 形态必须稳定
- LLM 元数据测试：`extractor_version/model_profile` 必须按 contract 落库

### 14.2 Integration tests

至少覆盖：

1. `single_url`
2. `market_web`
3. `social` Reddit
4. `policy`

断言内容：

- `Document.doc_type` 正常
- `Document.uri` 正常
- `Document.extracted_data.schema_version` 存在
- `Document.extracted_data.structured_extraction_status` 存在
- 对应域对象存在时，`policy/market/sentiment` 仍可被读取
- 旧消费侧接口在不改调用代码的前提下行为不变
- 抽取结果中能追踪到使用的 extractor/model 关键信息

### 14.4 Unified structured extraction regression checks

建议单列一组轻量回归检查，避免“contract 稳定但抽取质量漂移”：

1. 固定样本文本集
2. 对 policy / market / sentiment / ER 各跑一次抽取
3. 检查：
   - 返回结构合法
   - 关键字段不缺失
   - fallback 比例未异常升高
   - structured output -> JSON fallback 的比例可观测

### 14.3 DB 抽样 SQL

建议纳入固定验收脚本：

```sql
select
  count(*) as total,
  count(*) filter (where extracted_data ? 'schema_version') as with_schema_version,
  count(*) filter (where extracted_data ? 'structured_extraction_status') as with_structured_status,
  count(*) filter (where extracted_data ? 'source_ref') as with_source_ref
from documents
where created_at >= now() - interval '7 day';
```

再加一个反向检查：

```sql
select id, doc_type, uri
from documents
where created_at >= now() - interval '7 day'
  and extracted_data ? 'extraction_status'
  and not extracted_data ? 'structured_extraction_status'
limit 100;
```

第二条 SQL 的目标是把“旧字段仍在裸奔”的残留链路抓出来。

## 15. 原子任务建议（升级版）

### AT-11A 契约固化

- 目标：定义 Terminal Ingest Contract v1.1
- 输入：`single_url` 现有字段 + `NormalizedIngestEnvelope`
- 输出：contract 文档 + Pydantic model
- 验收：contract test 覆盖必填字段和状态映射

### AT-12A Writer 收口

- 目标：抽离 `terminal_writer`
- 输入：`single_url` 的 `_persist_single_url_document`
- 输出：公共写库服务
- 验收：`single_url` 改为仅构造 payload，不再直接 `Document(...)`

### AT-12B Unified structured extraction service 收口

- 目标：抽离统一 LLM 结构化服务
- 输入：`ExtractionApplicationService` + `extract_structured_enriched_safe`
- 输出：`unified_structured_extraction_service`
- 验收：各来源不再自行决定抽取状态字段名与落库方式

### AT-13A Source adapters

- 目标：将 `market_web/social/policy` 改为 adapter -> writer
- 输入：三条现有链路
- 输出：统一 payload 构造
- 验收：四条主链路字段口径一致

### AT-14A Consumer compatibility

- 目标：梳理并修正读取侧兼容点
- 输入：graph/indexer/api 中的 `extracted_data.*` 读取
- 输出：兼容清单与必要修补
- 验收：关键消费链路无回归

### AT-14B Consumer facade modularization

- 目标：为消费侧建立统一读取层
- 输入：API / graph / indexer / stats 当前散落读取逻辑
- 输出：document view/facade services
- 验收：新增消费逻辑不再直接拼 JSON 路径

### AT-15A 历史补齐与观测

- 目标：补历史最低字段并建立 SQL 巡检
- 输入：`documents` 历史记录
- 输出：幂等回填脚本 + 观测查询
- 验收：新写入完整率 100%，历史补齐按批完成

## 16. 结论：推荐的实施原则

本次“模块化”不建议理解为“把一个大文件拆成几个文件”。

更准确的目标应是：

1. 把“来源特定逻辑”和“末端持久化逻辑”拆开
2. 把“LLM 结构化抽取能力”和“末端 contract / writer”拆开
3. 把“公共结构化元数据”和“业务域对象”拆开
4. 把“写入侧标准化”和“读取侧兼容改造”分阶段推进
5. 先冻结消费侧字段，再逐步让消费侧模块化

如果按这个方向推进，后续新增来源时只需要：

- 新增一个 source adapter
- 复用同一个 normalizer
- 复用同一个 writer

而不需要再复制一套 `Document(...) + extracted_data` 组装逻辑。

而后续消费侧模块化时，也只需要：

- 让业务模块改读 facade/view service
- 逐步减少对顶层兼容字段的直接依赖
- 最终在时机成熟后再清理兼容层
