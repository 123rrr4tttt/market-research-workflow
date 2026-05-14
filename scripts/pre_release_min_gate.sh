#!/usr/bin/env bash
set -euo pipefail

# Minimal pre-release quality gate:
# 1) frontend lint/build when dependencies are available
# 2) critical backend tests via existing backend pre_release_gate.sh
# 3) rollback drill dry-run to ensure rollback path remains executable
# 4) metrics schema check
#
# Observability enhancement (non-invasive):
# - optional run report output via --report <path> or MIN_GATE_REPORT_PATH
# - per-phase status tracking (pass/skip/fail)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/main/frontend-modern"
BACKEND_GATE="${ROOT_DIR}/main/backend/scripts/pre_release_gate.sh"
METRICS_SCHEMA_CHECK="${ROOT_DIR}/main/backend/scripts/check_agent_symbolic_metrics_schema.py"
DEPLOY_SCRIPT="${ROOT_DIR}/scripts/docker-deploy.sh"

MODE_ARGS=()
REPORT_PATH="${MIN_GATE_REPORT_PATH:-}"

lint_status="skip"
frontend_build_status="skip"
backend_status="skip"
rollback_drill_status="skip"
metrics_schema_status="skip"

emit_report() {
  if [[ -z "${REPORT_PATH}" ]]; then
    return 0
  fi

  mkdir -p "$(dirname "${REPORT_PATH}")"
  cat >"${REPORT_PATH}" <<EOF
{
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "root": "${ROOT_DIR}",
  "lint": "${lint_status}",
  "frontend_build": "${frontend_build_status}",
  "backend": "${backend_status}",
  "rollback_drill": "${rollback_drill_status}",
  "metrics_schema": "${metrics_schema_status}",
  "result": "${1}"
}
EOF
  echo "[min-gate] report=${REPORT_PATH}"
}

usage() {
  echo "usage: $0 [--full] [--strict] [--report <path>]" >&2
}

on_error() {
  local line="$1"
  backend_status="${backend_status:-fail}"
  emit_report "fail"
  echo "[min-gate] FAIL (line=${line})" >&2
}

trap 'on_error $LINENO' ERR

while (($# > 0)); do
  case "$1" in
    --full|--strict)
      MODE_ARGS+=("$1")
      shift
      ;;
    --report)
      if (($# < 2)); then
        echo "[min-gate] missing value for --report" >&2
        usage
        exit 2
      fi
      REPORT_PATH="$2"
      shift 2
      ;;
    *)
      echo "[min-gate] unknown arg: $1" >&2
      usage
      exit 2
      ;;
  esac
done

echo "[min-gate] root=${ROOT_DIR}"
echo "[min-gate] phase 1/5: frontend lint/build"

if [[ -f "${FRONTEND_DIR}/package.json" ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    lint_status="skip"
    echo "[min-gate] SKIP lint: npm not found"
  elif [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
    lint_status="skip"
    echo "[min-gate] SKIP lint: node_modules missing (${FRONTEND_DIR}/node_modules)"
    echo "[min-gate] hint: cd ${FRONTEND_DIR} && npm ci"
  else
    (
      cd "${FRONTEND_DIR}"
      npm run lint
      npm run build
    )
    lint_status="pass"
    frontend_build_status="pass"
    echo "[min-gate] PASS frontend lint/build"
  fi
else
  lint_status="skip"
  frontend_build_status="skip"
  echo "[min-gate] SKIP frontend lint/build: frontend package.json not found"
fi

echo "[min-gate] phase 2/5: critical backend tests"
if [[ ! -x "${BACKEND_GATE}" ]]; then
  chmod +x "${BACKEND_GATE}"
fi
if ((${#MODE_ARGS[@]} > 0)); then
  "${BACKEND_GATE}" "${MODE_ARGS[@]}"
else
  "${BACKEND_GATE}"
fi
backend_status="pass"

echo "[min-gate] phase 3/5: rollback drill (dry-run)"
if [[ ! -f "${DEPLOY_SCRIPT}" ]]; then
  rollback_drill_status="fail"
  echo "[min-gate] ERROR: docker deploy script not found: ${DEPLOY_SCRIPT}" >&2
  exit 2
fi
bash "${DEPLOY_SCRIPT}" rollback-drill --dry-run --skip-preflight
rollback_drill_status="pass"

echo "[min-gate] phase 4/5: metrics schema"
if [[ ! -f "${METRICS_SCHEMA_CHECK}" ]]; then
  metrics_schema_status="fail"
  echo "[min-gate] ERROR: metrics schema check script not found: ${METRICS_SCHEMA_CHECK}" >&2
  exit 2
fi
if [[ -x "${ROOT_DIR}/main/backend/.venv311/bin/python" ]]; then
  "${ROOT_DIR}/main/backend/.venv311/bin/python" "${METRICS_SCHEMA_CHECK}"
else
  python3 "${METRICS_SCHEMA_CHECK}"
fi
metrics_schema_status="pass"

echo "[min-gate] phase 5/5: release package hygiene"
git -C "${ROOT_DIR}" status --short -- ':!main/backend/.venv311' >/dev/null

emit_report "pass"
echo "[min-gate] PASS"
