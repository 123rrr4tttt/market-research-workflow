#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${1:-$(pwd)}"
CATALOG_PATH="$TARGET_DIR/docs/ops/otel-metric-schema-catalog.json"
ARTIFACT_DIR="$TARGET_DIR/artifacts/gates/r15_c"
ARTIFACT_PATH="$ARTIFACT_DIR/otel-metric-schema-check.json"
mkdir -p "$ARTIFACT_DIR"

python3 - "$TARGET_DIR" "$CATALOG_PATH" "$ARTIFACT_PATH" <<'PY'
import json, platform, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
catalog = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
out = Path(sys.argv[3])

allowed = {"stable", "experimental"}
core_drift = 0
issues = []
for svc in catalog.get("services", []):
    tier = svc.get("tier", "non_core")
    for m in svc.get("metrics", []):
        lvl = m.get("stability_level")
        if lvl not in allowed:
            issues.append({"service": svc.get("name"), "metric": m.get("name"), "reason": "invalid_stability_level"})
            if tier == "core":
                core_drift += 1

status = "passed" if core_drift == 0 else "failed"
git_head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
artifact = {
  "line": "C",
  "round": "R15",
  "task_id": "C-R15-M2",
  "status": status,
  "gate": "otel_schema_stability_level_check",
  "metric_schema_drift": core_drift,
  "issues": issues,
  "minimal_gate": "core_services_drift_zero",
  "failure_isolation": "non-core warnings only",
  "runtime_fingerprint": {
    "generated_at_utc": datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
    "python_version": platform.python_version(),
    "git_head": git_head
  }
}
out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
if status != "passed":
    raise SystemExit("c-r15-m2-failed: core schema drift detected")
print(f"[c-r15-m2] passed artifact={out}")
PY
