#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_ROOT="${ROLLBACK_SNAPSHOT_DIR:-${SCRIPT_DIR}/.rollback_snapshots}"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"
ENV_FILE="${SCRIPT_DIR}/../backend/.env"

usage() {
  cat <<USAGE
Usage: $(basename "$0") {snapshot|rollback|list} [snapshot_id] [--no-restart]

Commands:
  snapshot                Save rollback checkpoint for compose/env and current git head
  list                    List available checkpoint IDs
  rollback [snapshot_id]  Restore checkpoint (default: latest) and restart stack

Options:
  --no-restart            Restore files but skip service restart
USAGE
}

latest_snapshot_id() {
  if [[ ! -d "${BACKUP_ROOT}" ]]; then
    return 1
  fi
  ls -1 "${BACKUP_ROOT}" 2>/dev/null | sort | tail -n1
}

create_snapshot() {
  mkdir -p "${BACKUP_ROOT}"
  local snapshot_id
  snapshot_id="$(date +%Y%m%d-%H%M%S)"
  local snapshot_dir="${BACKUP_ROOT}/${snapshot_id}"
  mkdir -p "${snapshot_dir}"

  cp "${COMPOSE_FILE}" "${snapshot_dir}/docker-compose.yml"
  if [[ -f "${ENV_FILE}" ]]; then
    cp "${ENV_FILE}" "${snapshot_dir}/backend.env"
  fi

  if git -C "${SCRIPT_DIR}/../.." rev-parse --verify HEAD >/dev/null 2>&1; then
    git -C "${SCRIPT_DIR}/../.." rev-parse HEAD > "${snapshot_dir}/git_head.txt"
  fi

  printf '%s\n' "${snapshot_id}"
}

list_snapshots() {
  if [[ ! -d "${BACKUP_ROOT}" ]]; then
    echo "No checkpoints found."
    return 0
  fi
  ls -1 "${BACKUP_ROOT}" | sort
}

rollback_snapshot() {
  local snapshot_id="${1:-}"
  local do_restart="${2:-true}"

  if [[ -z "${snapshot_id}" ]]; then
    snapshot_id="$(latest_snapshot_id || true)"
  fi

  if [[ -z "${snapshot_id}" ]]; then
    echo "No checkpoint found. Create one via: ./scripts/docker-deploy.sh checkpoint" >&2
    return 1
  fi

  local snapshot_dir="${BACKUP_ROOT}/${snapshot_id}"
  if [[ ! -d "${snapshot_dir}" ]]; then
    echo "Checkpoint not found: ${snapshot_id}" >&2
    return 1
  fi

  cp "${snapshot_dir}/docker-compose.yml" "${COMPOSE_FILE}"
  if [[ -f "${snapshot_dir}/backend.env" ]]; then
    cp "${snapshot_dir}/backend.env" "${ENV_FILE}"
  fi

  echo "Restored checkpoint: ${snapshot_id}"
  if [[ -f "${snapshot_dir}/git_head.txt" ]]; then
    echo "Saved git head: $(cat "${snapshot_dir}/git_head.txt")"
  fi

  if [[ "${do_restart}" == "true" ]]; then
    "${SCRIPT_DIR}/restart.sh"
  fi
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

cmd="$1"
shift

case "${cmd}" in
  snapshot)
    create_snapshot
    ;;
  list)
    list_snapshots
    ;;
  rollback)
    no_restart=false
    snapshot_id=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --no-restart)
          no_restart=true
          shift
          ;;
        *)
          snapshot_id="$1"
          shift
          ;;
      esac
    done
    if [[ "${no_restart}" == "true" ]]; then
      rollback_snapshot "${snapshot_id}" "false"
    else
      rollback_snapshot "${snapshot_id}" "true"
    fi
    ;;
  *)
    usage
    exit 1
    ;;
esac
