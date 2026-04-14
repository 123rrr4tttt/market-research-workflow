#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PACK_DIR="$ROOT/codex_settings/frozen_v1"
PROMPT_DIR="$PACK_DIR/prompts/clusters"
LOG_DIR="$PACK_DIR/logs"
ART_DIR="$PACK_DIR/artifacts"

CLUSTER="${1:-}"
if [[ -z "$CLUSTER" ]]; then
  echo "usage: $0 <cluster-id>"
  echo "example: $0 C3"
  exit 2
fi

PROMPT_FILE="$PROMPT_DIR/${CLUSTER}.md"
if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "[ERROR] prompt not found: $PROMPT_FILE"
  exit 2
fi

if ! command -v codex >/dev/null 2>&1; then
  echo "[ERROR] codex CLI not found in PATH"
  exit 2
fi

mkdir -p "$LOG_DIR" "$ART_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
JSONL="$LOG_DIR/${CLUSTER}-${TS}.jsonl"
LAST_MSG="$ART_DIR/${CLUSTER}-${TS}.last.txt"
STDOUT_LOG="$LOG_DIR/${CLUSTER}-${TS}.stdout.log"

MODEL="${MODEL:-gpt-5}"

{
  echo "== run cluster =="
  echo "cluster=$CLUSTER"
  echo "model=$MODEL"
  echo "prompt=$PROMPT_FILE"
  echo "jsonl=$JSONL"
  echo "last=$LAST_MSG"
  echo
} | tee "$STDOUT_LOG"

cat "$PACK_DIR/prompts/COMMON_RULES.md" "$PROMPT_FILE" | \
  codex exec \
    -C "$ROOT" \
    -c 'approval_policy="never"' \
    -c 'mcp_servers.figma.enabled=false' \
    --sandbox danger-full-access \
    -m "$MODEL" \
    --json \
    -o "$LAST_MSG" \
    - >> "$JSONL" 2>> "$STDOUT_LOG"

{
  echo
  echo "== done =="
  echo "cluster=$CLUSTER"
  echo "jsonl=$JSONL"
  echo "last=$LAST_MSG"
} | tee -a "$STDOUT_LOG"
