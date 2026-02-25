#!/bin/bash
# 本地开发环境启动脚本

set -e  # 遇到错误立即退出（除明确使用set +e的地方）

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DEV_RELOAD="${DEV_RELOAD:-1}"
if [ "${1:-}" = "--low-memory" ]; then
    DEV_RELOAD=0
fi

echo "🚀 启动本地开发环境..."

# 检查虚拟环境
if [ ! -d ".venv311" ]; then
    echo "❌ 虚拟环境不存在，请先创建：python3.11 -m venv .venv311"
    exit 1
fi

# 激活虚拟环境
source .venv311/bin/activate

# 确保本地启动环境隔离：清除DOCKER_ENV环境变量
# 这样可以确保使用localhost而不是容器服务名
unset DOCKER_ENV
export DOCKER_ENV=""

# 检查.env文件
if [ ! -f ".env" ]; then
    echo "⚠️  .env文件不存在，将使用默认配置（localhost）"
    echo "💡 提示：可以复制 .env.local.example 为 .env.local 并修改配置"
fi

# 启动数据库服务（如果需要）
OPS_DIR="$(cd "$SCRIPT_DIR/../ops" && pwd)"
if [ -f "$OPS_DIR/docker-compose.yml" ]; then
    echo ""
    echo "📦 检查数据库服务状态..."
    
    # 检查Docker是否运行
    if ! docker info >/dev/null 2>&1; then
        echo "⚠️  Docker未运行，跳过数据库服务启动"
        echo "💡 提示：如需使用数据库，请先启动Docker并运行：cd $OPS_DIR && docker-compose up -d db es redis"
    else
        cd "$OPS_DIR"
        
        # 检查服务是否已运行
        set +e  # 允许错误
        DB_RUNNING=$(docker-compose ps -q db 2>/dev/null | wc -l | tr -d ' ')
        ES_RUNNING=$(docker-compose ps -q es 2>/dev/null | wc -l | tr -d ' ')
        REDIS_RUNNING=$(docker-compose ps -q redis 2>/dev/null | wc -l | tr -d ' ')
        set -e  # 恢复错误检查
        
        if [ "$DB_RUNNING" -eq 0 ] || [ "$ES_RUNNING" -eq 0 ] || [ "$REDIS_RUNNING" -eq 0 ]; then
            echo "🚀 启动数据库服务（db, es, redis）..."
            docker-compose up -d db es redis
            
            # 等待服务就绪
            echo "⏳ 等待数据库服务就绪..."
            sleep 3
            
            # 检查PostgreSQL是否就绪
            MAX_RETRIES=15
            RETRY=0
            set +e  # 允许错误
            while [ $RETRY -lt $MAX_RETRIES ]; do
                if docker-compose exec -T db pg_isready -U postgres >/dev/null 2>&1; then
                    echo "✅ PostgreSQL已就绪"
                    break
                fi
                RETRY=$((RETRY + 1))
                if [ $RETRY -lt $MAX_RETRIES ]; then
                    echo "   等待PostgreSQL... ($RETRY/$MAX_RETRIES)"
                    sleep 1
                fi
            done
            set -e
            
            # 检查Elasticsearch是否就绪
            RETRY=0
            set +e  # 允许错误
            while [ $RETRY -lt $MAX_RETRIES ]; do
                if curl -s http://localhost:9200 >/dev/null 2>&1; then
                    echo "✅ Elasticsearch已就绪"
                    break
                fi
                RETRY=$((RETRY + 1))
                if [ $RETRY -lt $MAX_RETRIES ]; then
                    echo "   等待Elasticsearch... ($RETRY/$MAX_RETRIES)"
                    sleep 1
                fi
            done
            set -e
            
            echo "✅ 数据库服务启动完成"
        else
            echo "✅ 数据库服务已在运行"
        fi
        
        cd "$SCRIPT_DIR"
    fi
else
    echo "⚠️  未找到docker-compose.yml，跳过数据库服务启动"
fi

# 检查端口是否被占用
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo ""
    echo "⚠️  端口8000已被占用"
    
    # 检查是否是Docker容器占用的端口
    set +e
    DOCKER_CONTAINER=$(docker ps --format "{{.ID}}\t{{.Ports}}" | grep ":8000->" | awk '{print $1}' | head -1)
    set -e
    
    if [ -n "$DOCKER_CONTAINER" ]; then
        echo "检测到Docker容器正在使用8000端口（容器ID: $DOCKER_CONTAINER）"
        echo "💡 提示：如果要在本地运行，请先停止Docker容器："
        echo "   cd $OPS_DIR && docker-compose stop backend"
        read -p "是否要停止Docker backend容器？(y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            cd "$OPS_DIR"
            docker-compose stop backend 2>/dev/null || true
            cd "$SCRIPT_DIR"
            sleep 2
        else
            echo "请手动停止占用端口的进程或使用其他端口"
            exit 1
        fi
    else
        read -p "是否要停止占用8000端口的进程？(y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            lsof -ti:8000 | xargs kill -9 2>/dev/null || true
            sleep 1
        else
            echo "请手动停止占用端口的进程或使用其他端口"
            exit 1
        fi
    fi
fi

echo ""
if [ "$DEV_RELOAD" = "1" ]; then
    RELOAD_DESC="自动重载"
else
    RELOAD_DESC="低内存模式（无重载）"
fi

echo "✅ 启动后端服务（端口8000，${RELOAD_DESC}）..."
echo "🔒 环境隔离：已清除DOCKER_ENV，使用localhost连接数据库服务"
echo "📝 日志文件：/tmp/uvicorn.log"
echo "🌐 API文档：http://localhost:8000/docs"
echo "📊 健康检查：http://localhost:8000/api/v1/health"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

# 启动服务（明确设置DOCKER_ENV为空，确保使用localhost）
if [ "$DEV_RELOAD" = "1" ]; then
    DOCKER_ENV="" uvicorn app.main:app --reload --port 8000
else
    DOCKER_ENV="" uvicorn app.main:app --port 8000
fi

