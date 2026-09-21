#!/usr/bin/env bash
set -e
set -u
set -o pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/run_performance_capacity_nightly.sh [options]

Repo-local nightly wrapper for the performance/capacity baseline smoke lane.

Options:
  --date YYYY-MM-DD              Run date directory. Defaults to UTC today.
  --output-dir DIR               Output directory. Defaults to development/latest-dev-docs/automation-runs/performance-capacity-baseline/<date>.
  --previous PATH                Previous performance-baseline.json. Use "none" to disable auto-detection.
  --api-base URL                 Optional service base URL to probe; unavailable services are recorded unless --service-required is set.
  --service-required             Treat service readiness probe failure as a baseline failure.
  --allow-service-failure        Record service fail-fast evidence but keep the wrapper exit code zero.
  --probe-timeout SECONDS        Service probe timeout. Defaults to 0.25.
  --fail-on-degradation          Exit non-zero when the generated artifact records degradation.
  --dry-run                      Print the resolved plan without writing artifacts.
  -h, --help                     Show this help.
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
default_base_dir="${repo_root}/development/latest-dev-docs/automation-runs/performance-capacity-baseline"
run_date="$(date -u +%F)"
output_dir=""
previous_arg=""
api_base=""
service_required=0
allow_service_failure=0
probe_timeout="0.25"
fail_on_degradation=0
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
    --previous)
      previous_arg="${2:?--previous requires a path or none}"
      shift 2
      ;;
    --api-base)
      api_base="${2:?--api-base requires a URL}"
      shift 2
      ;;
    --service-required)
      service_required=1
      shift
      ;;
    --allow-service-failure)
      allow_service_failure=1
      shift
      ;;
    --probe-timeout)
      probe_timeout="${2:?--probe-timeout requires seconds}"
      shift 2
      ;;
    --fail-on-degradation)
      fail_on_degradation=1
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

if [[ -z "$output_dir" ]]; then
  output_dir="${default_base_dir}/${run_date}"
