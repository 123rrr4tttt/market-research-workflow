# MRW 函子化后继迁移冻结合同族索引

Status: `FROZEN_FOR_IMPLEMENTATION · AMENDED_V2.3 · USER_APPROVED_2026-09-01`

Frozen topic root:

`/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration`

本文件只与 `02_functorial-successor-migration-development-contract.freeze.json` 中完全匹配的 SHA-256 一起生效。任一冻结成员字节变化都会使冻结失效，并要求重新审查和重新生成 manifest。

## 合同优先级

1. 本文件裁决冻结族成员、优先级、授权上限与下一阶段。
2. `18_functorial-successor-effect-failed-state-machine-amendment.v1.md` 与 `19_functorial-successor-effect-failed-state-machine-amendment.v1.json` 只对冻结 §10.5 增加 `RUNNING + EffectFailed -> FAILED`，并优先裁决该事件的 guard、effect disposition 与 Step/Run 分离。
3. `20_functorial-successor-semantic-movement-completeness-amendment.v1.md` 与 `21_functorial-successor-semantic-movement-completeness-amendment.v1.json` 把 semantic movement completeness 规定为 P1/P3/P4/P5、CapabilitySpec pilot 与 candidate review 的强制输入，裁决 movement record 字段、disposition 枚举、`UNASSIGNED_BLOCKER` 阻断、双门独立 review、generator/worker 规则、C7 最低语义链与机械化开发模型路由。cell/file/test/hash closure 不等于 movement closure；locator 是证据，不是能力 taxonomy。
4. `06_functorial-successor-runtime-architecture-correction.draft.zh-CN.md` 裁决综合信息研究语义、程序运行元语言、同构 RuntimeNode、public/project 双平面、F-0/F-1/P0–P2 顺序与 first specimen。
5. `10_functorial-successor-domain-contract-snapshot.v1.json`、`11_functorial-successor-first-specimen-contract.v1.json`、`16_functorial-successor-first-specimen-schema-bundle.v1.1.schema.json`、`17_functorial-successor-requiredness-correction.freeze-amendment.v1.json`、`14_functorial-successor-crash-window-fixtures.v1.json` 裁决第一阶段机器可读语义、字段映射与反例。
6. `09_functorial-successor-f0-semantic-owner-inventory.v1.json` 裁决 first-specimen owner/readback 边界；`13_functorial-successor-c1-c9-locator-pending-inventory.v1.json` 只冻结 locator 与 `ELIGIBILITY_PENDING`，不预判 P1 disposition。
7. `08_symmetric-functorial-architecture-diagram-atlas.draft.zh-CN.md` 是冻结规范图集；图不得脱离文字合同单独授权。
8. `15_functorial-successor-old-goal-stop-receipt.v1.json` 只裁决旧 Goal 不可复用与新 Goal gate，不授予实现完成状态。
9. `00_functorial-successor-migration-development-contract.draft.md` 只保留未被上述文件覆盖的 worktree census、能力无损、legacy adapter、parity、rollback、authority ceiling 与最终审查纪律。
10. `00_functorial-successor-migration-development-contract.draft.zh-CN.md` 是非权威中文翻译参考。
11. `07_functorial-successor-architecture-diagram-atlas.draft.zh-CN.md` 与 `12_functorial-successor-first-specimen-schema-bundle.v1.schema.json` 为 `SUPERSEDED_NON_NORMATIVE_EVIDENCE`，不得进入实现裁决。

## 冻结成员摘要

