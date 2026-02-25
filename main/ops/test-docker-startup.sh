#!/bin/bash
# Docker启动测试脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🧪 Docker启动测试"
echo "=================="
echo ""

# 检查Docker是否运行
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker未运行，请先启动Docker Desktop"
    exit 1
fi
echo "✅ Docker已运行"
echo ""

# 检查配置文件
echo "📋 检查配置文件..."
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ docker-compose.yml 不存在"
    exit 1
fi
echo "✅ docker-compose.yml 存在"

# 验证配置
echo "🔍 验证docker-compose配置..."
docker-compose config >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ docker-compose配置有效"
else
    echo "❌ docker-compose配置无效"
    exit 1
fi
echo ""

# 检查启动脚本
echo "📝 检查启动脚本..."
ENTRYPOINT_SCRIPT="../backend/docker-entrypoint.sh"
if [ ! -f "$ENTRYPOINT_SCRIPT" ]; then
    echo "❌ 启动脚本不存在: $ENTRYPOINT_SCRIPT"
    exit 1
fi

if [ ! -x "$ENTRYPOINT_SCRIPT" ]; then
    echo "⚠️  启动脚本不可执行，正在修复..."
    chmod +x "$ENTRYPOINT_SCRIPT"
fi
echo "✅ 启动脚本存在且可执行"
echo ""

# 停止现有服务（如果存在）
echo "🛑 停止现有服务..."
docker-compose down 2>/dev/null || true
echo ""

# 启动服务
echo "🚀 启动服务..."
echo "   这将启动: PostgreSQL, Elasticsearch, Redis, Backend"
echo "   预计需要1-2分钟..."
echo ""

docker-compose up -d

echo ""
echo "⏳ 等待服务启动..."
sleep 5

# 检查服务状态
echo ""
echo "📊 服务状态:"
docker-compose ps

echo ""
echo "📋 检查服务健康状态..."
echo ""

# 检查PostgreSQL
echo -n "PostgreSQL: "
if docker-compose exec -T db pg_isready -U postgres >/dev/null 2>&1; then
    echo "✅ 健康"
else
    echo "❌ 未就绪"
fi

# 检查Elasticsearch
echo -n "Elasticsearch: "
if curl -s http://localhost:9200 >/dev/null 2>&1; then
    echo "✅ 健康"
else
    echo "❌ 未就绪"
fi

# 检查Redis
echo -n "Redis: "
if docker-compose exec -T redis redis-cli ping >/dev/null 2>&1; then
    echo "✅ 健康"
else
    echo "❌ 未就绪"
fi

# 等待Backend启动
echo ""
echo "⏳ 等待Backend服务启动（最多60秒）..."
MAX_WAIT=60
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s http://localhost:8000/api/v1/health >/dev/null 2>&1; then
        echo "✅ Backend已启动"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
    echo -n "."
done
echo ""

# 检查Backend健康状态
echo ""
echo "🏥 Backend健康检查:"
HEALTH_RESPONSE=$(curl -s http://localhost:8000/api/v1/health 2>/dev/null || echo "{}")
if echo "$HEALTH_RESPONSE" | grep -q "ok"; then
    echo "✅ 基础健康检查通过"
    echo "   响应: $HEALTH_RESPONSE"
else
    echo "❌ 健康检查失败"
    echo "   响应: $HEALTH_RESPONSE"
fi

# 深度健康检查
echo ""
echo "🔍 深度健康检查:"
DEEP_HEALTH=$(curl -s http://localhost:8000/api/v1/health/deep 2>/dev/null || echo "{}")
echo "   响应: $DEEP_HEALTH"

# 检查日志
echo ""
echo "📋 最近的后端日志（最后10行）:"
echo "----------------------------------------"
docker-compose logs --tail=10 backend
echo "----------------------------------------"

echo ""
echo "✅ 测试完成！"
echo ""
echo "📝 有用的命令:"
echo "   查看所有日志: docker-compose logs -f"
echo "   查看后端日志: docker-compose logs -f backend"
echo "   停止服务: docker-compose down"
echo "   重启服务: docker-compose restart"
echo "   访问API文档: http://localhost:8000/docs"
echo ""

