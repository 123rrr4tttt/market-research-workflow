# R41 Interface Contract

Version: `R41`  
Source batch: `2026-03-04-scout-r41`

## Scope

- This document extracts interface-level contracts for R41 from:
  - `reference-pool/2026-03-04-scout-r41/AB-envelope.md`
  - `reference-pool/2026-03-04-scout-r41/CD-envelope.md`
  - `reference-pool/2026-03-04-scout-r41/EF-envelope.md`
  - `reference-pool/2026-03-04-scout-r41/codex_handoff.md`
- Contract-only, no code implementation details.

## Contract Matrix

| Line | Input Contract | Output Contract | Gate / Validator | Failure Isolation |
|---|---|---|---|---|
| A | `gate_trend.v6` (`anchor_freeze_id`, `confidence_band`, `sample_floor`, `approval_ticket_id`) | `comparability_verdict`, `freeze_decision_trace`, `window_guard_status` | `anchor schema validator`, `shift-ticket policy lint` | degrade advisory + keep baseline lock; manual audit on bind failure |
| B | `required_check.topology.v5` (`critical_path`, `tier_deadline_minutes`, `debt_budget_key`, `hard_cap_state`) | `auto_degrade_plan_ref`, `deadline_violation_class`, `owner_ack` | `budget hard-cap validator`, `escalation policy lint` | keep manual freeze; fallback recovery gate |
| C | compatibility payload with profile/signature fields | `compatibility_score` + reason/evidence + waiver lifecycle fields | `profile signature validator`, `waiver lifecycle lint` | downgrade warning or keep manual gate |
| D | replay seed/fingerprint + timeout context | replay proof envelope + timeout remediation envelope | `replay proof checker`, `timeout remediation lint` | disable auto-pass; escalate blocking review |
| E | threshold source signatures + drill proof freshness fields | staged readiness envelope (`signature_continuity_status`, `freshness_violation_stage`, `decision_trace_id`) | `threshold signature validator`, `drill freshness lint` | fallback threshold policy; auto degrade + manual approval |
| F | calibration lineage set + break-glass chain fields | calibration governance envelope (`lineage_closure_verdict`, `expiry_invalidation_status`, `debt_cap_status`) | `calibration lineage validator`, `breakglass expiry lint` | manual approval downgrade; force block when expiry fields missing |

## R41 Required Fields (by line)

- A: `anchor_freeze_id`, `anchor_epoch`, `freeze_approver_chain`, `shift_ticket_id`
- B: `auto_degrade_plan_ref`, `owner_ack`, `escalation_stage`
- C: `normalization_profile_id`, `profile_signature`, `score_reason_code`, `evidence_digest`, `lifecycle_state`, `sunset_checkpoint_ref`
- D: `deterministic_replay_proof`, `seed`, `runtime_fingerprint`, `timeout_severity`, `remediation_ticket`
- E: `threshold_source_signature`, `policy_epoch`, `drill_proof_ref`, `freshness_window_days`
- F: `anchor_lineage`, `comparable_batch_set_hash`, `approval_chain_ref`, `expiry_guard`

## Acceptance Targets

- Coverage fields target: `100%` unless line policy explicitly allows fallback.
- Waiver lifecycle closure: `>=98%` (line C).
- Drill freshness conformance: `>=95%` (line E).

## Compatibility

- All contracts are R41-compatible and can fallback to previous-round baselines as described in each line's failure isolation.
- Implementation lanes should keep `research(+1) / interface(-1)` sequencing constraints.
