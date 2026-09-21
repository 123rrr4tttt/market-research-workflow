#!/usr/bin/env bash
set -e
set -u
set -o pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/run_llm_report_token_state_retention_nightly.sh [options]

Repo-local nightly wrapper for LLM report export token state retention cleanup.

Options:
  --date YYYY-MM-DD              Run date directory. Defaults to UTC today.
  --output-dir DIR               Output directory. Defaults to development/latest-dev-docs/automation-runs/llm-report-token-state-retention/<date>.
  --retention-days N             Retention window passed to the cleanup script. Defaults to 30.
  --execute                      Delete eligible terminal token state rows. Omit to run cleanup in dry-run mode.
  --fail-on-degraded             Exit non-zero when the cleanup report records degraded token state storage.
  --dry-run                      Print the resolved plan without writing artifacts or running cleanup.
  -h, --help                     Show this help.
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
default_base_dir="${repo_root}/development/latest-dev-docs/automation-runs/llm-report-token-state-retention"
run_date="$(date -u +%F)"
output_dir=""
retention_days="30"
execute=0
fail_on_degraded=0
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      run_date="${2:?--date requires YYYY-MM-DD}"
      shift 2
      ;;
    --output-dir)
      output_dir="${2:?--output-dir requires a directory}"
      shift 2
      ;;
    --retention-days)
      retention_days="${2:?--retention-days requires an integer}"
      shift 2
      ;;
    --execute)
      execute=1
      shift
      ;;
    --fail-on-degraded)
      fail_on_degraded=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "FAIL unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! "$run_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "FAIL --date must use YYYY-MM-DD" >&2
  exit 2
fi

if [[ ! "$retention_days" =~ ^[0-9]+$ || "$retention_days" -lt 1 ]]; then
  echo "FAIL --retention-days must be an integer >= 1" >&2
  exit 2
fi

if [[ -z "$output_dir" ]]; then
  output_dir="${default_base_dir}/${run_date}"
