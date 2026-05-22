# 快速启动指南

> 最后更新：2026-05-22 | 首次运行请复制 `main/backend/.env.example` 为 `main/backend/.env`

导航：
- [根索引](../INDEX.md)
- [Docker 启动指南](./ops-README.md)
- [frontend-modern 说明](../A_ARCHITECTURE/frontend-modern-README.md)

## 重要提示

本文档面向 GitHub 团队协作，所有命令均基于仓库根目录执行。

## 推荐入口：launcher-first

优先通过平台脚本启动 Docker Web Launcher：

```bash
bash scripts/platform-macos.sh docker-start
```

这会启动 `launcher-agent` 与 `launcher-ui`，然后打开 Docker Web Launcher，默认地址为：

- Docker Web Launcher: http://127.0.0.1:5176

查看当前 Docker 应用服务状态：

```bash
bash scripts/platform-macos.sh docker-status
```

直接启动完整 modern-ui 栈：

```bash
bash scripts/platform-macos.sh docker-full-start
```

停止 Docker 应用服务：

```bash
bash scripts/platform-macos.sh docker-stop
```

重启 Docker 应用服务：

```bash
bash scripts/platform-macos.sh docker-restart
```

## 服务访问地址

启动成功后，可以通过以下地址访问：

- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/api/v1/health
- **Modern 前端**: http://localhost:5174
- **Docker Web Launcher**: http://127.0.0.1:5176

## 兼容入口

旧的 `main/ops/start-all.sh`、`stop-all.sh`、`restart.sh` 仍保留为兼容入口，但不再是本文档的首选启动路径：

```bash
cd main/ops
./start-all.sh
```

## 详细文档

更多详细信息请参考：`main/ops/README.md` 与仓库根目录下的 `scripts/platform-macos.sh`。
