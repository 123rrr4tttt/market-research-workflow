#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/main/backend"
OPTIONAL_ENHANCEMENTS_SCRIPT="${ROOT_DIR}/scripts/optional-enhancements.sh"
WORKER_PID_FILE="/tmp/celery-local-worker.pid"

usage() {
  cat <<USAGE
Usage: $(basename "$0") {start|stop|restart|status|health} [extra args...]

Commands:
  start      Start pure-local stack via backend/start-local.sh
  stop       Stop pure-local stack via backend/stop-local.sh
  restart    Restart pure-local stack
  status     Show local process status (backend/frontend/worker)
  health     Check local backend health endpoints

Examples:
  local-deploy.sh start --with-searxng --with-yacy --with-lancedb
  local-deploy.sh stop --local-only
USAGE
}

require_backend_dir() {
  if [[ ! -d "${BACKEND_DIR}" ]]; then
    echo "❌ Missing directory: ${BACKEND_DIR}" >&2
    exit 1
  fi
}

is_listening() {
  local port="$1"
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
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
    *)
      START_LOCAL_ARGS+=("$arg")
      STOP_LOCAL_ARGS+=("$arg")
      ;;
  esac
done

case "$cmd" in
  start)
    require_backend_dir
    if [[ "${HELP_REQUESTED}" -eq 1 ]]; then
      cd "${BACKEND_DIR}"
      exec ./start-local.sh --help
    fi
    if [[ ${#ENHANCEMENT_ARGS[@]} -gt 0 ]]; then
      "${OPTIONAL_ENHANCEMENTS_SCRIPT}" start "${ENHANCEMENT_ARGS[@]}"
    fi
    cd "${BACKEND_DIR}"
    exec ./start-local.sh "${START_LOCAL_ARGS[@]}"
    ;;
  stop)
    "${OPTIONAL_ENHANCEMENTS_SCRIPT}" stop || true
    require_backend_dir
    cd "${BACKEND_DIR}"
    exec ./stop-local.sh "${STOP_LOCAL_ARGS[@]}"
    ;;
  restart)
    require_backend_dir
    "${OPTIONAL_ENHANCEMENTS_SCRIPT}" stop || true
    cd "${BACKEND_DIR}"
    ./stop-local.sh "${STOP_LOCAL_ARGS[@]}" || true
    if [[ ${#ENHANCEMENT_ARGS[@]} -gt 0 ]]; then
      "${OPTIONAL_ENHANCEMENTS_SCRIPT}" start "${ENHANCEMENT_ARGS[@]}"
    fi
    exec ./start-local.sh "${START_LOCAL_ARGS[@]}"
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
