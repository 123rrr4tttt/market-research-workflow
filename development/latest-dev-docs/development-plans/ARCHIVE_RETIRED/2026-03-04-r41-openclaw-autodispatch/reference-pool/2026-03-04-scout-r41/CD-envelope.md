# C/D Envelope — 2026-03-04-scout-r41

## Line C (R41 envelope)
- focus: compatibility explainability closure + exception review cadence hardening
- must:
  - `compatibility_score` 增加 `score_reason_code` + `evidence_digest`
  - exception 增加 `review_cycle` + `next_review_due_at`
- gate metrics:
  - `compatibility_reason_coverage_rate` (target=100%)
  - `exception_review_schedule_binding_rate` (target>=99%)
- rollback: 回退到 R41 `normalization_profile_id + profile_signature`

## Line D (R41 envelope)
- focus: replay evidence notarization + timeout remediation SLA closure
- must:
  - `deterministic_replay_proof` 增加 `proof_notary_id` + `proof_issued_at`
  - `remediation_ticket` 增加 `sla_deadline_at` + `owner_ack_ref`
- gate metrics:
  - `replay_proof_notary_binding_rate` (target=100%)
  - `timeout_remediation_sla_binding_rate` (target=100%)
- rollback: 回退到 R41 `seed/runtime_fingerprint + timeout_severity`

control-resume-trigger: 请总控开启下一任务
