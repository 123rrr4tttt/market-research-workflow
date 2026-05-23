# 统一质检前门原子任务清单（来源库先行）- 2026-03-14

## Summary

本清单用于把“统一标准化质检”从历史 `single_url` 末端逻辑中抽离出来，上移为独立的 `quality frontdoor` 能力，并优先在 `source_library terminal output` 之后落地。

本轮的主目标不是先统一 writer，也不是先回收所有历史采集链，而是先建立一套独立、可复用、可裁决的质量前门，让来源库输出在进入结构化、清洗、发回、持久化之前，先获得稳定的一次质量判断。

一句话原则：

先把质检统一，不先把 writer 统一；先让来源库能给出稳定质量决策，再决定历史链路怎么回收。

## Scope

### In Scope

- 定义 `quality frontdoor` 的输入输出 contract
- 抽离统一质检步骤：
  - `light_filter`
  - `meaningful_gate`
  - provenance 判定
  - content 判定
- 明确前门动作：
  - `accept`
  - `reject`
  - `defer`
  - `return_for_cleanup`
- 在 `source_library terminal output` 之后先接入
- 形成统一质量元数据与审计轨迹

### Out of Scope

- 第一阶段不要求统一所有 writer
- 第一阶段不要求回收所有 legacy collect 链
- 第一阶段不要求把 `single_url` 作为标准实现继续扩散
- 第一阶段不要求消费侧同步改造

## Design Goals

### G1. 统一质量裁决

同一份采集结果，不应由不同入口各自定义“是否值得入库”。

### G2. 先来源库，后历史链

来源库现在已经有 clean boundary，适合作为第一条稳定接入链。

### G3. 清洗与裁决分层

前门不仅做 reject，也要支持：

- 清洗后继续
- 发回清洗
- 暂缓进入结构化

### G4. 质量元数据可追溯

每一次前门决策都需要留下：

- reason code
- degraded flags
- cleanup actions
- audit snapshot

## Unified Frontdoor Responsibilities

`quality frontdoor` 第一阶段承担：

1. contract gate
2. light normalization
3. quality evaluation
4. cleanup dispatch
5. admission decision
6. quality metadata emission

它不负责：

- graph side effects
- index side effects
- 业务消费字段拼装

## Frontdoorization Boundary

本轮不再把这些模块笼统写成“离散保留”，而是改成两类：

### 应前门化的离散能力

这部分应改造成 `quality frontdoor` 内部能力，而不是继续单独立模块：

- `light_filter`
- `meaningful_gate`
- provenance 判定步骤
- content 判定步骤
- cleanup / return-for-cleanup 步骤

判断标准：

- 它们直接参与“是否继续处理”的质量裁决
- 它们直接参与“是否需要清洗/回发”的动作决策

### 继续后置的模块

这部分仍保持在前门之后：

- `structured_extraction`
- `unified_structured_extraction_service`（迁移期薄包装，后续待收编）
- `terminal_normalizer`
- `terminal_compat`
- `terminal_writer`
- graph/index/vector downstream

判断标准：

- 它们不负责质量准入裁决
- 它们只消费前门的标准化结果继续处理

## Cleanup Matrix

| 模块 | 目标状态 | 需要清理 | 可保留 | 对应任务 |
|---|---|---|---|---|
| `light_filter` | 并入前门 | 清理链路内联过滤分支和重复标记 | 规则本体 | `AT-QF-03` |
| `meaningful_gate` | 并入前门 | 清理散落阈值和重复 reason code | 判定规则与阈值经验 | `AT-QF-04` |
| provenance 判定步骤 | 并入前门 | 清理各入口各自 provenance 判断 | provenance 规则，可复用 `url_policy_check()` | `AT-QF-05` |
| content 判定步骤 | 并入前门 | 清理标题/正文有效性重复判断点 | 内容有效性规则，可复用 `content_quality_check()` | `AT-QF-05` |
| cleanup / return-for-cleanup 步骤 | 并入前门 | 清理手工 if/else 清洗分支、reject/defer/重跑混用 | 动作枚举、重放协议 | `AT-QF-06`、`AT-QF-06A`、`AT-QF-11` |
| `structured_extraction` | 继续后置 | 清理入口自定义抽取编排 | extractor 本体 | `AT-QF-06A`、后续 extraction 任务 |
| `unified_structured_extraction_service` | 继续后置 | 仅保留 frontdoor 调用边界，避免入口直接碰底层 extractor；与现有 frontdoor 编排已有重叠 | 迁移期薄包装 | 调用全部迁到 frontdoor 后评估收编或并回 |
| `terminal_normalizer` | 继续后置 | 清理兼容字段与标准层混写 | contract 组装逻辑 | `AT-QF-08` |
| `terminal_compat` | 继续后置 | 清理入口自己拼兼容字段 | compat mapper | `AT-QF-08` |
| `terminal_writer` | 继续后置 | 清理直写 `Document(...)` 末端 | 统一 writer | 后续 writer 任务 |

