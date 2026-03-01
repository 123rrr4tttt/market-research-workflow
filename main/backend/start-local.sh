#!/bin/bash
# 本地开发环境启动脚本

set -e

# Ensure Homebrew tools (node, psql, etc.) are in PATH when available
if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null)" || true
elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv 2>/dev/null)" || true
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend-modern"
OPS_DIR="$(cd "$SCRIPT_DIR/../ops" && pwd)"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_LOG_FILE="/tmp/frontend-modern-dev.log"
FRONTEND_PID_FILE="/tmp/frontend-modern-dev.pid"
WORKER_LOG_FILE="/tmp/celery-local-worker.log"
WORKER_PID_FILE="/tmp/celery-local-worker.pid"
CELERY_LOG_LEVEL="${CELERY_LOG_LEVEL:-info}"
CELERY_CONCURRENCY="${CELERY_CONCURRENCY:-3}"
CELERY_PREFETCH_MULTIPLIER="${CELERY_PREFETCH_MULTIPLIER:-2}"
CELERY_MAX_TASKS_PER_CHILD="${CELERY_MAX_TASKS_PER_CHILD:-100}"
CELERY_MAX_MEMORY_PER_CHILD="${CELERY_MAX_MEMORY_PER_CHILD:-500000}"
CELERY_QUEUES="${CELERY_QUEUES:-celery}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
VENV_DIR=".venv311"
REQ_FILE="requirements.txt"
REQ_HASH_FILE="${VENV_DIR}/.requirements.sha256"

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

DEV_RELOAD="${DEV_RELOAD:-1}"
USE_DOCKER_DEPS=0
NON_INTERACTIVE=0
FORCE=0
WITH_LOCAL_WORKER=1
AUTO_INSTALL_DEPS=1

usage() {
    cat <<'EOF'
Usage: ./start-local.sh [options]

Options:
  --low-memory          关闭自动重载，降低内存占用
  --with-docker-deps    自动启动 Docker 依赖（db/es/redis）
  --non-interactive     非交互模式，端口冲突时直接失败退出
  --force               强制模式，端口冲突时自动处理并继续
  --with-local-worker   同时启动本机 Celery worker（默认已开启）
  --no-local-worker     不启动本机 Celery worker
  --no-auto-install     不自动安装缺失依赖（Homebrew/Node/PostgreSQL/Redis/pgvector）
  -h, --help            显示帮助

初始化时自动：安装 Python 依赖、PostgreSQL/Redis（Homebrew）、pgvector、Node.js、
复制 .env、数据库迁移、演示数据导入（无数据时）。
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --low-memory)
            DEV_RELOAD=0
            shift
            ;;
        --with-docker-deps)
            USE_DOCKER_DEPS=1
            shift
            ;;
        --non-interactive)
            NON_INTERACTIVE=1
            shift
            ;;
        --force)
            FORCE=1
            NON_INTERACTIVE=1
            shift
            ;;
        --with-local-worker)
            WITH_LOCAL_WORKER=1
            shift
            ;;
        --no-local-worker)
            WITH_LOCAL_WORKER=0
            shift
            ;;
        --no-auto-install)
            AUTO_INSTALL_DEPS=0
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "❌ 未知参数: $1"
            usage
            exit 2
            ;;
    esac
done

ensure_modern_frontend_running() {
    if [ ! -d "$FRONTEND_DIR" ]; then
        echo "⚠️  未找到 modern 前端目录，跳过前端启动：$FRONTEND_DIR"
        return
    fi

    if lsof -Pi :"$FRONTEND_PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "✅ modern 前端已运行（端口$FRONTEND_PORT）"
        return
    fi

    if ! command -v npm >/dev/null 2>&1; then
        echo "⚠️  未检测到 npm，跳过 modern 前端启动"
        return
    fi

    echo ""
    echo "🎨 启动 modern 前端（端口$FRONTEND_PORT）..."
    cd "$FRONTEND_DIR"

    if [ ! -d "node_modules" ]; then
        echo "📦 安装 frontend-modern 依赖..."
        npm install
    fi

    VITE_API_PROXY_TARGET="http://localhost:8000" nohup npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" >"$FRONTEND_LOG_FILE" 2>&1 &
    FRONTEND_PID=$!
    echo "$FRONTEND_PID" >"$FRONTEND_PID_FILE"

    for _ in $(seq 1 60); do
        if lsof -Pi :"$FRONTEND_PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done

    if lsof -Pi :"$FRONTEND_PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "✅ modern 前端已启动：http://$FRONTEND_HOST:$FRONTEND_PORT"
        echo "📝 前端日志：$FRONTEND_LOG_FILE"
    elif grep -q "VITE v" "$FRONTEND_LOG_FILE" 2>/dev/null; then
        echo "✅ modern 前端已启动（日志就绪）：http://$FRONTEND_HOST:$FRONTEND_PORT"
        echo "📝 前端日志：$FRONTEND_LOG_FILE"
    else
        echo "⚠️  modern 前端启动超时，请检查日志：$FRONTEND_LOG_FILE"
    fi

    cd "$SCRIPT_DIR"
}

