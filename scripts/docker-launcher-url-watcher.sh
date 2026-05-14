#!/usr/bin/env bash

set -euo pipefail

LAUNCHER_URL="${LAUNCHER_URL:-http://127.0.0.1:5176}"
PROJECT_NAME="${LAUNCHER_PROJECT_NAME:-mrw-launcher}"
SERVICE_NAME="${LAUNCHER_SERVICE_NAME:-launcher-ui}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/market-research-workflow"
LAST_OPEN_FILE="${STATE_DIR}/docker-launcher-url-watcher.last-open"
COOLDOWN_SECONDS="${COOLDOWN_SECONDS:-8}"

mkdir -p "$STATE_DIR"

log() {
  printf '[docker-launcher-url-watcher] %s\n' "$*" >&2
}

is_macos() {
  [[ "${OSTYPE:-}" == darwin* ]]
}

is_launcher_running() {
  docker ps \
    --filter "label=com.docker.compose.project=${PROJECT_NAME}" \
    --filter "label=com.docker.compose.service=${SERVICE_NAME}" \
    --format '{{.ID}}' 2>/dev/null | grep -q .
}

wait_for_url() {
  local waited=0
  while [[ "$waited" -lt 45 ]]; do
    if curl -fsS --max-time 1 "$LAUNCHER_URL" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done
  return 1
}

recently_opened() {
  local now last
  now="$(date +%s)"
  last="$(cat "$LAST_OPEN_FILE" 2>/dev/null || echo 0)"
  [[ $((now - last)) -lt "$COOLDOWN_SECONDS" ]]
}

open_launcher() {
  if recently_opened; then
    return 0
  fi
  if ! wait_for_url; then
    log "launcher URL not reachable: ${LAUNCHER_URL}"
    return 1
  fi
  date +%s >"$LAST_OPEN_FILE"
  if is_macos; then
    open "$LAUNCHER_URL" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$LAUNCHER_URL" >/dev/null 2>&1 || true
  else
    log "Open this URL: ${LAUNCHER_URL}"
  fi
}

wait_for_docker() {
  until docker info >/dev/null 2>&1; do
    sleep 3
  done
}

main() {
  wait_for_docker
  if is_launcher_running; then
    open_launcher || true
  fi
  while true; do
    docker events \
      --filter type=container \
      --filter event=start \
      --filter "label=com.docker.compose.project=${PROJECT_NAME}" \
      --filter "label=com.docker.compose.service=${SERVICE_NAME}" \
      --format '{{.Time}} {{.Actor.Attributes.name}}' 2>/dev/null |
      while read -r _event_time _container_name; do
        open_launcher || true
      done
    sleep 3
    wait_for_docker
  done
}

main "$@"