elif [[ "$output_dir" != /* ]]; then
  output_dir="${repo_root}/${output_dir}"
fi

artifact_path="${output_dir}/retention-report.json"
manifest_path="${output_dir}/nightly-manifest.json"
history_path="${default_base_dir}/trend-history.jsonl"

scheduled_evidence_json() {
  "$python_bin" <<'PY'
from __future__ import annotations

import json
import os


TRUE_VALUES = {"1", "true", "yes", "on", "scheduled", "scheduler"}
env = {
    "CODEX_AUTOMATION_ID": os.environ.get("CODEX_AUTOMATION_ID", "").strip(),
    "CODEX_AUTOMATION_RUN_ID": os.environ.get("CODEX_AUTOMATION_RUN_ID", "").strip(),
    "MRW_SCHEDULED_RUN_EVIDENCE": os.environ.get("MRW_SCHEDULED_RUN_EVIDENCE", "").strip(),
}

has_codex_scheduler = bool(env["CODEX_AUTOMATION_ID"] or env["CODEX_AUTOMATION_RUN_ID"])
has_explicit_flag = env["MRW_SCHEDULED_RUN_EVIDENCE"].lower() in TRUE_VALUES
if not (has_codex_scheduler or has_explicit_flag):
    print("")
    raise SystemExit(0)

print(
    json.dumps(
        {
            "scheduled_run_evidence": True,
            "trigger": "codex_app_scheduler" if has_codex_scheduler else "scheduled",
            "source": "codex_app" if has_codex_scheduler else "mrw_scheduled_run_evidence",
            "run_source": "scheduled",
            "execution_source": "scheduled",
            "env": {key: value for key, value in env.items() if value},
        },
        sort_keys=True,
    )
)
PY
}

if [[ -n "${PYTHON:-}" ]]; then
  python_bin="${PYTHON}"
elif [[ -x "/Users/wangyiliang/.local/bin/python3.11" ]]; then
  python_bin="/Users/wangyiliang/.local/bin/python3.11"
elif command -v python3.11 >/dev/null 2>&1; then
  python_bin="$(command -v python3.11)"
elif command -v python3 >/dev/null 2>&1; then
  python_bin="$(command -v python3)"
else
  echo "FAIL no python3 interpreter found" >&2
  exit 2
fi

cleanup_mode="--dry-run"
if [[ "$execute" -eq 1 ]]; then
  cleanup_mode="--execute"
fi

cleanup_cmd=(
  "$python_bin"
  "${repo_root}/main/backend/scripts/cleanup_llm_report_export_token_state.py"
  --retention-days "$retention_days"
  "$cleanup_mode"
)

if [[ "$dry_run" -eq 1 ]]; then
  printf 'DRY-RUN repo_root=%s\n' "$repo_root"
  printf 'DRY-RUN run_date=%s\n' "$run_date"
  printf 'DRY-RUN output_dir=%s\n' "$output_dir"
  printf 'DRY-RUN retention_days=%s\n' "$retention_days"
  printf 'DRY-RUN execute=%s\n' "$execute"
  printf 'DRY-RUN artifact=%s\n' "$artifact_path"
  printf 'DRY-RUN manifest=%s\n' "$manifest_path"
  printf 'DRY-RUN history=%s\n' "$history_path"
  printf 'DRY-RUN cleanup_cmd='
  printf '%q ' "${cleanup_cmd[@]}"
  printf '\n'
  exit 0
fi

scheduled_evidence="$(scheduled_evidence_json)"

mkdir -p "$output_dir"

set +e
"${cleanup_cmd[@]}" > "$artifact_path"
cleanup_rc=$?
set -e

"$python_bin" - \
  "$run_date" \
  "$retention_days" \
  "$execute" \
  "$artifact_path" \
  "$manifest_path" \
  "$history_path" \
  "$cleanup_rc" \
  "$fail_on_degraded" \
  "$scheduled_evidence" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


run_date = sys.argv[1]
retention_days = int(sys.argv[2])
execute = bool(int(sys.argv[3]))
artifact_path = Path(sys.argv[4])
manifest_path = Path(sys.argv[5])
history_path = Path(sys.argv[6])
cleanup_rc = int(sys.argv[7])
fail_on_degraded = bool(int(sys.argv[8]))
scheduled_evidence_raw = sys.argv[9]
scheduled_evidence = None
if scheduled_evidence_raw:
    try:
        parsed_scheduled_evidence = json.loads(scheduled_evidence_raw)
    except json.JSONDecodeError:
        parsed_scheduled_evidence = None
    scheduled_evidence = parsed_scheduled_evidence if isinstance(parsed_scheduled_evidence, dict) else None

artifact = load_json(artifact_path)
generated_at = now_utc()
summary = artifact.get("summary", {}) if isinstance(artifact, dict) else {}
counts = artifact.get("counts", {}) if isinstance(artifact, dict) else {}
status = artifact.get("status") if isinstance(artifact, dict) else None
degraded = bool(status == "degraded" or summary.get("token_state_store_degraded"))

nightly_status = "passed"
if cleanup_rc != 0:
    nightly_status = "failed"
elif degraded:
    nightly_status = "degraded"

manifest = {
    "schema_version": "llm_report_token_state_retention_nightly_manifest.v1",
    "generated_at": generated_at,
    "run_date": run_date,
    "lane": "llm_report_token_state_retention_nightly",
    "status": nightly_status,
    "mode": "execute" if execute else "dry_run",
    "fail_on_degraded": fail_on_degraded,
    "retention_days": retention_days,
    "paths": {
        "artifact": str(artifact_path),
        "history": str(history_path),
    },
    "current": {
        "status": status,
        "mode": artifact.get("mode") if isinstance(artifact, dict) else None,
        "run_id": artifact.get("run_id") if isinstance(artifact, dict) else None,
        "contract_version": artifact.get("contract_version") if isinstance(artifact, dict) else None,
        "started_at_utc": artifact.get("started_at_utc") if isinstance(artifact, dict) else None,
        "finished_at_utc": artifact.get("finished_at_utc") if isinstance(artifact, dict) else None,
    },
    "retention_plan": artifact.get("retention_plan", {}) if isinstance(artifact, dict) else {},
    "query_window": artifact.get("query_window", {}) if isinstance(artifact, dict) else {},
    "counts": counts if isinstance(counts, dict) else {},
    "degraded": {
        "flag": degraded,
        "token_state_store_degraded": bool(summary.get("token_state_store_degraded")) if isinstance(summary, dict) else None,
    },
    "validation": {
        "cleanup_exit_code": cleanup_rc,
    },
}
if scheduled_evidence:
    scheduled_fields = {
        "scheduled_run_evidence": True,
        "trigger": scheduled_evidence.get("trigger"),
        "source": scheduled_evidence.get("source"),
        "run_source": scheduled_evidence.get("run_source"),
        "execution_source": scheduled_evidence.get("execution_source"),
        "scheduler": scheduled_evidence,
    }
    if artifact is not None:
        artifact.update(scheduled_fields)
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest.update(
        scheduled_fields
    )

manifest_path.parent.mkdir(parents=True, exist_ok=True)
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

history_row = {
    "schema_version": "llm_report_token_state_retention_trend_history.v1",
    "generated_at": generated_at,
    "run_date": run_date,
    "status": nightly_status,
    "mode": manifest["mode"],
    "retention_days": retention_days,
    "artifact": str(artifact_path),
    "candidate_count": manifest["counts"].get("candidate_count"),
    "deleted_count": manifest["counts"].get("deleted_count"),
    "memory_candidate_count": manifest["counts"].get("memory_candidate_count"),
    "memory_deleted_count": manifest["counts"].get("memory_deleted_count"),
    "degraded_flag": degraded,
    "cleanup_exit_code": cleanup_rc,
}
if scheduled_evidence:
    history_row.update(
        {
            "scheduled_run_evidence": True,
            "trigger": scheduled_evidence.get("trigger"),
            "source": scheduled_evidence.get("source"),
            "run_source": scheduled_evidence.get("run_source"),
            "execution_source": scheduled_evidence.get("execution_source"),
        }
    )
history_path.parent.mkdir(parents=True, exist_ok=True)
with history_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(history_row, sort_keys=True) + "\n")

print(
    "OK llm_report_token_state_retention_manifest "
    f"status={nightly_status} degraded={degraded} manifest={manifest_path}"
)
PY

if [[ "$cleanup_rc" -ne 0 ]]; then
  echo "FAIL LLM report token state cleanup exited ${cleanup_rc}" >&2
  exit "$cleanup_rc"
fi

degraded_flag="$("$python_bin" - "$manifest_path" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("true" if manifest.get("degraded", {}).get("flag") else "false")
PY
)"

if [[ "$fail_on_degraded" -eq 1 && "$degraded_flag" == "true" ]]; then
  echo "FAIL LLM report token state retention degraded" >&2
  exit 1
fi

echo "OK llm_report_token_state_retention artifact=${artifact_path} manifest=${manifest_path} history=${history_path}"
