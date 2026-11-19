#!/bin/bash
# 本地开发环境启动脚本

set -e

# Ensure Homebrew tools (node, psql, etc.) are in PATH when available
if [[ -x /opt/homebrew/bin/brew ]]; then
    PATH="$PATH:/opt/homebrew/bin:/opt/homebrew/sbin"
elif [[ -x /usr/local/bin/brew ]]; then
    PATH="$PATH:/usr/local/bin:/usr/local/sbin"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd "$ROOT_DIR/.." && pwd)"
export PYTHONPATH="$SCRIPT_DIR:$REPO_DIR/src:$REPO_DIR"
FRONTEND_DIR="$ROOT_DIR/frontend-modern"
OPS_DIR="$(cd "$SCRIPT_DIR/../ops" && pwd)"
WEBUI_DIR="$OPS_DIR/codex-webui"
ES_LOCAL_SCRIPT="$REPO_DIR/scripts/start-es-local.sh"
BACKEND_PORT="${BACKEND_PORT:-8000}"
MRW_LOCAL_STATE_DIR="${MRW_LOCAL_STATE_DIR:-$REPO_DIR/.local-run}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_LOG_FILE="${MRW_LOCAL_STATE_DIR}/frontend-modern-dev.log"
FRONTEND_PID_FILE="${MRW_LOCAL_STATE_DIR}/frontend-modern-dev.pid"
FRONTEND_MODE="${FRONTEND_MODE:-}"
WORKER_LOG_FILE="${MRW_LOCAL_STATE_DIR}/celery-local-worker.log"
WORKER_PID_FILE="${MRW_LOCAL_STATE_DIR}/celery-local-worker.pid"
CELERY_LOG_LEVEL="${CELERY_LOG_LEVEL:-info}"
CELERY_CONCURRENCY="${CELERY_CONCURRENCY:-3}"
CELERY_PREFETCH_MULTIPLIER="${CELERY_PREFETCH_MULTIPLIER:-2}"
CELERY_MAX_TASKS_PER_CHILD="${CELERY_MAX_TASKS_PER_CHILD:-100}"
CELERY_MAX_MEMORY_PER_CHILD="${CELERY_MAX_MEMORY_PER_CHILD:-500000}"
CELERY_QUEUES="${CELERY_QUEUES:-celery}"
CELERY_WORKER_NODENAME="${CELERY_WORKER_NODENAME:-}"
if [[ "$OSTYPE" == darwin* ]]; then
    CELERY_POOL="${CELERY_POOL:-solo}"
else
    CELERY_POOL="${CELERY_POOL:-prefork}"
fi
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
VENV_DIR=".venv311"
REQ_FILE="requirements.txt"
OPTIONAL_REQ_FILE="requirements-optional-enhancements.txt"
REQ_HASH_FILE="${VENV_DIR}/.requirements.sha256"
OPTIONAL_REQ_HASH_FILE="${VENV_DIR}/.requirements-optional-enhancements.sha256"

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
BACKEND_ONLY=0
WITH_LOCAL_WORKER=1
AUTO_INSTALL_DEPS=1
KEEP_DOCKER_DEPS=0
WITH_LANCEDB=0
PROVISION=0
PREPARE_DEPENDENCIES=0

usage() {
    cat <<'EOF'
Usage: ./start-local.sh [options]

Options:
  --low-memory          关闭自动重载，降低内存占用
  --with-docker-deps    自动启动 Docker 依赖（db/es/redis）
  --keep-docker-deps    纯本机模式下保留 Docker 依赖（默认会自动停止，避免模式混用）
  --non-interactive     非交互模式，端口冲突时直接失败退出
  --force               强制模式，端口冲突时自动处理并继续
  --backend-only        仅启动后端；跳过本机前端和 Celery worker
  --with-local-worker   同时启动本机 Celery worker（默认已开启）
  --no-local-worker     不启动本机 Celery worker
  --provision           允许创建环境、安装依赖、启动依赖、迁移和导入 seed
  --prepare-dependencies
                        仅在当前源码根准备 Python/frontend/WebUI 依赖后退出
  --no-provision        仅使用现有环境与数据（默认）
  --no-auto-install     不自动安装缺失依赖（Homebrew/PostgreSQL/pgvector）
  --with-lancedb        安装并启用 LanceDB 本地索引增强（可选依赖）
  -h, --help            显示帮助

默认仅使用现有环境与数据；使用 --provision 时才安装项目依赖、
复制 .env、执行数据库迁移并导入演示数据。前端所需的 Node.js 和 pnpm 由使用者准备；
本机 Redis 由使用者按需启动，Redis 不可用时不启动本机任务 worker。

依赖准备不会读取或创建 .env，不启动服务、Docker 或 Homebrew，也不迁移或导入数据。
若需复用另一份相同源码的运行依赖，可设置 MRW_DEPENDENCY_SOURCE_ROOT 为其绝对根目录；
源码导入仍会校验为当前脚本所在根目录。
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
        --keep-docker-deps)
            KEEP_DOCKER_DEPS=1
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
        --backend-only)
            BACKEND_ONLY=1
            WITH_LOCAL_WORKER=0
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
        --with-lancedb)
            WITH_LANCEDB=1
            shift
            ;;
        --provision)
            PROVISION=1
            shift
            ;;
        --prepare-dependencies)
            PREPARE_DEPENDENCIES=1
            shift
            ;;
        --no-provision)
            PROVISION=0
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

