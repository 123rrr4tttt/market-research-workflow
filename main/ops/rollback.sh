#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_ROOT="${ROLLBACK_SNAPSHOT_DIR:-${SCRIPT_DIR}/.rollback_snapshots}"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"
ENV_FILE="${SCRIPT_DIR}/../backend/.env"

# --- Standard observability env + optional rollout hooks ---
pre_rollback() { :; }
post_rollback() { :; }

if [[ "${1:-}" != "dry-run" && -n "${OPS_HOOK_FILE:-}" && -f "${OPS_HOOK_FILE}" ]]; then
  # shellcheck disable=SC1090
  . "${OPS_HOOK_FILE}"
fi

setup_observability_env() {
  local repo_root
  repo_root="$(cd "${SCRIPT_DIR}/../.." 2>/dev/null && pwd)"
  : "${SERVICE_NAME:=$(basename "${repo_root}")}"
  if [[ -z "${APP_VERSION:-}" ]]; then
    if git -C "${repo_root}" rev-parse --git-dir >/dev/null 2>&1; then
      APP_VERSION="$(git -C "${repo_root}" describe --tags --always --dirty 2>/dev/null || git -C "${repo_root}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    else
      APP_VERSION="unknown"
    fi
  fi
  : "${DEPLOY_COLOR:=blue}"
  : "${ENV:=dev}"
  export SERVICE_NAME APP_VERSION DEPLOY_COLOR ENV
  echo "🔧 Observability env => SERVICE_NAME=${SERVICE_NAME} APP_VERSION=${APP_VERSION} DEPLOY_COLOR=${DEPLOY_COLOR} ENV=${ENV}"
}

usage() {
  cat <<USAGE
Usage: $(basename "$0") {snapshot|rollback|list} [snapshot_id] [--no-restart]
       $(basename "$0") dry-run --dry-run --fixture --fixture-root DIR --operation OP
       $(basename "$0") dry-run --dry-run --fixture --fixture-root DIR --plan-receipt FILE

Commands:
  snapshot                Save rollback checkpoint for compose/env and current git head
  list                    List available checkpoint IDs
  rollback [snapshot_id]  Restore checkpoint (default: latest) and restart stack
  dry-run                 Plan or validate a fixture-only rollback receipt

Options:
  --no-restart            Restore files but skip service restart
  --dry-run --fixture     Required by dry-run; no execution authority is available
  --fixture-root DIR      Fixture boundary for planning and receipt validation
  --operation OP          Fixture recovery operation accepted by fixture_recovery_tools
  --plan-receipt FILE     Receipt to validate; it must be inside --fixture-root
USAGE
}

reject_dry_run() {
  printf '%s\n' '{"schema_version":"ops.production_contract.recovery-receipt.v1","operation":"rollback_adapter","result":"rejected","authority":false,"executed":false,"failure_reason":"fixture-only dry-run contract violated"}'
  return 2
}

