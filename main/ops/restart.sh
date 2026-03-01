#!/bin/bash
# Docker 重启脚本 - 使用统一启动脚本重启所有服务

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

usage() {
    cat <<'EOF'
Usage: ./restart.sh [options]

Start options (透传给 start-all.sh):
  --non-interactive
  --force
  --profile <name>
  --services <list>

Stop options (透传给 stop-all.sh):
  --remove-orphans
  --no-remove-orphans
  --volumes

Common:
  -h, --help
EOF
}

START_ARGS=()
STOP_ARGS=()

while [ $# -gt 0 ]; do
    case "$1" in
        --non-interactive|--force)
            START_ARGS+=("$1")
            shift
            ;;
        --profile)
            [ $# -ge 2 ] || { echo "❌ --profile 需要参数"; usage; exit 2; }
            START_ARGS+=("$1" "$2")
            STOP_ARGS+=("$1" "$2")
            shift 2
            ;;
        --services)
            [ $# -ge 2 ] || { echo "❌ --services 需要参数"; usage; exit 2; }
            START_ARGS+=("$1" "$2")
            STOP_ARGS+=("$1" "$2")
            shift 2
            ;;
        --remove-orphans|--no-remove-orphans|--volumes)
            STOP_ARGS+=("$1")
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

echo "🔄 Docker 服务重启"
echo "=================="
echo ""
echo "⚠️  注意: 此脚本将使用统一启动脚本重启所有服务"
echo ""

if [ -f "./stop-all.sh" ]; then
    echo "🛑 停止所有服务..."
    ./stop-all.sh "${STOP_ARGS[@]}"
else
    echo "⚠️  stop-all.sh 不存在，使用传统方式停止..."
    if command -v docker-compose >/dev/null 2>&1; then
        docker-compose down 2>/dev/null || true
    else
        docker compose down 2>/dev/null || true
    fi
fi

echo ""
echo "⏳ 等待服务完全停止..."
sleep 3

if [ -f "./start-all.sh" ]; then
    echo "🚀 启动所有服务..."
    ./start-all.sh "${START_ARGS[@]}"
else
    echo "❌ start-all.sh 不存在，请确保统一启动脚本已创建"
    exit 1
fi

echo ""
echo "✅ 重启完成！"
echo ""
echo "💡 提示:"
echo "   启动服务: ./start-all.sh"
echo "   停止服务: ./stop-all.sh"
echo "   重启服务: ./restart.sh"
