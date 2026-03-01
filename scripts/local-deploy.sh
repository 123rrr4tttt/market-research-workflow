#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/main/backend"
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
  local-deploy.sh start
  local-deploy.sh stop
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

case "$cmd" in
  start)
    require_backend_dir
    cd "${BACKEND_DIR}"
    exec ./start-local.sh "$@"
    ;;
  stop)
    require_backend_dir
    cd "${BACKEND_DIR}"
    exec ./stop-local.sh "$@"
    ;;
  restart)
    require_backend_dir
    cd "${BACKEND_DIR}"
    ./stop-local.sh "$@" || true
    exec ./start-local.sh "$@"
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
