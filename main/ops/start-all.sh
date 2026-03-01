#!/bin/bash
# 统一容器启动脚本 - 项目唯一的容器启动方式
# 启动主服务（数据库、Elasticsearch、Redis、后端API、Celery Worker）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

NON_INTERACTIVE=false
FORCE=false
MAX_WAIT=60
PROFILE_ARGS=()
SERVICE_ARGS=()

usage() {
    cat <<'EOF'
Usage: ./start-all.sh [options]

Options:
  --non-interactive       非交互模式，端口冲突时直接失败退出
  --force                 非交互模式，端口冲突时继续执行
  --profile <name>        透传给 docker compose --profile，可重复
  --services <list>       仅启动指定服务，逗号分隔（如 "db,backend"）
  -h, --help              显示帮助
EOF
}

parse_services() {
    local raw="$1"
    local item
    local old_ifs="$IFS"
    IFS=',' read -r -a items <<<"$raw"
    IFS="$old_ifs"
    for item in "${items[@]}"; do
        item="${item//[[:space:]]/}"
        if [ -n "$item" ]; then
            SERVICE_ARGS+=("$item")
        fi
    done
}

profile_selected() {
    local target="$1"
    local p
    for p in "${PROFILE_ARGS[@]}"; do
        if [ "$p" = "$target" ]; then
            return 0
        fi
    done
    return 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --non-interactive)
            NON_INTERACTIVE=true
            shift
            ;;
        --force)
            FORCE=true
            NON_INTERACTIVE=true
            shift
            ;;
        --profile)
            [ $# -ge 2 ] || { echo "❌ --profile 需要参数"; usage; exit 2; }
            PROFILE_ARGS+=("$2")
            shift 2
            ;;
        --services)
            [ $# -ge 2 ] || { echo "❌ --services 需要参数"; usage; exit 2; }
            parse_services "$2"
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

COMPOSE_FLAGS=()
for profile in "${PROFILE_ARGS[@]}"; do
    COMPOSE_FLAGS+=(--profile "$profile")
done

compose() {
    if command -v docker-compose >/dev/null 2>&1; then
        docker-compose "${COMPOSE_FLAGS[@]}" "$@"
    elif docker compose version >/dev/null 2>&1; then
        docker compose "${COMPOSE_FLAGS[@]}" "$@"
    else
        echo "❌ 未找到 docker-compose 或 docker compose"
        return 127
    fi
}

service_selected() {
    local target="$1"
    local s
    if [ ${#SERVICE_ARGS[@]} -eq 0 ]; then
        case "$target" in
            frontend-modern) profile_selected modern-ui && return 0 || return 1 ;;
            backend-test) profile_selected test && return 0 || return 1 ;;
            scrapyd) profile_selected scrapyd && return 0 || return 1 ;;
        esac
        return 0
    fi
    for s in "${SERVICE_ARGS[@]}"; do
        if [ "$s" = "$target" ]; then
            return 0
        fi
    done
    return 1
}

wait_for() {
    local name="$1"
    local cmd="$2"
    local waited=0
    while [ "$waited" -lt "$MAX_WAIT" ]; do
        if eval "$cmd"; then
            echo "✅ $name 已就绪"
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    echo "❌ $name 在 ${MAX_WAIT} 秒内未就绪"
    return 1
}

echo "🚀 统一容器启动脚本"
echo "===================="
echo ""
echo "这将启动当前独立项目的主服务："
echo "  ✅ PostgreSQL, Elasticsearch, Redis, Backend API, Celery Worker"
echo "  ℹ️ 可选服务: Scrapyd（需 --profile scrapyd）"
echo ""

# 检查 Docker 是否运行
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker 未运行，正在尝试启动 Docker Desktop..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        open -a Docker 2>/dev/null || true
    fi
    echo "⏳ 请等待 Docker Desktop 完全启动（约30秒）"
    echo "   然后重新运行此脚本: ./start-all.sh"
    exit 1
fi

echo "✅ Docker 已运行"
echo ""