if [ "$PREPARE_DEPENDENCIES" = "1" ]; then
    PROVISION=1
fi

if [ -z "$FRONTEND_MODE" ]; then
    if [ "$PROVISION" = "1" ]; then
        FRONTEND_MODE="dev"
    else
        FRONTEND_MODE="preview"
    fi
fi

ensure_modern_frontend_running() {
    if [ ! -d "$FRONTEND_DIR" ]; then
        echo "❌ 未找到 modern 前端目录：$FRONTEND_DIR"
        return 1
    fi

    if [[ -n "$(lsof -nP -iTCP:"$FRONTEND_PORT" -sTCP:LISTEN -t 2>/dev/null || true)" ]]; then
        if port_has_only_owned_listener "$FRONTEND_PORT" "$FRONTEND_DIR" "vite"; then
            echo "✅ modern 前端已运行（端口${FRONTEND_PORT}）"
            return 0
        fi
        echo "❌ 前端端口$FRONTEND_PORT 被非本仓库进程占用"
        return 1
    fi

    if ! command -v pnpm >/dev/null 2>&1; then
        echo "❌ 未检测到 pnpm；请先准备 Node.js 和 pnpm"
        return 1
    fi

    echo ""
    echo "🎨 启动 modern 前端（端口${FRONTEND_PORT}）..."
    cd "$FRONTEND_DIR"

    if [ ! -x "node_modules/.bin/vite" ]; then
        if [ "$PROVISION" != "1" ]; then
            echo "❌ modern 前端依赖缺失；先运行 scripts/local-deploy.sh prepare"
            return 1
        fi
        echo "📦 按 pnpm-lock.yaml 准备 frontend-modern 依赖..."
        pnpm install --frozen-lockfile || return 1
    fi
    if [ "$FRONTEND_MODE" = "preview" ] && [ ! -f "dist/index.html" ]; then
        echo "❌ modern 前端静态产物缺失；先完成构建或显式 FRONTEND_MODE=dev"
        return 1
    fi

    VITE_API_PROXY_TARGET="http://127.0.0.1:${BACKEND_PORT}" nohup pnpm run "$FRONTEND_MODE" --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" --strictPort >"$FRONTEND_LOG_FILE" 2>&1 &
    FRONTEND_PID=$!
    echo "$FRONTEND_PID" >"$FRONTEND_PID_FILE"

    for _ in $(seq 1 60); do
        if lsof -Pi :"$FRONTEND_PORT" -sTCP:LISTEN -t >/dev/null 2>&1 || ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
            break
        fi
        sleep 0.5
    done

    if lsof -Pi :"$FRONTEND_PORT" -sTCP:LISTEN -t >/dev/null 2>&1 && port_has_only_owned_listener "$FRONTEND_PORT" "$FRONTEND_DIR" "vite"; then
        echo "✅ modern 前端已启动：http://$FRONTEND_HOST:$FRONTEND_PORT"
        echo "📝 前端日志：$FRONTEND_LOG_FILE"
    else
        echo "❌ modern 前端未就绪，请检查日志：$FRONTEND_LOG_FILE"
        return 1
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
        echo "⚠️  当前系统不支持自动安装 Homebrew（OSTYPE=${OSTYPE}）"
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
        PATH="$PATH:/opt/homebrew/bin:/opt/homebrew/sbin"
    elif [[ -x /usr/local/bin/brew ]]; then
        PATH="$PATH:/usr/local/bin:/usr/local/sbin"
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

ensure_local_postgres_running() {
    if is_tcp_open "$DB_HOST" "$DB_PORT"; then
        echo "✅ PostgreSQL 已运行（$DB_HOST:${DB_PORT}）"
        return 0
    fi

    echo "⚠️  PostgreSQL 未监听（$DB_HOST:${DB_PORT}），尝试自动启动..."
    if try_start_brew_postgres; then
        for _ in $(seq 1 30); do
            if is_tcp_open "$DB_HOST" "$DB_PORT"; then
                echo "✅ PostgreSQL 已自动启动（$DB_HOST:${DB_PORT}）"
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

stop_conflicting_docker_deps_for_local_mode() {
    if [ "$KEEP_DOCKER_DEPS" = "1" ]; then
        echo "ℹ️  --keep-docker-deps 已启用：保留 Docker db/es/redis（可能导致本机/容器模式混用）"
        return 0
    fi

    if [ ! -f "$OPS_DIR/docker-compose.yml" ]; then
        return 0
    fi
    if ! docker info >/dev/null 2>&1; then
        return 0
    fi

    local db_running=0
    local es_running=0
    local redis_running=0
    set +e
    db_running=$(cd "$OPS_DIR" && compose ps -q db 2>/dev/null | wc -l | tr -d ' ')
    es_running=$(cd "$OPS_DIR" && compose ps -q es 2>/dev/null | wc -l | tr -d ' ')
    redis_running=$(cd "$OPS_DIR" && compose ps -q redis 2>/dev/null | wc -l | tr -d ' ')
    set -e

    if [ "${db_running:-0}" -eq 0 ] && [ "${es_running:-0}" -eq 0 ] && [ "${redis_running:-0}" -eq 0 ]; then
        return 0
    fi

    echo "🔀 检测到 Docker 依赖服务正在运行（db/es/redis），为避免本机/容器模式混用，将自动停止它们。"
    cd "$OPS_DIR"
    compose stop db es redis >/dev/null 2>&1 || true
    cd "$SCRIPT_DIR"
    sleep 1
    echo "✅ 已停止 Docker db/es/redis，切换为纯本机依赖模式"
}

ensure_local_elasticsearch_running() {
    local es_url="${ES_URL:-http://localhost:9200}"
    local es_hostport="${es_url#*://}"
    es_hostport="${es_hostport%%/*}"
    local es_host="${es_hostport%%:*}"
    local es_port="${es_hostport##*:}"

    if [ -z "$es_host" ]; then
        es_host="localhost"
    fi
    if [ -z "$es_port" ] || [ "$es_port" = "$es_hostport" ]; then
        es_port="9200"
    fi

    case "$es_host" in
        localhost|127.0.0.1)
            ;;
        *)
            echo "ℹ️  ES_URL 指向远程地址（${es_url}），跳过本机 Elasticsearch 启动"
            return 0
            ;;
    esac

    if command -v curl >/dev/null 2>&1 && curl -fsS "$es_url" >/dev/null 2>&1; then
        echo "✅ Elasticsearch 已运行（${es_host}:${es_port}）"
        return 0
    fi

    if [ ! -f "$ES_LOCAL_SCRIPT" ]; then
        echo "⚠️  未找到本机 Elasticsearch 启动脚本：$ES_LOCAL_SCRIPT"
        echo "💡 提示：可手动启动 Elasticsearch，或使用 --with-docker-deps"
        return 0
    fi

    echo "🚀 尝试启动本机 Elasticsearch（${es_host}:${es_port}）..."
    if bash "$ES_LOCAL_SCRIPT" start; then
        echo "✅ 本机 Elasticsearch 已启动"
        return 0
    fi

    echo "⚠️  本机 Elasticsearch 启动失败，相关全文检索功能将不可用"
    echo "💡 提示：查看 /opt/homebrew/var/log/elasticsearch.log 或改用 --with-docker-deps"
    return 0
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
    if [ "$PROVISION" != "1" ]; then
        if [ ! -x "${VENV_DIR}/bin/python" ] || [ ! -x "${VENV_DIR}/bin/uvicorn" ]; then
            echo "❌ 后端运行环境缺失；使用 --provision 创建并安装依赖"
            return 1
        fi
        # shellcheck disable=SC1091
        source "${VENV_DIR}/bin/activate"
        return 0
    fi

    local pycmd
    pycmd="$(detect_python_cmd)" || {
        echo "❌ 未找到 Python 解释器（需要 python3.11 或 python3）"
        return 1
    }

    if [ ! -d "$VENV_DIR" ]; then
        echo "📦 创建后端虚拟环境：${VENV_DIR}（${pycmd}）"
        "$pycmd" -m venv "$VENV_DIR"
    fi

    # shellcheck disable=SC1091
    source "${VENV_DIR}/bin/activate"

    if [ ! -f "$REQ_FILE" ]; then
        echo "⚠️  未找到 ${REQ_FILE}，跳过依赖安装"
        return 0
    fi

    local cur_hash
    cur_hash="$(shasum -a 256 "$REQ_FILE" | awk '{print $1}')"
    local old_hash=""
    if [ -f "$REQ_HASH_FILE" ]; then
        old_hash="$(cat "$REQ_HASH_FILE" 2>/dev/null || true)"
    fi

    if [ "$cur_hash" != "$old_hash" ]; then
        echo "📦 安装后端 Python 依赖（${REQ_FILE}）..."
        if ! python -m pip install -r "$REQ_FILE"; then
            echo "❌ 后端依赖安装失败。"
            echo "请检查网络或私有源配置后重试：pip install -r $REQ_FILE"
            return 1
        fi
        echo "$cur_hash" > "$REQ_HASH_FILE"
    else
        echo "✅ 后端 Python 依赖已是最新"
    fi

    if [ "$WITH_LANCEDB" -eq 1 ]; then
        if [ ! -f "$OPTIONAL_REQ_FILE" ]; then
            echo "⚠️  未找到 ${OPTIONAL_REQ_FILE}，跳过 LanceDB 可选依赖安装"
            return 0
        fi
        local optional_hash
        optional_hash="$(shasum -a 256 "$OPTIONAL_REQ_FILE" | awk '{print $1}')"
        local old_optional_hash=""
        if [ -f "$OPTIONAL_REQ_HASH_FILE" ]; then
            old_optional_hash="$(cat "$OPTIONAL_REQ_HASH_FILE" 2>/dev/null || true)"
        fi
        if python - <<'PY' >/dev/null 2>&1 && [ "$optional_hash" = "$old_optional_hash" ]; then
import lancedb
PY
            echo "✅ LanceDB 本地索引增强已安装"
        else
            echo "📦 安装 LanceDB 本地索引增强（${OPTIONAL_REQ_FILE}）..."
            if ! python -m pip install -r "$OPTIONAL_REQ_FILE"; then
                echo "❌ LanceDB 可选依赖安装失败。"
                return 1
            fi
            echo "$optional_hash" > "$OPTIONAL_REQ_HASH_FILE"
        fi
    fi
}

