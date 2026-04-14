#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${1:-$(pwd)}"
CONTRACT_PATH="$TARGET_DIR/docs/ops/r15-d-provenance-request-contract.json"
ARTIFACT_DIR="$TARGET_DIR/artifacts/gates/r15_d"
ARTIFACT_PATH="$ARTIFACT_DIR/provenance-blocking-gate.json"
mkdir -p "$ARTIFACT_DIR"

python3 - "$TARGET_DIR" "$CONTRACT_PATH" "$ARTIFACT_PATH" <<'PY'
import json, platform, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
contract = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
out = Path(sys.argv[3])
required = ["source_id", "retrieval_time", "chunk_hash", "model_version", "citation_id"]
schema = contract.get("request_schema", {})
missing = [f for f in required if not str(schema.get(f, "")).strip()]
completeness = round((len(required) - len(missing)) / len(required), 4)
status = "passed" if not missing else "failed"

git_head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
artifact = {
  "line": "D",
  "round": "R15",
  "task_id": "D-R15-M1",
  "status": status,
  "gate": "provenance_completeness_fail_fast",
  "provenance_completeness": completeness,
  "missing_fields": missing,
  "minimal_gate": "missing_field_rate_zero",
  "failure_isolation": "only D-line publish chain",
  "runtime_fingerprint": {
    "generated_at_utc": datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
    "python_version": platform.python_version(),
    "git_head": git_head
  }
}
out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
if missing:
    raise SystemExit(37)
print(f"[d-r15-m1] passed artifact={out}")
PY
