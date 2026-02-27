#!/bin/bash
# 统一容器停止脚本 - 停止当前独立项目服务

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

compose() {
    if command -v docker-compose >/dev/null 2>&1; then
        docker-compose "$@"
    elif docker compose version >/dev/null 2>&1; then
        docker compose "$@"
    else
        echo "❌ 未找到 docker-compose 或 docker compose"
        return 127
    fi
}

echo "🛑 统一容器停止脚本"
echo "===================="
echo ""
echo "这将停止项目主服务："
echo "  ✅ PostgreSQL, Elasticsearch, Redis, Backend API, Celery Worker"
echo ""

if ! docker info >/dev/null 2>&1; then
    echo "⚠️  Docker 未运行，无需停止服务"
    exit 0
fi

echo "📦 停止主服务..."
if [ -f "docker-compose.yml" ]; then
    compose down
    echo "✅ 主服务已停止"
else
    echo "⚠️  主服务 docker-compose.yml 不存在，跳过"
fi

echo ""
echo "✅ 所有服务已停止！"
echo ""
echo "💡 提示:"
echo "   如需删除数据卷，请手动运行: cd ops && docker compose down -v"
echo "   (⚠️  这会删除所有数据库数据)"
echo ""
