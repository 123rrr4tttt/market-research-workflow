#!/usr/bin/env bash
set -euo pipefail

# Bootstrap context for "swarm[file]" workflow.
# This script is intentionally deterministic so Codex can consume stable output.

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <file-path>"
  exit 2
fi

TARGET="$1"
ROOT="$(pwd)"

if [[ ! -f "$TARGET" ]]; then
  echo "[ERROR] file_not_found: $TARGET"
  echo "[HINT] candidates:"
  rg --files | rg "$(basename "$TARGET")" | head -n 5 || true
  exit 1
fi

EXT="${TARGET##*.}"
BASE="$(basename "$TARGET")"

echo "=== SWARM FILE BOOTSTRAP ==="
echo "root: $ROOT"
echo "target: $TARGET"
echo "ext: $EXT"
echo

echo "--- git_status_short ---"
git status --short "$TARGET" || true
echo

echo "--- symbols_rough ---"
case "$EXT" in
  py)
    rg -n "^(def |class )" "$TARGET" || true
    ;;
  ts|tsx|js|jsx)
    rg -n "^(export |function |class |const .*=>|async function )" "$TARGET" || true
    ;;
  go)
    rg -n "^(func |type )" "$TARGET" || true
    ;;
  *)
    rg -n "^(#|def |class |function |export |func )" "$TARGET" || true
    ;;
esac
echo

echo "--- inbound_references_top20 ---"
rg -n --glob '!**/.git/**' --glob '!**/node_modules/**' --glob '!**/.venv/**' "$BASE" . | head -n 20 || true
echo

echo "--- same_stem_files_top20 ---"
STEM="${BASE%.*}"
rg --files | rg "/${STEM}(\\.|$)" | head -n 20 || true
echo

echo "--- done ---"
