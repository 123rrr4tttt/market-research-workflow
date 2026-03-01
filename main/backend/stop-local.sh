#!/bin/bash
# 停止本地开发环境脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

compose() {
    if command -v docker-compose >/dev/null 2>&1; then
        docker-compose "$@"
    elif docker compose version >/dev/null 2>&1; then
        docker compose "$@"
    else
        return 127
    fi
}

echo "🛑 停止本地开发环境..."

FRONTEND_PORT="${FRONTEND_PORT:-5173}"
FRONTEND_PID_FILE="/tmp/frontend-modern-dev.pid"
WORKER_PID_FILE="/tmp/celery-local-worker.pid"
USE_DOCKER_DEPS=0
WITH_LOCAL_WORKER=1

for arg in "$@"; do
    case "$arg" in
        --with-docker-deps)
            USE_DOCKER_DEPS=1
            ;;
        --with-local-worker)
            WITH_LOCAL_WORKER=1
            ;;
        --no-local-worker)
            WITH_LOCAL_WORKER=0
            ;;
    esac
done

# 停止后端服务
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    OPS_DIR="$(cd "$SCRIPT_DIR/../ops" && pwd)"
    DOCKER_BACKEND_RUNNING=""
    if [ -f "$OPS_DIR/docker-compose.yml" ] && docker info >/dev/null 2>&1; then
        set +e
        DOCKER_BACKEND_RUNNING="$(cd "$OPS_DIR" && compose ps -q backend 2>/dev/null)"
        set -e
    fi

    if [ -n "${DOCKER_BACKEND_RUNNING}" ]; then
        echo "检测到 Docker backend 占用 8000，停止容器 backend..."
        cd "$OPS_DIR"
        compose stop backend 2>/dev/null || true
        cd "$SCRIPT_DIR"
        echo "✅ Docker backend 已停止"
    else
        echo "停止本机后端服务（端口8000）..."
        lsof -ti:8000 | xargs kill -9 2>/dev/null || true
        sleep 1
        echo "✅ 本机后端服务已停止"
    fi
else
    echo "✅ 后端服务未运行"
fi

# 停止modern前端服务
if [ -f "$FRONTEND_PID_FILE" ]; then
    FRONTEND_PID="$(cat "$FRONTEND_PID_FILE" 2>/dev/null || true)"
    if [ -n "${FRONTEND_PID:-}" ] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
        echo "停止 modern 前端（PID $FRONTEND_PID）..."
        kill "$FRONTEND_PID" 2>/dev/null || true
        sleep 1
    fi
    rm -f "$FRONTEND_PID_FILE"
fi

if lsof -Pi :"$FRONTEND_PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "停止 modern 前端（端口$FRONTEND_PORT）..."
    lsof -ti:"$FRONTEND_PORT" | xargs kill -9 2>/dev/null || true
    sleep 1
    echo "✅ modern 前端已停止"
else
    echo "✅ modern 前端未运行"
fi

# 停止本机 celery worker（可选）
if [ "$WITH_LOCAL_WORKER" = "1" ]; then
    if [ -f "$WORKER_PID_FILE" ]; then
        WORKER_PID="$(cat "$WORKER_PID_FILE" 2>/dev/null || true)"
        if [ -n "${WORKER_PID:-}" ] && kill -0 "$WORKER_PID" >/dev/null 2>&1; then
            echo "停止本机 Celery worker（PID $WORKER_PID）..."
            kill "$WORKER_PID" 2>/dev/null || true
            sleep 1
        fi
        rm -f "$WORKER_PID_FILE"
        echo "✅ 本机 Celery worker 已停止"
    else
        echo "✅ 本机 Celery worker 未运行"
    fi
fi

# 停止数据库服务（可选，Docker依赖模式）
if [ "$USE_DOCKER_DEPS" = "1" ]; then
    OPS_DIR="$(cd "$SCRIPT_DIR/../ops" && pwd)"
    if [ -f "$OPS_DIR/docker-compose.yml" ]; then
        echo ""
        if docker info >/dev/null 2>&1; then
            echo "停止数据库服务（db, es, redis）..."
            cd "$OPS_DIR"
            compose stop db es redis 2>/dev/null || true
            cd "$SCRIPT_DIR"
            echo "✅ 数据库服务已停止"
        else
            echo "⚠️  Docker未运行，跳过数据库服务停止"
        fi
    fi
else
    echo "✅ 保持纯本机模式：不处理 Docker db/es/redis"
fi

echo ""
echo "✅ 所有服务已停止"
