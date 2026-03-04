#!/usr/bin/env bash
set -euo pipefail

# Minimal pre-release quality gate:
# 1) lint (frontend eslint when dependencies are available)
# 2) critical backend tests via existing backend pre_release_gate.sh
#
# Observability enhancement (non-invasive):
# - optional run report output via --report <path> or MIN_GATE_REPORT_PATH
# - per-phase status tracking (pass/skip/fail)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/main/frontend-modern"
BACKEND_GATE="${ROOT_DIR}/main/backend/scripts/pre_release_gate.sh"

MODE_ARGS=()
REPORT_PATH="${MIN_GATE_REPORT_PATH:-}"

lint_status="skip"
backend_status="skip"

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
  "backend": "${backend_status}",
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
echo "[min-gate] phase 1/2: lint"

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
    )
    lint_status="pass"
    echo "[min-gate] PASS lint"
  fi
else
  lint_status="skip"
  echo "[min-gate] SKIP lint: frontend package.json not found"
fi

echo "[min-gate] phase 2/2: critical backend tests"
if [[ ! -x "${BACKEND_GATE}" ]]; then
  chmod +x "${BACKEND_GATE}"
fi
if ((${#MODE_ARGS[@]} > 0)); then
  "${BACKEND_GATE}" "${MODE_ARGS[@]}"
else
  "${BACKEND_GATE}"
fi
backend_status="pass"

emit_report "pass"
echo "[min-gate] PASS"
