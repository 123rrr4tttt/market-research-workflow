#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-$BACKEND_DIR/.venv311-fixed/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[E-LINE][ERROR] Python not found/executable: $PYTHON_BIN" >&2
  echo "[E-LINE][HINT] Set PYTHON_BIN or ensure .venv311-fixed is prepared." >&2
  exit 2
fi

cd "$BACKEND_DIR"

echo "[E-LINE] python: $($PYTHON_BIN --version 2>&1)"
echo "[E-LINE] running deep-health/db-reliability gate tests..."

"$PYTHON_BIN" -m pytest \
  tests/integration/test_deep_health_db_degraded_unittest.py \
  tests/unit/test_db_session_reliability_unittest.py \
  tests/e2e/test_deep_health_smoke_e2e.py \
  tests/core_business/test_health_and_context_core_e2e.py \
  -q