## Suggested Contract

### Input

`FrontdoorIngressEnvelope v1`

最少需要：

- `contract_version`
- `ingress_type`
- `entrypoint`
- `source_mode`
- `source_ref`
- `collection_payload`
- `raw_snapshot`

### Output

`QualityFrontdoorDecision v1`

建议字段：

```json
{
  "status": "ok|error",
  "data": {
    "admission": "accept|reject|defer|return_for_cleanup",
    "quality_assessment": {
      "quality_score": 0.0,
      "meaningful": true,
      "provenance_ok": true,
      "content_ok": true
    },
    "cleanup_actions": [],
    "reason_code": "ok",
    "degradation_flags": [],
    "normalized_payload": {},
    "dispatch_plan": {
      "run_cleanup": false,
      "run_extraction": false,
      "run_writer": false
    }
  },
  "error": null,
  "meta": {
    "trace_id": "string",
    "ingest_id": "string",
    "retryable": false
  }
}
```

## Atomic Task List

### A. Contract Definition

#### AT-QF-01 定义 `QualityFrontdoorDecision v1`

目标：冻结统一质检前门输出契约。

输入：

- `FrontdoorIngressEnvelope v1`
- 当前 frontdoor `accept|reject|defer` 状态机

输出：

- `QualityFrontdoorDecision v1` 结构定义

验收：

- 明确 `return_for_cleanup`
- 明确 `quality_assessment`
- 明确 `cleanup_actions`

#### AT-QF-02 定义统一 `reason_code` 枚举

目标：统一前门拒绝、清洗、暂缓原因。

输入：

- 现有 `single_url` rejection breakdown
- 现有 frontdoor `reason_code`

输出：

- `reason_code` 枚举表

验收：

- 至少覆盖：
  - `missing_contract_field`
  - `empty_candidate`
  - `low_information_density`
  - `insufficient_provenance`
  - `cleanup_required`
  - `records_only_deferred`

### B. Quality Modules

#### AT-QF-03 抽离 `light_filter`

目标：将最轻量的噪音拦截统一收口。

输入：

- 历史 `single_url` 过滤逻辑
- 来源库采集结果典型样本

输出：

- 独立 `light_filter` 模块

验收：

- 不依赖 `single_url` 调用上下文
- 可直接接受 frontdoor normalized payload

#### AT-QF-04 抽离 `meaningful_gate`

目标：统一判断内容是否值得进入结构化或持久化。

输入：

- 文本长度
- 信息密度
- 标题/正文有效性

输出：

- 独立 `meaningful_gate`

验收：

- 输出 `pass/fail + reason_code + score_delta`

#### AT-QF-05 定义 provenance / content 判定步骤

目标：统一判断来源可信度、可追溯性与正文有效性。

输入：

- `source_ref`
- URL
- domain
- handler/meta

验收：

- 能区分：
  - provenance sufficient
  - provenance weak but usable
  - provenance failed
- 能统一输出 content 有效性结论，不再额外单独立 `content_gate` 模块

#### AT-QF-06 定义 cleanup / return-for-cleanup 步骤

目标：对需要清洗的内容给出处理动作，并把回清洗作为前门内部状态，而不是单独立模块。

输入：

- 原始 payload
- 质检结果

输出：

- `cleanup_actions`

验收：

- 至少支持：
  - strip boilerplate
  - trim tracking fragments
  - refetch suggested
  - defer for later

#### AT-QF-06A 完成离散模块前门化切分

目标：明确哪些历史离散模块应并入前门，哪些继续后置。

输入：

- 现有 `03` 文档中的离散模块清单
- 统一质检前门职责边界

输出：

- 一份固定的 frontdoorization boundary

验收：

- `light_filter / meaningful_gate / provenance/content 判定 / cleanup-return 步骤` 明确归入前门
- `structured_extraction / writer / graph/index` 明确继续后置

### C. Frontdoor Orchestration

