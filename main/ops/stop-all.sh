#!/bin/bash
# 统一容器停止脚本 - 停止当前独立项目服务

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🛑 统一容器停止脚本"
echo "===================="
echo ""
echo "这将停止项目主服务："
echo "  ✅ PostgreSQL, Elasticsearch, Redis, Backend API, Celery Worker"
echo ""

# 检查 Docker 是否运行
if ! docker info >/dev/null 2>&1; then
    echo "⚠️  Docker 未运行，无需停止服务"
    exit 0
fi

# 停止主服务
echo "📦 停止主服务..."
cd "$SCRIPT_DIR"
if [ -f "docker-compose.yml" ]; then
    docker-compose down
    echo "✅ 主服务已停止"
else
    echo "⚠️  主服务 docker-compose.yml 不存在，跳过"
fi
echo ""

echo "✅ 所有服务已停止！"
echo ""
echo "💡 提示:"
echo "   如需删除数据卷，请手动运行: cd ops && docker-compose down -v"
echo "   (⚠️  这会删除所有数据库数据)"
echo ""

