#!/bin/bash
# 统一容器停止脚本 - 停止当前独立项目服务

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

REMOVE_ORPHANS=true
WITH_VOLUMES=false
PROFILE_ARGS=()
SERVICE_ARGS=()

usage() {
    cat <<'EOF'
Usage: ./stop-all.sh [options]

Options:
  --remove-orphans        停止时删除孤儿容器（默认开启）
  --no-remove-orphans     停止时保留孤儿容器
  --volumes               同时删除数据卷（危险操作）
  --profile <name>        透传给 docker compose --profile，可重复
  --services <list>       兼容参数（down 为项目级操作，会忽略服务列表）
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

while [ $# -gt 0 ]; do
    case "$1" in
        --remove-orphans)
            REMOVE_ORPHANS=true
            shift
            ;;
        --no-remove-orphans)
            REMOVE_ORPHANS=false
            shift
            ;;
        --volumes)
            WITH_VOLUMES=true
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

echo "🛑 统一容器停止脚本"
echo "===================="
echo ""
echo "这将停止项目主服务："
echo "  ✅ PostgreSQL, Elasticsearch, Redis, Backend API, Celery Worker"
echo ""

if ! docker info >/dev/null 2>&1; then
    echo "⚠️  Docker 未运行，无需停止服务"
    exit 0
fi

echo "📦 停止主服务..."
if [ -f "docker-compose.yml" ]; then
    if [ ${#SERVICE_ARGS[@]} -gt 0 ]; then
        echo "ℹ️ --services 参数已接收，但 docker compose down 是项目级操作，将忽略服务列表"
    fi
    DOWN_ARGS=(down)
    if [ "$REMOVE_ORPHANS" = true ]; then
        DOWN_ARGS+=(--remove-orphans)
    fi
    if [ "$WITH_VOLUMES" = true ]; then
        DOWN_ARGS+=(-v)
    fi
    compose "${DOWN_ARGS[@]}"
    echo "✅ 主服务已停止"
else
    echo "⚠️  主服务 docker-compose.yml 不存在，跳过"
fi

echo ""
echo "✅ 所有服务已停止！"
echo ""
echo "💡 提示:"
if [ "$WITH_VOLUMES" = true ]; then
    echo "   已使用 --volumes 删除数据卷"
    echo "   (⚠️  数据卷已被移除，数据库数据会丢失)"
else
    echo "   如需删除数据卷，可加参数: ./stop-all.sh --volumes"
    echo "   (⚠️  这会删除所有数据库数据)"
fi
echo ""