#### AT-QF-07 实现 `quality frontdoor` 状态机

目标：把质检放进 frontdoor 主调度。

输入：

- ingress envelope
- contract gate
- light filter / gates

输出：

- 状态机：
  - `RECEIVED`
  - `CONTRACT_VALIDATED`
  - `NORMALIZED`
  - `QUALITY_EVALUATED`
  - `RETURNED_FOR_CLEANUP`
  - `ADMISSION_DECIDED`
  - `DONE|FAILED|DEFERRED`

验收：

- `return_for_cleanup` 有单独状态，不与 `reject` 混用

#### AT-QF-07A 迁移统一结构化调用到 frontdoor

目标：让 frontdoor 成为唯一默认结构化调度入口。

输入：

- `single_url`
- `news`
- `url_pool`
- 其他仍直接碰 extraction 的链路

输出：

- 调用迁移清单
- frontdoor 统一调度落地

验收：

- 新入口默认不再直接调用结构化能力
- 结构化调用点显著收敛到 frontdoor

#### AT-QF-07B 修剪重叠结构化链路

目标：清理与 frontdoor 重叠的结构化包装与重复编排。

输入：

- 已迁移调用点
- `unified_structured_extraction_service`

输出：

- 重复调用点清单
- 修剪方案

验收：

- `unified_structured_extraction_service` 明确仅保留迁移期边界，或被进一步收编

#### AT-QF-08 固定质量元数据透传规则

目标：让后续结构化与 writer 都能消费统一质检结果。

输入：

- quality frontdoor decision

输出：

- 透传字段规范：
  - `quality_score`
  - `degradation_flags`
  - `frontdoor_reason_code`
  - `cleanup_actions`

验收：

- `terminal_normalizer` 不再只是被动透传历史上下文

### D. Source Library First Landing

#### AT-QF-09 为来源库接入 `quality frontdoor`

目标：来源库成为第一条真实接入链。

输入：

- `SourceLibraryTerminalOutput v1`
- `source_library_ingress_adapter`

输出：

- 来源库输出进入统一质检前门

验收：

- 对 records-only 结果可输出 `defer`
- 对 document-candidate 可输出四态决策

#### AT-QF-10 建立来源库专项验证样本集

目标：用真实来源库结果验证质检动作。

输入：

- `news.general.regulation`
- `market.general.baseline`
- 关键词检索样本

输出：

- 样本库与预期动作清单

验收：

- 每个样本都能说明为何 `accept/reject/defer/return_for_cleanup`

### E. Cleanup / Return Path

#### AT-QF-11 定义 `return_for_cleanup` 处理协议

目标：明确“发回清洗”不是丢弃，也不是直接进入 writer。

输入：

- quality frontdoor decision
- cleanup router

输出：

- 回清洗协议

验收：

- 能说明：
  - 谁负责清洗
  - 清洗后如何重放
  - 最大重试次数

### F. Validation

#### AT-QF-12 建立统一质检回归检查

目标：让前门质检具备独立门禁。

输入：

- source_library 样本
- rejection / cleanup 样本

输出：

- contract tests
- unit tests
- runtime validation checklist

验收：

- 任何 reason code 漂移都会被测试发现

## Validation Suggestions

### Contract Tests

- 非法 envelope 必须 `reject`
- `records-only` 必须可 `defer`
- 需要清洗的 payload 必须可 `return_for_cleanup`

### Runtime Checks

- 跑一组来源库关键词样本
- 检查每条候选的 quality decision
- 检查 `quality_score / reason_code / cleanup_actions`

### Audit Checks

- 每条 frontdoor decision 必须带 `trace_id`
- 每次 `return_for_cleanup` 必须可追溯原始 payload

## Execution Order

1. `AT-QF-01` 定义 decision contract
2. `AT-QF-02` 固定 reason code
3. `AT-QF-03` 到 `AT-QF-06` 抽离四个质检/清洗模块
4. `AT-QF-07` 和 `AT-QF-08` 接入 frontdoor 主调度
5. `AT-QF-09` 到 `AT-QF-10` 在来源库链真实落地
6. `AT-QF-11` 到 `AT-QF-12` 封闭 cleanup 与回归门禁

## Final Note

当前最重要的不是把所有历史采集路径立刻改成同一 writer，而是先让系统拥有一个独立、权威、可复用的质量裁决层。

来源库已经有 clean terminal boundary，所以它是统一质检前门最合适的第一落点。
