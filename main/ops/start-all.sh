#!/bin/bash
# 统一容器启动脚本 - 项目唯一的容器启动方式
# 启动主服务（数据库、Elasticsearch、Redis、后端API、Celery Worker）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

echo "🚀 统一容器启动脚本"
echo "===================="
echo ""
echo "这将启动当前独立项目的主服务："
echo "  ✅ PostgreSQL, Elasticsearch, Redis, Backend API, Celery Worker"
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
    if lsof -i :$port >/dev/null 2>&1; then
        echo "⚠️  警告: 端口 $port ($service) 已被占用"
        echo "   请检查是否有其他服务正在使用此端口"
        read -p "   是否继续？(y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

echo "🔍 检查端口占用..."
check_port 5432 "PostgreSQL"
check_port 9200 "Elasticsearch"
check_port 6379 "Redis"
check_port 8000 "Backend API"
echo "✅ 端口检查完成"
echo ""

# 停止现有服务（如果存在）
echo "🛑 停止现有服务..."
compose down 2>/dev/null || true
echo "✅ 清理完成"
echo ""

# 启动主服务
echo "📦 启动主服务..."
echo "   包括: PostgreSQL, Elasticsearch, Redis, Backend API, Celery Worker"
compose up -d

echo ""
echo "⏳ 等待主服务启动..."
sleep 10

echo ""
echo "📊 主服务状态:"
compose ps

echo ""
echo "⏳ 等待服务就绪（最多60秒）..."
MAX_WAIT=60
WAITED=0

while [ $WAITED -lt $MAX_WAIT ]; do
    if compose exec -T db pg_isready -U postgres >/dev/null 2>&1; then
        echo "✅ PostgreSQL 已就绪"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done

WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s http://localhost:9200 >/dev/null 2>&1; then
        echo "✅ Elasticsearch 已就绪"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done

WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if compose exec -T redis redis-cli ping >/dev/null 2>&1; then
        echo "✅ Redis 已就绪"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done

WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s http://localhost:8000/api/v1/health >/dev/null 2>&1; then
        echo "✅ Backend API 已就绪"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done

WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if compose ps celery-worker | grep -q "Up" 2>/dev/null; then
        echo "✅ Celery Worker 已启动"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done

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

echo -n "Backend API: "
if curl -s http://localhost:8000/api/v1/health >/dev/null 2>&1; then
    echo "✅ 健康"
    echo "   API 文档: http://localhost:8000/docs"
    echo "   健康检查: http://localhost:8000/api/v1/health"
else
    echo "⏳ 启动中..."
fi
echo ""

echo -n "Celery Worker: "
if compose ps celery-worker | grep -q "Up" 2>/dev/null; then
    echo "✅ 运行中"
    echo "   查看日志: docker compose logs -f celery-worker"
else
    echo "❌ 未运行"
    echo "   请检查日志: docker compose logs celery-worker"
fi
echo ""

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
