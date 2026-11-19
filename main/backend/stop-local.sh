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
FRONTEND_DIR="$(cd "$SCRIPT_DIR/../frontend-modern" && pwd)"
FRONTEND_PID_FILE="/tmp/frontend-modern-dev.pid"
WORKER_PID_FILE="/tmp/celery-local-worker.pid"
BACKEND_LAUNCHD_LABEL="com.mrw.successor-backend"
FRONTEND_LAUNCHD_LABEL="com.mrw.frontend-modern"
WORKER_LAUNCHD_LABEL="com.mrw.local-worker"
GUI_DOMAIN="gui/$(id -u)"
USE_DOCKER_DEPS=0
WITH_LOCAL_WORKER=1
LOCAL_ONLY=0

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
        --local-only)
            LOCAL_ONLY=1
            ;;
    esac
done

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
    local pid command_line cwd foreign_owner=0 stopped=0
    while IFS= read -r pid; do
        [ -n "$pid" ] || continue
        command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
        cwd="$(pid_cwd "$pid")"
        if [ "$cwd" = "$expected_cwd" ] && [[ "$command_line" == *"$command_marker"* ]]; then
            terminate_pid_gracefully "$pid" "端口${port}的" || return 1
            stopped=1
        else
            foreign_owner=1
        fi
    done < <(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)

    if [ "$foreign_owner" = "1" ]; then
        echo "⚠️ 端口${port}包含非本仓库进程，已跳过"
        return 1
    fi
    if [ "$stopped" = "1" ]; then
        echo "✅ 端口${port}的本仓库进程已停止"
    fi
    return 0
}

stop_launchd_backend() {
    if [ "$OSTYPE" = darwin ] && launchctl print "$GUI_DOMAIN/$BACKEND_LAUNCHD_LABEL" >/dev/null 2>&1; then
        launchctl bootout "$GUI_DOMAIN/$BACKEND_LAUNCHD_LABEL" >/dev/null 2>&1 || true
        for _ in $(seq 1 20); do
            if ! launchctl print "$GUI_DOMAIN/$BACKEND_LAUNCHD_LABEL" >/dev/null 2>&1; then
                break
            fi
            sleep 0.1
        done
        echo "✅ 本机后端 LaunchAgent 已停止（${BACKEND_LAUNCHD_LABEL}）"
        return 0
    fi
    return 1
}

stop_launchd_service() {
    local label="$1"
    local description="$2"
    if [ "$OSTYPE" = darwin ] && launchctl print "$GUI_DOMAIN/$label" >/dev/null 2>&1; then
        launchctl bootout "$GUI_DOMAIN/$label" >/dev/null 2>&1 || true
        echo "✅ 本机${description} LaunchAgent 已停止（${label}）"
        return 0
    fi
    return 1
}

# 停止后端服务
if stop_launchd_backend; then
    :
elif lsof -nP -iTCP:8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    OPS_DIR="$(cd "$SCRIPT_DIR/../ops" && pwd)"
    DOCKER_BACKEND_RUNNING=""
    if [ -f "$OPS_DIR/docker-compose.yml" ] && docker info >/dev/null 2>&1; then
        set +e
        DOCKER_BACKEND_RUNNING="$(cd "$OPS_DIR" && compose ps -q backend 2>/dev/null)"
        set -e
    fi

    if [ -n "${DOCKER_BACKEND_RUNNING}" ]; then
        if [ "$LOCAL_ONLY" = "1" ]; then
            echo "检测到 Docker backend 占用 8000，--local-only 已启用，跳过容器 backend"
        else
            echo "检测到 Docker backend 占用 8000，停止容器 backend..."
            cd "$OPS_DIR"
            compose stop backend 2>/dev/null || true
            cd "$SCRIPT_DIR"
            echo "✅ Docker backend 已停止"
        fi
    else
        echo "停止本机后端服务（端口8000）..."
        if stop_owned_port_listener 8000 "$SCRIPT_DIR" "uvicorn app.main:app"; then
            echo "✅ 本机后端服务已停止"
        else
            echo "⚠️ 8000 端口存在未识别进程，未停止"
        fi
    fi
else
    echo "✅ 后端服务未运行"
fi

# 停止modern前端服务
if stop_launchd_service "$FRONTEND_LAUNCHD_LABEL" "modern 前端"; then
    :
elif [ -f "$FRONTEND_PID_FILE" ]; then
    FRONTEND_PID="$(cat "$FRONTEND_PID_FILE" 2>/dev/null || true)"
    if [ -n "${FRONTEND_PID:-}" ] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
        echo "停止 modern 前端（PID ${FRONTEND_PID}）..."
        kill "$FRONTEND_PID" 2>/dev/null || true
        sleep 1
    fi
    rm -f "$FRONTEND_PID_FILE"
fi

if lsof -nP -iTCP:"$FRONTEND_PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "停止 modern 前端（端口${FRONTEND_PORT}）..."
    if stop_owned_port_listener "$FRONTEND_PORT" "$FRONTEND_DIR" "vite"; then
        echo "✅ modern 前端已停止"
    else
        echo "⚠️ 前端端口存在未识别进程，未停止"
    fi
else
    echo "✅ modern 前端未运行"
fi

# 停止本机 celery worker（可选）
if [ "$WITH_LOCAL_WORKER" = "1" ]; then
    if stop_launchd_service "$WORKER_LAUNCHD_LABEL" "Celery worker"; then
        :
    elif [ -f "$WORKER_PID_FILE" ]; then
        WORKER_PID="$(cat "$WORKER_PID_FILE" 2>/dev/null || true)"
        if [ -n "${WORKER_PID:-}" ] && kill -0 "$WORKER_PID" >/dev/null 2>&1; then
            echo "停止本机 Celery worker（PID ${WORKER_PID}）..."
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
