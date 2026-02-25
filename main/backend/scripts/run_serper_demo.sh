#!/bin/bash
# Run Serper web search test in demo subproject context.
# Usage: ./scripts/run_serper_demo.sh [from backend dir]
# Or: cd main/backend && ./scripts/run_serper_demo.sh

cd "$(dirname "$0")/.."
set -a
[ -f .env ] && source .env
set +a
export SERPER_API_KEY="${SERPER_API_KEY:-}"
python3 scripts/test_serper_demo.py
