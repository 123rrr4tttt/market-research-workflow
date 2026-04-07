# 离散模块前门化清单与后处理前门计划（2026-03-12）

## 1. 目标

在来源库末端收敛后，将“非来源库职责”先按模块拆开，避免一次性并链重构；同时明确其中哪些模块应被前门吸收，哪些模块继续后置。

对应关系：

- 来源库末端统一：见 `02_source-library-terminal-output-unification-and-boundary-2026-03-12.md`
- 本文负责：离散模块分层判断 + 前门化落地计划

## 1.1 边界修正（2026-03-14）

当前后续实现与实测已经说明一件事：

1. `single_url` 不能再被视为统一标准的权威宿主
2. 它只能被视为历史遗留链路中的一条兼容实现
3. 统一标准化质检应以前门层为中心定义，而不是继续围绕 `single_url` 复制或迁就

因此从本版本开始，本文中的前门职责应按下面的优先级理解：

1. 先在 `source_library terminal output` 之后落地统一质检
2. 先把遗留 `meaningful_gate / light_filter` 以及 provenance/content 判定逻辑收编成前门层能力
3. 再决定如何回收 `single_url` 历史质检逻辑

## 1.2 结构化层修正（2026-03-14）

`unified structured extraction` 当前已经与现有架构发生部分重叠，不应继续被当作一个长期独立、稳定并列的模块层。

原因很直接：

1. [postprocess_frontdoor.py](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/ingest/postprocess_frontdoor.py) 已经直接编排结构化调用
2. [unified_structured_extraction_service.py](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/ingest/unified_structured_extraction_service.py) 目前只是对现有 extraction 能力的一层薄包装
3. 如果继续把它当作长期并列模块，会让 frontdoor 和 structured orchestration 都承担“统一调度”的语义，边界变糊

因此本文后续口径调整为：

1. `unified_structured_extraction_service` 视为迁移期调用边界
2. 第一目标是迁移各入口调用到 frontdoor
3. 第二目标是修剪 `single_url/news/url_pool` 等链路里的重复结构化调用与重复编排
4. 边界稳定后，再决定是否将该薄包装并回 frontdoor 或 extraction 主服务

## 2. 离散模块分层（前门化优先）

以下模块从“来源库链条”中明确剥离，但不是都长期离散保留，而是分成两类：

1. 应改造成前门组成部分的模块
   - `meaningful_gate` / `light_filter`
   - provenance/content 判定步骤
   - 清洗回发/重放步骤
2. 暂时后置、由前门分发的模块
   - `structured_extraction` / `extraction.application`
   - `Document` 持久化 writer
   - 索引/向量化/图谱后续处理
   - 指标、重试、回退编排

这里的判断原则是：

1. 凡是用于回答“这份内容是否值得继续处理、是否需要清洗、是否应回发”的模块，应前门化。
2. 凡是用于回答“内容接下来如何被结构化、写库、索引、消费”的模块，继续后置。

## 2.1 应并入前门的离散模块

这部分不应长期写成“frontdoor -> discrete modules”的外接件，而应逐步成为 `quality frontdoor` 内部能力：

1. `light_filter`
2. `meaningful_gate`
3. provenance 判定步骤（不单独立模块）
4. content 判定步骤（不单独立模块）
5. cleanup / return-for-cleanup 步骤（不单独立模块）

前门化后的职责是：

1. 给出质量裁决
2. 给出清洗动作
3. 给出是否继续进入 extraction / writer 的调度建议

## 2.2 继续后置的模块

以下模块仍然保持前门之后的分发式结构：

1. 结构化抽取
   - `structured_extraction` / `extraction.application`
2. 入库与写模型
   - `Document` 持久化 writer
3. 索引/向量化/图谱后续处理
4. 指标、重试、回退编排

后置原则：

1. 不修改其原有业务语义，仅改变入口对接方式。
2. 所有后置模块只接受前门标准化输出或其标准映射输入。
3. 保留独立开关，支持分模块灰度与快速回退。

## 2.3 离散模块清理表

