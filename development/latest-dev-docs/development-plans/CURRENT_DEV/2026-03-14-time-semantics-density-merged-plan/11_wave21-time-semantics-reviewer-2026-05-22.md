# Wave21 Time Semantics Reviewer（2026-05-22）

## 任务范围

独立复核 time semantics 三目录：

- `2026-03-02-source-time-window-smart-timestamp-plan`
- `2026-03-05-time-statistics-remediation-plan`
- `2026-03-14-time-semantics-density-merged-plan`

结论优先级：先判断 `closed / external_blocked / retired`，并聚焦 `production data semantic chain` 的边界是否可在仓内闭环。

## 总体结论

- 三目录均为 `external_blocked`。
- 共同原因是 `production_data_semantic_chain_live_validation_not_run` 在三处 evidence 均显式保留；检查器仅做本地确定性闭环，不等价于 production data closure。
- 当前缺口并不来自现有核心代码未落地，而是来自「外部运行条件/真实生产证据不足」与「生产数据体量与反馈链路可验证性缺失」。

## 逐目录复核

### 1) 2026-03-02-source-time-window-smart-timestamp-plan

- Decision：`external_blocked`
- Evidence：
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md` 对该目录记录 `partial`，并写明 `wave20_verified` 后仍为「生产数据语义链未封口」。
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-02-source-time-window-smart-timestamp-plan/06_wave15-source-time-production-readiness-2026-05-22.md` 报告 `production_data_semantic_chain=ready_not_run`，并说明可由 `--live-evidence-json` 额外补齐。
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-02-source-time-window-smart-timestamp-plan/07_wave17-source-time-production-sample-readback-gate-2026-05-22.md` 明确 `production_data_semantic_chain: ready_not_run` 且 `sample_does_not_claim_live_production=true`。
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-02-source-time-window-smart-timestamp-plan/08_wave20-time-semantics-sample-provenance-readback-2026-05-22.md` 明确未使用 live production data/public network/replay/生产 DB/API/UI readback，剩余：
    - `production_data_semantic_chain_live_validation_not_run`
    - `live_source_time_coverage_distribution_not_measured`
    - `live_decision_log_features_readback_not_verified`
- Risk：
  - 需要外部 live 生产查询路径与决策日志回读，单纯仓内重跑无法消除。
  - 历史源时间 backfill 与 source_time 覆盖率测算未在本地固定数据中闭合。
- 推荐迁档动作：
  - 保留目录在 CURRENT_DEV（当前仍有开放生产链任务），同时新增一个专用 live evidence 子任务目录（如 `wave21-*`）存放外部证据 JSON 与脚本复现说明，并把本目录状态标注为 `external_blocked + external evidence pending`。

### 2) 2026-03-05-time-statistics-remediation-plan

- Decision：`external_blocked`
- Evidence：
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md` 记录该目录为 `partial`，并写明 Wave14/Wave20 之后仍有生产验证未闭合项。
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-05-time-statistics-remediation-plan/09_wave14-time-density-current-state-evidence-2026-05-22.md` 说明局部检查为 `status=passed_with_known_gaps`，并保留 `external_gap`：决策日志 volume、反馈对齐、生产鲜度证明、historical backfill、release 门禁。
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-05-time-statistics-remediation-plan/08_wave12-time-density-decision-log-freshness-evidence-2026-05-22.md` 与 `07_wave10...` 同步写明本地 checker 不依赖 live 数据，live volume/alignment 未验证。
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-05-time-statistics-remediation-plan/10_wave20-time-semantics-sample-provenance-readback-2026-05-22.md` 明确 `production_data_semantic_chain_live_verified=false`，同一组 live-gap markers 未打通。
- Risk：
  - 当前 evidence 可用于 repo 内 deterministic 验证，但 release/gating 与 feedback 链路仍需生产采样才能合规宣告闭口。
  - 若缺少稳定的生产数据回放窗口，`production_state` 仍只能停留在 `partial`。
- 推荐迁档动作：
  - 在该目录内新增「`external_production_data_evidence`」章节（或子文件）专门承接外部数据补齐项；待 live 证据齐备后再评估是否从 CURRENT_DEV 下封存至 ARCHIVE_CLOSED。

### 3) 2026-03-14-time-semantics-density-merged-plan

- Decision：`external_blocked`
- Evidence：
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md` 对该目录记录 `partial`，并写明 Wave8/Wave10/Wave12/Wave20 后「生产数据语义链仍未封口」。
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-14-time-semantics-density-merged-plan/09_wave12-time-density-decision-log-contract-evidence-2026-05-22.md` 将生产 freshness/volume/alignment 明确标为 `external_gap`，并不作全局闭口。
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-14-time-semantics-density-merged-plan/10_wave20-time-semantics-sample-provenance-readback-2026-05-22.md` 与 `08_wave10...` 明确 `status=passed_with_known_gaps`、`production_data_semantic_chain_live_validation_not_run`。
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-14-time-semantics-density-merged-plan/README.md` 与 `05_merged-unified-report...` 均为主读本，未见已进入 release 级 production 终止条件。
- Risk：
  - 决策链中 OPE/反馈体量、生产决策日志读回、外部服务配置验证仍待外部条件满足。
  - 已有 deterministic contract 通过不足以支持闭口决策，容易出现「docs 一致但生产链路不稳定」误判。
- 推荐迁档动作：
  - 维持本目录在 CURRENT_DEV 作为主入口，但新增 `archive-ready` 标记仅当 `production_data_semantic_chain` 引入 live evidence 后才可考虑迁入 `ARCHIVE_CLOSED`；当前阶段建议先创建 `2026-05-22-wave21-proof-gap` 运行证据集并挂在该目录。

## 生产语义链归因结论

- 结论：`production_data_semantic_chain` 不是仓内代码实现缺口，而是外部条件缺口（生产服务/真实决策日志/反馈量级/运行时证据）。  
- 三目录共同属于「可重复的本地确定性门禁已建立，但生产证明缺失」状态；应归类为 **`external_blocked`**，不应误标 `closed`。

