#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

BACKEND_DIR="${ROOT_DIR}/main/backend"
LOCAL_DEPLOY_SCRIPT="${ROOT_DIR}/scripts/local-deploy.sh"
DOCKER_DEPLOY_SCRIPT="${ROOT_DIR}/scripts/docker-deploy.sh"
DOCKER_LAUNCHER_SCRIPT="${ROOT_DIR}/scripts/docker-launcher-ui.sh"
DOCKER_APP_CONTROL_SCRIPT="${ROOT_DIR}/scripts/docker-app-control.sh"
CONFIG_SCRIPT="${ROOT_DIR}/scripts/configure-external-services.py"

usage() {
  echo "Usage: $(basename "$0") {ui|start|stop|restart|status|health|local-start|local-stop|docker-start|docker-full-start|docker-stop|docker-restart|docker-status|configure|doctor|config-status} [extra args...]"
}

if [[ ! -d "${BACKEND_DIR}" ]]; then
  echo "Error: missing directory: ${BACKEND_DIR}" >&2
  exit 1
fi

if [[ ! -f "${LOCAL_DEPLOY_SCRIPT}" ]]; then
  echo "Error: script not found: ${LOCAL_DEPLOY_SCRIPT}" >&2
  exit 1
fi

if [[ ! -f "${DOCKER_DEPLOY_SCRIPT}" ]]; then
  echo "Error: script not found: ${DOCKER_DEPLOY_SCRIPT}" >&2
  exit 1
fi

if [[ ! -f "${DOCKER_LAUNCHER_SCRIPT}" ]]; then
  echo "Error: script not found: ${DOCKER_LAUNCHER_SCRIPT}" >&2
  exit 1
fi

if [[ ! -f "${DOCKER_APP_CONTROL_SCRIPT}" ]]; then
  echo "Error: script not found: ${DOCKER_APP_CONTROL_SCRIPT}" >&2
  exit 1
fi

if [[ ! -f "${CONFIG_SCRIPT}" ]]; then
  echo "Error: script not found: ${CONFIG_SCRIPT}" >&2
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
  ui)
    echo "Running: ${cmd}"
    exec python3 "${ROOT_DIR}/scripts/launch.py" "$@"
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
  docker-start)
    echo "Running: ${cmd}"
    exec "${DOCKER_LAUNCHER_SCRIPT}" "$@"
    ;;
  docker-full-start)
    echo "Running: ${cmd}"
    exec "${DOCKER_DEPLOY_SCRIPT}" start --profile modern-ui "$@"
    ;;
  docker-stop)
    echo "Running: ${cmd}"
    exec "${DOCKER_APP_CONTROL_SCRIPT}" stop "$@"
    ;;
  docker-restart)
    echo "Running: ${cmd}"
    exec "${DOCKER_APP_CONTROL_SCRIPT}" restart "$@"
    ;;
  docker-status)
    echo "Running: ${cmd}"
    exec "${DOCKER_APP_CONTROL_SCRIPT}" status "$@"
    ;;
  configure)
    echo "Running: ${cmd}"
    exec python3 "${ROOT_DIR}/scripts/launch.py" "$@"
    ;;
  doctor)
    echo "Running: ${cmd}"
    exec python3 "${CONFIG_SCRIPT}" doctor "$@"
    ;;
  config-status)
    echo "Running: ${cmd}"
    exec python3 "${CONFIG_SCRIPT}" status "$@"
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
