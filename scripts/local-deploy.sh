#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/main/backend"
OPTIONAL_ENHANCEMENTS_SCRIPT="${ROOT_DIR}/scripts/optional-enhancements.sh"
WORKER_PID_FILE="/tmp/celery-local-worker.pid"

usage() {
  cat <<USAGE
Usage: $(basename "$0") {start|stop|restart|preflight|status|health} [extra args...]

Commands:
  start      Start pure-local stack via backend/start-local.sh
  stop       Stop pure-local stack via backend/stop-local.sh
  restart    Restart pure-local stack
  preflight  Validate local commands/files/ports and write structured evidence
  status     Show local process status (backend/frontend/worker)
  health     Check local backend health endpoints

Examples:
  local-deploy.sh start --with-searxng --with-yacy --with-lancedb
  local-deploy.sh start --backend-only
  local-deploy.sh stop --local-only
USAGE
}

require_backend_dir() {
  if [[ ! -d "${BACKEND_DIR}" ]]; then
    echo "❌ Missing directory: ${BACKEND_DIR}" >&2
    exit 1
  fi
}

resolve_backend_python() {
  if [[ -n "${PYTHON:-}" ]]; then
    printf '%s\n' "${PYTHON}"
  elif [[ -x "/Users/wangyiliang/.local/bin/python3.11" ]]; then
    printf '%s\n' "/Users/wangyiliang/.local/bin/python3.11"
  elif command -v python3.11 >/dev/null 2>&1; then
    command -v python3.11
  elif [[ -x "${BACKEND_DIR}/.venv/bin/python" ]]; then
    printf '%s\n' "${BACKEND_DIR}/.venv/bin/python"
  else
    printf '%s\n' "python3"
  fi
}

is_listening() {
  local port="$1"
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
}

preflight_records_file=""

init_preflight_records() {
  preflight_records_file="$(mktemp)"
}

record_preflight_check() {
  local category="$1"
  local name="$2"
  local status="$3"
  local required="$4"
  local recommended="$5"
  local detail="${6:-}"
  if [[ -n "${preflight_records_file:-}" ]]; then
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$category" "$name" "$status" "$required" "$recommended" "$detail" >>"${preflight_records_file}"
  fi
}

record_backend_security_preflight_checks() {
  local backend_python="$1"
  local checker="${BACKEND_DIR}/scripts/check_llm_report_export_secret_preflight.py"
  local output=""
  local rc=0
  if output="$("${backend_python}" "${checker}" --records-tsv 2>&1)"; then
    rc=0
  else
    rc=$?
  fi
  local parsed_any=0
  while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    if [[ "${line}" == *$'\t'* ]]; then
      local category name check_status required recommended detail
      IFS=$'\t' read -r category name check_status required recommended detail <<<"${line}"
      record_preflight_check "${category}" "${name}" "${check_status}" "${required}" "${recommended}" "${detail}"
      parsed_any=1
    fi
  done <<<"${output}"
  if [[ "${parsed_any}" -eq 0 ]]; then
    record_preflight_check "security_secret" "backend_security_preflight" "failed" "true" \
      "python3 main/backend/scripts/check_llm_report_export_secret_preflight.py" \
      "security preflight checker did not emit structured records"
  fi
  return "${rc}"
}

run_security_preflight_fail_fast() {
  local backend_python
  backend_python="$(resolve_backend_python)"
  if "${backend_python}" "${BACKEND_DIR}/scripts/check_llm_report_export_secret_preflight.py" >/dev/null; then
    return 0
  fi
  echo "❌ Security preflight failed; run remediation:"
  echo "   ./scripts/local-deploy.sh preflight"
  return 1
}

