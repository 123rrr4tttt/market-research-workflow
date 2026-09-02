# MRW 函子化后继迁移语义运动完整性冻结修正

Status: `FROZEN_AUTHORIZED · ADDITIVE_NORMATIVE_AMENDMENT`

Authorized by user: `2026-09-01`

Authority source: direct user authorization in supervisor task `01a05039-0c9c-7873-8d9f-b60ef1af179f`

Authority decision: adopt semantic movement completeness as a development
standard for the functorial successor migration and synchronize the target
Goal thread.

Resolved blocker: `SEMANTIC_MOVEMENT_COMPLETENESS_NORMATIVE_AMENDMENT_REQUIRED`

Base architecture contract:

`06_functorial-successor-runtime-architecture-correction.draft.zh-CN.md`

Base architecture SHA-256:

`c93b58e15a3dbaa1e5e1be9bebfbc41143b97b8e91eb9774851d1f5d78fe3a93`

Base freeze manifest:

`02_functorial-successor-migration-development-contract.freeze.json`

Base freeze manifest SHA-256:

`0798933179c1d9a3d0359c2b16debc4e0b6f16f7fbccca485dcd50c54ef9530c`

## 1. 修正原因

冻结合同族已经要求 cell/file/test/hash closure、CapabilitySpec 与独立 exact-candidate review，
但未把 semantic movement completeness 规定为 P1/P3/P4/P5、CapabilitySpec pilot 与 candidate
review 的强制输入，也未规定 movement record 的必填字段、合法 disposition 与
`UNASSIGNED_BLOCKER` 的 promotion 阻断语义。结果是 locator evidence
（文件、模块、cell、测试计数、行范围）可能被误读为能力无损迁移证明，contract-only、
unwired 或 disabled 语义能力也可能因缺少 live owner 而无声消失。

本 amendment 只增加 movement completeness 规范与对应 gate，不增加新的 C7 顶级 cell，
不改变既有 30-cell topology，不授权任何 live provider、外部 delivery、cutover、
authority transfer 或 production canonical write，也不自行证明 P4 或 C7 完成。

## 2. 适用范围

本 amendment 适用于 functorial successor migration 及同库内任何迁移、重命名、
删除、重构、后端替换、代码生成、能力提升、阶段完成或 legacy 退休工作。

## 3. 强制输入

`legacy/donor semantic movement inventory` 与 `successor movement matrix` 是以下工作
的强制输入，不得以 locator/cell/file/test/hash closure 替代：

- P1（设施与能力迁移资格审计）；
- P3（C2–C6 迁移）；
- P4（C7–C9 迁移）；
- P5（assembly/canary/cutover）；
- CapabilitySpec pilot；
- candidate review。

## 4. Movement record 必填字段

每条 movement record 必须包含：

- `source_object`：legacy/donor 对象、contract、data shape 或 behavior；
- `target_object`：successor 对象、contract、data shape 或 behavior；
- `named_transform`：显式 function、adapter、mapping 或 manual procedure；
- `owner`：可问责的 person 或 team；
- `effect`：side effect 与可观察行为；
- `failure`：failure modes 及其传播；
- `resource`：compute、storage、network、memory 或 cost impact；
- `authority`：permissions、roles 与 authorization boundary；
- `recovery`：retry、rollback、compensation 与 restart behavior；
- `projection_loss`：该运动丢失或削弱的内容；
- `source_evidence`：可复现的 legacy source behavior 指针；
- `target_realization`：可复现的 target behavior 指针；
- `acceptance_trace`：证明转换与 loss account 正确的 test 或 review trace。

缺任一必填字段的记录不得计入 movement completeness。

## 5. Disposition 枚举

每条 movement record 必须有且仅有一个 disposition，只允许以下值：

- `PRESERVED_AS`；
- `MOVED_TO`；
- `REIMPLEMENTED_AS`；
- `DECLARED_LOSS`；
- `EXPLICITLY_REJECTED`；
- `UNASSIGNED_BLOCKER`。

禁止自由文本 disposition。`UNASSIGNED_BLOCKER` 是 blocker，不是 placeholder。

## 6. UNASSIGNED_BLOCKER gate

`UNASSIGNED_BLOCKER > 0` 时禁止：

- capability 或 capability-family promotion；
- phase 或 milestone 完成；
- candidate 进入 canonical target；
- legacy retirement 或 freeze；
- generator/parallel-worker output 被视为 promotion。

cell/file/test/hash closure 不能替代 movement closure。green tests 与 exact hashes
只证明 declared scope，不证明能力无损迁移。

## 7. Locator 与语义能力分离

locator（文件、模块、cell、测试计数、行范围）是证据，不是能力 taxonomy。
`legacy/donor semantic movement inventory` 是能力清单；`runtime authority inventory`
记录 live wiring points。两者必须分离，不能互相替代。

contract-only、unwired 或 disabled semantic capability 也必须落位、声明损失或拒绝，
不得因缺少 live owner 而删除。

## 8. 独立 review 双门

独立 review 必须同时检查两门：

1. `declared-scope correctness`：每条 movement record 必填字段完整、disposition
   合法、movement matrix 行唯一且可 trace；