is_tcp_open() {
    local host="$1"
    local port="$2"
    if command -v pg_isready >/dev/null 2>&1; then
        pg_isready -h "$host" -p "$port" >/dev/null 2>&1 && return 0
    fi
    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 && return 0
    fi
    if command -v nc >/dev/null 2>&1; then
        nc -z "$host" "$port" >/dev/null 2>&1 && return 0
    fi
    return 1
}

ensure_homebrew_available() {
    if command -v brew >/dev/null 2>&1; then
        return 0
    fi

    if [ "$AUTO_INSTALL_DEPS" != "1" ]; then
        return 1
    fi

    if [[ "$OSTYPE" != darwin* ]] && [[ "$OSTYPE" != linux* ]]; then
        echo "⚠️  当前系统不支持自动安装 Homebrew（OSTYPE=$OSTYPE）"
        return 1
    fi

    if ! command -v curl >/dev/null 2>&1; then
        echo "⚠️  缺少 curl，无法自动安装 Homebrew"
        return 1
    fi

    if [ "$NON_INTERACTIVE" != "1" ]; then
        echo "⚠️  未检测到 Homebrew，准备自动安装。"
        read -p "是否继续安装 Homebrew？(y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return 1
        fi
    fi

    echo "📦 正在安装 Homebrew（仅首次会较慢）..."
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || return 1

    if [[ -x /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null)" || true
    elif [[ -x /usr/local/bin/brew ]]; then
        eval "$(/usr/local/bin/brew shellenv 2>/dev/null)" || true
    fi

    if command -v brew >/dev/null 2>&1; then
        echo "✅ Homebrew 安装完成"
        return 0
    fi
    return 1
}

try_start_brew_postgres() {
    if ! ensure_homebrew_available; then
        return 1
    fi

    local svcs=()
    while IFS= read -r line; do
        [ -n "$line" ] && svcs+=("$line")
    done < <(brew services list 2>/dev/null | awk '/^postgresql(@[0-9]+)?[[:space:]]/ {print $1}' | sort -rV)

    if [ ${#svcs[@]} -eq 0 ]; then
        while IFS= read -r formula; do
            [ -n "$formula" ] && svcs+=("$formula")
        done < <(brew list --formula 2>/dev/null | awk '/^postgresql(@[0-9]+)?$/ {print $1}' | sort -rV)
    fi

    # Auto-install postgresql when Homebrew exists but postgresql formula/service is missing.
    if [ ${#svcs[@]} -eq 0 ]; then
        echo "📦 未检测到 PostgreSQL，尝试使用 Homebrew 自动安装 postgresql..."
        if brew install postgresql >/dev/null 2>&1; then
            while IFS= read -r formula; do
                [ -n "$formula" ] && svcs+=("$formula")
            done < <(brew list --formula 2>/dev/null | awk '/^postgresql(@[0-9]+)?$/ {print $1}' | sort -rV)
        fi
    fi

    if [ ${#svcs[@]} -eq 0 ]; then
        return 1
    fi

    local svc
    for svc in "${svcs[@]}"; do
        echo "🔧 尝试启动本机 PostgreSQL 服务：$svc"
        brew services start "$svc" >/dev/null 2>&1 || brew services restart "$svc" >/dev/null 2>&1 || true
        for _ in $(seq 1 8); do
            if is_tcp_open "$DB_HOST" "$DB_PORT"; then
                return 0
            fi
            sleep 1
        done
    done
    return 1
}

try_start_brew_redis() {
    if ! ensure_homebrew_available; then
        return 1
    fi

    local svcs=()
    while IFS= read -r line; do
        [ -n "$line" ] && svcs+=("$line")
    done < <(brew services list 2>/dev/null | awk '/^redis(@[0-9]+)?[[:space:]]/ {print $1}' | sort -rV)

    if [ ${#svcs[@]} -eq 0 ]; then
        while IFS= read -r formula; do
            [ -n "$formula" ] && svcs+=("$formula")
        done < <(brew list --formula 2>/dev/null | awk '/^redis(@[0-9]+)?$/ {print $1}' | sort -rV)
    fi

    # Auto-install redis when Homebrew exists but redis formula/service is missing.
    if [ ${#svcs[@]} -eq 0 ]; then
        echo "📦 未检测到 Redis，尝试使用 Homebrew 自动安装 redis..."
        if brew install redis >/dev/null 2>&1; then
            while IFS= read -r formula; do
                [ -n "$formula" ] && svcs+=("$formula")
            done < <(brew list --formula 2>/dev/null | awk '/^redis(@[0-9]+)?$/ {print $1}' | sort -rV)
        fi
    fi

    if [ ${#svcs[@]} -eq 0 ]; then
        return 1
    fi

    local svc
    for svc in "${svcs[@]}"; do
        echo "🔧 尝试启动本机 Redis 服务：$svc"
        brew services start "$svc" >/dev/null 2>&1 || brew services restart "$svc" >/dev/null 2>&1 || true
        for _ in $(seq 1 8); do
            if is_tcp_open "$REDIS_HOST" "$REDIS_PORT"; then
                return 0
            fi
            sleep 1
        done
    done
    return 1
}

ensure_local_postgres_running() {
    if is_tcp_open "$DB_HOST" "$DB_PORT"; then
        echo "✅ PostgreSQL 已运行（$DB_HOST:$DB_PORT）"
        return 0
    fi

    echo "⚠️  PostgreSQL 未监听（$DB_HOST:$DB_PORT），尝试自动启动..."
    if try_start_brew_postgres; then
        for _ in $(seq 1 30); do
            if is_tcp_open "$DB_HOST" "$DB_PORT"; then
                echo "✅ PostgreSQL 已自动启动（$DB_HOST:$DB_PORT）"
                return 0
            fi
            sleep 1
        done
    fi

    echo "❌ PostgreSQL 启动失败或未安装。"
    echo "请先确保本机数据库可用：$DB_HOST:$DB_PORT"
    echo "可选：brew services restart postgresql@16（按你的实际版本调整）"
    if command -v brew >/dev/null 2>&1; then
        echo "当前 brew services 状态："
        brew services list 2>/dev/null | awk '/^postgresql(@[0-9]+)?[[:space:]]/ {print "  - "$0}'
    fi
    return 1
}

ensure_local_redis_running() {
    if is_tcp_open "$REDIS_HOST" "$REDIS_PORT"; then
        echo "✅ Redis 已运行（$REDIS_HOST:$REDIS_PORT）"
        return 0
    fi

    echo "⚠️  Redis 未监听（$REDIS_HOST:$REDIS_PORT），尝试自动启动..."
    if try_start_brew_redis; then
        for _ in $(seq 1 30); do
            if is_tcp_open "$REDIS_HOST" "$REDIS_PORT"; then
                echo "✅ Redis 已自动启动（$REDIS_HOST:$REDIS_PORT）"
                return 0
            fi
            sleep 1
        done
    fi

    echo "❌ Redis 启动失败或未安装。"
    echo "请先确保本机 Redis 可用：$REDIS_HOST:$REDIS_PORT"
    echo "可选：brew services restart redis"
    if command -v brew >/dev/null 2>&1; then
        echo "当前 brew services 状态："
        brew services list 2>/dev/null | awk '/^redis(@[0-9]+)?[[:space:]]/ {print "  - "$0}'
    fi
    return 1
}

detect_python_cmd() {
    if command -v python3.11 >/dev/null 2>&1; then
        echo "python3.11"
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        echo "python3"
        return 0
    fi
    return 1
}

ensure_backend_venv() {
    local pycmd
    pycmd="$(detect_python_cmd)" || {
        echo "❌ 未找到 Python 解释器（需要 python3.11 或 python3）"
        return 1
    }

    if [ ! -d "$VENV_DIR" ]; then
        echo "📦 创建后端虚拟环境：$VENV_DIR（$pycmd）"
        "$pycmd" -m venv "$VENV_DIR"
    fi

    # shellcheck disable=SC1091
    source "${VENV_DIR}/bin/activate"

    if [ ! -f "$REQ_FILE" ]; then
        echo "⚠️  未找到 $REQ_FILE，跳过依赖安装"
        return 0
    fi

    local cur_hash
    cur_hash="$(shasum -a 256 "$REQ_FILE" | awk '{print $1}')"
    local old_hash=""
    if [ -f "$REQ_HASH_FILE" ]; then
        old_hash="$(cat "$REQ_HASH_FILE" 2>/dev/null || true)"
    fi

    if [ "$cur_hash" != "$old_hash" ]; then
        echo "📦 安装后端 Python 依赖（$REQ_FILE）..."
        if ! python -m pip install -r "$REQ_FILE"; then
            echo "❌ 后端依赖安装失败。"
            echo "请检查网络或私有源配置后重试：pip install -r $REQ_FILE"
            return 1
        fi
        echo "$cur_hash" > "$REQ_HASH_FILE"
    else
        echo "✅ 后端 Python 依赖已是最新"
    fi
}

run_psql_local() {
    local psql_cmd=""
    if command -v psql >/dev/null 2>&1; then
        psql_cmd="psql"
    elif [[ -x /opt/homebrew/opt/postgresql/bin/psql ]]; then
        psql_cmd="/opt/homebrew/opt/postgresql/bin/psql"
    elif [[ -x /usr/local/opt/postgresql/bin/psql ]]; then
        psql_cmd="/usr/local/opt/postgresql/bin/psql"
    else
        return 127
    fi
    PGPASSWORD="${PGPASSWORD:-}" "$psql_cmd" -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" -U "${DB_USER:-postgres}" -d "${DB_NAME:-postgres}" "$@" 2>/dev/null
}

# Ensure DB user from .env can connect; on Homebrew PostgreSQL, create postgres user if missing
ensure_postgres_user_ready() {
    if [ "$USE_DOCKER_DEPS" = "1" ]; then
        return 0
    fi
    if [ -f ".env" ]; then
        set -a
        # shellcheck source=/dev/null
        source ".env"
        set +a
        if [[ -n "${DATABASE_URL:-}" ]] && [[ "$DATABASE_URL" =~ postgresql[^:]*://([^:]+):([^@]*)@([^:]+):([0-9]+)/([^?]*) ]]; then
            DB_USER="${BASH_REMATCH[1]}"
            PGPASSWORD="${BASH_REMATCH[2]}"
            DB_HOST="${BASH_REMATCH[3]}"
            DB_PORT="${BASH_REMATCH[4]}"
            DB_NAME="${BASH_REMATCH[5]}"
        fi
    fi
    if run_psql_local -c "SELECT 1" >/dev/null 2>&1; then
        echo "✅ 数据库用户 ${DB_USER:-postgres} 连接正常"
        return 0
    fi
    # Homebrew PostgreSQL often has no postgres user; try current user and create postgres
    local current_user
    current_user="$(whoami 2>/dev/null || echo "$USER")"
    if [ -z "$current_user" ]; then
        return 1
    fi
    local psql_cmd=""
    if command -v psql >/dev/null 2>&1; then
        psql_cmd="psql"
    elif [[ -x /opt/homebrew/opt/postgresql/bin/psql ]]; then
        psql_cmd="/opt/homebrew/opt/postgresql/bin/psql"
    elif [[ -x /usr/local/opt/postgresql/bin/psql ]]; then
        psql_cmd="/usr/local/opt/postgresql/bin/psql"
    else
        return 127
    fi
    if PGPASSWORD="" "$psql_cmd" -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" -U "$current_user" -d "${DB_NAME:-postgres}" -c "SELECT 1" >/dev/null 2>&1; then
        echo "📦 检测到 Homebrew PostgreSQL 无 postgres 用户，尝试创建..."
        if PGPASSWORD="" "$psql_cmd" -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" -U "$current_user" -d "${DB_NAME:-postgres}" -c "DO \$\$ BEGIN CREATE USER postgres WITH PASSWORD 'postgres' SUPERUSER; EXCEPTION WHEN duplicate_object THEN NULL; END \$\$;" 2>/dev/null; then
            echo "✅ 已创建 postgres 用户（密码: postgres）"
            if run_psql_local -c "SELECT 1" >/dev/null 2>&1; then
                return 0
            fi
        fi
        echo "⚠️  无法创建 postgres 用户。请手动执行："
        echo "   psql -U $current_user -d ${DB_NAME:-postgres} -c \"CREATE USER postgres WITH PASSWORD 'postgres' SUPERUSER;\""
        echo "   或修改 .env 中 DATABASE_URL 使用当前用户：postgresql+psycopg2://$current_user@localhost:5432/postgres"
        return 1
    fi
    return 1
}

ensure_pgvector_available() {
    if [ "$USE_DOCKER_DEPS" = "1" ]; then
        return 0
    fi
    if [ -f ".env" ]; then
        set -a
        # shellcheck source=/dev/null
        source ".env"
        set +a
        if [[ -n "${DATABASE_URL:-}" ]] && [[ "$DATABASE_URL" =~ postgresql[^:]*://([^:]+):([^@]*)@([^:]+):([0-9]+)/([^?]*) ]]; then
            DB_USER="${BASH_REMATCH[1]}"
            PGPASSWORD="${BASH_REMATCH[2]}"
            DB_HOST="${BASH_REMATCH[3]}"
            DB_PORT="${BASH_REMATCH[4]}"
            DB_NAME="${BASH_REMATCH[5]}"
        fi
    fi
    if run_psql_local -c "SELECT 1 FROM pg_extension WHERE extname='vector'" 2>/dev/null | grep -q 1; then
        echo "✅ pgvector 扩展已安装"
        return 0
    fi
    if run_psql_local -c "CREATE EXTENSION IF NOT EXISTS vector" 2>/dev/null; then
        echo "✅ pgvector 扩展已启用"
        return 0
    fi
    echo "⚠️  pgvector 扩展不可用，尝试通过 Homebrew 安装..."
    if ! ensure_homebrew_available; then
        echo "❌ 未找到 Homebrew，请先安装: https://brew.sh"
        return 1
    fi
    if brew install pgvector 2>/dev/null; then
        echo "📦 pgvector 已安装，重启 PostgreSQL..."
        pg_svc=$(brew services list 2>/dev/null | awk '/^postgresql(@[0-9]+)?[[:space:]]/ {print $1}' | head -1)
        if [ -n "$pg_svc" ]; then
            brew services restart "$pg_svc" 2>/dev/null || true
        else
            brew services restart postgresql 2>/dev/null || brew services restart postgresql@16 2>/dev/null || true
        fi
        echo "⏳ 等待 PostgreSQL 就绪..."
        sleep 5
        for _ in $(seq 1 15); do
            if run_psql_local -c "SELECT 1" >/dev/null 2>&1; then
                if run_psql_local -c "CREATE EXTENSION IF NOT EXISTS vector" 2>/dev/null; then
                    echo "✅ pgvector 扩展已启用"
                    return 0
                fi
            fi
            sleep 1
        done
    fi
    echo "⚠️  pgvector 安装或启用失败，数据库迁移可能失败"
    return 0
}

ensure_node_available() {
    if command -v npm >/dev/null 2>&1; then
        return 0
    fi
    echo "⚠️  未检测到 npm，尝试通过 Homebrew 安装 Node.js..."
    if ! ensure_homebrew_available; then
        echo "⚠️  未找到 Homebrew，跳过 modern 前端启动"
        return 1
    fi
    if brew install node 2>/dev/null; then
        echo "✅ Node.js 已安装"
        eval "$(brew shellenv 2>/dev/null)" || true
        return 0
    fi
    return 1
}

ensure_local_worker_running() {
    if [ "$WITH_LOCAL_WORKER" != "1" ]; then
        return 0
    fi

    if [ ! -x "${VENV_DIR}/bin/celery" ]; then
        echo "❌ 未找到 celery 命令，请确认依赖安装成功"
        return 1
    fi

    if [ -f "$WORKER_PID_FILE" ]; then
        local worker_pid
        worker_pid="$(cat "$WORKER_PID_FILE" 2>/dev/null || true)"
        if [ -n "${worker_pid:-}" ] && kill -0 "$worker_pid" >/dev/null 2>&1; then
            echo "✅ 本机 Celery worker 已运行（PID $worker_pid）"
            return 0
        fi
        rm -f "$WORKER_PID_FILE"
    fi

    echo ""
    echo "🧵 启动本机 Celery worker..."
    nohup "${VENV_DIR}/bin/celery" -A app.celery_app worker \
        --loglevel="${CELERY_LOG_LEVEL}" \
        --concurrency="${CELERY_CONCURRENCY}" \
        --prefetch-multiplier="${CELERY_PREFETCH_MULTIPLIER}" \
        --max-tasks-per-child="${CELERY_MAX_TASKS_PER_CHILD}" \
        --max-memory-per-child="${CELERY_MAX_MEMORY_PER_CHILD}" \
        --queues="${CELERY_QUEUES}" \
        >"$WORKER_LOG_FILE" 2>&1 &
    local worker_pid=$!
    echo "$worker_pid" >"$WORKER_PID_FILE"
    sleep 1
    if kill -0 "$worker_pid" >/dev/null 2>&1; then
        echo "✅ 本机 Celery worker 已启动（PID $worker_pid）"
        echo "📝 Worker 日志：$WORKER_LOG_FILE"
        return 0
    fi
    echo "❌ 本机 Celery worker 启动失败，请检查日志：$WORKER_LOG_FILE"
    return 1
}

echo "🚀 启动本地开发环境..."

ensure_backend_venv || exit 1

unset DOCKER_ENV
export DOCKER_ENV=""

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "📄 复制 .env.example 为 .env"
        cp .env.example .env
    else
        echo "⚠️  .env文件不存在，将使用默认配置（localhost）"
        echo "💡 提示：可以复制 .env.example 为 .env 并修改配置"
    fi
fi

if [ "$USE_DOCKER_DEPS" = "1" ]; then
    if [ -f "$OPS_DIR/docker-compose.yml" ]; then
        echo ""
        echo "📦 检查数据库服务状态（Docker依赖模式）..."

        if ! docker info >/dev/null 2>&1; then
            echo "⚠️  Docker未运行，跳过数据库服务启动"
            echo "💡 提示：如需使用数据库，请先启动Docker并运行：cd $OPS_DIR && docker compose up -d db es redis"
        else
            cd "$OPS_DIR"
            set +e
            DB_RUNNING=$(compose ps -q db 2>/dev/null | wc -l | tr -d ' ')
            ES_RUNNING=$(compose ps -q es 2>/dev/null | wc -l | tr -d ' ')
            REDIS_RUNNING=$(compose ps -q redis 2>/dev/null | wc -l | tr -d ' ')
            set -e

            if [ "$DB_RUNNING" -eq 0 ] || [ "$ES_RUNNING" -eq 0 ] || [ "$REDIS_RUNNING" -eq 0 ]; then
                echo "🚀 启动数据库服务（db, es, redis）..."
                compose up -d db es redis

                echo "⏳ 等待数据库服务就绪..."
                sleep 3
            else
                echo "✅ 数据库服务已在运行"
            fi

            cd "$SCRIPT_DIR"
        fi
    else
        echo "⚠️  未找到docker-compose.yml，跳过数据库服务启动"
    fi
else
    echo ""
    echo "📦 使用纯本机依赖模式（不启动 Docker db/es/redis）"
    ensure_local_postgres_running || exit 1
    ensure_postgres_user_ready || exit 1
    ensure_local_redis_running || exit 1
    ensure_pgvector_available || true
fi

# Run alembic migrations and seed demo data when empty
ensure_db_migrated_and_seeded() {
    echo ""
    echo "📦 检查数据库迁移与演示数据..."
    local migrated=0
    local last_err=""
    for attempt in 1 2 3 4 5; do
        last_err=$(alembic upgrade head 2>&1) && migrated=1 && break
        if [ "$attempt" -lt 5 ]; then
            echo "⏳ 迁移失败，${attempt}秒后重试 ($attempt/5)..."
            sleep "$attempt"
        fi
    done
    if [ "$migrated" != "1" ]; then
        echo "⚠️  数据库迁移失败"
        echo "$last_err" | tail -15
        echo "💡 若数据库状态不一致，可新建空库: createdb market_intel_dev 并修改 .env 中 DATABASE_URL 的数据库名"
        return 0
    fi
    # Check if demo_proj exists; if not, load seed
    if python -c "
from sqlalchemy import create_engine, text
from app.settings.config import settings
e = create_engine(settings.database_url)
with e.connect() as c:
    r = c.execute(text(\"SELECT 1 FROM public.projects WHERE project_key='demo_proj' LIMIT 1\")).fetchone()
    exit(0 if r else 1)
" 2>/dev/null; then
        echo "✅ 演示项目 demo_proj 已存在"
        return 0
    fi
    echo "📥 未检测到演示数据，导入 demo_proj 种子..."
    SEED_SCRIPT="$SCRIPT_DIR/scripts/load_demo_proj_seed.sh"
    if [ -f "$SEED_SCRIPT" ]; then
        if USE_LOCAL=1 bash "$SEED_SCRIPT" 2>/dev/null; then
            echo "✅ 演示数据导入完成"
        else
            echo "⚠️  演示数据导入失败，可稍后手动执行: USE_LOCAL=1 $SEED_SCRIPT"
        fi
    else
        echo "⚠️  未找到导入脚本: $SEED_SCRIPT"
    fi
}

ensure_db_migrated_and_seeded

if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null; then
    echo ""
    echo "⚠️  端口8000已被占用"

    DOCKER_CONTAINER=""
    if command -v docker >/dev/null 2>&1; then
        set +e
        DOCKER_CONTAINER=$(docker ps --format "{{.ID}}\t{{.Ports}}" 2>/dev/null | grep ":8000->" | awk '{print $1}' | head -1)
        set -e
    fi

    if [ -n "$DOCKER_CONTAINER" ]; then
        echo "检测到Docker容器正在使用8000端口（容器ID: $DOCKER_CONTAINER）"
        echo "💡 提示：如果要在本地运行，请先停止Docker容器："
        echo "   cd $OPS_DIR && docker compose stop backend"
        if [ "$FORCE" = "1" ]; then
            echo "🚨 --force 已启用，自动停止 Docker backend 容器"
            cd "$OPS_DIR"
            compose stop backend 2>/dev/null || true
            cd "$SCRIPT_DIR"
            sleep 2
        elif [ "$NON_INTERACTIVE" = "1" ]; then
            echo "❌ --non-interactive 模式遇到端口冲突，退出"
            exit 1
        else
            read -p "是否要停止Docker backend容器？(y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                cd "$OPS_DIR"
                compose stop backend 2>/dev/null || true
                cd "$SCRIPT_DIR"
                sleep 2
            else
                echo "请手动停止占用端口的进程或使用其他端口"
                exit 1
            fi
        fi
    else
        if [ "$FORCE" = "1" ]; then
            echo "🚨 --force 已启用，自动停止占用8000端口的进程"
            lsof -ti:8000 | xargs kill -9 2>/dev/null || true
            sleep 1
        elif [ "$NON_INTERACTIVE" = "1" ]; then
            echo "❌ --non-interactive 模式遇到端口冲突，退出"
            exit 1
        else
            read -p "是否要停止占用8000端口的进程？(y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                lsof -ti:8000 | xargs kill -9 2>/dev/null || true
                sleep 1
            else
                echo "请手动停止占用端口的进程或使用其他端口"
                exit 1
            fi
        fi
    fi
fi

ensure_node_available || true
ensure_modern_frontend_running
ensure_local_worker_running || exit 1

echo ""
if [ "$DEV_RELOAD" = "1" ]; then
    RELOAD_DESC="自动重载"
else
    RELOAD_DESC="低内存模式（无重载）"
fi

echo "✅ 启动后端服务（端口8000，${RELOAD_DESC}）..."
echo "🔒 环境隔离：已清除DOCKER_ENV，使用localhost连接数据库服务"
echo "📝 日志文件：/tmp/uvicorn.log"
echo "🌐 API文档：http://localhost:8000/docs（本机）"
echo "🌐 局域网访问：http://$(ipconfig getifaddr en0 2>/dev/null || ifconfig | grep 'inet ' | grep -v 127.0.0.1 | awk '{print $2}' | head -1):8000/docs"
echo "📊 健康检查：http://localhost:8000/api/v1/health"
echo "🎨 modern 前端：http://$FRONTEND_HOST:$FRONTEND_PORT"
if [ "$WITH_LOCAL_WORKER" = "1" ]; then
    echo "🧵 本机 Celery worker：已启用（日志 $WORKER_LOG_FILE）"
fi
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
if [ "$DEV_RELOAD" = "1" ]; then
    DOCKER_ENV="" uvicorn app.main:app --reload --host "$BACKEND_HOST" --port 8000
else
    DOCKER_ENV="" uvicorn app.main:app --host "$BACKEND_HOST" --port 8000
fi
