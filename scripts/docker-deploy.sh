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
  preflight  Validate commands/files/docker/ports (supports: --profile <name>)
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

  check_port() {
    local port="$1"
    local service_name="$2"
    if ! command -v lsof >/dev/null 2>&1; then
      echo "⚠️ lsof not found; skip port check for ${service_name} (${port})"
      return 0
    fi
    if lsof -i :"${port}" >/dev/null 2>&1; then
      echo "❌ Port ${port} in use (${service_name})"
      missing=1
      return 1
    fi
    echo "✅ Port ${port} available (${service_name})"
    return 0
  }

  check_port 5432 "PostgreSQL"
  check_port 9200 "Elasticsearch"
  check_port 6379 "Redis"
  check_port 8000 "Backend API"
  if [[ "$preflight_scrapyd" == true ]]; then
    check_port 6800 "Scrapyd"
  fi

  (
    cd "${OPS_DIR}"
    compose "${compose_flags[@]}" config >/dev/null
  )
  echo "✅ Compose config is valid"
  if [[ -n "$preflight_profiles_label" ]]; then
    echo "✅ Compose profiles checked: ${preflight_profiles_label}"
  fi

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
    preflight "$@"
    ;;
  *)
    usage
    exit 1
    ;;
esac
