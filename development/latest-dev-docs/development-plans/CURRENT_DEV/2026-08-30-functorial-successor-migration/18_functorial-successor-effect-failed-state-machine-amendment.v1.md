# MRW 后继运行时 `EffectFailed` 状态机冻结修正

Status: `FROZEN_AUTHORIZED · ADDITIVE_NORMATIVE_AMENDMENT`

Authorized by user: `2026-08-31`

Authority source: direct user authorization in supervisor task `01a05039-0c9c-7873-8d9f-b60ef1af179f`

Authority decision: authorize only `StepEvent.EFFECT_FAILED`, `RUNNING -> FAILED`, and `EffectDisposition.FAILED`

Resolved blocker: `P0C_EFFECT_FAILED_NORMATIVE_AMENDMENT_REQUIRED`

Base architecture contract:

`06_functorial-successor-runtime-architecture-correction.draft.zh-CN.md`

Base architecture SHA-256:

`c93b58e15a3dbaa1e5e1be9bebfbc41143b97b8e91eb9774851d1f5d78fe3a93`

## 1. 修正原因

冻结合同已经定义 interpreter 只能返回 `SUCCEEDED | FAILED | OUTCOME_UNKNOWN`，但 §10.5 只为 success 与 unknown 提供了普通 effect-step 转换，没有为确定性 `FAILED` 提供 reducer event。结果是正常 interpreter failure 只能被错误地表示为 receipt lost、branch skip、admission rejection、readback failure，或绕过 reducer 直接写数据库。

本 amendment 只补全已存在的 `FAILED` outcome，不增加新的 effect family、重试权限、完成语义或 canonical authority。

本 amendment 对 `06` 的 §10.5 增加唯一一条 effect-step 边，并收紧 §10.4 中 `RequiredStepFailed` 的派生 guard。除这两个明确裁决外，`06` 的其他条款继续有效；尤其不裁决或追认 §4.7 与 §10.5 之间尚待单独处理的 branch 边。

## 2. 新增规范事件

```text
StepEvent.EFFECT_FAILED = "EffectFailed"
```

唯一新增 StepState 转换：

```text
RUNNING + EffectFailed -> FAILED
```

对应 effect disposition：

```text
EffectDisposition.IN_FLIGHT -> EffectDisposition.FAILED
```

`FAILED` 已属于冻结 StepState 和 EffectDisposition 集合；本修正不新增状态。

## 3. Guard 与绑定

`EffectFailed` 只能在以下条件全部成立时进入 reducer：

- step 当前为 `RUNNING`；
- exact `RuntimeAssignment`、`HandlerBinding`、attempt、execution epoch、incarnation 和 expected step revision 匹配；
- 同一 active attempt 的 claim、未过期 lease、current authority、expected revision 与 CAS 前置条件全部有效；
- interpreter 返回确定性的 typed `FAILED`，而不是 `OUTCOME_UNKNOWN`、cancel、branch disposition 或 admission result；
- failure body 已写入 project-scoped value/failure store，public control plane 只保存 bounded `failure_ref/failure_digest`；
- event metadata 满足 allowlist，并与 assignment/attempt/failure closure digest 绑定。

任何 guard 失败都不得写 `EffectFailed` 或直接更新 step snapshot。

stale assignment、attempt、epoch、incarnation、claim、lease、authority 或 revision 只能 fail closed；不得借 recovery protocol 把 stale submit 转换为 `EffectFailed`。

事件由 `RuntimeNode/interpreter` 形成；纯 reducer 独占合法转换判定；`RuntimeUnitOfWork` 独占 event、step snapshot 与 effect disposition 的原子持久化。emitter 不得直接写 terminal snapshot，repository/UoW 也不得绕过 reducer 自行推断合法边。

## 4. 明确不等价关系

`EffectFailed` 不得替代或被以下事件替代：

- `EffectReceiptLost`：结果可能已发生但未知，必须进入 `RECONCILING`；
- `AuthoritativeReadbackFailed`：recovery handler readback 后确认失败，只能从 `RECONCILING` 发生；
- `BranchSkipped/BranchNotSelected`：语义分支没有执行；
- `CommitOrDeliveryRejected`：admission 或 delivery commit/readback 被拒绝；
- `CancellationRequested`：用户/authority 取消，不是 interpreter failure。