| 模块 | 前门化/后置 | 需要清理的遗留形态 | 短期保留 | 清理完成标志 |
|---|---|---|---|---|
| `light_filter` | 前门化 | 入口内联过滤分支、链路内各自命名的轻筛选标记、与 `single_url` 上下文强绑定的调用方式 | 过滤规则本体 | 前门统一调用，其他入口不再各自定义轻筛选分支 |
| `meaningful_gate` | 前门化 | 基于单链路上下文的 worthiness 判断、散落的最小长度/内容密度阈值、重复 rejection reason | 打分规则与阈值经验 | 统一输出 `pass/fail + reason_code + score_delta` |
| provenance 判定步骤 | 前门化 | 各链路自己判断 domain/source_ref/url 可用性的散装逻辑、重复 provenance warning | 来源可信度判定规则，可复用 `url_policy_check()` | provenance 只在前门裁决，后续模块只消费结果 |
| content 判定步骤 | 前门化 | 标题/正文有效性、正文空洞、模板页判断散落在各入口的问题 | 内容有效性判定规则，可复用 `content_quality_check()` | 内容有效性在前门统一出结论，不再在 writer 前重复判断 |
| cleanup / return-for-cleanup 步骤 | 前门化 | 手工 if/else 清理动作、“清洗后重跑”没有标准状态、回发和 reject 混用、重试口径不统一 | 清洗动作枚举、重放能力与 trace 规则 | 前门统一产出 `cleanup_actions`，`return_for_cleanup` 成为独立 admission 和状态机分支 |
| `structured_extraction` | 后置 | 入口侧决定抽取字段集、抽取状态字段名不一致、失败语义散落 | extractor 本体与 prompt/model 配置 | 只由前门之后统一调度，不再由各采集链直接拼抽取结果 |
| `unified_structured_extraction_service` | 后置 | 仅作为 frontdoor 到 extractor 的迁移期薄包装，当前已与 frontdoor 编排重叠 | 统一调用边界 | 等调用全部迁移到 frontdoor 后，修剪重复链路并评估是否并回 |
| `terminal_normalizer` | 后置 | 顶层兼容字段和内部标准结构混写、状态字段漂移 | 标准 contract 组装逻辑 | 所有 normalized 输出只从统一 normalizer 产生 |
| `terminal_compat` | 后置 | 业务入口自己拼 `policy/market/sentiment/entities_relations` 顶层字段 | compat 映射逻辑 | 顶层兼容字段只由 compat mapper 生成 |
| `terminal_writer` | 后置 | 各入口直写 `Document(...)`、各自处理去重与 `Source` 获取 | writer 去重和落库逻辑 | 新增写入只走统一 writer |
| graph/index/vector downstream | 后置 | 直接读取原始 JSON 路径、消费侧自己解释质量状态 | facade / adapter 读取逻辑 | 消费侧只读前门后标准结果或 view/facade |
| 指标、重试、回退编排 | 后置 | 每条链路各自记指标、各自重试、失败后不可追踪 | trace、审计、重试机制 | 指标与重试围绕前门状态机统一记录 |

清理原则：

1. 清理的是“入口内联和重复语义”，不是立刻推倒规则本体。
2. 能前门化的先前门化，不能前门化的先收口为前门后的唯一实现。
3. 所有清理项都应以“减少重复判断点”为验收标准，而不是只看代码是否搬了位置。

## 3. 后处理前门（Pre-Process Frontdoor）计划

## 3.1 位置与职责

位置：`source library terminal output -> quality frontdoor -> post-frontdoor modules`

职责：

1. 校验来源库统一输出契约（Contract Gate）。
2. 统一承接历史遗留质检逻辑：
   - `light_filter`
   - `meaningful gate`
   - provenance/content 判定步骤
3. 吸收可前门化的离散质检/清洗模块，形成统一质量裁决层。
4. 做最小清洗（Light Clean）与必要清理/回发，不做业务域抽取。
5. 给出准入决策（Admission）：`accept|reject|defer|return_for_cleanup`。
6. 产出可重试、可回退、可审计的标准 envelope。

这里的关键调整是：

1. 前门首先是统一质检前门
2. 前门不是 `single_url` 逻辑的薄包装
3. 前门应优先以来源库输出为主输入边界落地

## 3.2 前门输入输出

输入：`SourceLibraryTerminalOutput v1`

输出（建议）：

