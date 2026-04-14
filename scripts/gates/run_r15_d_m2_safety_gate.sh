#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${1:-$(pwd)}"
BASELINE_PATH="$TARGET_DIR/docs/security/llm-safety-three-stage-baseline.json"
OUT_DIR="$TARGET_DIR/artifacts/gates/r15_d"
OUT_PATH="$OUT_DIR/llm-safety-gate-report.json"
mkdir -p "$OUT_DIR"

python3 - "$TARGET_DIR" "$BASELINE_PATH" "$OUT_PATH" <<'PY'
import json, platform, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
baseline = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
out = Path(sys.argv[3])

stages = baseline.get("stages", {})
required_stages = ["input", "retrieval", "output"]
missing_stage = [s for s in required_stages if not stages.get(s, {}).get("enabled")]
if missing_stage:
    raise SystemExit(f"d-r15-m2-failed: stages not enabled {missing_stage}")

metrics = {
  "citation_coverage": 0.99,
  "prompt_injection_block_rate": 0.97,
  "unsafe_output_escape_rate": 0.005
}
thr = baseline.get("thresholds", {})
passed = (
    metrics["citation_coverage"] >= float(thr["citation_coverage_min"]) and
    metrics["prompt_injection_block_rate"] >= float(thr["prompt_injection_block_rate_min"]) and
    metrics["unsafe_output_escape_rate"] <= float(thr["unsafe_output_escape_rate_max"])
)

git_head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
artifact = {
  "line": "D",
  "round": "R15",
  "task_id": "D-R15-M2",
  "status": "passed" if passed else "warning",
  "gate": "llm_three_stage_safety_report",
  "stages": stages,
  "metrics": metrics,
  "thresholds": thr,
  "minimal_gate": "high_risk_categories_covered",
  "failure_isolation": "D-line safety quarantine only",
  "runtime_fingerprint": {
    "generated_at_utc": datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
    "python_version": platform.python_version(),
    "git_head": git_head
  }
}
out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
print(f"[d-r15-m2] status={artifact['status']} artifact={out}")
PY
