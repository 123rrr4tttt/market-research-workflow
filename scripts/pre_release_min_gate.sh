#!/usr/bin/env bash
set -euo pipefail

# Minimal pre-release quality gate:
# 1) lint (frontend eslint when dependencies are available)
# 2) critical backend tests via existing backend pre_release_gate.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/main/frontend-modern"
BACKEND_GATE="${ROOT_DIR}/main/backend/scripts/pre_release_gate.sh"

MODE_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --full|--strict)
      MODE_ARGS+=("$arg")
      ;;
    *)
      echo "[min-gate] unknown arg: $arg" >&2
      echo "usage: $0 [--full] [--strict]" >&2
      exit 2
      ;;
  esac
done

echo "[min-gate] root=${ROOT_DIR}"
echo "[min-gate] phase 1/2: lint"

if [[ -f "${FRONTEND_DIR}/package.json" ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "[min-gate] SKIP lint: npm not found"
  elif [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
    echo "[min-gate] SKIP lint: node_modules missing (${FRONTEND_DIR}/node_modules)"
    echo "[min-gate] hint: cd ${FRONTEND_DIR} && npm ci"
  else
    (
      cd "${FRONTEND_DIR}"
      npm run lint
    )
    echo "[min-gate] PASS lint"
  fi
else
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

echo "[min-gate] PASS"