2. `predecessor-to-successor movement completeness`：declared scope 内每条语义能力
   都有 movement record 或 explicit rejection record，无能力因缺 live owner 而消失，
   legacy trace 与 target trace 可映射，至少一条 failure/reverse-return case 被 trace，
   有 declared loss 或 explicit zero-loss declaration，`UNASSIGNED_BLOCKER` 计数已报告。

只审 declared scope 而漏审 predecessor-to-successor inventory 不构成通过。

## 9. Generator 与 parallel worker 规则

generator 与 parallel worker 只能消费已通过 completeness gate 的 spec；
generator 不得把 omission 固化为 schema。worker completion 只证明 bounded job
结束，不证明能力迁移或 promotion 被授权。worker output 若新增、删除或改写语义能力，
必须先折回 movement inventory，才能进入任何 promotion gate。

## 10. C7 最低语义链

`C7.1` 最低语义链必须覆盖：

```text
RawSnapshot
  -> NormalizedIngestEnvelope
  -> DigestionDecision
  -> one_of { Extract, Chunk, Summarize, PassThrough }
  -> StructuredMaterialCandidate
```

`DigestionDecision` 之后四个分支是 alternatives，不是顺序数组；每次只执行由
`DigestionDecision` 选择的那条路径，且 prefix、被选分支、suffix 保持有向顺序，
不默认四者串行，也不默认分支之间交换。机器可读表示见
`21_functorial-successor-semantic-movement-completeness-amendment.v1.json` 的
`c7_minimum_semantic_chain.ordered_prefix/decision_alternatives/ordered_suffix`。

随后：

```text
StructuredMaterialCandidate
  -> C7.2 Verify | Admit
  -> C7.3 Index | Graph Projection
  -> C7.4 Recovery
```

C7 拥有 format/structure processing：snapshot capture、envelope normalization、
digestion routing、extraction/chunking/summarization 与 structural candidate
formation 至 admission。C8 从 structured/admitted material 之后开始 typed
knowledge，不得吞并 raw-content structuring。链中每条边都必须有带 source
evidence 与 target acceptance trace 的 movement record；缺失边即
`UNASSIGNED_BLOCKER`，即使每个 cell 都有 locator。

## 11. Cell topology 保持

本 amendment 不要求新增顶级 C7 cell；C7 链可作为 `C7.1` 的显式子操作或
Program movements 表达，保持既有 30-cell topology。`C7.2 Verify|Admit` 是语义
gate，不是文件存在性检查。

## 12. 当前 C7 pilot 晋级 gate

当前 C7 pilot 在以下条件全部满足前不得晋级：

1. 生成 legacy/donor semantic movement inventory 与 successor movement matrix；
2. 补齐 legacy decision parity（`STRUCTURED_JSON`、`long-report`、`derived-report`、
   `pass-through`）；
3. `UNASSIGNED_BLOCKER == 0`；
4. 独立 review 双门通过。

## 13. 授权上限

本 amendment 只授权目标 Goal 在验证更新后的 freeze manifest 后，以
semantic movement completeness gate 作为下一授权阶段前提。它不授权 live provider、
外部 delivery、cutover、authority transfer 或 production canonical write；不自行
证明 P4 或 C7 完成；也不改变 02 manifest 中既有的 authority exclusions 与
goal gate。

Target Goal/thread: `01a0504c-47ef-77e1-9783-454dbcbe3697`

Supervisor thread: `01a05039-0c9c-7873-8d9f-b60ef1af179f`

## 14. 当前阶段语义与 P1–P3 retrospective backfill

本 amendment 不自行撤销或重新证明目标工作树已记录的 P0–P3 local-only promotion；
当前状态由可变 `03`/`04` 裁决。但在任何 P4 family/aggregate/candidate/authority
claim 之前，必须为 P1–P3 已完成 scope 做 retrospective movement-matrix
backfill，把 legacy/donor semantic movement inventory 与 successor movement
matrix 补到已完成范围。backfill 发现的 `UNASSIGNED_BLOCKER` 只阻断依赖它的
promotion/candidate，不伪造全局回滚。当前 C7 pilot 必须先完成
`12. 当前 C7 pilot 晋级 gate` 指定的 C7 matrix、legacy decision parity、
`UNASSIGNED_BLOCKER == 0` 与独立双门 review。

该规则的机器可读表示写入 `21` 的 `retrospective_backfill` 与
`current_stage_semantics` 字段；本文件与 21 对该规则的解释一致。

## 15. 机械化开发模型路由

当前迁移开发规范同时规定模型路由与 authority 边界：

- 已固定 IO 契约后的机械化开发默认交给 DeepSeek（含批量代码实现、机械重构、
  fixtures/tests/docs sync、格式化、确定性 generator/hash）；
- 主线/高推理模型独占 architecture、semantic movement matrix、frozen/normative
  authority、risk acceptance、promotion、integration 与 final review；
- DeepSeek 每个工作包必须显式给出目标/输入/输出/允许读写范围/验收；
- DeepSeek 不得扩大语义、修改 frozen semantics、决定 authority/cutover/promotion
  或回退他人改动；
- DeepSeek 输出仅是 implementation evidence，必须经主线 completeness 与
  promotion review 后才可进入任何 promotion gate。

该规则的机器可读表示写入 `21_functorial-successor-semantic-movement-completeness-amendment.v1.json`
的 `model_routing` 字段；本文件与 21 对该规则的解释一致。
