#!/bin/bash
# Docker容器启动脚本
# 处理数据库迁移、服务就绪检查等初始化任务

set -e

echo "🚀 启动后端服务容器..."

# 等待PostgreSQL就绪
echo "⏳ 等待PostgreSQL服务就绪..."
MAX_RETRIES=30
RETRY=0
until pg_isready -h db -U postgres -d postgres >/dev/null 2>&1; do
    RETRY=$((RETRY + 1))
    if [ $RETRY -ge $MAX_RETRIES ]; then
        echo "❌ PostgreSQL服务未能在${MAX_RETRIES}次重试后就绪"
        exit 1
    fi
    echo "   等待PostgreSQL... ($RETRY/$MAX_RETRIES)"
    sleep 2
done
echo "✅ PostgreSQL已就绪"

# 等待Elasticsearch就绪
echo "⏳ 等待Elasticsearch服务就绪..."
RETRY=0
until curl -s http://es:9200 >/dev/null 2>&1; do
    RETRY=$((RETRY + 1))
    if [ $RETRY -ge $MAX_RETRIES ]; then
        echo "❌ Elasticsearch服务未能在${MAX_RETRIES}次重试后就绪"
        exit 1
    fi
    echo "   等待Elasticsearch... ($RETRY/$MAX_RETRIES)"
    sleep 2
done
echo "✅ Elasticsearch已就绪"

# 等待Redis就绪（使用Python检查，因为redis-cli可能不可用）
echo "⏳ 等待Redis服务就绪..."
RETRY=0
until python -c "import redis; r=redis.Redis(host='redis', port=6379, db=0); r.ping()" >/dev/null 2>&1; do
    RETRY=$((RETRY + 1))
    if [ $RETRY -ge $MAX_RETRIES ]; then
        echo "❌ Redis服务未能在${MAX_RETRIES}次重试后就绪"
        exit 1
    fi
    echo "   等待Redis... ($RETRY/$MAX_RETRIES)"
    sleep 2
done
echo "✅ Redis已就绪"

# 运行数据库迁移
echo "📦 运行数据库迁移..."
cd /app
alembic upgrade head || {
    echo "⚠️  数据库迁移失败，但继续启动（可能是数据库未初始化）"
}

echo "✅ 初始化完成，启动应用服务..."

# 执行传入的命令（通常是uvicorn）
exec "$@"

