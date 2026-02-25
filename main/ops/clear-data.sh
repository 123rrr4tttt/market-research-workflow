#!/bin/bash
# Clear all persisted data: PostgreSQL, Elasticsearch volumes + local LLM cache.
# Run from repo root or from ops/.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DATA="$PROJECT_ROOT/backend/data"

echo "🗑️  清除项目数据存储"
echo "===================="

# 1. Stop containers and remove Docker volumes (db_data, es_data)
echo ""
echo "📦 停止容器并删除数据卷 (PostgreSQL, Elasticsearch)..."
cd "$SCRIPT_DIR"
if [ -f "docker-compose.yml" ]; then
    docker-compose down -v 2>/dev/null || true
    echo "✅ 容器已停止，命名卷已删除"
else
    echo "⚠️  docker-compose.yml 不存在，跳过"
fi

# 2. Remove local LLM cache (SQLite)
echo ""
echo "📁 删除本地缓存 (backend/data)..."
if [ -d "$BACKEND_DATA" ]; then
    rm -rf "$BACKEND_DATA"
    echo "✅ 已删除 $BACKEND_DATA"
else
    echo "   (目录不存在，跳过)"
fi

echo ""
echo "✅ 数据存储已清除。"
echo "   - PostgreSQL 数据卷 db_data 已删除"
echo "   - Elasticsearch 数据卷 es_data 已删除"
echo "   - Redis 无持久化卷，重启后即为空"
echo "   - backend/data (LangChain 缓存) 已删除"
echo ""
echo "💡 重新启动服务后数据库为空，需重新执行迁移: cd ops && docker-compose up -d && docker-compose exec backend alembic upgrade head"
