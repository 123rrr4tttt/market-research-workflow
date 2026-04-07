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
    args = parser.parse_args()

    realcase = _read_json(Path(args.realcase))
    perf = _read_json(Path(args.perf))
    ope = _read_json(Path(args.ope)) if args.ope else {}
    policy_health = _read_json(Path(args.policy_health)) if args.policy_health else {}

    failed = int(realcase.get("failed") or 0)
    p95 = _to_float(perf.get("api_p95_seconds"), 999.0)
    error_rate = _to_float(perf.get("api_error_rate"), 1.0)
    dr_ci_low = _to_float((((ope.get("estimators") or {}).get("dr") or {}).get("ci_low")), -999.0)
    p95_kl_to_base = _to_float(policy_health.get("p95_kl_to_base"), 999.0)
    p95_abs_shift = _to_float(policy_health.get("p95_abs_shift"), 999.0)
    benefit_lift_48h = _to_float(policy_health.get("benefit_lift_48h"), -999.0)
    degradation_hours = int(policy_health.get("degradation_hours") or 0)
    current_policy_version = str(policy_health.get("current_policy_version") or "")
    previous_policy_version = str(policy_health.get("previous_policy_version") or "")

    gate_realcase = failed == 0
    gate_p95 = p95 <= args.p95_threshold
    gate_error = error_rate <= args.error_rate_threshold
    gate_ope = dr_ci_low >= args.ope_dr_lower_threshold if ope else True
    gate_kl = p95_kl_to_base <= args.kl_p95_threshold if policy_health else True
    gate_shift = p95_abs_shift <= args.abs_shift_p95_threshold if policy_health else True
    gate_benefit = benefit_lift_48h >= args.benefit_lift_min if policy_health else True
    decision = "GO" if (gate_realcase and gate_p95 and gate_error and gate_ope and gate_kl and gate_shift and gate_benefit) else "NO-GO"
    rollback_recommended = bool(
        decision == "NO-GO"
        and policy_health
        and degradation_hours >= int(args.degradation_hours_threshold)
        and benefit_lift_48h < 0
    )

    lines: list[str] = []
    lines.append("# Prompt-Time-Density Go/No-Go Report")
    lines.append("")
    lines.append(f"- decision: `{decision}`")
    lines.append(f"- gate_realcase: `{gate_realcase}` (failed={failed})")
    lines.append(f"- gate_p95: `{gate_p95}` (p95={p95}, threshold={args.p95_threshold})")
    lines.append(
        f"- gate_error_rate: `{gate_error}` (error_rate={error_rate}, threshold={args.error_rate_threshold})"
    )
    if ope:
        lines.append(
            f"- gate_ope_dr_ci_low: `{gate_ope}` (dr_ci_low={dr_ci_low}, threshold={args.ope_dr_lower_threshold})"
        )
    if policy_health:
        lines.append(
            f"- gate_kl_p95: `{gate_kl}` (p95_kl_to_base={p95_kl_to_base}, threshold={args.kl_p95_threshold})"
        )
        lines.append(
            f"- gate_abs_shift_p95: `{gate_shift}` (p95_abs_shift={p95_abs_shift}, threshold={args.abs_shift_p95_threshold})"
        )
        lines.append(
            f"- gate_benefit_lift_48h: `{gate_benefit}` (benefit_lift_48h={benefit_lift_48h}, threshold={args.benefit_lift_min})"
        )
        lines.append(
            f"- degradation_hours: `{degradation_hours}` (threshold={args.degradation_hours_threshold})"
        )
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

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "decision": decision,
                "rollback_recommended": rollback_recommended,
                "rollback_target_policy_version": previous_policy_version or None,
                "output": str(out_path),
            }
        )
    )
    return 0 if decision == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
