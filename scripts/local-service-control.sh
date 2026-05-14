#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/main/backend"
FRONTEND_DIR="${ROOT_DIR}/main/frontend-modern"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_LOG_FILE="/tmp/frontend-modern-dev.log"
FRONTEND_PID_FILE="/tmp/frontend-modern-dev.pid"
WORKER_LOG_FILE="/tmp/celery-local-worker.log"
WORKER_PID_FILE="/tmp/celery-local-worker.pid"
CELERY_LOG_LEVEL="${CELERY_LOG_LEVEL:-info}"
CELERY_CONCURRENCY="${CELERY_CONCURRENCY:-3}"
CELERY_PREFETCH_MULTIPLIER="${CELERY_PREFETCH_MULTIPLIER:-2}"
CELERY_MAX_TASKS_PER_CHILD="${CELERY_MAX_TASKS_PER_CHILD:-100}"
CELERY_MAX_MEMORY_PER_CHILD="${CELERY_MAX_MEMORY_PER_CHILD:-500000}"
CELERY_QUEUES="${CELERY_QUEUES:-celery}"
if [[ "$OSTYPE" == darwin* ]]; then
  CELERY_POOL="${CELERY_POOL:-solo}"
else
  CELERY_POOL="${CELERY_POOL:-prefork}"
fi

usage() {
  cat <<'EOF'
Usage: local-service-control.sh {frontend-start|frontend-stop|worker-start|worker-stop|backend-start|backend-stop|local-stop}

Controls one local runtime surface without touching Docker compose services.
EOF
}

is_listening() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

stop_frontend() {
  if [[ -f "$FRONTEND_PID_FILE" ]]; then
    pid="$(cat "$FRONTEND_PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" 2>/dev/null || true
      sleep 1
    fi
    rm -f "$FRONTEND_PID_FILE"
  fi
  if is_listening "$FRONTEND_PORT"; then
    lsof -ti:"$FRONTEND_PORT" | xargs kill -9 2>/dev/null || true
  fi
  echo "✅ local frontend stopped"
}

start_frontend() {
  if is_listening "$FRONTEND_PORT"; then
    echo "✅ local frontend already listening on :$FRONTEND_PORT"
    return 0
  fi
  if ! command -v npm >/dev/null 2>&1; then
    echo "❌ npm is required to start frontend"
    return 1
  fi
  cd "$FRONTEND_DIR"
  if [[ ! -d node_modules ]]; then
    npm install
  fi
  VITE_API_PROXY_TARGET="http://localhost:8000" nohup npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" >"$FRONTEND_LOG_FILE" 2>&1 &
  echo "$!" >"$FRONTEND_PID_FILE"
  echo "✅ local frontend starting on :$FRONTEND_PORT"
}

stop_worker() {
  if [[ -f "$WORKER_PID_FILE" ]]; then
    pid="$(cat "$WORKER_PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" 2>/dev/null || true
      sleep 1
    fi
    rm -f "$WORKER_PID_FILE"
  fi
  pkill -f "${BACKEND_DIR}/.venv311/bin/celery.*-A app.celery_app worker" 2>/dev/null || true
  echo "✅ local worker stopped"
}

start_worker() {
  cd "$BACKEND_DIR"
  if [[ -f "$WORKER_PID_FILE" ]]; then
    pid="$(cat "$WORKER_PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      echo "✅ local worker already running (PID $pid)"
      return 0
    fi
    rm -f "$WORKER_PID_FILE"
  fi
  if [[ ! -x .venv311/bin/celery ]]; then
    echo "❌ missing .venv311/bin/celery; start the local stack once to install backend dependencies"
    return 1
  fi
  worker_nodename="celery-local-$(date +%s)@%h"
  nohup .venv311/bin/celery -A app.celery_app worker \
    --hostname="$worker_nodename" \
    --pool="$CELERY_POOL" \
    --loglevel="$CELERY_LOG_LEVEL" \
    --concurrency="$CELERY_CONCURRENCY" \
    --prefetch-multiplier="$CELERY_PREFETCH_MULTIPLIER" \
    --max-tasks-per-child="$CELERY_MAX_TASKS_PER_CHILD" \
    --max-memory-per-child="$CELERY_MAX_MEMORY_PER_CHILD" \
    --queues="$CELERY_QUEUES" \
    >"$WORKER_LOG_FILE" 2>&1 &
  echo "$!" >"$WORKER_PID_FILE"
  echo "✅ local worker starting"
}

stop_backend() {
  pids="$(lsof -ti:8000 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    echo "✅ local backend not listening"
    return 0
  fi
  killed=0
  for pid in $pids; do
    command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if [[ "$command_line" == *"uvicorn app.main:app"* || "$command_line" == *"/uvicorn app.main:app"* ]]; then
      kill -9 "$pid" 2>/dev/null || true
      killed=1
    fi
  done
  if [[ "$killed" == "1" ]]; then
    echo "✅ local backend stopped"
  else
    echo "ℹ️ :8000 is not owned by local uvicorn; skipped"
  fi
}

start_backend() {
  cd "$ROOT_DIR"
  exec ./scripts/local-deploy.sh start --force --no-local-worker
}

cmd="${1:-}"
case "$cmd" in
  frontend-start) start_frontend ;;
  frontend-stop) stop_frontend ;;
  worker-start) start_worker ;;
  worker-stop) stop_worker ;;
  backend-start) start_backend ;;
  backend-stop) stop_backend ;;
  local-stop) exec "${ROOT_DIR}/scripts/local-deploy.sh" stop --local-only ;;
  -h|--help|"") usage ;;
  *)
    usage
    exit 2
    ;;
esac
