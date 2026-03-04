# CV01~CV02 文档封口链准备：封口证据模板草案与迁移前置清单（2026-03-03）

更新时间：2026-03-03（PST）  
适用范围：`main/backend` 当前工作树与测试入口  
用途：用于执行 CV01（现状封口）与 CV02（迁移前封口）时，快速生成可复现证据包。

## 1. 当前代码与测试状态快照（已采集）

### 1.1 代码状态（工作树）

采集命令：

```bash
git status --short
```

当前结论（2026-03-03）：
- 工作树为 `dirty`，存在大量 `M`/`D`/`??`（包含 `main/backend/*` 与 `development/latest-dev-docs/*`）。
- 本轮封口文档应采用“证据时间戳 + 命令输出”口径，不以“干净工作树”作为前提。

### 1.2 测试状态（环境与执行）

采集命令：

```bash
python3 --version
python3 -m unittest discover -s main/backend/tests -p '*_unittest.py'
python3 -m pytest -q main/backend/tests
```

当前结论（2026-03-03）：
- 解释器：`Python 3.9.6`。
- `unittest`：执行到收集/导入阶段，`FAILED (errors=11, skipped=25)`。
- `pytest`：`1 skipped, 15 errors during collection`。
- 主要阻塞类型：
  - 依赖缺失：`fastapi`、`sqlalchemy`、`numpy`、`pydantic_settings`。
  - 版本语法不兼容：`dataclass(slots=True)` 与 `match` 语法在 Python 3.9 环境不兼容。
  - 模块导入链失败：`Document` from `app.models.entities` 导入失败。

## 2. CV01 封口证据模板（现状基线封口）

> 目标：在迁移动作开始前，固化“当前代码与测试现状”并可复验。

### 2.1 元数据模板

```md
# CV01 封口证据单
- Evidence ID:
- 记录时间（PST）:
- 记录人:
- 变更范围（目录/模块）:
- 基线分支/提交（可为空，若为 dirty 需标注）:
```

### 2.2 代码状态证据模板

```md
## Code Snapshot
- Command: `git status --short`
- Output Artifact: `artifacts/cv01/git_status_short.txt`
- 判定:
  - [ ] 工作树干净
  - [ ] 工作树非干净（需附“并行开发说明”）
- 并行开发说明（如适用）:
```

### 2.3 测试状态证据模板

```md
## Test Snapshot
- Python Runtime: `python3 --version`
- Unit/Unittest: `python3 -m unittest discover -s main/backend/tests -p '*_unittest.py'`
- Pytest Aggregate: `python3 -m pytest -q main/backend/tests`
- Output Artifacts:
  - `artifacts/cv01/unittest_discover.txt`
  - `artifacts/cv01/pytest_q.txt`
- 结果摘要:
  - passed:
  - failed:
  - skipped:
  - collect_error:
- 阻塞分组:
  - [ ] 依赖缺失
  - [ ] 解释器版本不兼容
  - [ ] 业务回归失败
  - [ ] 其他:
```

### 2.4 CV01 封口判定模板

```md
## CV01 Gate Decision
- Gate: `BASELINE_EVIDENCE_CAPTURED`
- Decision: `PASS | COND_PASS | FAIL`
- 条件（若 `COND_PASS`）:
- 下一步动作:
- 审核人:
```

## 3. CV02 封口证据模板（迁移前封口）

> 目标：在执行迁移（代码/数据/配置）前，确认前置条件、回滚路径、最小回归集合齐备。

### 3.1 元数据模板

```md
# CV02 迁移前封口证据单
- Evidence ID:
- 记录时间（PST）:
- 迁移主题:
- 目标环境:
- 风险级别（L/M/H）:
```

### 3.2 前置条件模板

```md
## Preconditions
- [ ] 迁移目标与边界已冻结（模块/表/API）
- [ ] 依赖安装方案明确（requirements/lock/docker image）
- [ ] Python 版本策略明确（建议 >=3.10）
- [ ] DB 备份/快照完成并有恢复演练记录
- [ ] 回滚脚本/步骤可执行
- [ ] 最小回归集合已定义并可一键执行
- [ ] 观察指标与告警阈值已定义
```

### 3.3 最小回归集模板（迁移前必须）

```md
## Minimal Regression Set
- Command Set:
  1. `python3 -m unittest discover -s main/backend/tests -p '*_unittest.py'`
  2. `python3 -m pytest -q main/backend/tests`
  3. `<domain smoke command>`
- Pass Criteria:
  - 关键入口：`health / process / ingest` 可用
  - 关键测试：无新增 collect error
  - 错误预算：迁移前后错误类型不扩散
```

### 3.4 CV02 封口判定模板