# 检查端口占用
check_port() {
    local port=$1
    local service=$2
    if lsof -i :"$port" >/dev/null 2>&1; then
        echo "⚠️  警告: 端口 $port ($service) 已被占用"
        if [ "$FORCE" = true ]; then
            echo "   --force 已启用，忽略端口冲突继续执行"
            return 0
        fi
        if [ "$NON_INTERACTIVE" = true ]; then
            echo "   --non-interactive 模式下遇到端口冲突，退出"
            exit 1
        fi
        echo "   请检查是否有其他服务正在使用此端口"
        read -p "   是否继续？(y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

echo "🔍 检查端口占用..."
service_selected db && check_port 5432 "PostgreSQL"
service_selected es && check_port 9200 "Elasticsearch"
service_selected redis && check_port 6379 "Redis"
service_selected backend && check_port 8000 "Backend API"
service_selected scrapyd && check_port 6800 "Scrapyd"
echo "✅ 端口检查完成"
echo ""

# 停止现有服务（如果存在）
if [ ${#SERVICE_ARGS[@]} -eq 0 ]; then
    echo "🛑 停止现有服务..."
    compose down 2>/dev/null || true
    echo "✅ 清理完成"
    echo ""
else
    echo "ℹ️ 检测到 --services，跳过全量 down 以避免影响未指定服务"
    echo ""
fi

# 启动主服务
echo "📦 启动主服务..."
echo "   包括: PostgreSQL, Elasticsearch, Redis, Backend API, Celery Worker"
if [ ${#SERVICE_ARGS[@]} -gt 0 ]; then
    compose up -d "${SERVICE_ARGS[@]}"
else
    compose up -d
fi

echo ""
echo "⏳ 等待主服务启动..."
sleep 10

echo ""
echo "📊 主服务状态:"
compose ps

echo ""
echo "⏳ 等待服务就绪（最多60秒）..."
FAILED=0
if service_selected db; then
    wait_for "PostgreSQL" "compose exec -T db pg_isready -U postgres >/dev/null 2>&1" || FAILED=1
fi
if service_selected es; then
    wait_for "Elasticsearch" "curl -sf http://localhost:9200 >/dev/null 2>&1" || FAILED=1
fi
if service_selected redis; then
    wait_for "Redis" "compose exec -T redis redis-cli ping >/dev/null 2>&1" || FAILED=1
fi
if service_selected backend; then
    wait_for "Backend API" "curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1" || FAILED=1
fi
if service_selected celery-worker; then
    wait_for "Celery Worker" "compose ps celery-worker | grep -q 'Up' 2>/dev/null" || FAILED=1
fi
if service_selected scrapyd; then
    wait_for "Scrapyd" "curl -sf http://localhost:6800/daemonstatus.json >/dev/null 2>&1" || FAILED=1
fi

echo ""
echo "📊 所有服务状态汇总"
echo "===================="
echo ""
echo "主服务:"
compose ps
echo ""

echo "🏥 服务健康检查"
echo "================"
echo ""

if service_selected backend; then
    echo -n "Backend API: "
    if curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1; then
        echo "✅ 健康"
        echo "   API 文档: http://localhost:8000/docs"
        echo "   健康检查: http://localhost:8000/api/v1/health"
    else
        echo "⏳ 启动中..."
    fi
    echo ""
fi

if service_selected celery-worker; then
    echo -n "Celery Worker: "
    if compose ps celery-worker | grep -q "Up" 2>/dev/null; then
        echo "✅ 运行中"
        echo "   查看日志: docker compose logs -f celery-worker"
    else
        echo "❌ 未运行"
        echo "   请检查日志: docker compose logs celery-worker"
    fi
    echo ""
fi

if service_selected scrapyd; then
    echo -n "Scrapyd: "
    if curl -sf http://localhost:6800/daemonstatus.json >/dev/null 2>&1; then
        echo "✅ 运行中"
        echo "   状态接口: http://localhost:6800/daemonstatus.json"
    else
        echo "❌ 未就绪"
        echo "   请检查日志: docker compose logs scrapyd"
    fi
    echo ""
fi

if [ "$FAILED" -ne 0 ]; then
    echo "❌ 启动完成但有服务在超时内未就绪"
    exit 1
fi

echo "✅ 所有服务启动完成！"
echo ""
echo "📝 常用命令:"
echo "   查看所有日志: cd ops && docker compose logs -f"
echo "   查看后端日志: cd ops && docker compose logs -f backend"
echo "   停止所有服务: cd ops && ./stop-all.sh"
echo ""
echo "🌐 服务访问地址:"
echo "   Backend API: http://localhost:8000/docs"
echo ""