```json
{
  "status": "ok|error",
  "data": {
    "admission": "accept|reject|defer|return_for_cleanup",
    "normalized_payload": {},
    "raw_snapshot_ref": "string",
    "rollback_token": "string"
  },
  "error": null,
  "meta": {
    "trace_id": "string",
    "ingest_id": "string",
    "attempt": 1,
    "reason_code": "ok",
    "retryable": false
  }
}
```

## 3.3 前门最小状态机

1. `RECEIVED`
2. `CONTRACT_VALIDATED`
3. `QUALITY_EVALUATED`
4. `LIGHT_CLEANED`
5. `ADMISSION_DECIDED`
6. `DISPATCHED`（分发到后置模块）
7. `DONE|FAILED|DEFERRED|RETURNED_FOR_CLEANUP`

状态机要求：

1. 每次状态迁移都带 `trace_id + reason_code`。
2. `DEFERRED` 必须带 `retryable=true`。
3. `FAILED` 必须落可审计错误快照。
4. `RETURNED_FOR_CLEANUP` 必须明确回发原因和建议处理动作。

## 4. 回退/重试治理（与前门绑定）

1. 幂等键：`ingest_id + payload_hash`
2. 回退令牌：`rollback_token` 指向最近一次成功可消费版本
3. 重试策略：仅对 `retryable=true` 执行自动重试
4. 审计记录：保存
   - 入参快照
   - 清洗后快照
   - 决策结果
   - 分发结果

## 5. 原子任务（前门化 + 后置模块对接）

### AT-PF-01 前门契约实现

- 目标：定义并实现 `PostProcessFrontdoorEnvelope v1`
- 输入：`SourceLibraryTerminalOutput v1`
- 输出：标准 `status/data/error/meta`
- 验收：契约测试通过，字段完整

### AT-PF-01A 统一质检层定义

- 目标：把遗留质检逻辑抽象成前门统一质检层
- 输入：`light_filter / meaningful_gate / provenance/content 判定逻辑`
- 输出：统一 `quality_assessment` 结构与 `admission` 枚举
- 验收：来源库链可以不依赖 `single_url` 直接得到一致质检结论

### AT-PF-02 后置模块适配器

- 目标：为前门之后的后置模块增加统一 adapter
- 输入：前门 `normalized_payload`
- 输出：模块统一入参与结果映射
- 验收：每个后置模块至少 1 条贯通测试

### AT-PF-02A 来源库先行落地

- 目标：统一质检前门先接 `source_library terminal output`
- 输入：`SourceLibraryTerminalOutput v1`
- 输出：来源库链的 `quality_assessment + admission`
- 验收：来源库侧能先独立完成质检、清洗/回发/清理决策

### AT-PF-02B 结构化调用迁移到 frontdoor

- 目标：把统一结构化调用入口迁到 frontdoor 主调度
- 输入：`single_url/news/url_pool` 等链路当前的结构化调用点
- 输出：前门成为统一结构化调度入口
- 验收：新增链路不再直接编排结构化调用

### AT-PF-02C 修剪重复结构化链路

- 目标：移除与 frontdoor 重叠的重复结构化调用和中间包装
- 输入：已迁移调用点、`unified_structured_extraction_service`
- 输出：重复调用点清单与修剪方案
- 验收：frontdoor 外部的重复结构化编排显著减少

### AT-PF-03 回退重试链

- 目标：接入 `rollback_token + retryable` 机制
- 输入：前门决策与模块执行结果
- 输出：回退记录与重试计划
- 验收：失败场景可重放、可回退

### AT-PF-04 观测与审计

- 目标：建立前门可观测指标
- 输入：状态机过程事件
- 输出：`accept/reject/defer` 比例、重试率、回退次数
- 验收：可按 `trace_id/ingest_id` 追溯全流程

## 6. 里程碑建议

1. M1：来源库链先上线统一质检前门（不以 `single_url` 为标准）
2. M2：结构化调用迁到 frontdoor，修剪重复链路
3. M3：模块适配器接入，统一分发
4. M4：回退/重试自动化
5. M5：回收历史质检与重复结构化实现并封口

## 7. 完成定义

满足以下条件可判定“离散模块前门化 + 前门计划”进入可开发状态：

1. 哪些离散模块应并入前门、哪些继续后置，边界责任明确。
2. 前门输入输出契约冻结。
3. 原子任务可并行执行并具备验收标准。
