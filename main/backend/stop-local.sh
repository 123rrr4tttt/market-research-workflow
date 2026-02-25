#!/bin/bash
# 停止本地开发环境脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🛑 停止本地开发环境..."

# 停止后端服务
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo "停止后端服务（端口8000）..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    sleep 1
    echo "✅ 后端服务已停止"
else
    echo "✅ 后端服务未运行"
fi

# 停止数据库服务（可选）
OPS_DIR="$(cd "$SCRIPT_DIR/../ops" && pwd)"
if [ -f "$OPS_DIR/docker-compose.yml" ]; then
    echo ""
    read -p "是否要停止数据库服务（db, es, redis）？(y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cd "$OPS_DIR"
        if docker info >/dev/null 2>&1; then
            echo "停止数据库服务..."
            docker-compose stop db es redis 2>/dev/null || true
            echo "✅ 数据库服务已停止"
        else
            echo "⚠️  Docker未运行，跳过数据库服务停止"
        fi
        cd "$SCRIPT_DIR"
    fi
fi

echo ""
echo "✅ 所有服务已停止"

