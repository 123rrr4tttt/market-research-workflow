#!/bin/bash
# Docker 启动自检脚本（含 preflight/端口/健康检查）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "$SCRIPT_DIR"

WITH_SCRAPYD=false
MAX_WAIT=90

usage() {
    cat <<'USAGE'
Usage: ./test-docker-startup.sh [options]

Options:
  --with-scrapyd      启用 scrapyd profile 并检查其健康状态
  --max-wait <sec>    单项健康检查最大等待秒数（默认 90）
  -h, --help          显示帮助
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        --with-scrapyd)
            WITH_SCRAPYD=true
            shift
            ;;
        --max-wait)
            [ $# -ge 2 ] || { echo "❌ --max-wait 需要参数"; usage; exit 2; }
            MAX_WAIT="$2"
            shift 2
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

COMPOSE_FLAGS=()
if [ "$WITH_SCRAPYD" = true ]; then
    COMPOSE_FLAGS+=(--profile scrapyd)
fi

compose_run() {
    compose "${COMPOSE_FLAGS[@]}" "$@"
}

check_port() {
    local port="$1"
    local name="$2"
    if lsof -i :"$port" >/dev/null 2>&1; then
        echo "❌ 端口冲突: $name 使用端口 $port"
        return 1
    fi
    echo "✅ 端口可用: $name ($port)"
}

wait_for() {
    local name="$1"
    local cmd="$2"
    local waited=0
    while [ "$waited" -lt "$MAX_WAIT" ]; do
        if eval "$cmd"; then
            echo "✅ $name 健康"
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    echo "❌ $name 在 ${MAX_WAIT}s 内未就绪"
    return 1
}

echo "🧪 Docker 启动自检"
echo "===================="
echo ""

if [ ! -f "docker-compose.yml" ]; then
    echo "❌ docker-compose.yml 不存在"
    exit 1
fi

echo "🔎 运行 preflight..."
if [ "$WITH_SCRAPYD" = true ]; then
    "${ROOT_DIR}/scripts/docker-deploy.sh" preflight --profile scrapyd
else
    "${ROOT_DIR}/scripts/docker-deploy.sh" preflight
fi
echo "✅ preflight 通过"
echo ""

echo "🔍 检查端口占用..."
check_port 5432 "PostgreSQL"
check_port 9200 "Elasticsearch"
check_port 6379 "Redis"
check_port 8000 "Backend API"
if [ "$WITH_SCRAPYD" = true ]; then
    check_port 6800 "Scrapyd"
fi
echo ""

ENTRYPOINT_SCRIPT="../backend/docker-entrypoint.sh"
if [ ! -f "$ENTRYPOINT_SCRIPT" ]; then
    echo "❌ 启动脚本不存在: $ENTRYPOINT_SCRIPT"
    exit 1
fi
if [ ! -x "$ENTRYPOINT_SCRIPT" ]; then
    chmod +x "$ENTRYPOINT_SCRIPT"
fi

if [ "$WITH_SCRAPYD" = true ]; then
    echo "📦 启动服务: 核心服务 + scrapyd(profile)"
else
    echo "📦 启动服务: 核心服务"
fi
compose_run down --remove-orphans >/dev/null 2>&1 || true
compose_run up -d

echo ""
echo "📊 服务状态"
compose_run ps

echo ""
echo "⏳ 健康检查（每项最多 ${MAX_WAIT}s）"
FAILED=0
wait_for "PostgreSQL" "compose_run exec -T db pg_isready -U postgres >/dev/null 2>&1" || FAILED=1
wait_for "Elasticsearch" "curl -sf http://localhost:9200 >/dev/null 2>&1" || FAILED=1
wait_for "Redis" "compose_run exec -T redis redis-cli ping >/dev/null 2>&1" || FAILED=1
wait_for "Backend API" "curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1" || FAILED=1
wait_for "Celery Worker" "compose_run ps celery-worker | grep -q 'Up' >/dev/null 2>&1" || FAILED=1
if [ "$WITH_SCRAPYD" = true ]; then
    wait_for "Scrapyd" "curl -sf http://localhost:6800/daemonstatus.json >/dev/null 2>&1" || FAILED=1
fi

echo ""
echo "🏥 API 健康响应"
HEALTH_RESPONSE=$(curl -s http://localhost:8000/api/v1/health 2>/dev/null || echo "{}")
DEEP_HEALTH=$(curl -s http://localhost:8000/api/v1/health/deep 2>/dev/null || echo "{}")
echo "health: $HEALTH_RESPONSE"
echo "health/deep: $DEEP_HEALTH"
if [ "$WITH_SCRAPYD" = true ]; then
    SCRAPYD_STATUS=$(curl -s http://localhost:6800/daemonstatus.json 2>/dev/null || echo "{}")
    echo "scrapyd: $SCRAPYD_STATUS"
fi

echo ""
echo "📋 最近日志（backend / celery-worker）"
compose_run logs --tail=10 backend || true
compose_run logs --tail=10 celery-worker || true
if [ "$WITH_SCRAPYD" = true ]; then
    compose_run logs --tail=10 scrapyd || true
fi

if [ "$FAILED" -ne 0 ]; then
    echo ""
    echo "❌ 启动自检失败"
    exit 1
fi

echo ""
echo "✅ 启动自检通过"
