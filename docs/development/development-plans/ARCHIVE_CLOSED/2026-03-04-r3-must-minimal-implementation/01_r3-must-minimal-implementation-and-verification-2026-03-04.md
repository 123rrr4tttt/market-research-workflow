<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-04-r3-must-minimal-implementation/01_r3-must-minimal-implementation-and-verification-2026-03-04.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-04-r3-must-minimal-implementation/01_r3-must-minimal-implementation-and-verification-2026-03-04.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# R3 Must 最小实现与验证（2026-03-04）

## 0. 输入与目标
- 任务时间：2026-03-04（PST）
- 参考输入：
  - `/Users/wangyiliang/Desktop/openclaw/docs/reference-pool/2026-03-04-scout-r1/reference_pack.md`
  - `/Users/wangyiliang/Desktop/openclaw/docs/reference-pool/2026-03-04-scout-r1/research_note.md`
- 本次目标（R3）：
  1) repo-level 映射
  2) Must 最小实现（质量门禁、失败阻断、回滚、可观测、安全）
  3) 建立参考包到改动的映射
  4) 执行验证并记录结果

## 1. Repo-level 映射（关键目录/文件）

### 1.1 关键目录
- `.github/workflows/`：CI 流水线定义。
- `main/backend/`：后端主应用、迁移、测试、脚本。
- `main/backend/tests/`：测试金字塔资产（`unit/integration/contract/e2e`）。
- `main/backend/tests/quarantine/`：flaky 隔离清单。
- `main/backend/app/main.py`：请求链路、`X-Request-Id`、`/metrics`、健康检查。
- `main/ops/`：docker compose、启动停止重启脚本、运维说明。
- `scripts/docker-deploy.sh`：统一部署入口（start/stop/restart/health/preflight）。
- `development/latest-dev-docs/`：开发文档入口与索引。

### 1.2 现有测试/CI/可观测/发布回滚资产
- 测试：`main/backend/tests/README.md` + `main/backend/pytest.ini` + `scripts/test-standardize.sh`。
- CI：`.github/workflows/backend-tests.yml`（含 unit/integration/coverage/contract/e2e/docker/flaky 相关任务）。
- 可观测：`main/backend/app/main.py`（`X-Request-Id`、`/metrics`、`/api/v1/health`、`/api/v1/health/deep`）+ `main/ops/docker-compose.yml` healthcheck。
- 发布/回滚：已有 start/stop/restart；缺标准化“检查点+回滚”命令。

## 2. Must 最小实现（本次落地）

### 2.1 质量工程 + CI 失败阻断
- 新增阻断式工作流：`.github/workflows/r3-must-gates.yml`
- 固化测试金字塔门禁：`unit -> integration -> contract`（deterministic lane）
- 固化覆盖率阻断：`scripts/check_coverage_thresholds.py`（core=100, other=20）

### 2.2 安全门禁（SAST/依赖/secret）
- 同工作流新增：
  - `pip-audit`（依赖漏洞，阻断）
  - `bandit`（SAST 基线，阻断）
  - `gitleaks`（secret scan，阻断）

### 2.3 可回滚
- 新增：`main/ops/rollback.sh`
  - `snapshot`：生成检查点（compose/env/git head）
  - `list`：列检查点
  - `rollback [id]`：恢复检查点，默认恢复 latest 并重启
- 接入统一入口：`scripts/docker-deploy.sh`
  - 新命令：`checkpoint`、`rollback`、`rollback-list`
- 运维文档补充：`main/ops/README.md`

### 2.4 可观测
- 本仓已有 request_id + metrics + health/deep health 基线；本次不重复造轮子。
- 通过 R3 文档将可观测路径与验证命令纳入任务闭环。

## 3. reference_pack / research_note -> 具体改动映射

| 参考项 | 落地要求 | 本次改动 |
|---|---|---|
| reference_pack B.Must | 测试金字塔 + CI 失败阻断 | `.github/workflows/r3-must-gates.yml` 增加阻断式 `unit/integration/contract` 与 coverage gate |
| reference_pack B.Tests-Metrics | 关键覆盖率与回归质量可量化 | 在同一 gate 中执行 `check_coverage_thresholds.py` |
| reference_pack D.Must | SAST/依赖/secret scanning 入 CI | `.github/workflows/r3-must-gates.yml` 增加 `bandit`、`pip-audit`、`gitleaks` |
| reference_pack E.Must | 回滚路径可演练 | `main/ops/rollback.sh` + `scripts/docker-deploy.sh` 新增 `checkpoint/rollback/rollback-list` |
| reference_pack C.Must | 关键链路可观测（request_id/health/metrics） | 复用既有 `main/backend/app/main.py`；文档中明确入口与验证命令 |
| research_note B | 单元/集成/契约优先于全量 E2E | 新增 PR 阶段阻断 gate 覆盖前三层 |
| research_note D | 安全左移与持续扫描 | 新增安全阻断 job（三类扫描） |
| research_note E | 小批量、可回滚交付 | 新增检查点化 rollback 命令并接入统一发布入口 |

## 4. 验证命令与结果

| 命令 | 结果 |
|---|---|
| `bash -n scripts/docker-deploy.sh` | PASS |
| `bash -n main/ops/rollback.sh` | PASS |
| `main/ops/rollback.sh snapshot` | PASS（生成检查点：`20260304-002000`） |
| `main/ops/rollback.sh list` | PASS（可见最新检查点） |
| `main/ops/rollback.sh rollback --no-restart` | PASS（恢复 latest，不触发重启） |
| `cd main/backend && python3 -m pytest tests/e2e/test_health_smoke_e2e.py tests/e2e/test_deep_health_smoke_e2e.py -q` | FAIL（Python 3.9 环境，类型注解 `str | None` 不兼容） |
| `cd main/backend && python3.11 -m pytest tests/e2e/test_health_smoke_e2e.py tests/e2e/test_deep_health_smoke_e2e.py -q` | FAIL（Python 3.11 环境缺少 pytest） |
| `python3.11 -m venv .venv_r3 && .venv_r3/bin/pip install -r main/backend/requirements.txt pytest && cd main/backend && ../../.venv_r3/bin/python -m pytest tests/e2e/test_health_smoke_e2e.py tests/e2e/test_deep_health_smoke_e2e.py -q` | PASS（`2 passed, 13 warnings`） |

## 5. 风险与后续
- `pip-audit`/`bandit` 初次接入可能暴露历史安全债，属于预期阻断；建议按严重度建立修复 SLA。
- 当前 rollback 是“配置与环境检查点回滚”；若需要镜像级/DB 级回滚，应在后续迭代补充。