本 amendment 不授权任何 branch transition，包括但不限于 `BranchSelected`、`BranchUnresolved` 及其 Step/Run 后态。未列入冻结 §10.5 的 branch 边继续 fail closed；实现可以使用既有合法边表达 selected activation，或等待独立 additive amendment，不得由本文件追认。

## 5. Step 与 Run 分离

`EffectFailed` 只把当前 step 折叠为 `FAILED`。它不得直接写 Run terminal state。

Run 是否失败由 frozen completion/failure policy 另行派生：

```text
RunEvent.REQUIRED_STEP_FAILED
nonterminal RunState -> FAILED
```

该派生必须从持久化 `QualifiedPlan` 的 required-step membership、`CompletionPolicy` 与冻结 failure policy 读取资格。调用者提供的 `failure_is_required`、请求字段、默认布尔值或非持久化推断均不得成为 `RequiredStepFailed` 的 guard。reconciliation 对 `AuthoritativeReadbackFailed` 的处理同样必须先证明目标 step 是 required，且 failure policy 不允许继续。

若 Program 的 failure policy 允许 retry、fallback、partial result、error accumulation 或 successor materialization，则必须按相应显式控制/新 execution epoch 处理；不得由 `EffectFailed` 自动重试或重排。

## 6. Retry、unknown 与 cancellation

- retry 仍要求 `RetryAuthorized`、剩余 budget、retryable failure 和新的 execution epoch/attempt；
- `OUTCOME_UNKNOWN` 仍走 `EffectReceiptLost -> RECONCILING`，不得降格为 `EffectFailed`；
- cancellation 仍走 `CANCEL_REQUESTED/CANCELLING`；
- lease expiry、node loss 或缺少 receipt 永远不是确定性 `EffectFailed` 证明；
- 不允许因加入本事件而重复执行非幂等 effect。

## 7. 冻结实现映射与验证

目标实现证据：

| 文件 | SHA-256 |
| --- | --- |
| `main/backend/app/successor_runtime/runtime/transitions.py` | `953e7c136fdc767493cf0da663b9d2ac46e19b781728fd3c809b072280b1c584` |
| `main/backend/app/successor_runtime/runtime/reducer.py` | `5cc248352d99e0738681df92974e2c50eb77d16234a756073a4877d625a8f388` |
| `main/backend/tests/successor_runtime/test_p0c_postgres_lifecycle.py` | `da4323537aa9b999ce3c7e9a2100a2d058bdbe5ef04c0044f24c673ca0fc7a46` |

P0-C promotion recheck 至少验证：

1. 合法 `RUNNING + EffectFailed -> FAILED`；
2. 非 `RUNNING` source state 拒绝该事件；
3. reducer 同时产生 `EffectDisposition.FAILED`；
4. step failure 不直接修改 Run；
5. required failure 通过独立 `RunEvent.REQUIRED_STEP_FAILED` 使 Run 失败；
6. unknown、readback failure、admission rejection、branch 与 cancellation 保持独立；
7. public control plane 不持久化 failure body bytes；
8. retry 创建新 epoch/attempt，不原地重放 effect。
9. caller-supplied `failure_is_required` 不能控制 Run terminal state；requiredness 从 persisted plan/policy 派生；
10. failed readback 只在 persisted requiredness 与 failure policy 允许时派生 `RequiredStepFailed`；
11. `BranchSelected/BranchUnresolved` 等未冻结 branch 边未被本 amendment 默许。

## 8. 授权上限

本 amendment 只授权目标 Goal 在验证更新后的 freeze manifest 后解除 `P0C_EFFECT_FAILED_NORMATIVE_AMENDMENT_REQUIRED`，重新执行 P0-C promotion review。它不自行证明 P0-C 完成，也不授权 P0-D、live provider、外部 delivery、candidate、cutover 或 authority transfer。

冻结时列出的实现哈希只证明 amendment 形成时的目标工作树观测身份，不证明实现已经符合本文件新增的 persisted-requiredness、owner 分离或 branch 排除要求。目标 Goal 必须修正并重新取证后才能通过 P0-C promotion。
