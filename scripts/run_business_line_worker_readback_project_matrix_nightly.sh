#!/usr/bin/env bash
set -e
set -u
set -o pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/run_business_line_worker_readback_project_matrix_nightly.sh [options]

Repo-local nightly wrapper for the business-line worker readback project matrix lane.

Options:
  --date YYYY-MM-DD                  Run date directory. Defaults to UTC today.
  --output-dir DIR                   Output directory. Defaults to development/latest-dev-docs/automation-runs/business-line-worker-readback-project-matrix/<date>.
  --api-base URL                     Backend base URL. Defaults to http://127.0.0.1:8000.
  --projects-api-url URL             Projects inventory API URL. Defaults to <api-base>/api/v1/projects.
  --project-key-regex REGEX          Project key filter. Defaults to ^demo_proj$.
  --exclude-project-key KEY          Project key to exclude. May be supplied multiple times.
  --max-projects N                   Maximum projects to keep after filtering.
  --timeout SECONDS                  HTTP/subprocess timeout passed to the matrix runner. Defaults to 5.
  --trigger-smoke                    Pass --trigger-smoke to the matrix runner.
  --allow-blocked                    Pass --allow-blocked to the matrix runner.
  --ensure-local-runtime             If backend health is unavailable, run scripts/local-deploy.sh start before the matrix.
  --runtime-preflight-timeout SECONDS Backend health timeout for --ensure-local-runtime. Defaults to 8.
  --dry-run                          Print the resolved plan without writing artifacts.
  -h, --help                         Show this help.
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
default_base_dir="${repo_root}/development/latest-dev-docs/automation-runs/business-line-worker-readback-project-matrix"
run_date="$(date -u +%F)"
output_dir=""
output_dir_was_default=1
api_base="http://127.0.0.1:8000"
projects_api_url=""
projects_api_url_was_default=1
project_key_regex="^demo_proj$"
exclude_project_keys=()
exclude_project_key_count=0
max_projects=""
timeout="5"
trigger_smoke=0
allow_blocked=0
ensure_local_runtime=0
runtime_preflight_timeout="8"
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      run_date="${2:?--date requires YYYY-MM-DD}"
      shift 2
      ;;
    --output-dir)
      output_dir="${2:?--output-dir requires a directory}"
      output_dir_was_default=0
      shift 2
      ;;
    --api-base)
      api_base="${2:?--api-base requires a URL}"
      shift 2
      ;;
    --projects-api-url)
      projects_api_url="${2:?--projects-api-url requires a URL}"
      projects_api_url_was_default=0
      shift 2
      ;;
    --project-key-regex)
      project_key_regex="${2:?--project-key-regex requires a regex}"
      shift 2
      ;;
    --exclude-project-key)
      exclude_project_keys+=("${2:?--exclude-project-key requires a project key}")
      exclude_project_key_count=$((exclude_project_key_count + 1))
      shift 2
      ;;
    --max-projects)
      max_projects="${2:?--max-projects requires an integer}"
      shift 2
      ;;
    --timeout)
      timeout="${2:?--timeout requires seconds}"
      shift 2
      ;;
    --trigger-smoke)
      trigger_smoke=1
      shift
      ;;
    --allow-blocked)
      allow_blocked=1
      shift
      ;;
    --ensure-local-runtime)
      ensure_local_runtime=1
      shift
      ;;
    --runtime-preflight-timeout)
      runtime_preflight_timeout="${2:?--runtime-preflight-timeout requires seconds}"
      shift 2
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

if [[ -n "$max_projects" && ( ! "$max_projects" =~ ^[0-9]+$ || "$max_projects" -lt 1 ) ]]; then
  echo "FAIL --max-projects must be an integer >= 1" >&2
  exit 2
fi

