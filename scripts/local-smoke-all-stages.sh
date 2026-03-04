#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/main/backend"
PORT="${SMOKE_PORT:-18000}"
HOST="127.0.0.1"
BASE_URL="http://${HOST}:${PORT}"
LOG_FILE="${SMOKE_LOG:-/tmp/backend_local_smoke_all_stages_$(date +%s).log}"

cd "$BACKEND_DIR"

# Lightweight gate before API smoke.
python3 -m py_compile \
  app/api/config.py \
  app/api/search.py \
  app/main.py \
  app/services/collect_runtime/runtime.py \
  app/services/llm/provider.py \
  app/services/settings_manager.py \
  app/services/source_library/runner.py \
  app/services/job_logger.py \
  app/settings/config.py

./.venv311/bin/python -m uvicorn app.main:app --host "$HOST" --port "$PORT" >"$LOG_FILE" 2>&1 &
PID=$!

cleanup() {
  kill "$PID" >/dev/null 2>&1 || true
  wait "$PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

sleep 8

python3 - <<'PY'
import json
import urllib.request
import urllib.error

base_url = 'http://127.0.0.1:18000'
checks = [
    ('GET', '/api/v1/health', None),
    ('GET', '/api/v1/health/deep', None),
    ('GET', '/api/v1/config', None),
    ('GET', '/api/v1/config/env', None),
    ('GET', '/api/v1/projects', None),
    ('GET', '/api/v1/process/stats', None),
    ('GET', '/api/v1/ingest/history?limit=5', None),
    ('GET', '/api/v1/ingest/news-resources', None),
    ('GET', '/api/v1/llm-config', None),
    ('GET', '/api/v1/project-customization/workflows', None),
    ('POST', '/api/v1/ingest/market', {
        'query_terms': ['market research'],
        'max_items': 1,
        'enable_extraction': False,
        'async_mode': True,
    }),
    ('POST', '/api/v1/ingest/source-library/sync', {}),
]

failed = []
for method, path, payload in checks:
    req = urllib.request.Request(base_url + path, method=method)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, data=data, timeout=60) as resp:
            code = resp.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:  # noqa: BLE001
        code = f'ERR:{e.__class__.__name__}'
    print(f'{method} {path} -> {code}')
    if code != 200:
        failed.append((method, path, code))

if failed:
    print('SMOKE_FAIL', failed)
    raise SystemExit(1)

print('SMOKE_PASS')
PY

echo "SMOKE_LOG=$LOG_FILE"
