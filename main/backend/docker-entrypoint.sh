#!/bin/bash
# Docker容器启动脚本
# 处理数据库迁移、服务就绪检查等初始化任务

set -e

echo "🚀 启动后端服务容器..."

parse_url_part() {
    # 用 Python 解析 URL，避免 bash 正则对 SQLAlchemy DSN 兼容性差。
    python - "$1" "$2" "$3" <<'PY'
import sys
from urllib.parse import urlparse

url, part, default = sys.argv[1], sys.argv[2], sys.argv[3]
parsed = urlparse(url)

if part == "host":
    print(parsed.hostname or default)
elif part == "port":
    print(parsed.port or default)
elif part == "user":
    print(parsed.username or default)
elif part == "path":
    value = (parsed.path or "").lstrip("/")
    print(value or default)
elif part == "scheme":
    # postgresql+psycopg2 -> postgresql
    print((parsed.scheme or default).split("+")[0])
else:
    print(default)
PY
}

MAX_RETRIES="${STARTUP_MAX_RETRIES:-30}"
RETRY_DELAY="${STARTUP_RETRY_DELAY:-2}"
DB_URL="${DATABASE_URL:-postgresql+psycopg2://postgres:postgres@db:5432/postgres}"
ES_URL="${ES_URL:-http://es:9200}"
REDIS_URL="${REDIS_URL:-redis://redis:6379/0}"

DB_HOST="$(parse_url_part "${DB_URL}" host db)"
DB_PORT="$(parse_url_part "${DB_URL}" port 5432)"
DB_USER="$(parse_url_part "${DB_URL}" user postgres)"
DB_NAME="$(parse_url_part "${DB_URL}" path postgres)"
ES_HOST="$(parse_url_part "${ES_URL}" host es)"
ES_PORT="$(parse_url_part "${ES_URL}" port 9200)"
ES_SCHEME="$(parse_url_part "${ES_URL}" scheme http)"
REDIS_HOST="$(parse_url_part "${REDIS_URL}" host redis)"
REDIS_PORT="$(parse_url_part "${REDIS_URL}" port 6379)"

# 等待PostgreSQL就绪
echo "⏳ 等待PostgreSQL服务就绪..."
RETRY=0
until pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" >/dev/null 2>&1; do
    RETRY=$((RETRY + 1))
    if [ $RETRY -ge $MAX_RETRIES ]; then
        echo "❌ PostgreSQL服务未能在${MAX_RETRIES}次重试后就绪"
        exit 1
    fi
    echo "   等待PostgreSQL... ($RETRY/$MAX_RETRIES)"
    sleep "${RETRY_DELAY}"
done
echo "✅ PostgreSQL已就绪"

# 等待Elasticsearch就绪
echo "⏳ 等待Elasticsearch服务就绪..."
RETRY=0
until curl -fsS "${ES_SCHEME}://${ES_HOST}:${ES_PORT}/_cluster/health" >/dev/null 2>&1; do
    RETRY=$((RETRY + 1))
    if [ $RETRY -ge $MAX_RETRIES ]; then
        echo "❌ Elasticsearch服务未能在${MAX_RETRIES}次重试后就绪"
        exit 1
    fi
    echo "   等待Elasticsearch... ($RETRY/$MAX_RETRIES)"
    sleep "${RETRY_DELAY}"
done
echo "✅ Elasticsearch已就绪"

# 等待Redis就绪（使用Python检查，因为redis-cli可能不可用）
echo "⏳ 等待Redis服务就绪..."
RETRY=0
until python -c "import redis; r=redis.Redis(host='${REDIS_HOST}', port=int('${REDIS_PORT}'), db=0); r.ping()" >/dev/null 2>&1; do
    RETRY=$((RETRY + 1))
    if [ $RETRY -ge $MAX_RETRIES ]; then
        echo "❌ Redis服务未能在${MAX_RETRIES}次重试后就绪"
        exit 1
    fi
    echo "   等待Redis... ($RETRY/$MAX_RETRIES)"
    sleep "${RETRY_DELAY}"
done
echo "✅ Redis已就绪"

# 运行数据库迁移
cd /app
if [[ "${RUN_MIGRATIONS:-true}" == "true" ]]; then
    echo "📦 运行数据库迁移..."
    alembic upgrade head
else
    echo "⏭️  已跳过数据库迁移 (RUN_MIGRATIONS=${RUN_MIGRATIONS})"
fi

echo "✅ 初始化完成，启动应用服务..."

# 执行传入的命令（通常是uvicorn）
exec "$@"
