#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OPS_DIR="${ROOT_DIR}/main/ops"
INSTALL_OPTIONAL_ENHANCEMENTS="${INSTALL_OPTIONAL_ENHANCEMENTS:-false}"

# Standard observability environment
setup_observability_env() {
  local repo_root
  repo_root="${ROOT_DIR}"
  : "${SERVICE_NAME:=$(basename "${repo_root}")}"
  if [[ -z "${APP_VERSION:-}" ]]; then
    if git -C "${repo_root}" rev-parse --git-dir >/dev/null 2>&1; then
      APP_VERSION="$(git -C "${repo_root}" describe --tags --always --dirty 2>/dev/null || git -C "${repo_root}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    else
      APP_VERSION="unknown"
    fi
  fi
  : "${DEPLOY_COLOR:=blue}"
  : "${ENV:=dev}"
  export SERVICE_NAME APP_VERSION DEPLOY_COLOR ENV
  echo "🔧 Observability env => SERVICE_NAME=${SERVICE_NAME} APP_VERSION=${APP_VERSION} DEPLOY_COLOR=${DEPLOY_COLOR} ENV=${ENV}"
}

normalize_optional_enhancement_args() {
  local mode="$1"
  shift
  NORMALIZED_ARGS=()
  local with_search_enhancements=false
  local with_lancedb=false
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --with-searxng|--with-yacy)
        with_search_enhancements=true
        shift
        ;;
      --with-lancedb)
        with_lancedb=true
        shift
        ;;
      *)
        NORMALIZED_ARGS+=("$1")
        shift
        ;;
    esac
  done
  if [[ "$with_search_enhancements" == true ]]; then
    NORMALIZED_ARGS+=(--profile search-enhancements)
  fi
  if [[ "$with_lancedb" == true ]]; then
    export INSTALL_OPTIONAL_ENHANCEMENTS=true
    if [[ "$mode" == "start" || "$mode" == "restart" ]]; then
      NORMALIZED_ARGS+=(--build)
    fi
  fi
}

usage() {
  cat <<USAGE
Usage: $(basename "$0") {start|stop|restart|status|logs|health|preflight|checkpoint|rollback|rollback-list|rollback-drill} [extra args...]

Commands:
  start      Start docker services (preferred, extra args are forwarded)
  stop       Stop docker services (extra args are forwarded)
  restart    Restart docker services (extra args are forwarded)
  status     Show compose service status
  logs       Tail backend logs (extra args override default backend target)
  health     Check API health endpoints
  preflight  Validate commands/files/docker/ports (supports: --profile <name>)
  checkpoint Create rollback checkpoint (compose/env + git head)
  rollback   Roll back to checkpoint (default latest, supports --no-restart)
  rollback-list  List rollback checkpoints
  rollback-drill  Rehearse stop/start rollback path (supports: --profile <name> --dry-run --skip-preflight)
USAGE
}

compose() {
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  elif docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  else
    echo "❌ Missing docker-compose and docker compose" >&2
    return 127
  fi
}

require_ops_dir() {
  if [[ ! -d "${OPS_DIR}" ]]; then
    echo "❌ Missing directory: ${OPS_DIR}" >&2
    exit 1
  fi
  if [[ ! -f "${OPS_DIR}/docker-compose.yml" ]]; then
    echo "❌ Missing file: ${OPS_DIR}/docker-compose.yml" >&2
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
  elif [[ -x "${ROOT_DIR}/main/backend/.venv/bin/python" ]]; then
    printf '%s\n' "${ROOT_DIR}/main/backend/.venv/bin/python"
  else
    printf '%s\n' "python3"
  fi
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
  local checker="${ROOT_DIR}/main/backend/scripts/check_llm_report_export_secret_preflight.py"
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
  if "${backend_python}" "${ROOT_DIR}/main/backend/scripts/check_llm_report_export_secret_preflight.py" >/dev/null; then
    return 0
  fi
  echo "❌ Security preflight failed; run remediation:"
  echo "   ./scripts/docker-deploy.sh preflight"
  return 1
}

