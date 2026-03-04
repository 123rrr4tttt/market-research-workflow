# EF Envelope Seed — from R41 Research Lane

- source_batch: `2026-03-04-scout-r41`
- target_batch: `2026-03-04-scout-r41`
- scope: `envelope-only`

## E-line envelope (R41)
- focus: threshold source signing continuity + drill freshness violation staged enforcement
- expected_io:
  - input: threshold source signatures (`threshold_source_signature`, `policy_epoch`) + drill proof refs (`drill_proof_ref`, `freshness_window_days`) + violation history
  - output: staged readiness envelope (`signature_continuity_status`, `freshness_violation_stage`, `decision_trace_id`, `remediation_deadline_ref`)
- boundary: no business implementation in this lane

## F-line envelope (R41)
- focus: calibration anchor lineage closure + break-glass expiry hard invalidation
- expected_io:
  - input: calibration lineage set (`calibration_anchor_lineage`, `comparable_batch_set_hash`) + break-glass chain (`approval_chain_ref`, `expiry_guard`) + override debt snapshot
  - output: calibration governance envelope (`lineage_closure_verdict`, `expiry_invalidation_status`, `debt_cap_status`, `advisory_flag`)
- boundary: no business implementation in this lane

status: ready-for-R41-research-expansion-only
