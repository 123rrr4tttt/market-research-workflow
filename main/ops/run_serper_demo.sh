#!/bin/bash
# Run Serper web search test in Docker (demo subproject).
# Requires: docker-compose services running
# SERPER_API_KEY: from backend/.env, or pass: SERPER_API_KEY=xxx ./run_serper_demo.sh
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load SERPER_API_KEY from backend/.env if not already set
if [ -z "$SERPER_API_KEY" ] && [ -f "../backend/.env" ]; then
  export SERPER_API_KEY=$(grep -E '^SERPER_API_KEY=' ../backend/.env 2>/dev/null | cut -d= -f2- | tr -d "'\"" | head -1)
fi

if [ -z "$SERPER_API_KEY" ]; then
  echo "⚠️  SERPER_API_KEY 未配置"
  echo "   请在 main/backend/.env 中设置 SERPER_API_KEY='your_key'"
  echo "   或运行: SERPER_API_KEY=your_key ./run_serper_demo.sh"
  exit 1
fi

echo "🔍 Docker 中运行 Serper 网页搜索测试 (demo: embodied ai)..."
docker-compose exec -e SERPER_API_KEY backend python scripts/test_serper_demo.py