if [[ ! "$timeout" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "FAIL --timeout must be a positive number of seconds" >&2
  exit 2
fi

if [[ ! "$runtime_preflight_timeout" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "FAIL --runtime-preflight-timeout must be a positive number of seconds" >&2
  exit 2
fi

if [[ -z "$output_dir" ]]; then
  output_dir="${default_base_dir}/${run_date}"
elif [[ "$output_dir" != /* ]]; then
  output_dir="${repo_root}/${output_dir}"
fi

if [[ -z "$projects_api_url" ]]; then
  projects_api_url="${api_base%/}/api/v1/projects"
fi

matrix_report_path="${output_dir}/business-line-worker-readback-project-matrix-report.json"
manifest_path="${output_dir}/nightly-manifest.json"
if [[ "$output_dir_was_default" -eq 1 ]]; then
  history_path="${default_base_dir}/trend-history.jsonl"
else
  history_path="${output_dir}/trend-history.jsonl"
fi

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

matrix_runner="${MRW_BUSINESS_LINE_WORKER_READBACK_PROJECT_MATRIX_RUNNER:-${repo_root}/scripts/run_business_line_worker_readback_project_matrix.py}"
local_deploy_script="${MRW_LOCAL_DEPLOY_SCRIPT:-${repo_root}/scripts/local-deploy.sh}"

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

trigger = "codex_app_scheduler"
source = "codex_app" if has_codex_scheduler else "mrw_scheduled_run_evidence"
print(
    json.dumps(
        {
            "scheduled_run_evidence": True,
            "trigger": trigger,
            "source": source,
            "run_source": "scheduled",
            "execution_source": "scheduled",
            "env": {key: value for key, value in env.items() if value},
        },
        sort_keys=True,
    )
)
PY
}

runtime_preflight_json() {
  "$python_bin" - "$api_base" "$runtime_preflight_timeout" "$ensure_local_runtime" "$local_deploy_script" <<'PY'
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def check_health(api_base: str, timeout: float) -> dict[str, object]:
    url = api_base.rstrip("/") + "/api/v1/health"
    started = time.time()
    try:
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-supplied local URL.
            status_code = int(response.status)
            ok = 200 <= status_code < 300
            return {
                "ok": ok,
                "status_code": status_code,
                "url": url,
                "duration_seconds": round(time.time() - started, 3),
            }
    except TimeoutError:
        return {"ok": False, "url": url, "error": f"timeout after {timeout} seconds"}
    except URLError as exc:
        return {"ok": False, "url": url, "error": str(exc.reason)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "url": url, "error": str(exc)}


api_base = sys.argv[1]
timeout = float(sys.argv[2])
ensure_runtime = bool(int(sys.argv[3]))
local_deploy_script = sys.argv[4]

preflight: dict[str, object] = {
    "checked_at": now_utc(),
    "ensure_local_runtime": ensure_runtime,
    "local_deploy_script": local_deploy_script,
}
if not ensure_runtime:
    preflight.update({"status": "skipped", "reason": "ensure_local_runtime_disabled"})
    print(json.dumps(preflight, sort_keys=True))
    raise SystemExit(0)

initial = check_health(api_base, timeout)
preflight["initial_health"] = initial
if initial.get("ok") is True:
    preflight.update({"status": "passed", "attempted_start": False})
    print(json.dumps(preflight, sort_keys=True))
    raise SystemExit(0)

started = time.time()
try:
    completed = subprocess.run(  # noqa: S603 - fixed operator-configured repo script.
        ["bash", local_deploy_script, "start"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=max(30.0, timeout * 10),
    )
    preflight.update(
        {
            "attempted_start": True,
            "start_exit_code": int(completed.returncode),
            "start_duration_seconds": round(time.time() - started, 3),
            "start_stdout_tail": completed.stdout[-1200:],
            "start_stderr_tail": completed.stderr[-1200:],
        }
    )
except subprocess.TimeoutExpired as exc:
    preflight.update(
        {
            "attempted_start": True,
            "start_exit_code": 124,
            "start_duration_seconds": round(time.time() - started, 3),
            "start_stdout_tail": (exc.stdout if isinstance(exc.stdout, str) else "")[-1200:],
            "start_stderr_tail": (exc.stderr if isinstance(exc.stderr, str) else "")[-1200:],
            "start_error": f"local deploy start timed out after {exc.timeout} seconds",
        }
    )
after = check_health(api_base, timeout)
preflight["post_start_health"] = after
preflight["status"] = "passed" if after.get("ok") is True else "blocked_by_environment"
print(json.dumps(preflight, sort_keys=True))
PY
}

matrix_cmd=(
  "$python_bin"
  "$matrix_runner"
  --api-base "$api_base"
  --projects-api-url "$projects_api_url"
  --project-key-regex "$project_key_regex"
  --artifact-dir "$output_dir"
  --timeout "$timeout"
  --json
)
if [[ "$exclude_project_key_count" -gt 0 ]]; then
  for project_key in "${exclude_project_keys[@]}"; do
    matrix_cmd+=(--exclude-project-key "$project_key")
  done
fi
if [[ -n "$max_projects" ]]; then
  matrix_cmd+=(--max-projects "$max_projects")
fi
if [[ "$trigger_smoke" -eq 1 ]]; then
  matrix_cmd+=(--trigger-smoke)
fi
if [[ "$allow_blocked" -eq 1 ]]; then
  matrix_cmd+=(--allow-blocked)
fi

if [[ "$dry_run" -eq 1 ]]; then
  printf 'DRY-RUN repo_root=%s\n' "$repo_root"
  printf 'DRY-RUN run_date=%s\n' "$run_date"
  printf 'DRY-RUN output_dir=%s\n' "$output_dir"
  printf 'DRY-RUN matrix_report=%s\n' "$matrix_report_path"
  printf 'DRY-RUN manifest=%s\n' "$manifest_path"
  printf 'DRY-RUN history=%s\n' "$history_path"
  printf 'DRY-RUN matrix_cmd='
  printf '%q ' "${matrix_cmd[@]}"
  printf '\n'
  printf 'DRY-RUN ensure_local_runtime=%s\n' "$ensure_local_runtime"
  printf 'DRY-RUN runtime_preflight_timeout=%s\n' "$runtime_preflight_timeout"
  exit 0
fi

scheduled_evidence="$(scheduled_evidence_json)"
runtime_preflight="$(runtime_preflight_json)"

mkdir -p "$output_dir"

matrix_started_epoch="$("$python_bin" - <<'PY'
import time
print(time.time())
PY
)"
matrix_started_at="$("$python_bin" - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
PY
)"
set +e
"${matrix_cmd[@]}"
matrix_rc=$?
set -e
matrix_finished_epoch="$("$python_bin" - <<'PY'
import time
print(time.time())
PY
)"
matrix_finished_at="$("$python_bin" - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
PY
)"

manifest_cmd=(
  "$python_bin"
  -
  "$run_date" \
  "$api_base" \
  "$projects_api_url" \
  "$project_key_regex" \
  "$max_projects" \
  "$timeout" \
  "$trigger_smoke" \
  "$allow_blocked" \
  "$projects_api_url_was_default" \
  "$matrix_report_path" \
  "$manifest_path" \
  "$history_path" \
  "$matrix_rc" \
  "$scheduled_evidence" \
  "$runtime_preflight" \
  "$matrix_started_at" \
  "$matrix_finished_at" \
  "$matrix_started_epoch" \
  "$matrix_finished_epoch"
)
if [[ "$exclude_project_key_count" -gt 0 ]]; then
  manifest_cmd+=("${exclude_project_keys[@]}")
fi

"${manifest_cmd[@]}" <<'PY'
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
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def compact_project(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_key": project.get("project_key"),
        "status": project.get("status"),
        "reason": project.get("reason"),
        "stopped_at": project.get("stopped_at"),
        "exit_code": project.get("exit_code"),
        "trigger_smoke_status": project.get("trigger_smoke_status"),
    }


def count_values(projects: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for project in projects:
        value = project.get(field)
        key = value if isinstance(value, str) and value else "__missing__"
        counts[key] = counts.get(key, 0) + 1
    return counts


def build_matrix_diagnostics(
    *,
    matrix_status: str,
    matrix_report_status: Any,
    matrix_exit_code: int,
    runtime_preflight: dict[str, Any],
    project_selection: dict[str, Any],
    summary: dict[str, Any],
    matrix_report: dict[str, Any] | None,
    duration_seconds: float,
    fallback_projects_api_url: str,
) -> dict[str, Any]:
    raw_projects = matrix_report.get("projects") if isinstance(matrix_report, dict) else []
    projects = [project for project in raw_projects if isinstance(project, dict)] if isinstance(raw_projects, list) else []
    blocked_projects = [compact_project(project) for project in projects if project.get("status") == "blocked_by_environment"]
    failed_projects = [compact_project(project) for project in projects if project.get("status") == "failed"]
    diagnostic_projects = blocked_projects + failed_projects
    raw_project_keys = project_selection.get("project_keys")
    project_keys = [key for key in raw_project_keys if isinstance(key, str)] if isinstance(raw_project_keys, list) else []
    first_blocked_reason = next(
        (
            project["reason"]
            for project in blocked_projects
            if isinstance(project.get("reason"), str) and project.get("reason")
        ),
        None,
    )
    summary_total = summary.get("total") if isinstance(summary.get("total"), int) else len(projects)
    projects_api_url = project_selection.get("projects_api_url")
    return {
        "matrix_status": matrix_status,
        "matrix_report_status": matrix_report_status,
        "matrix_exit_code": matrix_exit_code,
        "runtime_preflight_status": runtime_preflight.get("status"),
        "runtime_preflight_start_exit_code": runtime_preflight.get("start_exit_code"),
        "project_keys": project_keys,
        "projects_api_url": projects_api_url if isinstance(projects_api_url, str) else fallback_projects_api_url,
        "summary_total": summary_total,
        "duration_seconds": duration_seconds,
        "blocked_project_count": len(blocked_projects),
        "failed_project_count": len(failed_projects),
        "blocked_projects": blocked_projects,
        "failed_projects": failed_projects,
        "stopped_at_counts": count_values(diagnostic_projects, "stopped_at"),
        "reason_counts": count_values(diagnostic_projects, "reason"),
        "first_blocked_reason": first_blocked_reason,
    }


run_date = sys.argv[1]
api_base = sys.argv[2]
projects_api_url = sys.argv[3]
project_key_regex = sys.argv[4]
max_projects_raw = sys.argv[5]
timeout = sys.argv[6]
trigger_smoke = bool(int(sys.argv[7]))
allow_blocked = bool(int(sys.argv[8]))
projects_api_url_was_default = bool(int(sys.argv[9]))
matrix_report_path = Path(sys.argv[10])
manifest_path = Path(sys.argv[11])
history_path = Path(sys.argv[12])
matrix_rc = int(sys.argv[13])
scheduled_evidence_raw = sys.argv[14]
runtime_preflight_raw = sys.argv[15]
matrix_started_at = sys.argv[16]
matrix_finished_at = sys.argv[17]
matrix_started_epoch = float(sys.argv[18])
matrix_finished_epoch = float(sys.argv[19])
exclude_project_keys = [value for value in sys.argv[20:] if value]

scheduled_evidence = None
if scheduled_evidence_raw:
    try:
        parsed_scheduled_evidence = json.loads(scheduled_evidence_raw)
    except json.JSONDecodeError:
        parsed_scheduled_evidence = None
    scheduled_evidence = parsed_scheduled_evidence if isinstance(parsed_scheduled_evidence, dict) else None

runtime_preflight: dict[str, Any] = {}
if runtime_preflight_raw:
    try:
        parsed_runtime_preflight = json.loads(runtime_preflight_raw)
    except json.JSONDecodeError:
        parsed_runtime_preflight = {}
    runtime_preflight = parsed_runtime_preflight if isinstance(parsed_runtime_preflight, dict) else {}

matrix_report = load_json(matrix_report_path)
generated_at = now_utc()
report_status = matrix_report.get("status") if isinstance(matrix_report, dict) else None
nightly_status = report_status if isinstance(report_status, str) and report_status else "failed"
duration_seconds = round(max(0.0, matrix_finished_epoch - matrix_started_epoch), 3)
project_selection = (
    matrix_report.get("project_selection")
    if isinstance(matrix_report, dict) and isinstance(matrix_report.get("project_selection"), dict)
    else {
        "projects_api_url": projects_api_url,
        "project_key_regex": project_key_regex,
        "exclude_project_keys": exclude_project_keys,
        "max_projects": int(max_projects_raw) if max_projects_raw else None,
        "project_keys": [],
    }
)
summary = (
    matrix_report.get("summary")
    if isinstance(matrix_report, dict) and isinstance(matrix_report.get("summary"), dict)
    else {}
)
matrix_diagnostics = build_matrix_diagnostics(
    matrix_status=nightly_status,
    matrix_report_status=report_status,
    matrix_exit_code=matrix_rc,
    runtime_preflight=runtime_preflight,
    project_selection=project_selection,
    summary=summary,
    matrix_report=matrix_report,
    duration_seconds=duration_seconds,
    fallback_projects_api_url=projects_api_url,
)

manifest = {
    "schema_version": "business_line_worker_readback_project_matrix_nightly_manifest.v1",
    "lane": "business_line_worker_readback_project_matrix_nightly",
    "run_date": run_date,
    "status": nightly_status,
    "matrix_exit_code": matrix_rc,
    "matrix_report": str(matrix_report_path),
    "history_path": str(history_path),
    "project_selection": project_selection,
    "summary": summary,
    "generated_at": generated_at,
    "api_base": api_base,
    "projects_api_url": projects_api_url,
    "projects_api_url_was_default": projects_api_url_was_default,
    "project_key_regex": project_key_regex,
    "exclude_project_keys": exclude_project_keys,
    "max_projects": int(max_projects_raw) if max_projects_raw else None,
    "timeout": float(timeout),
    "trigger_smoke": trigger_smoke,
    "allow_blocked": allow_blocked,
    "matrix_report_status": report_status,
    "matrix_report_loaded": matrix_report is not None,
    "runtime_preflight": runtime_preflight,
    "matrix_started_at": matrix_started_at,
    "matrix_finished_at": matrix_finished_at,
    "duration_seconds": duration_seconds,
    "matrix_diagnostics": matrix_diagnostics,
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
    manifest.update(scheduled_fields)

manifest_path.parent.mkdir(parents=True, exist_ok=True)
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

history_row = {
    "schema_version": "business_line_worker_readback_project_matrix_trend_history.v1",
    "generated_at": generated_at,
    "run_date": run_date,
    "status": nightly_status,
    "matrix_exit_code": matrix_rc,
    "matrix_report": str(matrix_report_path),
    "summary": summary,
    "project_selection": project_selection,
    "api_base": api_base,
    "projects_api_url": projects_api_url,
    "project_key_regex": project_key_regex,
    "exclude_project_keys": exclude_project_keys,
    "max_projects": int(max_projects_raw) if max_projects_raw else None,
    "trigger_smoke": trigger_smoke,
    "allow_blocked": allow_blocked,
    "runtime_preflight_status": runtime_preflight.get("status"),
    "duration_seconds": duration_seconds,
    "matrix_diagnostics": matrix_diagnostics,
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
    "OK business_line_worker_readback_project_matrix_nightly_manifest "
    f"status={nightly_status} matrix_exit_code={matrix_rc} manifest={manifest_path}"
)
PY

if [[ "$matrix_rc" -ne 0 ]]; then
  echo "FAIL business-line worker readback project matrix exited ${matrix_rc}" >&2
  exit "$matrix_rc"
fi

echo "OK business_line_worker_readback_project_matrix_nightly matrix_report=${matrix_report_path} manifest=${manifest_path} history=${history_path}"
