# Dedup Diff — 2026-03-04-scout-r41

baseline_batch: 2026-03-04-scout-r41
compare_target:
- /Users/wangyiliang/Desktop/openclaw/docs/reference-pool/2026-03-04-scout-r41/reference_pack.md
- /Users/wangyiliang/Desktop/openclaw/docs/reference-pool/2026-03-04-scout-r41/codex_handoff.md

## dedup decision summary
- retain: R40 六线主轴不变（A趋势口径、B required-check、C兼容评分、D provenance、E deep-health、F质量门禁）。
- replace: 从“字段补齐”升级为“审批链/签名/时效护栏”强约束。
- preserve-nonconflict: R40 指标与回退锚点保留，R41 采用向后兼容扩展。

## conflict and overlap check
- B vs F: 均涉及预算与豁免；B 管 required-check 例外预算封顶，F 管质量 override 审批时效，边界清晰。
- A vs C: 均涉及可比性；A 管趋势锚点冻结，C 管评分归一配置签名，互补不冲突。
- D vs E: 均涉及时效证明；D 管吊销回放决定性，E 管恢复演练窗口，分轨独立。

## novelty delta (vs r40)
- A 新增：anchor_freeze_id/anchor_epoch/freeze_approver_chain + shift_ticket_id。
- B 新增：hard_cap auto_degrade_plan_ref + escalation_stage。
- C 新增：normalization_profile_id/profile_signature + waiver lifecycle_state。
- D 新增：deterministic_replay_proof + timeout remediation binding。
- E 新增：threshold_source_signature/policy_epoch + freshness_window_days。
- F 新增：calibration_anchor_lineage/comparable_batch_set_hash + expiry_guard。

## acceptance for handoff
- sources: 官方文档/成熟项目来源已附。
- boundaries: 已标注 advisory 与 hard-block 切换边界。
- dedup: 已给出替代/保留声明。
- ready_for_r41_buildlane: yes
