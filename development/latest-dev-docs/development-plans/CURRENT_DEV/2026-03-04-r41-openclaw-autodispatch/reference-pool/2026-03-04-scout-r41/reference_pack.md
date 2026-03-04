# Reference Pack — 2026-03-04-scout-r41

line: A
lane_focus: 趋势门禁锚点冻结升级 + 漂移审批链
must:
- trend comparability 必须输出 anchor_freeze_id/anchor_epoch/freeze_approver_chain，跨批比较需锚点一致。
- baseline_shift_reason 必须绑定 shift_ticket_id，未绑定不得进入 blocking gate。
optional:
- 增加锚点漂移热力图（按 service/stream）。
- 增加跨窗口口径差异摘要。
do_not:
- 不允许无 freeze_approver_chain 的锚点变更。
- 不允许 anchor_epoch 缺失时宣告“可同比”。
tests_metrics:
- metric: anchor_freeze_annotation_rate (target=100%)
- metric: unauthorized_anchor_shift_rate (target=0)
rollback_pointer: 回退至 R40 baseline_lock_id/release_window_tag 口径
innovation_direction: 锚点冻结审批化
innovation_hypothesis: 锚点漂移绑定审批链可降低跨批趋势误判。

line: B
lane_focus: required-check 预算硬封顶后自动降级编排
must:
- exception debt_budget_key 达到 hard_cap 后必须输出 auto_degrade_plan_ref 与 owner_ack。
- critical_path recovery_sla_minutes 超时需输出 escalation_stage（warn/block/freeze）。
optional:
- 增加预算消耗预测与回收建议。
- 增加关键路径阶段性恢复看板。
do_not:
- 不允许 hard_cap 触发后继续常规 exception 放行。
- 不允许 critical-path 无 escalation_stage。
tests_metrics:
- metric: hard_cap_auto_degrade_coverage_rate (target=100%)
- metric: critical_path_escalation_annotation_rate (target=100%)
rollback_pointer: 回退到 R40 debt_budget + recovery_sla 阻断策略
innovation_direction: 预算封顶自动降级化
innovation_hypothesis: 预算封顶后自动降级可避免例外债务失控外溢。

line: C
lane_focus: 合同评分归一升级 + waiver 生命周期闭环
must:
- compatibility_score 必须附 normalization_profile_id 与 profile_signature，确保跨团队一致计算。
- waiver 必须输出 lifecycle_state（proposed/approved/sunset）与 sunset_checkpoint_ref。
optional:
- 增加 profile 漂移回放报告。
- 增加 waiver 到期迁移风险分层。
do_not:
- 不允许未知 normalization_profile_id 参与 release gate。
- 不允许 waiver 无 sunset_checkpoint_ref。
tests_metrics:
- metric: normalization_profile_coverage_rate (target=100%)
- metric: waiver_lifecycle_closure_rate (target>=98%)
rollback_pointer: 回退到 R40 score_formula_version + consumer_ack_refs
innovation_direction: 评分归一配置签名化
innovation_hypothesis: 归一配置签名可显著降低口径分叉导致的兼容争议。

line: D
lane_focus: 吊销回放决定性证明 + 时效异常分层
must:
- replay_consistency_hash 必须同时输出 deterministic_replay_proof（seed+runtime_fingerprint）。
- readiness_proof_sla 超时需标注 timeout_severity 与 remediation_ticket。
optional:
- 增加多验证器差异根因聚类。
- 增加回放失败自动再验证窗口。
do_not:
- 不允许无 deterministic_replay_proof 的回放结果进入 final audit。
- 不允许 readiness_proof_sla 超时无 remediation_ticket。
tests_metrics:
- metric: deterministic_replay_proof_coverage_rate (target=100%)
- metric: readiness_timeout_remediation_binding_rate (target=100%)
rollback_pointer: 回退到 R40 replay_consistency_hash + readiness_proof_sla
innovation_direction: 回放决定性证明化
innovation_hypothesis: 决定性证明可显著降低“同证据不同结论”审计风险。

line: E
lane_focus: deep-health 演练窗口强门禁 + 阈值来源签名
must:
- multi_dim_threshold 必须附 threshold_source_signature 与 policy_epoch。
- drill_proof_ref 必须满足 freshness_window_days，超窗自动 warning->block。
optional:
- 增加阈值变更成本影响评估。
- 增加依赖链恢复瓶颈分解。
do_not:
- 不允许 threshold_source_signature 缺失进入自动决策。
- 不允许 drill_proof 超窗仍维持 ready verdict。
tests_metrics:
- metric: threshold_signature_coverage_rate (target=100%)
- metric: drill_freshness_window_conformance_rate (target>=95%)
rollback_pointer: 回退到 R40 threshold version + drill_proof_ref freshness
innovation_direction: 演练窗口强门禁化
innovation_hypothesis: 演练窗口强门禁可降低“纸面恢复、实战失效”概率。

line: F
lane_focus: 质量校准锚点治理 + break-glass 审批链完备
must:
- calibration verdict 必须附 calibration_anchor_lineage 与 comparable_batch_set_hash。
- break-glass 必须输出 approval_chain_ref + expiry_guard，过期自动失效。
optional:
- 增加跨批漂移归因模板。
- 增加 debt 封顶后服务降级路径建议。
do_not:
- 不允许无 comparable_batch_set_hash 的分数用于趋势宣告。
- 不允许 break-glass 无 expiry_guard。
tests_metrics:
- metric: calibration_anchor_lineage_coverage_rate (target=100%)
- metric: breakglass_expiry_guard_coverage_rate (target=100%)
rollback_pointer: 回退到 R40 comparable_batch_set + hard_cap_policy
innovation_direction: 校准锚点谱系化 + 审批链时效化
innovation_hypothesis: 锚点谱系 + 过期护栏能抑制质量门禁长期漂移。

next-batch-trigger: 主控可将 R41 作为 research(+1) 输入，优先 B→F→D 收敛“预算封顶执行+校准谱系+回放决定性”，再并行 A/C/E。