canonical_existing_dir() {
    local path="$1"
    [ -d "$path" ] || return 1
    (cd "$path" && pwd -P)
}

reuse_dependency_tree() {
    local label="$1"
    local source="$2"
    local target="$3"
    local source_real target_real
    source_real="$(canonical_existing_dir "$source")" || {
        echo "❌ 复用依赖缺失（${label}）：$source"
        return 1
    }
    if [ -e "$target" ] || [ -L "$target" ]; then
        target_real="$(canonical_existing_dir "$target")" || {
            echo "❌ 现有依赖路径不可用（${label}）：$target"
            return 1
        }
        if [ "$target_real" != "$source_real" ]; then
            echo "❌ 当前根已有不同依赖目录（${label}）：$target_real"
            return 1
        fi
    else
        ln -s "$source_real" "$target" || return 1
    fi
    echo "✅ 复用 ${label}：$source_real"
}

prepare_reused_dependencies() {
    local source_root source_backend source_frontend source_webui
    source_root="$(canonical_existing_dir "$MRW_DEPENDENCY_SOURCE_ROOT")" || {
        echo "❌ MRW_DEPENDENCY_SOURCE_ROOT 不是可读目录"
        return 1
    }
    if [[ "$MRW_DEPENDENCY_SOURCE_ROOT" != /* ]]; then
        echo "❌ MRW_DEPENDENCY_SOURCE_ROOT 必须是绝对路径"
        return 1
    fi
    if [ "$source_root" = "$REPO_DIR" ]; then
        echo "❌ 依赖来源必须与当前源码根不同；当前根无需复用"
        return 1
    fi

    source_backend="$source_root/main/backend"
    source_frontend="$source_root/main/frontend-modern"
    source_webui="$source_root/main/ops/codex-webui"
    cmp -s "$REQ_FILE" "$source_backend/$REQ_FILE" || {
        echo "❌ 依赖来源 requirements.txt 与当前候选不一致"
        return 1
    }
    cmp -s "$FRONTEND_DIR/pnpm-lock.yaml" "$source_frontend/pnpm-lock.yaml" || {
        echo "❌ 依赖来源 frontend pnpm-lock.yaml 与当前候选不一致"
        return 1
    }
    cmp -s "$WEBUI_DIR/pnpm-lock.yaml" "$source_webui/pnpm-lock.yaml" || {
        echo "❌ 依赖来源 WebUI pnpm-lock.yaml 与当前候选不一致"
        return 1
    }

    local requirements_hash source_requirements_hash
    requirements_hash="$(shasum -a 256 "$REQ_FILE" | awk '{print $1}')"
    source_requirements_hash="$(cat "$source_backend/$REQ_HASH_FILE" 2>/dev/null || true)"
    if [ "$requirements_hash" != "$source_requirements_hash" ]; then
        echo "❌ 依赖来源 Python 环境未绑定当前 requirements.txt"
        return 1
    fi

    reuse_dependency_tree "backend venv" "$source_backend/$VENV_DIR" "$SCRIPT_DIR/$VENV_DIR" || return 1
    reuse_dependency_tree "frontend node_modules" "$source_frontend/node_modules" "$FRONTEND_DIR/node_modules" || return 1
    reuse_dependency_tree "WebUI node_modules" "$source_webui/node_modules" "$WEBUI_DIR/node_modules" || return 1
}

verify_candidate_source_imports() {
    MRW_EXPECTED_SOURCE_ROOT="$REPO_DIR" python - <<'PY'
import importlib
import os
from pathlib import Path

root = Path(os.environ["MRW_EXPECTED_SOURCE_ROOT"]).resolve()
expected = {
    "app": root / "main" / "backend" / "app" / "__init__.py",
    "mrw_functorial_kit": root / "src" / "mrw_functorial_kit" / "__init__.py",
}
for name, expected_path in expected.items():
    module = importlib.import_module(name)
    actual_raw = getattr(module, "__file__", None)
    if not actual_raw:
        raise SystemExit(f"candidate source import has no file: {name}")
    actual = Path(actual_raw).resolve()
    if actual != expected_path.resolve():
        raise SystemExit(
            f"candidate source import escaped root: {name} expected={expected_path.resolve()} actual={actual}"
        )
    print(f"candidate_source_import={name} path={actual}")
PY
}

verify_backend_python311() {
    "$VENV_DIR/bin/python" - <<'PY'
import sys

if sys.version_info[:2] != (3, 11):
    raise SystemExit(
        f"backend runtime must be Python 3.11, got {sys.version_info.major}.{sys.version_info.minor}"
    )
print(f"backend_python={sys.executable} version={sys.version_info.major}.{sys.version_info.minor}")
PY
}

prepare_dependencies_only() {
    echo "📦 仅准备当前候选根的运行依赖：$REPO_DIR"
    if [ -n "${MRW_DEPENDENCY_SOURCE_ROOT:-}" ]; then
        prepare_reused_dependencies || return 1
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
    else
        if [ -d "$VENV_DIR" ]; then
            [ -x "$VENV_DIR/bin/python" ] || {
                echo "❌ 现有 $VENV_DIR 缺少 Python；请移除该不完整目录后重试"
                return 1
            }
            verify_backend_python311 || return 1
        elif ! command -v python3.11 >/dev/null 2>&1; then
            echo "❌ fresh dependency prepare requires an explicit python3.11 interpreter"
            return 1
        fi
        command -v pnpm >/dev/null 2>&1 || {
            echo "❌ pnpm 不可用；依赖准备不会自动安装 Node.js 或 pnpm"
            return 1
        }
        ensure_backend_venv || return 1
        echo "📦 按 pnpm-lock.yaml 准备 frontend-modern 依赖..."
        (cd "$FRONTEND_DIR" && pnpm install --frozen-lockfile) || return 1
        echo "📦 按 pnpm-lock.yaml 准备 Codex WebUI 依赖..."
        (cd "$WEBUI_DIR" && pnpm install --frozen-lockfile) || return 1
    fi

    [ -x "$VENV_DIR/bin/python" ] && [ -x "$VENV_DIR/bin/uvicorn" ] || {
        echo "❌ 后端运行依赖不完整"
        return 1
    }
    verify_backend_python311 || return 1
    [ -x "$FRONTEND_DIR/node_modules/.bin/vite" ] || {
        echo "❌ frontend-modern 运行依赖不完整"
        return 1
    }
    [ -x "$WEBUI_DIR/node_modules/.bin/codex" ] || {
        echo "❌ Codex WebUI 固定版本 CLI 不完整"
        return 1
    }
    verify_candidate_source_imports || return 1
    echo "✅ 依赖准备完成；未读取 .env，未启动服务，未执行迁移或 seed"
}

resolve_psql_cmd() {
    local psql_cmd=""
    if command -v psql >/dev/null 2>&1; then
        psql_cmd="psql"
    elif [[ -x /opt/homebrew/opt/postgresql@18/bin/psql ]]; then
        psql_cmd="/opt/homebrew/opt/postgresql@18/bin/psql"
    elif [[ -x /opt/homebrew/opt/postgresql@17/bin/psql ]]; then
        psql_cmd="/opt/homebrew/opt/postgresql@17/bin/psql"
    elif [[ -x /opt/homebrew/opt/postgresql@16/bin/psql ]]; then
        psql_cmd="/opt/homebrew/opt/postgresql@16/bin/psql"
    elif [[ -x /opt/homebrew/opt/postgresql/bin/psql ]]; then
        psql_cmd="/opt/homebrew/opt/postgresql/bin/psql"
    elif [[ -x /usr/local/opt/postgresql@18/bin/psql ]]; then
        psql_cmd="/usr/local/opt/postgresql@18/bin/psql"
    elif [[ -x /usr/local/opt/postgresql@17/bin/psql ]]; then
        psql_cmd="/usr/local/opt/postgresql@17/bin/psql"
    elif [[ -x /usr/local/opt/postgresql@16/bin/psql ]]; then
        psql_cmd="/usr/local/opt/postgresql@16/bin/psql"
    elif [[ -x /usr/local/opt/postgresql/bin/psql ]]; then
        psql_cmd="/usr/local/opt/postgresql/bin/psql"
    else
        return 127
    fi
    echo "$psql_cmd"
}

run_psql_local() {
    local psql_cmd=""
    psql_cmd="$(resolve_psql_cmd)" || return 127
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
    psql_cmd="$(resolve_psql_cmd)" || return 127
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

ensure_local_worker_running() {
    if [ "$WITH_LOCAL_WORKER" != "1" ]; then
        return 0
    fi

    if [ ! -x "${VENV_DIR}/bin/celery" ]; then
        echo "⚠️  未找到 celery 命令；跳过本机 Celery worker"
        return 0
    fi

    # Check the configured Redis connection, not a separate host/port or a PID.
    # Never print connection arguments or raw connection errors.
    if ! python - <<'PYTHON' >/dev/null 2>&1
import os

from redis import Redis
from app.settings.config import settings

url = os.getenv("CELERY_BROKER_READ_URL") or os.getenv("CELERY_BROKER_URL") or settings.redis_url
with Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1) as client:
    raise SystemExit(0 if client.ping() else 1)
PYTHON
    then
        echo "⚠️  Redis 连接未通过；跳过本机 Celery worker。请检查任务队列配置和 Redis 服务。"
        return 0
    fi

    if [ -f "$WORKER_PID_FILE" ]; then
        local worker_pid
        worker_pid="$(cat "$WORKER_PID_FILE" 2>/dev/null || true)"
        if [ -n "${worker_pid:-}" ] && kill -0 "$worker_pid" >/dev/null 2>&1; then
            echo "ℹ️  本机 Celery worker 进程已存在（PID ${worker_pid}）；未验证任务消费"
            return 0
        fi
        rm -f "$WORKER_PID_FILE"
    fi

    echo ""
    echo "🧵 启动本机 Celery worker..."
    local worker_nodename="$CELERY_WORKER_NODENAME"
    if [ -z "$worker_nodename" ]; then
        worker_nodename="celery-local-$(date +%s)@%h"
    fi
    nohup "${VENV_DIR}/bin/celery" -A app.celery_app worker \
        --hostname="${worker_nodename}" \
        --pool="${CELERY_POOL}" \
        --loglevel="${CELERY_LOG_LEVEL}" \
        --concurrency="${CELERY_CONCURRENCY}" \
        --prefetch-multiplier="${CELERY_PREFETCH_MULTIPLIER}" \
        --max-tasks-per-child="${CELERY_MAX_TASKS_PER_CHILD}" \
        --max-memory-per-child="${CELERY_MAX_MEMORY_PER_CHILD}" \
        --queues="${CELERY_QUEUES}" \
        >"$WORKER_LOG_FILE" 2>&1 &
    local worker_pid=$!
    if ! echo "$worker_pid" >"$WORKER_PID_FILE"; then
        echo "⚠️  无法记录本轮 worker PID；取消本次 worker 启动"
        kill -TERM "$worker_pid" 2>/dev/null || true
        return 1
    fi
    sleep 1
    if kill -0 "$worker_pid" >/dev/null 2>&1; then
        echo "ℹ️  本机 Celery worker 进程已启动（PID ${worker_pid}）；未验证任务消费"
        echo "📝 Worker 日志：$WORKER_LOG_FILE"
        return 0
    fi
    rm -f "$WORKER_PID_FILE"
    echo "⚠️  本机 Celery worker 启动失败，请检查日志：$WORKER_LOG_FILE"
    return 1
}

pid_cwd() {
    lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1
}

terminate_pid_gracefully() {
    local pid="$1"
    local label="$2"
    kill -TERM "$pid" 2>/dev/null || return 1
    for _ in $(seq 1 20); do
        if ! kill -0 "$pid" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.1
    done
    kill -KILL "$pid" 2>/dev/null || true
    sleep 0.2
    if kill -0 "$pid" >/dev/null 2>&1; then
        echo "❌ 无法停止${label}进程 $pid"
        return 1
    fi
    return 0
}

stop_owned_port_listener() {
    local port="$1"
    local expected_cwd="$2"
    local command_marker="$3"
    local pid command_line cwd foreign_owner=0 pid_line
    while IFS= read -r pid; do
        [ -n "$pid" ] || continue
        command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
        cwd="$(pid_cwd "$pid")"
        if [ "$cwd" = "$expected_cwd" ] && [[ "$command_line" == *"$command_marker"* ]]; then
            terminate_pid_gracefully "$pid" "端口${port}的" || return 1
        else
            foreign_owner=1
        fi
    done < <(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)

    if [ "$foreign_owner" = "1" ]; then
        echo "❌ 端口${port}包含非本仓库进程，已跳过"
        return 1
    fi
    return 0
}

port_has_only_owned_listener() {
    local port="$1"
    local expected_cwd="$2"
    local command_marker="$3"
    local pid command_line cwd
    while IFS= read -r pid; do
        [ -n "$pid" ] || continue
        command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
        cwd="$(pid_cwd "$pid")"
        if [ "$cwd" != "$expected_cwd" ] || [[ "$command_line" != *"$command_marker"* ]]; then
            return 1
        fi
    done < <(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)
    return 0
}

ensure_runtime_dependencies_ready() {
    if ! is_tcp_open "$DB_HOST" "$DB_PORT"; then
        echo "❌ PostgreSQL 未监听（$DB_HOST:${DB_PORT}）；现有运行模式不自动启动"
        return 1
    fi
    echo "✅ PostgreSQL 已运行（$DB_HOST:${DB_PORT}）"
    if command -v curl >/dev/null 2>&1 && curl -fsS "${ES_URL:-http://localhost:9200}" >/dev/null 2>&1; then
        echo "✅ Elasticsearch 已运行"
    else
        echo "ℹ️  Elasticsearch 未就绪，相关全文检索功能可能不可用"
    fi
    return 0
}

if [ "$PREPARE_DEPENDENCIES" = "1" ]; then
    prepare_dependencies_only
    exit $?
fi

echo "🚀 启动本地开发环境..."

ensure_backend_venv || exit 1

unset DOCKER_ENV
export DOCKER_ENV=""

if [ ! -f ".env" ]; then
    if [ "$PROVISION" = "1" ] && [ -f ".env.example" ]; then
        echo "📄 复制 .env.example 为 .env"
        cp .env.example .env
    else
        echo "❌ .env 文件不存在；使用 --provision 初始化"
        exit 1
    fi
elif [ "$PROVISION" != "1" ]; then
    set -a
    # shellcheck source=/dev/null
    source ".env"
    set +a
fi
if [[ -n "${DATABASE_URL:-}" ]] && [[ "$DATABASE_URL" =~ postgresql[^:]*://([^:]+):([^@]*)@([^:]+):([0-9]+)/([^?]*) ]]; then
    DB_HOST="${BASH_REMATCH[3]}"
    DB_PORT="${BASH_REMATCH[4]}"
fi

if [ "$USE_DOCKER_DEPS" = "1" ]; then
    if [ "$PROVISION" != "1" ]; then
        echo "❌ --with-docker-deps 需要显式 --provision；现有运行模式不启动容器依赖"
        exit 1
    fi
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
                compose up -d db
                compose up -d es redis || echo "⚠️  容器 Redis 或 Elasticsearch 启动失败；相关能力可能不可用"

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
    if [ "$PROVISION" = "1" ]; then
        stop_conflicting_docker_deps_for_local_mode
        ensure_local_postgres_running || exit 1
        ensure_postgres_user_ready || exit 1
        ensure_local_elasticsearch_running || true
        ensure_pgvector_available || true
    else
        ensure_runtime_dependencies_ready || exit 1
    fi
fi

# Run alembic migrations and seed demo data when empty
ensure_db_migrated_and_seeded() {
    echo ""
    echo "📦 检查数据库迁移与演示数据..."
    local migrated=0
    local last_err=""
    for attempt in 1 2 3 4 5; do
        last_err=$(python -m alembic upgrade head 2>&1) && migrated=1 && break
        if [ "$attempt" -lt 5 ]; then
            echo "⏳ 迁移失败，${attempt}秒后重试 ($attempt/5)..."
            sleep "$attempt"
        fi
    done
    if [ "$migrated" != "1" ]; then
        echo "❌ 数据库迁移失败，未启动服务"
        echo "$last_err" | tail -15
        echo "💡 若数据库状态不一致，可新建空库: createdb market_intel_dev 并修改 .env 中 DATABASE_URL 的数据库名"
        return 1
    fi
    # Use the same database and project-seed contract as the template API.
    echo "📥 检查演示项目 demo_proj（不覆盖已有数据）..."
    bash "$SCRIPT_DIR/scripts/load_demo_proj_seed.sh"
}

if [ "$PROVISION" = "1" ]; then
    ensure_db_migrated_and_seeded
fi

if lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN -t >/dev/null; then
    echo ""
    echo "⚠️  端口${BACKEND_PORT}已被占用"

    DOCKER_CONTAINER=""
    if command -v docker >/dev/null 2>&1; then
        set +e
        DOCKER_CONTAINER=$(docker ps --format "{{.ID}}\t{{.Ports}}" 2>/dev/null | grep ":${BACKEND_PORT}->" | awk '{print $1}' | head -1)
        set -e
    fi

    if [ -n "$DOCKER_CONTAINER" ]; then
        echo "检测到Docker容器正在使用${BACKEND_PORT}端口（容器ID: ${DOCKER_CONTAINER}）"
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
            echo "🚨 --force 已启用，自动停止占用${BACKEND_PORT}端口的进程"
            stop_owned_port_listener "$BACKEND_PORT" "$SCRIPT_DIR" "uvicorn app.main:app" || exit 1
        elif [ "$NON_INTERACTIVE" = "1" ]; then
            echo "❌ --non-interactive 模式遇到端口冲突，退出"
            exit 1
        else
            read -p "是否要停止占用${BACKEND_PORT}端口的进程？(y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                stop_owned_port_listener "$BACKEND_PORT" "$SCRIPT_DIR" "uvicorn app.main:app" || exit 1
            else
                echo "请手动停止占用端口的进程或使用其他端口"
                exit 1
            fi
        fi
    fi
fi

if [ "$BACKEND_ONLY" != "1" ]; then
    mkdir -p "$MRW_LOCAL_STATE_DIR"
    ensure_modern_frontend_running || echo "⚠️  业务界面未就绪；API 继续启动"
    ensure_local_worker_running || echo "⚠️  本机任务 worker 未启动；API 继续启动"
fi

echo ""
if [ "$DEV_RELOAD" = "1" ]; then
    RELOAD_DESC="自动重载"
else
    RELOAD_DESC="低内存模式（无重载）"
fi

echo "✅ 启动后端服务（端口${BACKEND_PORT}，${RELOAD_DESC}）..."
echo "🔒 环境隔离：已清除DOCKER_ENV，使用localhost连接数据库服务"
echo "🌐 API文档：http://127.0.0.1:${BACKEND_PORT}/docs（本机）"
echo "📊 健康检查：http://127.0.0.1:${BACKEND_PORT}/api/v1/health"
echo "🎨 modern 前端：http://$FRONTEND_HOST:$FRONTEND_PORT"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
if [ "$DEV_RELOAD" = "1" ]; then
    DOCKER_ENV="" uvicorn app.main:app --reload --host "$BACKEND_HOST" --port "$BACKEND_PORT"
else
    DOCKER_ENV="" uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
fi
