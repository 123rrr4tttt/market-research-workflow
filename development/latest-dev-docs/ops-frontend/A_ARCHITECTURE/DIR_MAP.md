# Legacy Directory Map (Pre-Restructure)

> 更新日期：2026-03-01 (PST)
> 作用：记录 `ops-frontend` 重构前的目录结构与职责边界（历史存档）。

## 目录结构

```text
ops-frontend/
├── A_INDEX/
│   ├── index.md
│   ├── QUICKSTART.md
│   ├── ops-README.md
│   ├── frontend-modern-README.md
│   └── DIR_MAP.md
├── B_MERGED/
│   └── MERGED_OPS_FRONTEND.md
├── C_REVIEW/
│   └── MERGED_OPS_FRONTEND_REVIEW.md
└── D_SOURCE/
    └── frontend-modern-figma-sync-PULL_STATUS_2026-02-27.md
```

## 文件职责映射

| 路径 | 角色 | 说明 |
|---|---|---|
| `A_INDEX/index.md` | 导航入口 | A_INDEX 总索引与建议阅读顺序 |
| `A_INDEX/QUICKSTART.md` | 快速执行 | 最短路径的启动/停止/重启命令 |
| `A_INDEX/ops-README.md` | 运维说明 | Docker 启动细节、健康检查、排障 |
| `A_INDEX/frontend-modern-README.md` | 前端说明 | modern 前端开发、容器运行、核心 API |
| `B_MERGED/MERGED_OPS_FRONTEND.md` | 合并草案 | 跨文档归并内容 |
| `C_REVIEW/MERGED_OPS_FRONTEND_REVIEW.md` | 评审记录 | 对合并草案与索引文档的复核结果 |
| `D_SOURCE/frontend-modern-figma-sync-PULL_STATUS_2026-02-27.md` | 原始来源 | Figma 同步状态原始记录 |

## 推荐阅读路径（重构后）

1. [INDEX.md](../INDEX.md)
2. [QUICKSTART.md](../E_OPS/QUICKSTART.md)
3. [ops-README.md](../E_OPS/ops-README.md)
4. [frontend-modern-README.md](./frontend-modern-README.md)
5. [MERGED_OPS_FRONTEND_REVIEW.md](../G_REVIEW/MERGED_OPS_FRONTEND_REVIEW.md)