| 文件 | 角色 | SHA-256 |
| --- | --- | --- |
| `00_functorial-successor-migration-development-contract.draft.md` | 基础约束 source draft | `5c4a886b9d921abde9fc30c00345e995ef355935c1dfc3fcc3d075e279157eb3` |
| `06_functorial-successor-runtime-architecture-correction.draft.zh-CN.md` | 规范架构合同 | `c93b58e15a3dbaa1e5e1be9bebfbc41143b97b8e91eb9774851d1f5d78fe3a93` |
| `08_symmetric-functorial-architecture-diagram-atlas.draft.zh-CN.md` | 规范主图集 | `bf84d20eba925d58ee36021d2e064af67bc8daef69ac234bc73c6396653931c9` |
| `09_functorial-successor-f0-semantic-owner-inventory.v1.json` | F-0 owner inventory | `c12a948a356184ceae5b58dbc85deb96759ff74d89f3b2dd09a4e719b9033741` |
| `10_functorial-successor-domain-contract-snapshot.v1.json` | DomainContractSnapshot | `1dd4c2c12c6a8c164b9f5b1464ae9801347b14a6a3ed75bf202c45b255b59959` |
| `11_functorial-successor-first-specimen-contract.v1.json` | first-specimen contract | `debd744d90e0dbad1d3c0a10c1482b5d2abcbdf54ca2129ddd5ddeafd92579a8` |
| `12_functorial-successor-first-specimen-schema-bundle.v1.schema.json` | superseded first-specimen schema evidence | `232787dc2493c759cc54182df0576a5256c4f8b20fc4b977c0d54b560addef5c` |
| `13_functorial-successor-c1-c9-locator-pending-inventory.v1.json` | C1–C9 locator inventory | `dcb1a3f09c54ee787f9ebae698b8b75c707fd5b8b1c23569fcca8ebc29be2c38` |
| `14_functorial-successor-crash-window-fixtures.v1.json` | declarative crash fixtures | `59bd849c02f50a28509f5964a4baacfe6275e2fc4a29ce7f1bed4efcdf855636` |
| `15_functorial-successor-old-goal-stop-receipt.v1.json` | old Goal stop receipt | `b75a9a7e408035dd69fd69775a61d9045ba8f52d962278de840e17fdf8ee34c0` |
| `16_functorial-successor-first-specimen-schema-bundle.v1.1.schema.json` | normative first-specimen schema | `8be6c2757a091efcd1a34de0e64a2a9804b5629f7a545b784ea674068c25b51e` |
| `17_functorial-successor-requiredness-correction.freeze-amendment.v1.json` | requiredness correction and field mapping | `6da23cb1201482599d9759e1b6405f806e4765e71f20ca01e2913cdc844f0544` |
| `18_functorial-successor-effect-failed-state-machine-amendment.v1.md` | normative EffectFailed state amendment | `057821fe6536988eddd84d75d1f955f0ff1919e37b27812bd259482e6e9a96c9` |
| `19_functorial-successor-effect-failed-state-machine-amendment.v1.json` | machine-readable EffectFailed amendment | `a0ca2e5406fd071d0902e66ebb2b38938ae42c365fe57ff921bfaa8b7ec78e6e` |
| `20_functorial-successor-semantic-movement-completeness-amendment.v1.md` | normative semantic movement completeness amendment | `dedf28b7712e7f66649fa2f68c66811129abd4777acc7d351765c693765e9278` |
| `21_functorial-successor-semantic-movement-completeness-amendment.v1.json` | machine-readable semantic movement completeness amendment | `85da71a5d6d1b0e5a90f2344ba79d79d2934d679cdc331c138bfb023b9cddf90` |

完整 bytes、lines、baseline、legacy disposition 与 review 记录以 `02` manifest 为准。

## 已冻结的核心观点

异构任务不被取消。它们的语义、effect、resource、failure、authority 和 canonical owner 被编码为版本化 `ObjectContract/OperationContract/Profile/HandlerBinding`；Program AST、ExecutionPlan、RuntimeAssignment、claim/lease/recovery 和 RuntimeNode protocol 保持同质。新增异构任务的正常路径不得修改共享 AST、compiler fold、通用 reducer 或 work-item 根 schema。

## 授权与禁止

当前续作授权边界为同一 Goal 的 `semantic movement completeness gate`，通过后进入 `P4 capability-spec pilot`：同步 v2.3 冻结族，把 legacy/donor semantic movement inventory 与 successor movement matrix 作为 P1/P3/P4/P5、CapabilitySpec pilot 与 candidate review 的强制输入，并在 movement matrix、legacy decision parity（`STRUCTURED_JSON`/`long-report`/`derived-report`/`pass-through`）、`UNASSIGNED_BLOCKER == 0` 与独立双门 review 完成前不晋级。cell/file/test/hash closure 不能替代 movement closure。本 amendment 不自行撤销或重新证明目标工作树已记录的 P0–P3 local-only promotion；当前状态由可变 `03`/`04` 裁决。但在任何 P4 family/aggregate/candidate/authority claim 前，必须为 P1–P3 已完成 scope 做 retrospective movement-matrix backfill；backfill 发现的 `UNASSIGNED_BLOCKER` 只阻断依赖它的 promotion/candidate，不伪造全局回滚。当前 C7 pilot 必须先完成 20/21 指定的 C7 matrix、legacy decision parity、zero-unassigned 与独立双门 review。v2.3 不授权 live provider、external delivery、cutover、authority transfer 或 candidate；production canonical write 仍受 02 authority exclusions 约束。

已固定 IO 契约后的机械化开发默认交给 DeepSeek（批量代码实现、机械重构、fixtures/tests/docs sync、格式化、确定性 generator/hash）；架构、semantic movement matrix、frozen/normative authority、risk acceptance、promotion、integration 与 final review 由主线/高推理模型独占。DeepSeek 工作包必须给出目标/输入/输出/允许读写范围/验收，不得扩大语义、修改 frozen semantics、决定 authority/cutover/promotion 或回退他人改动；其输出只是 implementation evidence，必须经主线 completeness 与 promotion review。

`03_functorial-successor-migration-development-progress.md` 与 `04_functorial-successor-capability-ledger.json` 是 Goal 生命周期中的可变 current-state artifacts，不属于不可变冻结内容；其初始摘要与 digest 由 `02` manifest 记录。

开发完成后，目标任务必须主动返回以 `SUPERVISOR_REVIEW_REQUEST` 开头的监督请求；未经过本监督任务独立复核，不得把 Goal 结果表述为最终通过。
