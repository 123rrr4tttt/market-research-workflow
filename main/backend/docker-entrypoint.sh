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
elif part == "password":
    print(parsed.password or default)
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
ES_USER="$(parse_url_part "${ES_URL}" user '')"
ES_PASSWORD="$(parse_url_part "${ES_URL}" password '')"

ES_CURL_AUTH=()
if [ -n "${ES_USER}" ] && [ -n "${ES_PASSWORD}" ]; then
    ES_CURL_AUTH=(--user "${ES_USER}:${ES_PASSWORD}")
fi

wait_for_service() {
    local name="$1" attempt=1
    shift
    echo "⏳ 等待${name}服务就绪..."
    until "$@" >/dev/null 2>&1; do
        if (( attempt >= MAX_RETRIES )); then
            echo "❌ ${name}服务未能在${MAX_RETRIES}次尝试后就绪" >&2
            return 1
        fi
        echo "   等待${name}... ($attempt/$MAX_RETRIES)"
        sleep "${RETRY_DELAY}"
        attempt=$((attempt + 1))
    done
    echo "✅ ${name}已就绪"
}

check_redis() {
    REDIS_URL="${REDIS_URL}" python - <<'PYTHON'
import os

from redis import Redis

with Redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=5, socket_timeout=5) as client:
    raise SystemExit(0 if client.ping() else 1)
PYTHON
}

wait_for_service PostgreSQL pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}"
wait_for_service Elasticsearch curl -fsS "${ES_CURL_AUTH[@]}" "${ES_SCHEME}://${ES_HOST}:${ES_PORT}/_cluster/health"
wait_for_service Redis check_redis

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
