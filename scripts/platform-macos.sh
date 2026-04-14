#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

BACKEND_DIR="${ROOT_DIR}/main/backend"
LOCAL_DEPLOY_SCRIPT="${ROOT_DIR}/scripts/local-deploy.sh"

usage() {
  echo "Usage: $(basename "$0") {start|stop|restart|status|health|local-start|local-stop} [extra args...]"
}

if [[ ! -d "${BACKEND_DIR}" ]]; then
  echo "Error: missing directory: ${BACKEND_DIR}" >&2
  exit 1
fi

if [[ ! -f "${LOCAL_DEPLOY_SCRIPT}" ]]; then
  echo "Error: script not found: ${LOCAL_DEPLOY_SCRIPT}" >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

cmd="$1"
shift
target="${LOCAL_DEPLOY_SCRIPT}"
target_arg=""

case "${cmd}" in
  start)
    target_arg="start"
    ;;
  stop)
    target_arg="stop"
    ;;
  restart)
    target_arg="restart"
    ;;
  status)
    target_arg="status"
    ;;
  health)
    target_arg="health"
    ;;
  local-start)
    target_arg="start"
    ;;
  local-stop)
    target_arg="stop"
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
exec "${target}" "${target_arg}" "$@"