write_preflight_manifest() {
  local runtime_mode="$1"
  local status="$2"
  local exit_code="$3"
  local profile_label="$4"
  local manifest_path="${MRW_PREFLIGHT_MANIFEST:-${TMPDIR:-/tmp}/mrw_${runtime_mode}_preflight_manifest.json}"
  if ! command -v python3 >/dev/null 2>&1; then
    echo "⚠️ python3 not found; structured preflight evidence was not written"
    return 0
  fi
  python3 - "${preflight_records_file}" "${manifest_path}" "${runtime_mode}" "${status}" "${exit_code}" "${profile_label}" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


records_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
runtime_mode = sys.argv[3]
status = sys.argv[4]
exit_code = int(sys.argv[5])
profile_label = sys.argv[6].strip()

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
    return "unknown"


ports = category_checks("port")
security_secrets = category_checks("security_secret") + category_checks("secret")
auth_checks = category_checks("auth")
provider_revoke_checks = category_checks("provider_revoke")
app_server_runtime_checks = category_checks("app_server_runtime")
dependencies = category_checks("dependency") + category_checks("file") + category_checks("compose")
service_checks = category_checks("service")
failed_required = [item for item in checks if item["required"] and item["status"] == "failed"]
recommended_command = "./scripts/docker-deploy.sh preflight"
if profile_label:
    profile_args = " ".join(f"--profile {profile}" for profile in profile_label.split())
    recommended_command = f"{recommended_command} {profile_args}"

manifest = {
    "schema_version": "ops_preflight_evidence_contract.v1",
    "generated_at": now_utc(),
    "runtime_mode": runtime_mode,
    "status": status,
    "profiles": profile_label.split(),
    "service_ping": {
        "status": aggregate_status(service_checks, empty="skipped"),
        "checks": service_checks,
    },
    "service_ready": {
        "status": aggregate_status(category_checks("compose"), empty="skipped"),
        "checks": category_checks("compose"),
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
  local compose_flags=()
  local preflight_profiles_label=""
  local preflight_scrapyd=false
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --profile)
        if [[ $# -lt 2 ]]; then
          echo "❌ --profile requires a value"
          return 2
        fi
        compose_flags+=(--profile "$2")
        preflight_profiles_label+="$2 "
        if [[ "$2" == "scrapyd" ]]; then
          preflight_scrapyd=true
        fi
        shift 2
        ;;
      *)
        echo "❌ Unknown preflight arg: $1"
        return 2
        ;;
    esac
  done

  require_ops_dir
  local missing=0
  init_preflight_records

  for cmd in docker curl; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      echo "❌ Missing command: $cmd"
      record_preflight_check "dependency" "command:${cmd}" "failed" "true" "install ${cmd}" "command not found"
      missing=1
    else
      echo "✅ Found command: $cmd"
      record_preflight_check "dependency" "command:${cmd}" "passed" "true" "" "command found"
    fi
  done

  if [[ "$(uname -s 2>/dev/null || true)" == "Linux" ]]; then
    if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
      if command -v xdg-open >/dev/null 2>&1; then
        echo "✅ Found command: xdg-open (package: xdg-utils)"
        record_preflight_check "dependency" "command:xdg-open" "passed" "false" "" "Linux desktop opener found"
      else
        echo "❌ Missing command: xdg-open (install package: xdg-utils)"
        record_preflight_check "dependency" "command:xdg-open" "failed" "false" "install xdg-utils" "Linux desktop opener missing"
        missing=1
      fi
    else
      echo "ℹ️ No Linux desktop display detected; xdg-utils is only required for auto-opening Docker Launcher UI"
      record_preflight_check "dependency" "command:xdg-open" "skipped" "false" "" "no Linux desktop display detected"
    fi
  fi

  if command -v docker-compose >/dev/null 2>&1; then
    echo "✅ Compose command: docker-compose"
    record_preflight_check "dependency" "command:compose" "passed" "true" "" "docker-compose"
  elif docker compose version >/dev/null 2>&1; then
    echo "✅ Compose command: docker compose"
    record_preflight_check "dependency" "command:compose" "passed" "true" "" "docker compose"
  else
    echo "❌ Missing compose command"
    record_preflight_check "dependency" "command:compose" "failed" "true" "install docker compose" "compose command not found"
    missing=1
  fi

  for f in start-all.sh stop-all.sh restart.sh; do
    if [[ -f "${OPS_DIR}/${f}" ]]; then
      echo "✅ Found script: main/ops/${f}"
      record_preflight_check "file" "main/ops/${f}" "passed" "true" "" "script found"
    else
      echo "❌ Missing script: main/ops/${f}"
      record_preflight_check "file" "main/ops/${f}" "failed" "true" "restore main/ops/${f}" "script missing"
      missing=1
    fi
  done

  if [[ -f "${ROOT_DIR}/main/backend/.env" ]]; then
    echo "✅ Found env file: main/backend/.env"
    record_preflight_check "file" "main/backend/.env" "passed" "true" "" "env file found"
  else
    echo "❌ Missing env file: main/backend/.env (try: cp main/backend/.env.example main/backend/.env)"
    record_preflight_check "file" "main/backend/.env" "failed" "true" "cp main/backend/.env.example main/backend/.env" "env file missing"
    missing=1
  fi

  local backend_python
  backend_python="$(resolve_backend_python)"
  if record_backend_security_preflight_checks "${backend_python}"; then
    echo "✅ Backend security preflight passed"
  else
    echo "❌ Backend security preflight failed"
    missing=1
  fi

  if ! docker info >/dev/null 2>&1; then
    echo "⚠️ Docker daemon not running (cannot deploy now)"
    record_preflight_check "service" "docker-daemon" "failed" "true" "open Docker Desktop or start dockerd" "docker info failed"
    write_preflight_manifest "docker" "failed" "2" "$preflight_profiles_label"
    return 2
  fi
  record_preflight_check "service" "docker-daemon" "passed" "true" "" "docker info passed"

  check_port() {
    local port="$1"
    local service_name="$2"
    if ! command -v lsof >/dev/null 2>&1; then
      echo "⚠️ lsof not found; skip port check for ${service_name} (${port})"
      record_preflight_check "port" "${service_name}:${port}" "skipped" "false" "install lsof" "lsof not found"
      return 0
    fi
    if lsof -i :"${port}" >/dev/null 2>&1; then
      echo "❌ Port ${port} in use (${service_name})"
      record_preflight_check "port" "${service_name}:${port}" "failed" "true" "lsof -i :${port}" "port in use"
      missing=1
      return 1
    fi
    echo "✅ Port ${port} available (${service_name})"
    record_preflight_check "port" "${service_name}:${port}" "passed" "true" "" "port available"
    return 0
  }

  check_port 5432 "PostgreSQL" || true
  check_port 9200 "Elasticsearch" || true
  check_port 6379 "Redis" || true
  check_port 8000 "Backend API" || true
  if [[ "$preflight_scrapyd" == true ]]; then
    check_port 6800 "Scrapyd" || true
  fi

  if (
    cd "${OPS_DIR}"
    if (( ${#compose_flags[@]} > 0 )); then
      compose "${compose_flags[@]}" config >/dev/null
    else
      compose config >/dev/null
    fi
  ); then
    echo "✅ Compose config is valid"
    record_preflight_check "compose" "main/ops/docker-compose.yml" "passed" "true" "./scripts/docker-deploy.sh preflight" "compose config valid"
  else
    echo "❌ Compose config is invalid"
    record_preflight_check "compose" "main/ops/docker-compose.yml" "failed" "true" "./scripts/docker-deploy.sh preflight" "compose config invalid"
    missing=1
  fi
  if [[ -n "$preflight_profiles_label" ]]; then
    echo "✅ Compose profiles checked: ${preflight_profiles_label}"
  fi

  if [[ $missing -ne 0 ]]; then
    write_preflight_manifest "docker" "failed" "1" "$preflight_profiles_label"
    return 1
  fi
  write_preflight_manifest "docker" "passed" "0" "$preflight_profiles_label"
  return 0
}

rollback_drill() {
  local dry_run=false
  local skip_preflight=false
  local profile_args=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --profile)
        if [[ $# -lt 2 ]]; then
          echo "❌ --profile requires a value"
          return 2
        fi
        profile_args+=(--profile "$2")
        shift 2
        ;;
      --dry-run)
        dry_run=true
        shift
        ;;
      --skip-preflight)
        skip_preflight=true
        shift
        ;;
      *)
        echo "❌ Unknown rollback-drill arg: $1"
        return 2
        ;;
    esac
  done

  require_ops_dir

  if [[ "$dry_run" == true ]]; then
    local profile_suffix=""
    if (( ${#profile_args[@]} > 0 )); then
      profile_suffix=" ${profile_args[*]}"
    fi
    echo "🔁 rollback-drill dry-run"
    echo "   step1: ./scripts/docker-deploy.sh preflight${profile_suffix}"
    echo "   step2: ./scripts/docker-deploy.sh stop${profile_suffix}"
    echo "   step3: ./scripts/docker-deploy.sh start${profile_suffix}"
    echo "   step4: ./scripts/docker-deploy.sh health"
    echo "   step5: ./scripts/docker-deploy.sh stop${profile_suffix}"
    return 0
  fi

  if [[ "$skip_preflight" != true ]]; then
    preflight "${profile_args[@]}"
  fi

  "${OPS_DIR}/stop-all.sh" "${profile_args[@]}"
  "${OPS_DIR}/start-all.sh" --non-interactive "${profile_args[@]}"

  curl -fsS http://localhost:8000/api/v1/health >/dev/null
  curl -fsS http://localhost:8000/api/v1/health/deep >/dev/null

  "${OPS_DIR}/stop-all.sh" "${profile_args[@]}"
  echo "✅ rollback-drill completed"
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

cmd="$1"
shift
# Export and log observability env
setup_observability_env
case "$cmd" in
  start)
    require_ops_dir
    normalize_optional_enhancement_args start "$@"
    run_security_preflight_fail_fast
    exec "${OPS_DIR}/start-all.sh" "${NORMALIZED_ARGS[@]}"
    ;;
  stop)
    require_ops_dir
    normalize_optional_enhancement_args stop "$@"
    exec "${OPS_DIR}/stop-all.sh" "${NORMALIZED_ARGS[@]}"
    ;;
  restart)
    require_ops_dir
    normalize_optional_enhancement_args restart "$@"
    run_security_preflight_fail_fast
    exec "${OPS_DIR}/restart.sh" "${NORMALIZED_ARGS[@]}"
    ;;
  status)
    require_ops_dir
    cd "${OPS_DIR}"
    compose ps "$@"
    ;;
  logs)
    require_ops_dir
    cd "${OPS_DIR}"
    if [[ $# -gt 0 ]]; then
      compose logs "$@"
    else
      compose logs -f backend
    fi
    ;;
  health)
    curl -fsS http://localhost:8000/api/v1/health
    echo
    curl -fsS http://localhost:8000/api/v1/health/deep
    echo
    ;;
  preflight)
    preflight "$@"
    ;;
  checkpoint)
    require_ops_dir
    exec "${OPS_DIR}/rollback.sh" snapshot "$@"
    ;;
  rollback)
    require_ops_dir
    exec "${OPS_DIR}/rollback.sh" rollback "$@"
    ;;
  rollback-list)
    require_ops_dir
    exec "${OPS_DIR}/rollback.sh" list "$@"
    ;;
  rollback-drill)
    rollback_drill "$@"
    ;;
  *)
    usage
    exit 1
    ;;
esac