write_preflight_manifest() {
  local status="$1"
  local exit_code="$2"
  local manifest_path="${MRW_PREFLIGHT_MANIFEST:-${TMPDIR:-/tmp}/mrw_local_preflight_manifest.json}"
  if ! command -v python3 >/dev/null 2>&1; then
    echo "⚠️ python3 not found; structured preflight evidence was not written"
    return 0
  fi
  python3 - "${preflight_records_file}" "${manifest_path}" "${status}" "${exit_code}" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


records_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
status = sys.argv[3]
exit_code = int(sys.argv[4])

checks = []
if records_path.exists():
    for line in records_path.read_text(encoding="utf-8").splitlines():
        category, name, check_status, required, recommended, detail = (line.split("\t") + [""] * 6)[:6]
        checks.append(
            {
                "category": category,
                "name": name,
                "status": check_status,
                "required": required == "true",
                "recommended_command": recommended or None,
                "detail": detail or None,
            }
        )


def category_checks(category: str) -> list[dict[str, object]]:
    return [item for item in checks if item["category"] == category]


def aggregate_status(items: list[dict[str, object]], *, empty: str = "not_checked") -> str:
    if not items:
        return empty
    if any(item["status"] == "failed" for item in items):
        return "failed"
    if any(item["status"] == "warn" for item in items):
        return "warn"
    if all(item["status"] == "passed" for item in items):
        return "passed"
    if all(item["status"] == "skipped" for item in items):
        return "skipped"
    return "unknown"


ports = category_checks("port")
service_checks = category_checks("service")
security_secrets = category_checks("security_secret") + category_checks("secret")
auth_checks = category_checks("auth")
provider_revoke_checks = category_checks("provider_revoke")
app_server_runtime_checks = category_checks("app_server_runtime")
dependencies = category_checks("dependency") + category_checks("file")
failed_required = [item for item in checks if item["required"] and item["status"] == "failed"]
recommended_command = "./scripts/local-deploy.sh preflight"

manifest = {
    "schema_version": "ops_preflight_evidence_contract.v1",
    "generated_at": now_utc(),
    "runtime_mode": "local",
    "status": status,
    "service_ping": {
        "status": aggregate_status(service_checks, empty="skipped"),
        "checks": service_checks,
    },
    "service_ready": {
        "status": aggregate_status(service_checks, empty="skipped"),
        "checks": service_checks,
    },
    "port": {
        "status": aggregate_status(ports, empty="not_checked"),
        "checks": ports,
    },
    "secret": {
        "status": aggregate_status(security_secrets, empty="not_checked"),
        "checks": security_secrets,
    },
    "security_secret": {
        "status": aggregate_status(security_secrets, empty="not_checked"),
        "checks": security_secrets,
    },
    "auth": {
        "status": aggregate_status(auth_checks, empty="not_checked"),
        "checks": auth_checks,
    },
    "provider_revoke": {
        "status": aggregate_status(provider_revoke_checks, empty="not_checked"),
        "checks": provider_revoke_checks,
    },
    "app_server_runtime": {
        "status": aggregate_status(app_server_runtime_checks, empty="not_checked"),
        "checks": app_server_runtime_checks,
    },
    "dependency": {
        "status": aggregate_status(dependencies, empty="not_checked"),
        "checks": dependencies,
    },
    "recommended_command": recommended_command,
    "fail_fast_decision": {
        "should_fail": bool(failed_required) or exit_code != 0,
        "status": "fail_fast" if failed_required or exit_code != 0 else "continue",
        "exit_code": exit_code,
        "reasons": [f"{item['category']}:{item['name']}" for item in failed_required],
        "recommended_command": recommended_command,
    },
    "checks": checks,
}

manifest_path.parent.mkdir(parents=True, exist_ok=True)
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  echo "✅ Structured preflight evidence: ${manifest_path}"
}

preflight() {
  require_backend_dir
  init_preflight_records
  local missing=0

  for cmd in curl lsof python3; do
    if command -v "$cmd" >/dev/null 2>&1; then
      echo "✅ Found command: $cmd"
      record_preflight_check "dependency" "command:${cmd}" "passed" "true" "" "command found"
    else
      echo "❌ Missing command: $cmd"
      record_preflight_check "dependency" "command:${cmd}" "failed" "true" "install ${cmd}" "command not found"
      missing=1
    fi
  done

  for f in start-local.sh stop-local.sh; do
    if [[ -f "${BACKEND_DIR}/${f}" ]]; then
      echo "✅ Found script: main/backend/${f}"
      record_preflight_check "file" "main/backend/${f}" "passed" "true" "" "script found"
    else
      echo "❌ Missing script: main/backend/${f}"
      record_preflight_check "file" "main/backend/${f}" "failed" "true" "restore main/backend/${f}" "script missing"
      missing=1
    fi
  done

  local backend_python
  backend_python="$(resolve_backend_python)"
  if record_backend_security_preflight_checks "${backend_python}"; then
    echo "✅ Backend security preflight passed"
  else
    echo "❌ Backend security preflight failed"
    missing=1
  fi

  check_local_port() {
    local port="$1"
    local service_name="$2"
    if ! command -v lsof >/dev/null 2>&1; then
      echo "⚠️ lsof not found; skip port check for ${service_name} (${port})"
      record_preflight_check "port" "${service_name}:${port}" "skipped" "false" "install lsof" "lsof not found"
      return 0
    fi
    if is_listening "$port"; then
      echo "✅ ${service_name} listening on :${port}"
      record_preflight_check "port" "${service_name}:${port}" "passed" "false" "" "port listening"
      record_preflight_check "service" "${service_name}" "passed" "false" "" "service listening"
    else
      echo "⚠️ ${service_name} not listening on :${port}"
      record_preflight_check "port" "${service_name}:${port}" "warn" "false" "./scripts/local-deploy.sh start" "port not listening"
      record_preflight_check "service" "${service_name}" "warn" "false" "./scripts/local-deploy.sh start" "service not listening"
    fi
  }

  check_local_port 8000 "backend"
  check_local_port 5173 "frontend-modern"

  if [[ $missing -ne 0 ]]; then
    write_preflight_manifest "failed" "1"
    return 1
  fi
  write_preflight_manifest "passed" "0"
  return 0
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

cmd="$1"
shift
ENHANCEMENT_ARGS=()
START_LOCAL_ARGS=()
STOP_LOCAL_ARGS=()
HELP_REQUESTED=0
for arg in "$@"; do
  case "$arg" in
    -h|--help)
      HELP_REQUESTED=1
      START_LOCAL_ARGS+=("$arg")
      STOP_LOCAL_ARGS+=("$arg")
      ;;
    --with-searxng)
      ENHANCEMENT_ARGS+=(--searxng)
      ;;
    --with-yacy)
      ENHANCEMENT_ARGS+=(--yacy)
      ;;
    --with-lancedb)
      ENHANCEMENT_ARGS+=(--lancedb)
      START_LOCAL_ARGS+=(--with-lancedb)
      ;;
    --backend-only)
      START_LOCAL_ARGS+=(--backend-only)
      ;;
    *)
      START_LOCAL_ARGS+=("$arg")
      STOP_LOCAL_ARGS+=("$arg")
      ;;
  esac
