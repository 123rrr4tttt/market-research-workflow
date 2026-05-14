#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OPS_DIR="${ROOT_DIR}/main/ops"
HOST_PROJECT_ROOT="${HOST_PROJECT_ROOT:-${ROOT_DIR}}"

APP_SERVICES=(db es redis backend celery-worker frontend-modern)
SEARCH_SERVICES=(searxng yacy)

usage() {
  echo "Usage: $(basename "$0") {start|stop|restart|status} [--with-search]"
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

cmd="$1"
shift

profiles=(--profile modern-ui)
services=("${APP_SERVICES[@]}")

for arg in "$@"; do
  case "$arg" in
    --with-search|--with-searxng|--with-yacy)
      profiles+=(--profile search-enhancements)
      services+=("${SEARCH_SERVICES[@]}")
      ;;
    *)
      echo "Error: unsupported argument: $arg" >&2
      usage
      exit 1
      ;;
  esac
done

cd "$OPS_DIR"

case "$cmd" in
  start)
    HOST_PROJECT_ROOT="$HOST_PROJECT_ROOT" docker compose "${profiles[@]}" up -d "${services[@]}"
    ;;
  stop)
    HOST_PROJECT_ROOT="$HOST_PROJECT_ROOT" docker compose "${profiles[@]}" stop "${services[@]}"
    ;;
  restart)
    HOST_PROJECT_ROOT="$HOST_PROJECT_ROOT" docker compose --profile modern-ui --profile search-enhancements stop "${APP_SERVICES[@]}" "${SEARCH_SERVICES[@]}" || true
    HOST_PROJECT_ROOT="$HOST_PROJECT_ROOT" docker compose "${profiles[@]}" up -d "${services[@]}"
    ;;
  status)
    HOST_PROJECT_ROOT="$HOST_PROJECT_ROOT" docker compose --profile modern-ui --profile search-enhancements ps --status running --services \
      | awk 'NF && $0 != "launcher-agent" && $0 != "launcher-ui"'
    ;;
  *)
    echo "Error: unsupported command: $cmd" >&2
    usage
    exit 1
    ;;
esac
