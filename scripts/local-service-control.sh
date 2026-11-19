#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/main/backend"
FRONTEND_DIR="${ROOT_DIR}/main/frontend-modern"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_MODE="${FRONTEND_MODE:-preview}"
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
FRONTEND_LAUNCHD_LABEL="com.mrw.frontend-modern"
WORKER_LAUNCHD_LABEL="com.mrw.local-worker"
BACKEND_LAUNCHD_LABEL="com.mrw.successor-backend"
FRONTEND_USE_LAUNCHD="${FRONTEND_USE_LAUNCHD:-0}"
WORKER_USE_LAUNCHD="${WORKER_USE_LAUNCHD:-0}"
BACKEND_USE_LAUNCHD="${BACKEND_USE_LAUNCHD:-0}"
if [[ "$OSTYPE" == darwin* ]]; then
  CELERY_POOL="${CELERY_POOL:-solo}"
else
  CELERY_POOL="${CELERY_POOL:-prefork}"
fi
GUI_DOMAIN="gui/$(id -u)"

usage() {
  cat <<'EOF'
Usage: local-service-control.sh {frontend-start|frontend-stop|worker-start|worker-stop|backend-start|backend-stop|local-stop}

Controls one local runtime surface without touching Docker compose services.
Set FRONTEND_USE_LAUNCHD=1, WORKER_USE_LAUNCHD=1, or BACKEND_USE_LAUNCHD=1
only when the corresponding host LaunchAgent is intentionally owned by this source root.
EOF
}

is_listening() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

launchd_plist_path() {
  printf '%s/Library/LaunchAgents/%s.plist' "$HOME" "$1"
}

is_launchd_service_loaded() {
  launchctl print "$GUI_DOMAIN/$1" >/dev/null 2>&1
}

start_launchd_service() {
  local label="$1"
  if ! is_launchd_service_loaded "$label"; then
    launchctl bootstrap "$GUI_DOMAIN" "$(launchd_plist_path "$label")"
  fi
  launchctl kickstart "$GUI_DOMAIN/$label"
  echo "✅ local $2 managed by launchd ($label)"
}

stop_launchd_service() {
  local label="$1"
  if is_launchd_service_loaded "$label"; then
    launchctl bootout "$GUI_DOMAIN/$label"
    echo "✅ local $2 stopped by launchd"
  else
    echo "ℹ️ local $2 launchd service is not loaded"
  fi
}

pid_cwd() {
  lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1
}

terminate_pid_gracefully() {
  local pid="$1"
  local label="$2"
  kill -TERM "$pid" 2>/dev/null || return 1
  for _ in $(seq 1 20); do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.1
  done
  kill -KILL "$pid" 2>/dev/null || true
  sleep 0.2
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "❌ cannot stop $pid owned by $label" >&2
    return 1
  fi
  return 0
}

stop_owned_port_listener() {
  local port="$1"
  local expected_cwd="$2"
  local command_marker="$3"
  local pid command_line cwd foreign_owner=0
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    cwd="$(pid_cwd "$pid")"
    if [[ "$cwd" == "$expected_cwd" && "$command_line" == *"$command_marker"* ]]; then
      terminate_pid_gracefully "$pid" "$expected_cwd" || return 1
    else
      foreign_owner=1
    fi
  done < <(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)

  if [[ "$foreign_owner" == "1" ]]; then
    echo "ℹ️ :$port contains a process not owned by $expected_cwd; skipped"
    return 1
  fi
  return 0
}

port_has_only_owned_listener() {
  local port="$1"
  local expected_cwd="$2"
  local command_marker="$3"
  local pid command_line cwd
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    cwd="$(pid_cwd "$pid")"
    if [[ "$cwd" != "$expected_cwd" || "$command_line" != *"$command_marker"* ]]; then
      return 1
    fi
  done < <(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)
  return 0
}

stop_frontend() {
  local pid command_line cwd
  if [[ "$OSTYPE" == darwin* && "$FRONTEND_USE_LAUNCHD" == "1" && -f "$(launchd_plist_path "$FRONTEND_LAUNCHD_LABEL")" ]]; then
    stop_launchd_service "$FRONTEND_LAUNCHD_LABEL" "frontend"
    return
  fi
  if [[ -f "$FRONTEND_PID_FILE" ]]; then
    pid="$(cat "$FRONTEND_PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
      cwd="$(pid_cwd "$pid")"
      if [[ "$cwd" == "$FRONTEND_DIR" && "$command_line" == *"vite"* ]]; then
        terminate_pid_gracefully "$pid" "$FRONTEND_DIR" || return 1
      else
        echo "ℹ️ frontend PID file points outside $FRONTEND_DIR; skipped"
      fi
    fi
    rm -f "$FRONTEND_PID_FILE"
  fi
  if is_listening "$FRONTEND_PORT"; then
    stop_owned_port_listener "$FRONTEND_PORT" "$FRONTEND_DIR" "vite" || true
  fi
  echo "✅ local frontend stopped"
}