done

case "$cmd" in
  start)
    require_backend_dir
    run_security_preflight_fail_fast
    if [[ "${HELP_REQUESTED}" -eq 1 ]]; then
      cd "${BACKEND_DIR}"
      exec ./start-local.sh --help
    fi
    if [[ ${#ENHANCEMENT_ARGS[@]} -gt 0 ]]; then
      "${OPTIONAL_ENHANCEMENTS_SCRIPT}" start "${ENHANCEMENT_ARGS[@]}"
    fi
    cd "${BACKEND_DIR}"
    if [[ ${#START_LOCAL_ARGS[@]} -gt 0 ]]; then
      exec ./start-local.sh "${START_LOCAL_ARGS[@]}"
    fi
    exec ./start-local.sh
    ;;
  stop)
    "${OPTIONAL_ENHANCEMENTS_SCRIPT}" stop || true
    require_backend_dir
    cd "${BACKEND_DIR}"
    if [[ ${#STOP_LOCAL_ARGS[@]} -gt 0 ]]; then
      exec ./stop-local.sh "${STOP_LOCAL_ARGS[@]}"
    fi
    exec ./stop-local.sh
    ;;
  restart)
    require_backend_dir
    run_security_preflight_fail_fast
    "${OPTIONAL_ENHANCEMENTS_SCRIPT}" stop || true
    cd "${BACKEND_DIR}"
    if [[ ${#STOP_LOCAL_ARGS[@]} -gt 0 ]]; then
      ./stop-local.sh "${STOP_LOCAL_ARGS[@]}" || true
    else
      ./stop-local.sh || true
    fi
    if [[ ${#ENHANCEMENT_ARGS[@]} -gt 0 ]]; then
      "${OPTIONAL_ENHANCEMENTS_SCRIPT}" start "${ENHANCEMENT_ARGS[@]}"
    fi
    if [[ ${#START_LOCAL_ARGS[@]} -gt 0 ]]; then
      exec ./start-local.sh "${START_LOCAL_ARGS[@]}"
    fi
    exec ./start-local.sh
    ;;
  preflight)
    preflight
    ;;
  status)
    echo "Local status:"
    if is_listening 8000; then
      echo "✅ backend listening on :8000"
    else
      echo "❌ backend not listening on :8000"
    fi
    if is_listening 5173; then
      echo "✅ frontend-modern listening on :5173"
    else
      echo "❌ frontend-modern not listening on :5173"
    fi
    if [[ -f "${WORKER_PID_FILE}" ]]; then
      worker_pid="$(cat "${WORKER_PID_FILE}" 2>/dev/null || true)"
      if [[ -n "${worker_pid:-}" ]] && kill -0 "${worker_pid}" >/dev/null 2>&1; then
        echo "✅ celery worker running (PID ${worker_pid})"
      else
        echo "❌ celery worker pid file exists but process is not running"
      fi
    else
      echo "❌ celery worker not running"
    fi
    echo ""
    echo "Optional enhancements:"
    "${OPTIONAL_ENHANCEMENTS_SCRIPT}" status || true
    ;;
  health)
    curl -fsS http://localhost:8000/api/v1/health
    echo
    curl -fsS http://localhost:8000/api/v1/health/deep
    echo
    ;;
  -h|--help)
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
