#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OPS_DIR="${ROOT_DIR}/main/ops"
BACKEND_DIR="${ROOT_DIR}/main/backend"
OPTIONAL_REQ="${BACKEND_DIR}/requirements-optional-enhancements.txt"
VENV_DIR="${BACKEND_DIR}/.venv311"
OPTIONAL_REQ_HASH_FILE="${VENV_DIR}/.requirements-optional-enhancements.sha256"

usage() {
  cat <<'USAGE'
Usage: optional-enhancements.sh {start|stop|status|install-lancedb} [options]

Options:
  --searxng       Start/status/stop SearXNG optional service
  --yacy          Start/status/stop YaCy optional service
  --lancedb       Install/status LanceDB optional Python dependency
  --all           Select all optional enhancements

These enhancements are opt-in. Base local/docker startup remains unchanged.
USAGE
}

compose() {
  cd "${OPS_DIR}"
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose --profile search-enhancements "$@"
  elif docker compose version >/dev/null 2>&1; then
    docker compose --profile search-enhancements "$@"
  else
    echo "❌ Missing docker compose command" >&2
    return 127
  fi
}

select_services=()
with_lancedb=false

parse_flags() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --searxng)
        select_services+=(searxng)
        shift
        ;;
      --yacy)
        select_services+=(yacy)
        shift
        ;;
      --lancedb)
        with_lancedb=true
        shift
        ;;
      --all)
        select_services+=(searxng yacy)
        with_lancedb=true
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "❌ Unknown option: $1" >&2
        usage
        exit 2
        ;;
    esac
  done
}

dedupe_services() {
  local seen=""
  local next=()
  local service
  for service in ${select_services[@]+"${select_services[@]}"}; do
    if [[ " ${seen} " != *" ${service} "* ]]; then
      next+=("${service}")
      seen="${seen} ${service}"
    fi
  done
  if (( ${#next[@]} > 0 )); then
    select_services=("${next[@]}")
  else
    select_services=()
  fi
}

install_lancedb() {
  if [[ ! -f "${OPTIONAL_REQ}" ]]; then
    echo "❌ Missing optional requirements: ${OPTIONAL_REQ}" >&2
    return 1
  fi
  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    echo "⚠️ Backend venv not found yet; start-local will create it before optional install"
    return 0
  fi
  local cur_hash old_hash
  cur_hash="$(shasum -a 256 "${OPTIONAL_REQ}" | awk '{print $1}')"
  old_hash=""
  if [[ -f "${OPTIONAL_REQ_HASH_FILE}" ]]; then
    old_hash="$(cat "${OPTIONAL_REQ_HASH_FILE}" 2>/dev/null || true)"
  fi
  if "${VENV_DIR}/bin/python" - <<'PY' >/dev/null 2>&1
import lancedb
PY
  then
    if [[ "${cur_hash}" == "${old_hash}" ]]; then
      echo "✅ LanceDB optional dependency already installed"
      return 0
    fi
  fi
  echo "📦 Installing optional LanceDB dependency"
  "${VENV_DIR}/bin/python" -m pip install -r "${OPTIONAL_REQ}"
  echo "${cur_hash}" > "${OPTIONAL_REQ_HASH_FILE}"
}

status_lancedb() {
  if [[ -x "${VENV_DIR}/bin/python" ]] && "${VENV_DIR}/bin/python" - <<'PY' >/dev/null 2>&1
import lancedb
PY
  then
    echo "✅ lancedb installed in backend venv"
  else
    echo "⚠️ lancedb not installed in backend venv"
  fi
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

cmd="$1"
shift
parse_flags "$@"
dedupe_services

case "${cmd}" in
  start)
    if (( ${#select_services[@]} > 0 )); then
      if ! docker info >/dev/null 2>&1; then
        echo "❌ Docker is required for SearXNG/YaCy optional services" >&2
        exit 1
      fi
      echo "🚀 Starting optional services: ${select_services[*]}"
      compose up -d ${select_services[@]+"${select_services[@]}"}
    fi
    if [[ "${with_lancedb}" == true ]]; then
      install_lancedb
    fi
    ;;
  stop)
    if (( ${#select_services[@]} == 0 )); then
      select_services=(searxng yacy)
    fi
    if docker info >/dev/null 2>&1; then
      echo "🛑 Stopping optional services: ${select_services[*]}"
      compose stop ${select_services[@]+"${select_services[@]}"} >/dev/null 2>&1 || true
    fi
    ;;
  status)
    if docker info >/dev/null 2>&1; then
      compose ps searxng yacy || true
    else
      echo "⚠️ Docker not running; SearXNG/YaCy unavailable"
    fi
    status_lancedb
    ;;
  install-lancedb)
    install_lancedb
    ;;
  *)
    echo "❌ Unknown command: ${cmd}" >&2
    usage
    exit 2
    ;;
esac