```md
## CV02 Gate Decision
- Gate: `MIGRATION_PREREQ_READY`
- Decision: `PASS | COND_PASS | FAIL`
- 未满足项:
- 缓释动作:
- 执行窗口:
- 回滚负责人:
```

## 4. 迁移前置清单（可执行版）

> 使用方式：逐项勾选，所有 P0 通过后才允许进入迁移动作。

### 4.1 P0（必须）

- [ ] `ENV-01`：运行时依赖已安装（`fastapi/sqlalchemy/numpy/pydantic_settings`）。
- [ ] `ENV-02`：解释器升级到兼容版本（建议 `Python 3.10+`，满足 `match` 与 `dataclass(slots=True)`）。
- [ ] `TEST-01`：`unittest discover` 不再出现导入级阻塞（collection/import hard fail 清零）。
- [ ] `TEST-02`：`pytest -q` 不再出现 collection error。
- [ ] `TEST-03`：关键业务回归（至少 `process + ingest + admin graph`）有可复跑记录。
- [ ] `ROLLBACK-01`：数据库备份与恢复步骤已验证一次。

### 4.2 P1（强建议）

- [ ] `DOC-01`：迁移范围与排除范围写入迁移单（避免并行误伤）。
- [ ] `OBS-01`：关键监控指标与日志关键字固化。
- [ ] `OPS-01`：迁移窗口与冻结窗口同步给协作方。

### 4.3 一键采证命令模板

```bash
# 建议在仓库根目录执行
mkdir -p artifacts/cv01 artifacts/cv02

git status --short > artifacts/cv01/git_status_short.txt
python3 --version > artifacts/cv01/python_version.txt
python3 -m unittest discover -s main/backend/tests -p '*_unittest.py' \
  > artifacts/cv01/unittest_discover.txt 2>&1 || true
python3 -m pytest -q main/backend/tests \
  > artifacts/cv01/pytest_q.txt 2>&1 || true

# 迁移前复采
python3 -m unittest discover -s main/backend/tests -p '*_unittest.py' \
  > artifacts/cv02/unittest_pre_migration.txt 2>&1 || true
python3 -m pytest -q main/backend/tests \
  > artifacts/cv02/pytest_pre_migration.txt 2>&1 || true
```

## 5. 当前风险登记（供 CV01/CV02 引用）

- `R-01 环境依赖缺失`：导致测试集无法进入业务断言阶段，封口结论偏向“环境阻塞”。
- `R-02 Python 版本偏低`：语法级不兼容使部分测试在收集阶段即失败。
- `R-03 工作树并行改动密集`：封口证据必须绑定时间戳和输出文件，避免误将并行改动归因于单一迁移任务。
- `R-04 导入链脆弱`：核心模型/设置模块导入失败会放大测试噪音，影响真实回归判读。

## 6. 本轮执行证据增量（2026-03-03 18:02 PST）

### 6.1 已完成验证（可直接引用）

- `SU06/US02`（Python 3.11）：
  - `main/backend/.venv311/bin/python -m pytest -q main/backend/tests/unit/test_single_url_ingest_unittest.py main/backend/tests/contract/test_ingest_response_contract_unittest.py main/backend/tests/core_business/test_resource_pool_core_contract.py main/backend/tests/integration/test_source_library_unified_search_single_url_integration_unittest.py`
  - 结果：`41 passed`
  - `main/backend/.venv311/bin/python -m pytest -q main/backend/tests/integration -k source_library`
  - 结果：`5 passed`
- `ST03`（后端名词密度链路）：
  - `main/backend/.venv311/bin/python -m pytest -q main/backend/tests/unit/test_noun_density_service_unittest.py`
  - 结果：`3 passed`
- `ST05`（回填报表脚本 dry-run）：
  - `python3 main/backend/scripts/backfill_time_window_density_report.py --dry-run --sample-size 20 --window-days 14`
  - 输出摘要：`rows=20`，`valid_time_ratio=0.9`，`duplicate_ratio=0.15`
- `ST06`（切主/回滚能力演练）：
  - `python3 main/backend/scripts/cutover_time_window_density_scheduler.py --dry-run --operator ST06`
  - `python3 main/backend/scripts/rollback_time_window_density_scheduler.py --dry-run --operator ST06`

### 6.2 豁免登记（本轮）

- `WAIVER-DOCKER-001`
  - 范围：`IP03` 的 `./scripts/docker-deploy.sh preflight`
  - 原因：当前环境缺少 `docker/compose`
  - 影响：不阻断 `CV01` 文档证据收口；阻断 `IP03` 封口判定
  - 解除条件：环境具备 `docker + compose` 后立即恢复执行 `IP03`
