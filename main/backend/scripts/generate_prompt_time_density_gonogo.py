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
    parser.add_argument("--output", default=".artifacts/prompt_time_density_gonogo.md")
    parser.add_argument("--p95-threshold", type=float, default=1.5)
    parser.add_argument("--error-rate-threshold", type=float, default=0.01)
    args = parser.parse_args()

    realcase = _read_json(Path(args.realcase))
    perf = _read_json(Path(args.perf))

    failed = int(realcase.get("failed") or 0)
    p95 = _to_float(perf.get("api_p95_seconds"), 999.0)
    error_rate = _to_float(perf.get("api_error_rate"), 1.0)

    gate_realcase = failed == 0
    gate_p95 = p95 <= args.p95_threshold
    gate_error = error_rate <= args.error_rate_threshold
    decision = "GO" if gate_realcase and gate_p95 and gate_error else "NO-GO"

    lines: list[str] = []
    lines.append("# Prompt-Time-Density Go/No-Go Report")
    lines.append("")
    lines.append(f"- decision: `{decision}`")
    lines.append(f"- gate_realcase: `{gate_realcase}` (failed={failed})")
    lines.append(f"- gate_p95: `{gate_p95}` (p95={p95}, threshold={args.p95_threshold})")
    lines.append(
        f"- gate_error_rate: `{gate_error}` (error_rate={error_rate}, threshold={args.error_rate_threshold})"
    )
    lines.append("")
    lines.append("## Rollback Steps")
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
    print(json.dumps({"decision": decision, "output": str(out_path)}))
    return 0 if decision == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())

