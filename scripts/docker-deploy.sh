#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OPS_DIR="${ROOT_DIR}/main/ops"

usage() {
  cat <<USAGE
Usage: $(basename "$0") {start|stop|restart|status|logs|health|preflight} [extra args...]

Commands:
  start      Start docker services (preferred, extra args are forwarded)
  stop       Stop docker services (extra args are forwarded)
  restart    Restart docker services (extra args are forwarded)
  status     Show compose service status
  logs       Tail backend logs (extra args override default backend target)
  health     Check API health endpoints
  preflight  Validate required commands/files and docker availability
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

preflight() {
  require_ops_dir
  local missing=0
  for cmd in docker curl; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      echo "❌ Missing command: $cmd"
      missing=1
    else
      echo "✅ Found command: $cmd"
    fi
  done

  if command -v docker-compose >/dev/null 2>&1; then
    echo "✅ Compose command: docker-compose"
  elif docker compose version >/dev/null 2>&1; then
    echo "✅ Compose command: docker compose"
  else
    echo "❌ Missing compose command"
    missing=1
  fi

  for f in start-all.sh stop-all.sh restart.sh; do
    if [[ -f "${OPS_DIR}/${f}" ]]; then
      echo "✅ Found script: main/ops/${f}"
    else
      echo "❌ Missing script: main/ops/${f}"
      missing=1
    fi
  done

  if [[ -f "${ROOT_DIR}/main/backend/.env" ]]; then
    echo "✅ Found env file: main/backend/.env"
  else
    echo "❌ Missing env file: main/backend/.env (try: cp main/backend/.env.example main/backend/.env)"
    missing=1
  fi

  if ! docker info >/dev/null 2>&1; then
    echo "⚠️ Docker daemon not running (cannot deploy now)"
    return 2
  fi

  (
    cd "${OPS_DIR}"
    compose config >/dev/null
  )
  echo "✅ Compose config is valid"

  if [[ $missing -ne 0 ]]; then
    return 1
  fi
  return 0
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

cmd="$1"
shift
case "$cmd" in
  start)
    require_ops_dir
    exec "${OPS_DIR}/start-all.sh" "$@"
    ;;
  stop)
    require_ops_dir
    exec "${OPS_DIR}/stop-all.sh" "$@"
    ;;
  restart)
    require_ops_dir
    exec "${OPS_DIR}/restart.sh" "$@"
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
    preflight
    ;;
  *)
    usage
    exit 1
    ;;
esac