run_dry_run() {
  local fixture_root=""
  local operation=""
  local plan_receipt=""
  local artifact_id="default"
  local restore_artifact_id="restored"
  local recovery_artifact_id="recovered"
  local current_artifact_id="current"
  local previous_artifact_id="previous"
  local config_name="app"
  local failure_kind="constraint_violation"
  local saw_dry_run=false
  local saw_fixture=false
  local -a planning_args=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) saw_dry_run=true; shift ;;
      --fixture) saw_fixture=true; shift ;;
      --fixture-root)
        [[ $# -ge 2 && -n "$2" ]] || reject_dry_run
        fixture_root="$2"; shift 2 ;;
      --operation)
        [[ $# -ge 2 && -n "$2" ]] || reject_dry_run
        operation="$2"; shift 2 ;;
      --plan-receipt)
        [[ $# -ge 2 && -n "$2" ]] || reject_dry_run
        plan_receipt="$2"; shift 2 ;;
      --artifact-id)
        [[ $# -ge 2 && -n "$2" ]] || reject_dry_run
        artifact_id="$2"; shift 2 ;;
      --restore-artifact-id)
        [[ $# -ge 2 && -n "$2" ]] || reject_dry_run
        restore_artifact_id="$2"; shift 2 ;;
      --recovery-artifact-id)
        [[ $# -ge 2 && -n "$2" ]] || reject_dry_run
        recovery_artifact_id="$2"; shift 2 ;;
      --current-artifact-id)
        [[ $# -ge 2 && -n "$2" ]] || reject_dry_run
        current_artifact_id="$2"; shift 2 ;;
      --previous-artifact-id)
        [[ $# -ge 2 && -n "$2" ]] || reject_dry_run
        previous_artifact_id="$2"; shift 2 ;;
      --config-name)
        [[ $# -ge 2 && -n "$2" ]] || reject_dry_run
        config_name="$2"; shift 2 ;;
      --failure-kind)
        [[ $# -ge 2 && -n "$2" ]] || reject_dry_run
        failure_kind="$2"; shift 2 ;;
      *) reject_dry_run ;;
    esac
  done

  if [[ "${saw_dry_run}" != "true" || "${saw_fixture}" != "true" || -z "${fixture_root}" ]]; then
    reject_dry_run
  fi

  if [[ -n "${plan_receipt}" ]]; then
    [[ -z "${operation}" ]] || reject_dry_run
    python3 - "${SCRIPT_DIR}" "${fixture_root}" "${plan_receipt}" <<'PY'
import json
import sys
from pathlib import Path

repository_root = Path(sys.argv[1])
sys.path.insert(0, str(repository_root))

from main.ops.production_contract.fixture_recovery_tools import (  # noqa: E402
    DRY_RUN_RESULT,
    RECEIPT_SCHEMA_VERSION,
    TARGET_CLASS,
    _ENDPOINT_KEY_PATTERN,
    _SECRET_KEY_PATTERN,
    FixturePathResolver,
    PlannedCommand,
    RecoveryReceipt,
    RecoveryToolError,
    _OPERATIONS,
    _artifact_id,
    _reject_network_context,
    _sha256,
)


def rejected() -> None:
    print(json.dumps({
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "operation": "rollback_adapter",
        "result": "rejected",
        "authority": False,
        "executed": False,
        "failure_reason": "fixture-only dry-run contract violated",
    }, ensure_ascii=False, sort_keys=True))
    raise SystemExit(2)


try:
    for label, supplied_value in {
        "fixture_root": sys.argv[2],
        "plan_receipt": sys.argv[3],
    }.items():
        if _SECRET_KEY_PATTERN.search(label) or _SECRET_KEY_PATTERN.search(supplied_value):
            rejected()
        if _ENDPOINT_KEY_PATTERN.search(label):
            rejected()
        _reject_network_context({"supplied_value": [supplied_value]})
    resolver = FixturePathResolver(Path(sys.argv[2]).expanduser())
    receipt_path = Path(sys.argv[3]).expanduser()
    if not receipt_path.is_absolute():
        receipt_path = Path.cwd() / receipt_path
    receipt_file = resolver.resolve(receipt_path.relative_to(resolver.root))
    value = json.loads(receipt_file.read_text(encoding="utf-8"))
    required_fields = {
        "schema_version", "receipt_digest", "operation", "input_digest",
        "target_class", "planned_commands", "result", "authority", "executed",
    }
    if not isinstance(value, dict) or set(value) != required_fields:
        rejected()
    if value["schema_version"] != RECEIPT_SCHEMA_VERSION:
        rejected()
    if value["operation"] not in _OPERATIONS:
        rejected()
    if value["target_class"] != TARGET_CLASS or value["result"] != DRY_RUN_RESULT:
        rejected()
    if value["authority"] is not False or value["executed"] is not False:
        rejected()
    if not isinstance(value["input_digest"], str) or len(value["input_digest"]) != 64:
        rejected()
    raw_commands = value["planned_commands"]
    if not isinstance(raw_commands, list):
        rejected()
    commands = []
    for order, raw_command in enumerate(raw_commands, start=1):
        if not isinstance(raw_command, dict) or set(raw_command) != {"order", "intent", "command"}:
            rejected()
        if raw_command["order"] != order or not isinstance(raw_command["intent"], str):
            rejected()
        command = raw_command["command"]
        if not isinstance(command, list) or not command:
            rejected()
        if not all(isinstance(item, str) for item in command):
            rejected()
        if not command[0].startswith("fixture."):
            rejected()
        for argument in command[1:]:
            if "/" in argument or "\\" in argument:
                argument_path = Path(argument).expanduser()
                if not argument_path.is_absolute():
                    rejected()
                try:
                    argument_relative = argument_path.relative_to(resolver.root)
                except ValueError:
                    rejected()
                resolver.resolve(argument_relative, must_exist=False)
            else:
                _artifact_id(argument, "command_argument")
        commands.append(PlannedCommand(
            order=order, intent=raw_command["intent"], command=tuple(command),
        ))
    _reject_network_context({
        "receipt_commands": [list(item.command) for item in commands],
        "receipt_intents": [item.intent for item in commands],
    })
    receipt = RecoveryReceipt(
        schema_version=value["schema_version"],
        receipt_digest=value["receipt_digest"],
        operation=value["operation"],
        input_digest=value["input_digest"],
        target_class=value["target_class"],
        planned_commands=tuple(commands),
        result=value["result"],
        authority=value["authority"],
        executed=value["executed"],
    )
    observed = receipt.to_dict()
    digest_payload = {
        key: observed[key]
        for key in (
            "schema_version", "operation", "input_digest", "target_class",
            "planned_commands", "result", "authority", "executed",
        )
    }
    if receipt.receipt_digest != _sha256(digest_payload):
        rejected()
    print(json.dumps(observed, ensure_ascii=False, sort_keys=True))
except (OSError, ValueError, TypeError, KeyError, RecoveryToolError):
    rejected()
PY
    return
  fi

  [[ -n "${operation}" ]] || reject_dry_run
  planning_args=(--dry-run --fixture --fixture-root "${fixture_root}" --operation "${operation}")
  planning_args+=(--artifact-id "${artifact_id}" --restore-artifact-id "${restore_artifact_id}")
  planning_args+=(--recovery-artifact-id "${recovery_artifact_id}")
  planning_args+=(--current-artifact-id "${current_artifact_id}")
  planning_args+=(--previous-artifact-id "${previous_artifact_id}")
  planning_args+=(--config-name "${config_name}" --failure-kind "${failure_kind}")

  python3 - "${SCRIPT_DIR}" "${planning_args[@]}" <<'PY'
import json
import sys
from pathlib import Path

repository_root = Path(sys.argv[1])
sys.path.insert(0, str(repository_root))

from main.ops.production_contract.fixture_recovery_tools import (  # noqa: E402
    RECEIPT_SCHEMA_VERSION,
    _ENDPOINT_KEY_PATTERN,
    _SECRET_KEY_PATTERN,
    _reject_network_context,
    main,
)


def rejected() -> None:
    print(json.dumps({
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "operation": "rollback_adapter",
        "result": "rejected",
        "authority": False,
        "executed": False,
        "failure_reason": "fixture-only dry-run contract violated",
    }, ensure_ascii=False, sort_keys=True))
    raise SystemExit(2)


values = dict(zip(sys.argv[2::2], sys.argv[3::2]))
try:
    for label, value in values.items():
        if _SECRET_KEY_PATTERN.search(label) or _SECRET_KEY_PATTERN.search(value):
            rejected()
        if _ENDPOINT_KEY_PATTERN.search(label):
            rejected()
        _reject_network_context({"value": [value]})
except (TypeError, ValueError):
    rejected()

raise SystemExit(main(sys.argv[2:]))
PY
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

if [[ "${cmd}" != "dry-run" ]]; then
  # Export and log observability env for existing operational commands.
  setup_observability_env
fi

case "${cmd}" in
  dry-run)
    run_dry_run "$@"
    ;;
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
      pre_rollback
      rollback_snapshot "${snapshot_id}" "false"
      post_rollback
    else
      pre_rollback
      rollback_snapshot "${snapshot_id}" "true"
      post_rollback
    fi
    ;;
  *)
    usage
    exit 1
    ;;
esac
