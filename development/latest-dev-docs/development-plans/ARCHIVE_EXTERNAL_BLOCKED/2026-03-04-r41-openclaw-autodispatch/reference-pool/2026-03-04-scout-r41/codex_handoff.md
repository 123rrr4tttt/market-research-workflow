# Codex Handoff — 2026-03-04-scout-r41

line: A
lane_focus: anchor freeze governance + drift approval chain
must_to_atomic:
- task_id: A-R41-M1
  goal: trend gate 增加 anchor_freeze_id/anchor_epoch/freeze_approver_chain
  acceptance: anchor freeze annotation coverage = 100%
  minimal_gate: anchor schema validator green
  failure_isolation: 缺失时降级 advisory 并保留 R40 baseline lock
- task_id: A-R41-M2
  goal: baseline_shift_reason 绑定 shift_ticket_id
  acceptance: unauthorized anchor shift violation = 0
  minimal_gate: shift-ticket policy lint pass
  failure_isolation: 绑定失败时转人工审计

line: B
lane_focus: budget hard-cap auto degrade + critical-path staged escalation
must_to_atomic:
- task_id: B-R41-M1
  goal: hard_cap 触发后输出 auto_degrade_plan_ref + owner_ack
  acceptance: hard-cap auto degrade coverage = 100%
  minimal_gate: budget hard-cap validator pass
  failure_isolation: 触发异常时保留 manual freeze
- task_id: B-R41-M2
  goal: critical-path 增加 escalation_stage(warn/block/freeze)
  acceptance: escalation annotation coverage = 100%
  minimal_gate: escalation policy lint pass
  failure_isolation: 缺失时退回 R40 recovery_sla gate

line: C
lane_focus: normalization profile signing + waiver lifecycle closure
must_to_atomic:
- task_id: C-R41-M1
  goal: compatibility score 增加 normalization_profile_id/profile_signature
  acceptance: normalization profile coverage = 100%
  minimal_gate: profile signature validator green
  failure_isolation: 签名缺失时降级 warning
- task_id: C-R41-M2
  goal: waiver 生命周期输出 lifecycle_state + sunset_checkpoint_ref
  acceptance: waiver lifecycle closure >=98%
  minimal_gate: waiver lifecycle policy lint pass
  failure_isolation: 缺失时保持人工 gate

line: D
lane_focus: deterministic replay proof + timeout remediation binding
must_to_atomic:
- task_id: D-R41-M1
  goal: replay 增加 deterministic_replay_proof(seed/runtime_fingerprint)
  acceptance: deterministic replay proof coverage = 100%
  minimal_gate: replay proof checker green
  failure_isolation: proof 缺失时禁用自动通过
- task_id: D-R41-M2
  goal: readiness 超时绑定 timeout_severity + remediation_ticket
  acceptance: timeout remediation binding = 100%
  minimal_gate: timeout remediation lint pass
  failure_isolation: 绑定失败时升级 blocking review

line: E
lane_focus: threshold source signing + drill freshness window enforcement
must_to_atomic:
- task_id: E-R41-M1
  goal: workload_profile 增加 threshold_source_signature + policy_epoch
  acceptance: threshold signature coverage = 100%
  minimal_gate: threshold signature validator pass
  failure_isolation: 缺失时回退 R40 threshold version policy
- task_id: E-R41-M2
  goal: drill_proof_ref 增加 freshness_window_days 强门禁
  acceptance: freshness window conformance >=95%
  minimal_gate: drill freshness window lint pass
  failure_isolation: 不达标时自动降级并转人工审批

line: F
lane_focus: calibration anchor lineage + break-glass expiry guard
must_to_atomic:
- task_id: F-R41-M1
  goal: calibration 输出 anchor_lineage + comparable_batch_set_hash
  acceptance: anchor lineage coverage = 100%
  minimal_gate: calibration lineage validator pass
  failure_isolation: 缺失时降级 manual approval
- task_id: F-R41-M2
  goal: break-glass 输出 approval_chain_ref + expiry_guard
  acceptance: expiry guard coverage = 100%
  minimal_gate: breakglass expiry policy lint pass
  failure_isolation: 缺失时强制阻断并要求审批补齐

next-batch-trigger: 主控可基于 R41 下发 build lane，建议先 B→F→D，再 A/C/E 并行收敛。
