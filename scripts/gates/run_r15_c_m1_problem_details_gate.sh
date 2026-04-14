#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${1:-$(pwd)}"
ARTIFACT_DIR="$TARGET_DIR/artifacts/gates/r15_c"
ARTIFACT_PATH="$ARTIFACT_DIR/problem-details-rfc9457-gate.json"
SCHEMA_PATH="$TARGET_DIR/docs/ops/problem-details-422-schema-versions.json"

mkdir -p "$ARTIFACT_DIR"

python3 - "$TARGET_DIR" "$SCHEMA_PATH" "$ARTIFACT_PATH" <<'PY'
import json, platform, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
schema = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
out = Path(sys.argv[3])

required_top = ["version_field", "v_current", "v_next", "coexistence_strategy", "migration_window_days"]
missing_top = [k for k in required_top if k not in schema]
if missing_top:
    raise SystemExit(f"c-r15-m1-failed: missing fields {missing_top}")

accept_versions = schema["coexistence_strategy"].get("accept_versions", [])
current_ver = schema["v_current"].get("schema_version")
next_ver = schema["v_next"].get("schema_version")
if not current_ver or not next_ver or current_ver == next_ver:
    raise SystemExit("c-r15-m1-failed: invalid current/next schema versions")
if not (current_ver in accept_versions and next_ver in accept_versions):
    raise SystemExit("c-r15-m1-failed: coexistence accept_versions missing current/next")

migration_days = int(schema["migration_window_days"])
if migration_days <= 0:
    raise SystemExit("c-r15-m1-failed: migration_window_days must be > 0")

git_head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
artifact = {
  "line": "C",
  "round": "R15",
  "task_id": "C-R15-M1",
  "status": "passed",
  "gate": "rfc9457_problem_details_blocking_ready",
  "minimal_gate": "migration_window_present",
  "migration_window_days": migration_days,
  "schema_versions": {"v_current": current_ver, "v_next": next_ver, "accept_versions": accept_versions},
  "failure_isolation": "only C-line",
  "runtime_fingerprint": {
    "generated_at_utc": datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
    "python_version": platform.python_version(),
    "git_head": git_head
  }
}
out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
print(f"[c-r15-m1] passed artifact={out}")
PY
