#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$BACKEND_DIR/.venv311/bin/python}"
TEST_FILE="${TEST_FILE:-$BACKEND_DIR/tests/integration/test_frontend_ingest_flow_smoke_unittest.py}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[ERROR] Python executable not found: $PYTHON_BIN" >&2
  exit 2
fi

cd "$BACKEND_DIR"

"$PYTHON_BIN" -m pytest "$TEST_FILE" -q
