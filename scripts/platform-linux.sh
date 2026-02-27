#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

BACKEND_DIR="${ROOT_DIR}/main/backend"
DEPLOY_SCRIPT="${ROOT_DIR}/scripts/docker-deploy.sh"

usage() {
  echo "Usage: $(basename "$0") {start|stop|restart|local-start|local-stop}"
}

if [[ ! -d "${BACKEND_DIR}" ]]; then
  echo "Error: missing directory: ${BACKEND_DIR}" >&2
  exit 1
fi

if [[ ! -f "${DEPLOY_SCRIPT}" ]]; then
  echo "Error: script not found: ${DEPLOY_SCRIPT}" >&2
  exit 1
fi

if [[ $# -ne 1 ]]; then
  usage
  exit 1
fi

cmd="$1"
target=""
target_arg=""

case "${cmd}" in
  start)
    target="${DEPLOY_SCRIPT}"
    target_arg="${cmd}"
    ;;
  stop)
    target="${DEPLOY_SCRIPT}"
    target_arg="${cmd}"
    ;;
  restart)
    target="${DEPLOY_SCRIPT}"
    target_arg="${cmd}"
    ;;
  local-start)
    target="${BACKEND_DIR}/start-local.sh"
    ;;
  local-stop)
    target="${BACKEND_DIR}/stop-local.sh"
    ;;
  *)
    echo "Error: unsupported command: ${cmd}" >&2
    usage
    exit 1
    ;;
esac

if [[ ! -f "${target}" ]]; then
  echo "Error: script not found: ${target}" >&2
  exit 1
fi

echo "Running: ${cmd}"
if [[ -n "${target_arg}" ]]; then
  exec "${target}" "${target_arg}"
fi
exec "${target}"
