# AB Envelope (R41 research-only)

- source_batch: `2026-03-04-scout-r40`
- target_batch: `2026-03-04-scout-r41`
- scope: `A/B envelope only (no business code changes)`

## A-line envelope
- focus: trend freeze-window 决策可追溯 + comparability 判定稳定性
- io_contract:
  - input: `gate_trend.v6` (`anchor_freeze_id`, `confidence_band`, `sample_floor`, `approval_ticket_id`)
  - output: verdict envelope (`comparability_verdict`, `freeze_decision_trace`, `window_guard_status`)

## B-line envelope
- focus: required-check 依赖拓扑 deadline 收敛 + hard-cap 自动降级闭环
- io_contract:
  - input: `required_check.topology.v5` (`critical_path`, `tier_deadline_minutes`, `debt_budget_key`, `hard_cap_state`)
  - output: lifecycle envelope (`auto_degrade_plan_ref`, `deadline_violation_class`, `owner_ack`)

## Constraints
- research lane only
- writable scope: `docs/reference-pool/2026-03-04-scout-r41`, `artifacts/orchestration`
