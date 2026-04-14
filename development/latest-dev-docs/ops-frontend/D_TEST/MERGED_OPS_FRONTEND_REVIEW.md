# MERGED Ops + Frontend Review

> Review date: 2026-03-01 (US/Pacific)
> Scope: `development/latest-dev-docs/ops-frontend`
> Goal: 校对命令可执行性与文档顺序，并补 README 入口

## 1) Reviewed docs

- `QUICKSTART.md`
- `ops-README.md`
- `frontend-modern-README.md`
- `frontend-modern-figma-sync-PULL_STATUS_2026-02-27.md`
- `index.md`
- `MERGED_OPS_FRONTEND.md`

## 2) Command executability check

### 2.1 Script/path checks (pass)

- `main/ops/start-all.sh` exists and executable (`-rwxr-xr-x`)
- `main/ops/stop-all.sh` exists and executable
- `main/ops/restart.sh` exists and executable
- `scripts/docker-deploy.sh` exists and executable
- `main/ops/docker-compose.yml` exists
- `main/frontend-modern/package.json` exists (`dev/build/lint/preview` scripts present)
- `main/backend/.env` and `main/backend/.env.example` both exist

### 2.2 Syntax checks (pass)

- `bash -n main/ops/start-all.sh`
- `bash -n main/ops/stop-all.sh`
- `bash -n main/ops/restart.sh`
- `bash -n scripts/docker-deploy.sh`

### 2.3 Environment/tooling checks

- `npm` available (`11.9.0`)
- `curl` available
- `lsof` available
- `docker` not found in current host environment
- `alembic` not found in current host environment

结论：文档中的脚本入口与路径有效；但涉及 `docker` / `docker compose` / `alembic` 的命令在当前主机环境无法直接执行，需要先安装 Docker（及相应容器/后端工具链）。

## 3) Document order sync

已将 `index.md` 调整为执行优先顺序：

1. `QUICKSTART.md`
2. `ops-README.md`
3. `frontend-modern-README.md`
4. `frontend-modern-figma-sync-PULL_STATUS_2026-02-27.md`
5. `MERGED_OPS_FRONTEND.md`
6. `MERGED_OPS_FRONTEND_REVIEW.md`

## 4) README entry links added

已在以下 README 类文件标题下补充统一入口一行：

- `ops-README.md`
- `frontend-modern-README.md`

链接目标：`./MERGED_OPS_FRONTEND_REVIEW.md`

## 5) Freshness notes

- 文档内时间戳包含 `2026-02-25`、`2026-02-27`、`2026-03-01`，与本次校对日期（`2026-03-01`）一致，无未来时间异常。
- `frontend-modern-figma-sync-PULL_STATUS_2026-02-27.md` 为状态快照文档，仍可保留原日期；后续若继续拉取节点，建议按同目录命名规则追加新状态文件。