elif [[ "$output_dir" != /* ]]; then
  output_dir="${repo_root}/${output_dir}"
fi

artifact_path="${output_dir}/performance-baseline.json"
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
elif command -v python3.11 >/dev/null 2>&1; then
  python_bin="$(command -v python3.11)"
elif command -v python3 >/dev/null 2>&1; then
  python_bin="$(command -v python3)"
else
  echo "FAIL no python3 interpreter found" >&2
  exit 2
fi

find_previous_artifact() {
  "$python_bin" - "$default_base_dir" "$artifact_path" <<'PY'
from pathlib import Path
import sys

base_dir = Path(sys.argv[1])
current = Path(sys.argv[2]).resolve()
candidates = []
if base_dir.exists():
    for path in base_dir.rglob("performance-baseline.json"):
        resolved = path.resolve()
        if resolved == current:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        candidates.append((stat.st_mtime, str(path)))
if candidates:
    print(max(candidates)[1])
PY
}

previous_path=""
if [[ "$previous_arg" == "none" ]]; then
  previous_path=""
elif [[ -n "$previous_arg" ]]; then
  if [[ "$previous_arg" == /* ]]; then
    previous_path="$previous_arg"
  else
    previous_path="${repo_root}/${previous_arg}"
  fi
else
  previous_path="$(find_previous_artifact)"
fi

baseline_cmd=(
  "$python_bin"
  "${repo_root}/scripts/performance_capacity_baseline.py"
  --output "$artifact_path"
  --probe-timeout "$probe_timeout"
)
if [[ -n "$previous_path" ]]; then
  baseline_cmd+=(--previous "$previous_path")
fi
if [[ -n "$api_base" ]]; then
  baseline_cmd+=(--api-base "$api_base")
fi
if [[ "$service_required" -eq 1 ]]; then
  baseline_cmd+=(--service-required)
fi
if [[ "$allow_service_failure" -eq 1 ]]; then
  baseline_cmd+=(--allow-service-failure)
fi

checker_cmd=(
  "$python_bin"
  "${repo_root}/scripts/check_performance_capacity_baseline_artifact.py"
  "$artifact_path"
)

if [[ "$dry_run" -eq 1 ]]; then
  printf 'DRY-RUN repo_root=%s\n' "$repo_root"
  printf 'DRY-RUN run_date=%s\n' "$run_date"
  printf 'DRY-RUN output_dir=%s\n' "$output_dir"
  printf 'DRY-RUN previous=%s\n' "${previous_path:-<none>}"
  printf 'DRY-RUN api_base=%s\n' "${api_base:-<none>}"
  printf 'DRY-RUN service_required=%s\n' "$service_required"
  printf 'DRY-RUN allow_service_failure=%s\n' "$allow_service_failure"
  printf 'DRY-RUN artifact=%s\n' "$artifact_path"
  printf 'DRY-RUN manifest=%s\n' "$manifest_path"
  printf 'DRY-RUN history=%s\n' "$history_path"
  printf 'DRY-RUN baseline_cmd='
  printf '%q ' "${baseline_cmd[@]}"
  printf '\n'
  printf 'DRY-RUN checker_cmd='
  printf '%q ' "${checker_cmd[@]}"
  printf '\n'
  exit 0
fi

scheduled_evidence="$(scheduled_evidence_json)"

mkdir -p "$output_dir"

set +e
"${baseline_cmd[@]}"
baseline_rc=$?
checker_rc=127
if [[ "$baseline_rc" -eq 0 && -f "$artifact_path" ]]; then
  "${checker_cmd[@]}"
  checker_rc=$?
fi
set -e

"$python_bin" - \
  "$run_date" \
  "$artifact_path" \
  "$previous_path" \
  "$manifest_path" \
  "$history_path" \
  "$baseline_rc" \
  "$checker_rc" \
  "$fail_on_degradation" \
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
artifact_path = Path(sys.argv[2])
previous_raw = sys.argv[3]
previous_path = Path(previous_raw) if previous_raw else None
manifest_path = Path(sys.argv[4])
history_path = Path(sys.argv[5])
baseline_rc = int(sys.argv[6])
checker_rc = int(sys.argv[7])
fail_on_degradation = bool(int(sys.argv[8]))
scheduled_evidence_raw = sys.argv[9]
scheduled_evidence = None
if scheduled_evidence_raw:
    try:
        parsed_scheduled_evidence = json.loads(scheduled_evidence_raw)
    except json.JSONDecodeError:
        parsed_scheduled_evidence = None
    scheduled_evidence = parsed_scheduled_evidence if isinstance(parsed_scheduled_evidence, dict) else None

artifact = load_json(artifact_path)
previous = load_json(previous_path) if previous_path else None
generated_at = now_utc()

degradation = artifact.get("degradation", {}) if artifact else {}
degradation_flag = bool(degradation.get("flag")) if isinstance(degradation, dict) else False
trend_record = artifact.get("trend_record", {}) if artifact else {}
service_probe = artifact.get("service_probe", {}) if artifact else {}

nightly_status = "passed"
if baseline_rc != 0 or checker_rc != 0:
    nightly_status = "failed"
elif degradation_flag:
    nightly_status = "degraded"

manifest = {
    "schema_version": "performance_capacity_nightly_manifest.v1",
    "generated_at": generated_at,
    "run_date": run_date,
    "lane": "performance_capacity_baseline_nightly",
    "status": nightly_status,
    "fail_on_degradation": fail_on_degradation,
    "paths": {
        "current_artifact": str(artifact_path),
        "previous_artifact": str(previous_path) if previous_path else None,
        "history": str(history_path),
    },
    "previous": {
        "status": "loaded" if previous else ("not_configured" if not previous_path else "unavailable"),
        "path": str(previous_path) if previous_path else None,
        "generated_at": previous.get("generated_at") if previous else None,
        "schema_version": previous.get("schema_version") if previous else None,
    },
    "current": {
        "status": artifact.get("status") if artifact else None,
        "generated_at": artifact.get("generated_at") if artifact else None,
        "schema_version": artifact.get("schema_version") if artifact else None,
    },
    "trend": {
        "status": trend_record.get("status") if isinstance(trend_record, dict) else None,
        "comparisons": trend_record.get("comparisons", []) if isinstance(trend_record, dict) else [],
    },
    "degradation": {
        "flag": degradation_flag,
        "reasons": degradation.get("reasons", []) if isinstance(degradation, dict) else [],
    },
    "service_probe": {
        "status": service_probe.get("status") if isinstance(service_probe, dict) else None,
        "enabled": service_probe.get("enabled") if isinstance(service_probe, dict) else None,
        "runtime_mode": service_probe.get("runtime_mode") if isinstance(service_probe, dict) else None,
        "service_ping": service_probe.get("service_ping") if isinstance(service_probe, dict) else None,
        "service_ready": service_probe.get("service_ready") if isinstance(service_probe, dict) else None,
        "port": service_probe.get("port") if isinstance(service_probe, dict) else None,
        "secret": service_probe.get("secret") if isinstance(service_probe, dict) else None,
        "dependency": service_probe.get("dependency") if isinstance(service_probe, dict) else None,
        "recommended_command": service_probe.get("recommended_command") if isinstance(service_probe, dict) else None,
        "fail_fast_decision": service_probe.get("fail_fast_decision") if isinstance(service_probe, dict) else None,
    },
    "validation": {
        "baseline_exit_code": baseline_rc,
        "checker_exit_code": checker_rc,
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
    "schema_version": "performance_capacity_trend_history.v1",
    "generated_at": generated_at,
    "run_date": run_date,
    "status": nightly_status,
    "previous_artifact": str(previous_path) if previous_path else None,
    "current_artifact": str(artifact_path),
    "current_generated_at": manifest["current"]["generated_at"],
    "trend_status": manifest["trend"]["status"],
    "degradation_flag": degradation_flag,
    "degradation_reasons": manifest["degradation"]["reasons"],
    "service_probe_status": manifest["service_probe"]["status"],
    "service_ping_status": (manifest["service_probe"].get("service_ping") or {}).get("status"),
    "service_ready_status": (manifest["service_probe"].get("service_ready") or {}).get("status"),
    "fail_fast_decision": manifest["service_probe"].get("fail_fast_decision"),
    "baseline_exit_code": baseline_rc,
    "checker_exit_code": checker_rc,
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
    "OK performance_capacity_nightly_manifest "
    f"status={nightly_status} degradation={degradation_flag} manifest={manifest_path}"
)
PY

if [[ "$baseline_rc" -ne 0 ]]; then
  echo "FAIL performance baseline generation exited ${baseline_rc}" >&2
  exit "$baseline_rc"
fi
if [[ "$checker_rc" -ne 0 ]]; then
  echo "FAIL performance baseline checker exited ${checker_rc}" >&2
  exit "$checker_rc"
fi

degradation_flag="$("$python_bin" - "$manifest_path" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("true" if manifest.get("degradation", {}).get("flag") else "false")
PY
)"

if [[ "$fail_on_degradation" -eq 1 && "$degradation_flag" == "true" ]]; then
  echo "FAIL performance capacity nightly degradation detected" >&2
  exit 1
fi

echo "OK performance_capacity_nightly artifact=${artifact_path} manifest=${manifest_path} history=${history_path}"
