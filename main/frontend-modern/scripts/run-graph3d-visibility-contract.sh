#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"
if command -v lsof >/dev/null 2>&1; then
  PIDS="$(lsof -ti tcp:4173 || true)"
  if [[ -n "${PIDS}" ]]; then
    kill ${PIDS} >/dev/null 2>&1 || true
  fi
fi
CI=1 npx playwright test tests/e2e/graph3d-visibility-contract.spec.ts --project=chromium "$@"
