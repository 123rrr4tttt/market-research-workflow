#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OPS_DIR="${ROOT_DIR}/main/ops"
HOST_PROJECT_ROOT="${HOST_PROJECT_ROOT:-${ROOT_DIR}}"
LAUNCHER_PROJECT_NAME="${LAUNCHER_PROJECT_NAME:-mrw-launcher}"
LAUNCHER_URL="${LAUNCHER_URL:-http://127.0.0.1:5176}"
MAX_WAIT="${MAX_WAIT:-90}"

open_url() {
  local url="$1"
  if [[ "${OSTYPE:-}" == darwin* ]]; then
    open "$url" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
  elif command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "Start-Process '$url'" >/dev/null 2>&1 || true
  else
    echo "Open this URL: $url"
  fi
}

ensure_docker_ready() {
  if docker info >/dev/null 2>&1; then
    return 0
  fi
  echo "Docker daemon is not ready; trying to open Docker Desktop..."
  if [[ "${OSTYPE:-}" == darwin* ]]; then
    open -a Docker >/dev/null 2>&1 || true
  fi
  local waited=0
  while [[ "$waited" -lt "$MAX_WAIT" ]]; do
    if docker info >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done
  echo "Docker daemon did not become ready within ${MAX_WAIT}s" >&2
  return 1
}

wait_for_launcher() {
  local waited=0
  while [[ "$waited" -lt "$MAX_WAIT" ]]; do
    if curl -fsS --max-time 1 "$LAUNCHER_URL" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done
  return 1
}

ensure_docker_ready

cd "$OPS_DIR"
echo "Starting Docker control UI only..."
HOST_PROJECT_ROOT="$HOST_PROJECT_ROOT" docker compose --profile modern-ui stop launcher-ui launcher-agent >/dev/null 2>&1 || true
HOST_PROJECT_ROOT="$HOST_PROJECT_ROOT" LAUNCHER_PROJECT_NAME="$LAUNCHER_PROJECT_NAME" \
  docker compose --project-name "$LAUNCHER_PROJECT_NAME" --profile modern-ui up -d --build launcher-agent launcher-ui

if wait_for_launcher; then
  echo "Opening Docker Web Launcher: $LAUNCHER_URL"
  open_url "$LAUNCHER_URL"
else
  echo "Docker Web Launcher did not become reachable: $LAUNCHER_URL" >&2
  exit 1
fi
