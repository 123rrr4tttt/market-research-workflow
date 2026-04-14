#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PACK_DIR="$ROOT/codex_settings/frozen_v1"

echo "== latest artifacts =="
ls -1t "$PACK_DIR/artifacts"/*.last.txt 2>/dev/null | head -n 20 || true

echo
echo "== latest stdout logs =="
ls -1t "$PACK_DIR/logs"/*.stdout.log 2>/dev/null | head -n 20 || true

echo
echo "== git status (short) =="
cd "$ROOT"
git status --short
