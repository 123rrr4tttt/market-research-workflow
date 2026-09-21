#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/main/backend"
FRONTEND_DIR="$ROOT_DIR/main/frontend-modern"
PYTHON_BIN="${PYTHON_BIN:-$BACKEND_DIR/.venv311/bin/python}"
BACKEND_BASE_URL="${BACKEND_BASE_URL:-http://127.0.0.1:8000}"
REQUIRE_BACKEND_PORT="${REQUIRE_BACKEND_PORT:-18001}"
REQUIRE_BACKEND_BASE_URL="${REQUIRE_BACKEND_BASE_URL:-http://127.0.0.1:${REQUIRE_BACKEND_PORT}}"
REQUIRE_BACKEND_LOG="${REQUIRE_BACKEND_LOG:-/tmp/repo_runtime_smoke_require_backend.log}"
PROJECT_KEY="${PROJECT_KEY:-demo_proj}"
SOURCE_ITEM_KEY="${SOURCE_ITEM_KEY:-}"

resolve_matrix_python() {
  if [[ -n "${MATRIX_PYTHON_BIN:-}" && -x "$MATRIX_PYTHON_BIN" ]]; then
    printf '%s\n' "$MATRIX_PYTHON_BIN"
  elif [[ -x "$PYTHON_BIN" ]]; then
    printf '%s\n' "$PYTHON_BIN"
  elif [[ -x "/Users/wangyiliang/.local/bin/python3.11" ]]; then
    printf '%s\n' "/Users/wangyiliang/.local/bin/python3.11"
  elif command -v python3.11 >/dev/null 2>&1; then
    command -v python3.11
  else
    command -v python3
  fi
}

if [[ "${1:-}" == "matrix" || "${1:-}" == "--matrix" ]]; then
  shift
  MATRIX_PYTHON="$(resolve_matrix_python)"
  exec "$MATRIX_PYTHON" "$ROOT_DIR/scripts/runtime_health_matrix.py" "$@"
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[ERROR] Python executable not found: $PYTHON_BIN" >&2
  exit 2
fi

cleanup() {
  if [[ -n "${REQUIRE_BACKEND_PID:-}" ]]; then
    kill "$REQUIRE_BACKEND_PID" >/dev/null 2>&1 || true
    wait "$REQUIRE_BACKEND_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "[runtime] starting temporary require-mode backend on ${REQUIRE_BACKEND_BASE_URL}"
(
  cd "$BACKEND_DIR"
  ENV=prod \
  PROJECT_KEY_ENFORCEMENT_MODE=warn \
  PROJECT_KEY_REQUIRE_IN_NON_DEV=true \
  "$PYTHON_BIN" -m uvicorn app.main:app --host 127.0.0.1 --port "$REQUIRE_BACKEND_PORT" >"$REQUIRE_BACKEND_LOG" 2>&1
) &
REQUIRE_BACKEND_PID=$!

"$PYTHON_BIN" - <<'PY' "$REQUIRE_BACKEND_BASE_URL"
import sys
import time
import urllib.error
import urllib.request

base_url = sys.argv[1].rstrip("/")
deadline = time.time() + 30
while time.time() < deadline:
    try:
        with urllib.request.urlopen(f"{base_url}/api/v1/health", timeout=2) as resp:
            if resp.status == 200:
                raise SystemExit(0)
    except Exception:
        time.sleep(0.5)
raise SystemExit(1)
PY

echo "[runtime] backend api smoke"
backend_args=(
  --base-url "$BACKEND_BASE_URL"
  --require-base-url "$REQUIRE_BACKEND_BASE_URL"
  --project-key "$PROJECT_KEY"
)
if [[ -n "$SOURCE_ITEM_KEY" ]]; then
  backend_args+=(--source-item-key "$SOURCE_ITEM_KEY")
fi
"$PYTHON_BIN" "$BACKEND_DIR/scripts/repo_runtime_smoke.py" "${backend_args[@]}"

echo "[runtime] frontend browser smoke"
cd "$FRONTEND_DIR"
VITE_API_PROXY_TARGET="$BACKEND_BASE_URL" npm run test:e2e:runtime
