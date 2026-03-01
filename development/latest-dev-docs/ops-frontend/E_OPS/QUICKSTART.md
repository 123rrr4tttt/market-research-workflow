# 快速启动指南

> 最后更新：2026-02 | 首次运行请复制 `backend/.env.example` 为 `backend/.env`

导航：
- [根索引](../INDEX.md)
- [Docker 启动指南](./ops-README.md)
- [frontend-modern 说明](../A_ARCHITECTURE/frontend-modern-README.md)

## ⚠️ 重要提示

本文档面向 GitHub 团队协作，所有命令均基于仓库根目录执行。

请先设置项目目录变量（按你的实际目录名修改）：

```bash
export PROJECT_DIR="main"
```

## 启动所有服务

```bash
cd "$PROJECT_DIR/ops"
./start-all.sh
```

这将自动启动：
- ✅ **主服务**：PostgreSQL, Elasticsearch, Redis, Backend API, Celery Worker

## 停止所有服务

```bash
cd "$PROJECT_DIR/ops"
./stop-all.sh
```

## 重启所有服务

```bash
cd "$PROJECT_DIR/ops"
./restart.sh
```

## 服务访问地址

启动成功后，可以通过以下地址访问：

### 主服务
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/api/v1/health

## 详细文档

更多详细信息请参考：`$PROJECT_DIR/ops/README.md`
