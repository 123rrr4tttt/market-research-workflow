# 信息收集工作流（market-intel）

> 最后更新：2026-02

多来源信息采集 → 结构化处理 → 可检索查询 → 可视化与运维。

**完整说明**：见 [`说明.md`](说明.md)

---

## 快速开始

```bash
export PROJECT_DIR="main"
cd "$PROJECT_DIR/ops"
./start-all.sh
```

停止：`./stop-all.sh`

**首次运行**：复制 `main/backend/.env.example` 为 `main/backend/.env`

**访问**：<http://localhost:8000/docs> | <http://localhost:8000/api/v1/health>

---

## 文档

| 文档 | 说明 |
|------|------|
| [说明.md](说明.md) | 项目说明（架构、目录、运行方式） |
| [main/QUICKSTART.md](main/QUICKSTART.md) | 快速启动 |
| [main/ops/README.md](main/ops/README.md) | Docker 运维 |
| [main/backend/README.local.md](main/backend/README.local.md) | 本地开发 |
| [main/backend/API接口文档.md](main/backend/API接口文档.md) | API 参考 |
