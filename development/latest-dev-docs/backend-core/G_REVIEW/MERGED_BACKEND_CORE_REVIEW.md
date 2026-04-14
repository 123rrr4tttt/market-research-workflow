# backend-core 文档合并校对与时效性同步

> 生成时间：2026-03-01（PST）  
> 范围：`development/latest-dev-docs/backend-core`（仅本目录文档落盘）

## 1. 校对目标

- 校对文档日期是否与当前项目状态一致
- 校对模块命名/接口命名是否与当前代码一致
- 校对脚本路径是否与当前仓库路径一致

## 2. 结论摘要

- 文档目录已完成一次镜像（见 `index.md`，生成于 2026-03-01），但仍存在若干“时效性偏差”。
- 主要偏差集中在：
  - 顶层文档更新时间仍写 `2026-02`
  - 接口模块统计与路由清单未覆盖 2026-03-01 后新增接口
  - 个别脚本/测试路径已迁移，文档仍保留旧路径

## 3. 详细核对结果

### 3.1 日期一致性

- 现状：
  - `README.md`、`README.local.md`、`API接口文档.md`、`docs/README.md`、`docs/接口层调查文档.backend-core.md` 顶部均为 `最后更新：2026-02`
  - `index.md` 生成时间为 `2026-03-01 07:27:25 PST`
  - `docs/INGEST_CHAIN_EVIDENCE_MATRIX_2026-03-01.backend-core.md`、`docs/INGEST_CHAIN_TASKBOARD_2026-03-01.backend-core.md` 已包含 2026-03-01 证据
- 判定：`部分不一致`（目录内存在 2026-03-01 新证据，但总览文档仍停留在 2026-02）

### 3.2 模块命名与路由时效性

- 当前代码（`main/backend/app/api/__init__.py`）已注册 `19` 个 APIRouter 模块，包含 `resource_pool`。
- `docs/接口层调查文档.backend-core.md` 仍写“模块数 18”，且模块表未纳入 `resource_pool`，存在时效性偏差。
- `docs/接口层调查文档.backend-core.md` 将 `project_customization.py` 的前缀写为 `/project_customization`；当前代码前缀为 `/project-customization`（`main/backend/app/api/project_customization.py`）。
- `docs/API_ROUTE_INVENTORY_2026-02-27.backend-core.md` 的路由清单总数为 `135`；按当前代码静态比对，新增接口至少包含：
  - `POST /api/v1/ingest/graph/structured-search`
  - `POST /api/v1/projects/auto-create`
- 判定：`不一致`（模块统计、前缀命名、路由清单存在落后）

### 3.3 脚本路径与测试路径

- 已确认存在且可用：
  - `scripts/docker-deploy.sh`
  - `scripts/local-deploy.sh`
  - `scripts/platform-macos.sh`
- 路径偏差：
  - `README.local.md` 写为 `ops/docker-compose.yml`，当前仓库实际为 `main/ops/docker-compose.yml`
  - `docs/INGEST_CHAIN_EVIDENCE_MATRIX_2026-03-01.backend-core.md` 引用：
    - `main/backend/tests/test_project_key_policy_unittest.py`
    - `main/backend/tests/test_ingest_baseline_matrix_unittest.py`
    - `main/backend/tests/test_frontend_modern_entry_baseline_unittest.py`
  - 上述测试文件当前位于 `main/backend/tests/integration/` 子目录（已迁移）
- 判定：`部分不一致`

## 4. 建议同步动作（下一轮）

1. 将目录内总览文档顶部“最后更新”统一推进到 `2026-03-01`（或更晚真实日期）。
2. 更新 `docs/接口层调查文档.backend-core.md`：
   - 模块数由 18 改为 19
   - 补入 `resource_pool` 模块
   - 修正 `project-customization` 路由前缀
3. 重新生成 `docs/API_ROUTE_INVENTORY_*.backend-core.md`，纳入 2026-03-01 后新增路由。
4. 修正文档中的旧路径引用：
   - `ops/docker-compose.yml` -> `main/ops/docker-compose.yml`
   - `main/backend/tests/test_*.py` -> `main/backend/tests/integration/test_*.py`

## 5. 校对说明

- 本次仅在 `development/latest-dev-docs/backend-core` 范围内落盘，不回滚或触碰其他目录改动。
- 核对依据来自仓库当前文件状态（截至 2026-03-01）。 