start_frontend() {
  if [[ "$OSTYPE" == darwin* && "$FRONTEND_USE_LAUNCHD" == "1" && -f "$(launchd_plist_path "$FRONTEND_LAUNCHD_LABEL")" ]]; then
    start_launchd_service "$FRONTEND_LAUNCHD_LABEL" "frontend"
    return
  fi
  if [[ -n "$(lsof -nP -iTCP:"$FRONTEND_PORT" -sTCP:LISTEN -t 2>/dev/null || true)" ]]; then
    if port_has_only_owned_listener "$FRONTEND_PORT" "$FRONTEND_DIR" "vite"; then
      echo "✅ local frontend already listening on :$FRONTEND_PORT"
      return 0
    fi
    echo "❌ :$FRONTEND_PORT is not owned by this frontend; refusing to start"
    return 1
  fi
  if ! command -v pnpm >/dev/null 2>&1; then
    echo "❌ pnpm is required to start frontend"
    return 1
  fi
  cd "$FRONTEND_DIR"
  if [[ ! -x node_modules/.bin/vite ]]; then
    echo "❌ frontend dependencies missing; run scripts/local-deploy.sh prepare"
    return 1
  fi
  if [[ "$FRONTEND_MODE" == "preview" && ! -f dist/index.html ]]; then
    echo "❌ frontend dist/index.html missing; build it before preview mode"
    return 1
  fi
  VITE_API_PROXY_TARGET="http://localhost:8000" nohup pnpm run "$FRONTEND_MODE" --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" --strictPort >"$FRONTEND_LOG_FILE" 2>&1 &
  echo "$!" >"$FRONTEND_PID_FILE"
  echo "✅ local frontend starting on :$FRONTEND_PORT"
}

stop_worker() {
  local pid command_line cwd
  if [[ "$OSTYPE" == darwin* && "$WORKER_USE_LAUNCHD" == "1" && -f "$(launchd_plist_path "$WORKER_LAUNCHD_LABEL")" ]]; then
    stop_launchd_service "$WORKER_LAUNCHD_LABEL" "worker"
    return
  fi
  if [[ -f "$WORKER_PID_FILE" ]]; then
    pid="$(cat "$WORKER_PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
      cwd="$(pid_cwd "$pid")"
      if [[ "$cwd" == "$BACKEND_DIR" && "$command_line" == *"app.celery_app worker"* ]]; then
        terminate_pid_gracefully "$pid" "$BACKEND_DIR" || return 1
      else
        echo "ℹ️ worker PID file points outside $BACKEND_DIR; skipped"
      fi
    fi
    rm -f "$WORKER_PID_FILE"
  fi
  pkill -f "${BACKEND_DIR}/.venv311/bin/celery.*-A app.celery_app worker" 2>/dev/null || true
  echo "✅ local worker stopped"
}

start_worker() {
  if [[ "$OSTYPE" == darwin* && "$WORKER_USE_LAUNCHD" == "1" && -f "$(launchd_plist_path "$WORKER_LAUNCHD_LABEL")" ]]; then
    start_launchd_service "$WORKER_LAUNCHD_LABEL" "worker"
    return
  fi
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
  if [[ "$OSTYPE" == darwin* && "$BACKEND_USE_LAUNCHD" == "1" && -f "$(launchd_plist_path "$BACKEND_LAUNCHD_LABEL")" ]] && is_launchd_service_loaded "$BACKEND_LAUNCHD_LABEL"; then
    stop_launchd_service "$BACKEND_LAUNCHD_LABEL" "backend"
    return
  fi
  pids="$(lsof -ti:8000 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    echo "✅ local backend not listening"
    return 0
  fi
  killed=0
  if stop_owned_port_listener 8000 "$BACKEND_DIR" "uvicorn app.main:app"; then
    killed=1
  fi
  if [[ "$killed" == "1" ]]; then
    echo "✅ local backend stopped"
  else
    echo "ℹ️ :8000 is not owned by local uvicorn; skipped"
  fi
}

start_backend() {
  if [[ "$OSTYPE" == darwin* && "$BACKEND_USE_LAUNCHD" == "1" && -f "$(launchd_plist_path "$BACKEND_LAUNCHD_LABEL")" ]]; then
    start_launchd_service "$BACKEND_LAUNCHD_LABEL" "backend"
    return
  fi
  cd "$ROOT_DIR"
  exec ./scripts/local-deploy.sh start --backend-only --no-local-worker --non-interactive --no-provision
}

cmd="${1:-}"
case "$cmd" in
  frontend-start) start_frontend ;;
  frontend-stop) stop_frontend ;;
  worker-start) start_worker ;;
  worker-stop) stop_worker ;;
  backend-start) start_backend ;;
  backend-stop) stop_backend ;;
  local-stop)
    stop_worker
    stop_frontend
    stop_backend
    ;;
  -h|--help|"") usage ;;
  *)
    usage
    exit 2
    ;;
esac
