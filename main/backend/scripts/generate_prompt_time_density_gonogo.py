#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected json object: {path}")
    return payload


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def build_gonogo_report(
    *,
    realcase: dict[str, Any],
    perf: dict[str, Any],
    ope: dict[str, Any] | None = None,
    policy_health: dict[str, Any] | None = None,
    p95_threshold: float = 1.5,
    error_rate_threshold: float = 0.01,
    ope_dr_lower_threshold: float = 0.0,
    kl_p95_threshold: float = 0.03,
    abs_shift_p95_threshold: float = 0.12,
    benefit_lift_min: float = 0.0,
    degradation_hours_threshold: int = 48,
    require_ope: bool = False,
    ope_min_contexts: int = 1,
    ope_max_latest_age_hours: float = 72.0,
    ope_min_ess_ratio: float = 0.20,
    ope_max_weight_cv: float = 2.5,
) -> dict[str, Any]:
    ope = ope or {}
    policy_health = policy_health or {}

    failed = int(realcase.get("failed") or 0)
    p95 = _to_float(perf.get("api_p95_seconds"), 999.0)
    error_rate = _to_float(perf.get("api_error_rate"), 1.0)
    ope_summary = ope.get("summary") or {}
    ope_diagnostics = ope.get("diagnostics") or {}
    ope_freshness = ope.get("freshness") or {}
    dr_ci_low = _to_float((((ope.get("estimators") or {}).get("dr") or {}).get("ci_low")), -999.0)
    contexts_used = int(ope_summary.get("contexts_used") or 0)
    latest_age_hours = ope_freshness.get("latest_age_hours")
    ess_ratio = ope_diagnostics.get("effective_sample_size_ratio")
    weight_cv = ope_diagnostics.get("weight_cv")
    p95_kl_to_base = _to_float(policy_health.get("p95_kl_to_base"), 999.0)
    p95_abs_shift = _to_float(policy_health.get("p95_abs_shift"), 999.0)
    benefit_lift_48h = _to_float(policy_health.get("benefit_lift_48h"), -999.0)
    degradation_hours = int(policy_health.get("degradation_hours") or 0)
    current_policy_version = str(policy_health.get("current_policy_version") or "")
    previous_policy_version = str(policy_health.get("previous_policy_version") or "")

    gate_realcase = failed == 0
    gate_p95 = p95 <= p95_threshold
    gate_error = error_rate <= error_rate_threshold
    gate_ope_present = bool(ope) or not require_ope
    gate_ope = dr_ci_low >= ope_dr_lower_threshold if ope else not require_ope
    gate_ope_contexts = contexts_used >= max(1, ope_min_contexts) if ope or require_ope else True
    gate_ope_freshness = (
        _to_float(latest_age_hours, 0.0) <= ope_max_latest_age_hours
        if latest_age_hours is not None and (ope or require_ope)
        else bool(ope_freshness) or not require_ope
    )
    gate_ope_ess = (
        _to_float(ess_ratio, 1.0) >= ope_min_ess_ratio
        if ess_ratio is not None and (ope or require_ope)
        else bool(ope_diagnostics) or not require_ope
    )
    gate_ope_weight = (
        _to_float(weight_cv, 0.0) <= ope_max_weight_cv
        if weight_cv is not None and (ope or require_ope)
        else bool(ope_diagnostics) or not require_ope
    )
    gate_kl = p95_kl_to_base <= kl_p95_threshold if policy_health else True
    gate_shift = p95_abs_shift <= abs_shift_p95_threshold if policy_health else True
    gate_benefit = benefit_lift_48h >= benefit_lift_min if policy_health else True
    all_gates = (
        gate_realcase
        and gate_p95
        and gate_error
        and gate_ope_present
        and gate_ope
        and gate_ope_contexts
        and gate_ope_freshness
        and gate_ope_ess
        and gate_ope_weight
        and gate_kl
        and gate_shift
        and gate_benefit
    )
    decision = "GO" if all_gates else "NO-GO"
    rollback_recommended = bool(
        decision == "NO-GO"
        and policy_health
        and degradation_hours >= int(degradation_hours_threshold)
        and benefit_lift_48h < 0
    )

    lines: list[str] = []
    lines.append("# Prompt-Time-Density Go/No-Go Report")
    lines.append("")
    lines.append(f"- decision: `{decision}`")
    lines.append(f"- gate_realcase: `{gate_realcase}` (failed={failed})")
    lines.append(f"- gate_p95: `{gate_p95}` (p95={p95}, threshold={p95_threshold})")
    lines.append(f"- gate_error_rate: `{gate_error}` (error_rate={error_rate}, threshold={error_rate_threshold})")
    if ope or require_ope:
        lines.append(f"- gate_ope_present: `{gate_ope_present}`")
        lines.append(f"- gate_ope_dr_ci_low: `{gate_ope}` (dr_ci_low={dr_ci_low}, threshold={ope_dr_lower_threshold})")
        lines.append(f"- gate_ope_contexts: `{gate_ope_contexts}` (contexts_used={contexts_used}, min={ope_min_contexts})")
        lines.append(
            f"- gate_ope_freshness: `{gate_ope_freshness}` "
            f"(latest_age_hours={latest_age_hours}, max={ope_max_latest_age_hours})"
        )
        lines.append(f"- gate_ope_ess: `{gate_ope_ess}` (ess_ratio={ess_ratio}, min={ope_min_ess_ratio})")
        lines.append(f"- gate_ope_weight_cv: `{gate_ope_weight}` (weight_cv={weight_cv}, max={ope_max_weight_cv})")
    if policy_health:
        lines.append(f"- gate_kl_p95: `{gate_kl}` (p95_kl_to_base={p95_kl_to_base}, threshold={kl_p95_threshold})")
        lines.append(f"- gate_abs_shift_p95: `{gate_shift}` (p95_abs_shift={p95_abs_shift}, threshold={abs_shift_p95_threshold})")
        lines.append(
            f"- gate_benefit_lift_48h: `{gate_benefit}` "
            f"(benefit_lift_48h={benefit_lift_48h}, threshold={benefit_lift_min})"
        )
        lines.append(f"- degradation_hours: `{degradation_hours}` (threshold={degradation_hours_threshold})")
        lines.append(
            f"- rollback_recommended: `{rollback_recommended}`"
            + (f" -> `{previous_policy_version}`" if rollback_recommended and previous_policy_version else "")
        )
    lines.append("")
    lines.append("## Rollback Steps")
    if rollback_recommended:
        lines.append("1. Stop rollout and freeze new traffic to prompt-time-density endpoints.")
        lines.append(
            "2. Roll back policy version"
            + (f" from `{current_policy_version}` to `{previous_policy_version}`." if current_policy_version else ".")
        )
        lines.append("3. Keep API contract unchanged, only switch policy config/version pointer.")
        lines.append("4. Re-run OPE + realcase checks before re-enable.")
    else:
        lines.append("1. Stop rollout and freeze new traffic to prompt-time-density endpoints.")
        lines.append("2. Revert backend entries in `main/backend/app/api/stats.py` and `main/backend/app/services/stats/`.")
        lines.append("3. Revert scheduler integration in `main/backend/app/services/tasks.py`.")
        lines.append("4. Re-run core contracts and realcase checks before re-enable.")
    lines.append("")
    lines.append("## Verification Commands")
    lines.append("```bash")
    lines.append("cd main/backend")
    lines.append(
        "python3.11 -m pytest -q tests/core_business/test_api_group_a_core_contract.py tests/core_business/test_process_consistency_core_contract.py -k \"prompt_time_density or invalid\""
    )
    lines.append("python3.11 scripts/run_realcase_prompt_time_density.py --project demo_proj --case-set all --fail-fast")
    lines.append("```")

    return {
        "decision": decision,
        "rollback_recommended": rollback_recommended,
        "rollback_target_policy_version": previous_policy_version or None,
        "lines": lines,
        "gates": {
            "realcase": gate_realcase,
            "p95": gate_p95,
            "error_rate": gate_error,
            "ope_present": gate_ope_present,
            "ope_dr_ci_low": gate_ope,
            "ope_contexts": gate_ope_contexts,
            "ope_freshness": gate_ope_freshness,
            "ope_ess": gate_ope_ess,
            "ope_weight_cv": gate_ope_weight,
            "kl_p95": gate_kl,
            "abs_shift_p95": gate_shift,
            "benefit_lift_48h": gate_benefit,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Go/No-Go report for prompt-time-density release gate.")
    parser.add_argument("--realcase", required=True, help="Path to realcase report json.")
    parser.add_argument("--perf", required=True, help="Path to performance metrics json.")
    parser.add_argument("--ope", help="Path to OPE report json.")
    parser.add_argument("--policy-health", help="Path to policy health summary json.")
    parser.add_argument("--output", default=".artifacts/prompt_time_density_gonogo.md")
    parser.add_argument("--p95-threshold", type=float, default=1.5)
    parser.add_argument("--error-rate-threshold", type=float, default=0.01)
    parser.add_argument("--ope-dr-lower-threshold", type=float, default=0.0)
    parser.add_argument("--kl-p95-threshold", type=float, default=0.03)
    parser.add_argument("--abs-shift-p95-threshold", type=float, default=0.12)
    parser.add_argument("--benefit-lift-min", type=float, default=0.0)
    parser.add_argument("--degradation-hours-threshold", type=int, default=48)
    parser.add_argument("--require-ope", action="store_true")
    parser.add_argument("--ope-min-contexts", type=int, default=1)
    parser.add_argument("--ope-max-latest-age-hours", type=float, default=72.0)
    parser.add_argument("--ope-min-ess-ratio", type=float, default=0.20)
    parser.add_argument("--ope-max-weight-cv", type=float, default=2.5)
    args = parser.parse_args()

    realcase = _read_json(Path(args.realcase))
    perf = _read_json(Path(args.perf))
    ope = _read_json(Path(args.ope)) if args.ope else {}
    policy_health = _read_json(Path(args.policy_health)) if args.policy_health else {}
    report = build_gonogo_report(
        realcase=realcase,
        perf=perf,
        ope=ope,
        policy_health=policy_health,
        p95_threshold=args.p95_threshold,
        error_rate_threshold=args.error_rate_threshold,
        ope_dr_lower_threshold=args.ope_dr_lower_threshold,
        kl_p95_threshold=args.kl_p95_threshold,
        abs_shift_p95_threshold=args.abs_shift_p95_threshold,
        benefit_lift_min=args.benefit_lift_min,
        degradation_hours_threshold=args.degradation_hours_threshold,
        require_ope=args.require_ope,
        ope_min_contexts=args.ope_min_contexts,
        ope_max_latest_age_hours=args.ope_max_latest_age_hours,
        ope_min_ess_ratio=args.ope_min_ess_ratio,
        ope_max_weight_cv=args.ope_max_weight_cv,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(report["lines"]), encoding="utf-8")
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "rollback_recommended": report["rollback_recommended"],
                "rollback_target_policy_version": report["rollback_target_policy_version"],
                "output": str(out_path),
            }
        )
    )
    return 0 if report["decision"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
