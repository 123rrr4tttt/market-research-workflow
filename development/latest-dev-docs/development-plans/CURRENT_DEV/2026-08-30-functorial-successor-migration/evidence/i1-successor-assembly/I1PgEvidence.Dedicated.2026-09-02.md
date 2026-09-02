# I1 全量 PostgreSQL 专用库证据报告（Dedicated 重跑，2026-09-02）

- 工作树：`/Users/wangyiliang/.codex/manual-worktrees/mrw-functorial-successor-p0`
- 分支：`codex/functorial-successor-p0`；HEAD：`35ca039c59d2efae8038a678995e8a0812032e43`；git status 48 行 dirty，本轮未 commit/push/reset/clean
- 执行目录：`main/backend`
- 解释器：`python3.11` 3.11.15；pytest 8.4.2；SQLAlchemy 2.0.35；psycopg2 2.9.9
- PostgreSQL：localhost:5432，PostgreSQL 18.3（Homebrew），Unix socket `/tmp`；本机用户 `wangyiliang` 超管连接
- 本轮只写本报告；未修改生产代码；临时运行日志在 `/tmp/i1_pg_dedicated_logs.DCfcnZ/`
- 基线库（运行前已存在，未删除）：`codex_p0c_full_chain_test`、`mrw_p0b_rereview_test_01a0504c`
- 基线角色：无 `mrw_*` / `codex_*` 角色

## 结果摘要

- 非 PG 全量对照：exit 0，`1370 passed / 117 skipped / 0 failed / 3 warnings`（63.12s），与 `I1TestEvidence.v1.json` 记录的 `1370/117/0` 一致；此前 `I1PgEvidence.I1.2026-09-02.md` 的 6 个失败本轮均不复现
- I1 PG 专用库逐文件重跑：38 个 PG opt-in 文件，38/38 exit 0，合计 `344 passed / 0 skipped / 0 failed / 0 errors`
- teardown：38 次运行每次 pre/post `pg_database` 均等于基线；最终库清单等于基线，新增残留库 0；`mrw_p0d_capacity_runner` 角色运行后不存在
- p0d capacity 标准 runner 路径已实测不可行：runner 固定库名 `mrw_successor_validation_<token>` 不含 `test|testing|ci`，被 fixture 拒绝；本轮以手动 socket 专用库完成该套件（5 passed）

## 1 非 PG 全量对照

命令（未设置 `SUCCESSOR_*` 环境变量）：

```text
env -u SUCCESSOR_TEST_DATABASE_URL -u SUCCESSOR_P3_C5_DATABASE_URL PYTHONDONTWRITEBYTECODE=1 python3.11 -m pytest tests/successor_runtime -q -p no:cacheprovider
```

- rc=0；`1370 passed, 117 skipped, 3 warnings in 63.12s`；无 failed、无 errors
- 与上一轮对照差异：`I1PgEvidence.I1.2026-09-02.md` 记录 `1364 passed / 117 skipped / 6 failed`；本轮 6 个失败全部消失
- 根因核实：3 个 I1 micro exact-binding 失败源于 `main/frontend-modern/src/lib/api/domains/successor-runtime.ts` 哈希漂移；当前文件 SHA-256 为 `cfd390ee67a183e9052a802e79ed0e33da492c3bafb7bdbf27c757a500901436`，`C9_2FrontendMilestone.v1.json`（mtime 07:16:07，晚于文件 mtime 07:02:37）已绑定同一哈希，重绑成立。P1P3 semantic-movement 3 个失败本轮由 `test_semantic_movement_generator.py` 全绿覆盖，说明持久工件与当前生成器输入已一致

## 2 PG opt-in 文件集定义

- 范围：`main/backend/tests/successor_runtime` 下 fixture 依赖 `SUCCESSOR_TEST_DATABASE_URL` 的测试文件
- 共 38 个 = 上一轮 34 个 `*postgres*.py` 测试文件 + 4 个非 `_postgres` 命名但消费 PG fixture/env 的文件：`test_p0b_uow_blob.py`、`test_p0c_production_composition_root.py`、`test_p0c_typed_submission_payloads.py`、`test_p0d_cw12_rolling_deploy.py`
- 未纳入：`test_p0c_boundaries.py`（仅 monkeypatch 测 guard，无 live DB）、`test_p5_c1_evidence_generator.py`（纯生成器测试）、`test_successor_postgres_validation_runner.py`（mock runner，无 live DB）

## 3 PG 专用库逐文件结果（38 个文件，串行）

统一建库/删库命令（每文件替换 `<db>` 与 `<file>`）：

```text
psql -h localhost -d postgres -q -c 'CREATE DATABASE "<db>"'
SUCCESSOR_TEST_DATABASE_URL=postgresql+psycopg2://localhost/<db> SUCCESSOR_P3_C5_DATABASE_URL= PYTHONDONTWRITEBYTECODE=1 python3.11 -m pytest -q -p no:cacheprovider <file>
psql -h localhost -d postgres -q -c 'DROP DATABASE IF EXISTS "<db>" WITH (FORCE)'
```

库名规则：`mrw_i1_<file_basename>_test`（如 `mrw_i1_test_p0b_postgres_integration_test`），全部满足各 fixture 的 `test|testing|ci` 命名 guard。p0d capacity 例外：URL 为 `postgresql+psycopg2:///<db>?host=/tmp`（Unix socket，fixture 强制）。每文件运行前/后 `pg_database` 过滤 `^(mrw_|codex_)` 均等于基线，故 teardown 每行均为 0 残留。

| 文件 | exit | passed | skipped | failed | errors | 数据库/说明 |
|---|---:|---:|---:|---:|---:|---|
| test_c7_movement_admission_postgres.py | 0 | 50 | 0 | 0 | 0 | URL 库 + 内部建/删 `mrw_c7_movement_admission_test` |
| test_c8_movement_closure_postgres.py | 0 | 23 | 0 | 0 | 0 | URL 库 + 内部建/删 `mrw_c8_movement_closure_test` |
| test_c8_research_artifact_delivery_bridge_postgres.py | 0 | 2 | 0 | 0 | 0 | URL 库 + 内部建/删 `mrw_c8_delivery_bridge_test` |
| test_c9_movement_closure_backend_postgres.py | 0 | 38 | 0 | 0 | 0 | URL 库 + 内部建/删 `mrw_c9_movement_closure_test` |
| test_c9_projection_sources_postgres.py | 0 | 17 | 0 | 0 | 0 | URL 库 + 内部建/删 `mrw_c9_projection_sources_test` |
| test_c9_typed_source_evolution_postgres.py | 0 | 5 | 0 | 0 | 0 | URL 库 + 内部建/删 `mrw_c9_typed_source_evolution_test` |
| test_p0b_postgres_integration.py | 0 | 18 | 0 | 0 | 0 | 专用库直接使用 |
| test_p0b_uow_blob.py | 0 | 36 | 0 | 0 | 0 | 专用库直接使用（含 PG smoke，非 PG 下为 35 passed/1 skipped） |
| test_p0c_delivery_recovery_postgres.py | 0 | 4 | 0 | 0 | 0 | 专用库直接使用（`mrw_p0c_postgres_acceptance` schema 建/删） |
| test_p0c_full_runtime_chain_postgres.py | 0 | 12 | 0 | 0 | 0 | 专用库直接使用 |
| test_p0c_postgres_activation.py | 0 | 4 | 0 | 0 | 0 | 纯测试文件，专用库无写入 |
| test_p0c_postgres_lifecycle.py | 0 | 9 | 0 | 0 | 0 | 纯测试文件，专用库无写入 |
| test_p0c_postgres_reconciliation.py | 0 | 4 | 0 | 0 | 0 | 纯测试文件，专用库无写入 |
| test_p0c_production_composition_root.py | 0 | 3 | 0 | 0 | 0 | 专用库直接使用（含 1 个 real-postgres 用例） |
| test_p0c_submission_postgres.py | 0 | 7 | 0 | 0 | 0 | 专用库直接使用 |
| test_p0c_two_nodes_postgres.py | 0 | 5 | 0 | 0 | 0 | 专用库直接使用 |
| test_p0c_typed_submission_payloads.py | 0 | 3 | 0 | 0 | 0 | 专用库直接使用（含 1 个 real-postgres 用例） |
| test_p0c_vertical_specimen_postgres.py | 0 | 3 | 0 | 0 | 0 | 专用库直接使用 |
| test_p0d_capacity_postgres.py | 0 | 5 | 0 | 0 | 0 | socket 专用库；fixture 建/删非超管角色 `mrw_p0d_capacity_runner` |
| test_p0d_cw11_postgres.py | 0 | 1 | 0 | 0 | 0 | 专用库直接使用 |
| test_p0d_cw12_rolling_deploy.py | 0 | 2 | 0 | 0 | 0 | 专用库直接使用 |
| test_p0d_gap_successor_postgres.py | 0 | 8 | 0 | 0 | 0 | 专用库直接使用 |
| test_p0d_research_projection_postgres.py | 0 | 2 | 0 | 0 | 0 | 专用库直接使用 |
| test_p0d_runtime_projection_postgres.py | 0 | 4 | 0 | 0 | 0 | 专用库直接使用 |
| test_p2_c2_1_canary_postgres.py | 0 | 16 | 0 | 0 | 0 | 专用库直接使用 |
| test_p3_c2_1_rehydration_postgres.py | 0 | 13 | 0 | 0 | 0 | 专用库直接使用 |
| test_p3_c2_23_runtime_canary_postgres.py | 0 | 1 | 0 | 0 | 0 | URL 库 + 内部建/删 `mrw_p3_c2_worker_test` |
| test_p3_c2_4_postgres.py | 0 | 2 | 0 | 0 | 0 | URL 库 + 内部建/删 `mrw_p3_c2_worker_test` |
| test_p3_c3_canary_postgres.py | 0 | 7 | 0 | 0 | 0 | URL 库 + 内部建/删 `mrw_p3_c3_worker_test` |
| test_p3_c4_4_postgres.py | 0 | 3 | 0 | 0 | 0 | URL 库 + 内部建/删 `mrw_p3_c4_worker_test` |
| test_p3_c4_5_runtime_postgres.py | 0 | 3 | 0 | 0 | 0 | URL 库 + 内部建/删 `mrw_p3_c4_worker_test` |
| test_p3_c5_2_reconciliation_postgres.py | 0 | 5 | 0 | 0 | 0 | 专用库直接使用（未设 worker URL） |
| test_p3_c5_3_projection_postgres.py | 0 | 4 | 0 | 0 | 0 | 专用库直接使用（未设 worker URL） |
| test_p3_c6_runtime_canary_postgres.py | 0 | 4 | 0 | 0 | 0 | 专用库直接使用（2 warnings） |
| test_p3_c6_worker_postgres.py | 0 | 6 | 0 | 0 | 0 | 专用库直接使用（schema `mrw_p3_c6_worker_test`） |
| test_p3_shared_idempotency_postgres.py | 0 | 2 | 0 | 0 | 0 | 专用库直接使用 |
| test_p4_c7_6_postgres.py | 0 | 4 | 0 | 0 | 0 | URL 库 + 内部建/删 `mrw_p4_c7_worker_test` |
| test_p5_c1_slice_acceptance_postgres.py | 0 | 9 | 0 | 0 | 0 | URL 库 + 内部随机库 `mrw_c1_slice_acceptance_test_<hex>` |

合计：`344 passed / 0 skipped / 0 failed / 0 errors`；38/38 exit 0。

## 4 p0d capacity 标准 runner 路径尝试

直接使用 socket 专用库已完成该套件（5 passed，见上表）。`scripts/run_successor_postgres_validation.py` 标准路径也实际尝试过，结果为不可行：

1. guard 复现（不建库，fixture 在连接前拒绝）：

```text
SUCCESSOR_TEST_DATABASE_URL=postgresql+psycopg2:///mrw_successor_validation_0123456789abcdef?host=/tmp python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime/test_p0d_capacity_postgres.py
```

精确错误：`Failed: refusing non-test database 'mrw_successor_validation_0123456789abcdef'`（`p0d_capacity_fixture.py:78`），2 passed / 3 errors，rc=1。

2. runner 实测（临时 admin 库 `mrw_i1_runner_admin_test`，跑完已删）：

```text
python3.11 scripts/run_successor_postgres_validation.py --database-url "postgresql+psycopg2://wangyiliang@/mrw_i1_runner_admin_test?host=/tmp" -- python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime/test_p0d_capacity_postgres.py
```

返回 JSON 要点：`status=FAIL`、`exit_code=1`、`database_name=mrw_successor_validation_f616898369aa5909`、`role_name=mrw_successor_validation_f616898369aa5909`、`socket_only=True`、`admin_superuser=True`、`child_returncode=1`、`created_database=True`、`dropped_database=True`、`issues=[{"code": "CHILD_VALIDATION_FAILED", "message": "child command returned 1"}]`；运行后无残留库/角色。

环境要求（p0d capacity fixture 强制）：Unix socket（`url.host` 必须为空）、库名含 `test|testing|ci`、空 public 表与空 `mrw_p0d_capacity_*` schema、超管 admin 时创建非超管角色 `mrw_p0d_capacity_runner` 并在 teardown 删除。runner 固定库名 `mrw_successor_validation_<token>` 不含 `test|testing|ci`，与 fixture guard 结构不兼容，因此标准路径对该套件不可行；本轮以手动 socket 专用库完成，不伪造通过。

## 5 与既有记录差异

### 5.1 非 PG 对照

| 记录 | passed | skipped | failed |
|---|---:|---:|---:|
| `I1TestEvidence.v1.json`（历史） | 1370 | 117 | 0 |
| `I1PgEvidence.I1.2026-09-02.md`（上一轮） | 1364 | 117 | 6 |
| 本轮 Dedicated 重跑 | 1370 | 117 | 0 |

上一轮 6 个失败本轮均不复现：3 个 I1 micro exact-binding 已由 `C9_2FrontendMilestone.v1.json` 重绑到当前 `successor-runtime.ts` 哈希；3 个 P1P3 semantic-movement 工件漂移已被当前生成器/持久工件一致状态覆盖（`test_semantic_movement_generator.py` 全绿）。

### 5.2 PG 逐文件（上一轮 mandated `postgres` URL vs 本轮专用库）

上一轮 34 个文件（`postgres` URL）为 `187 passed / 0 skipped / 0 failed / 113 errors`：16 个 exit 0，18 个因专用 test 库 guard 报 errors。本轮同 34 个文件在专用库下 `300 passed / 0 skipped / 0 failed / 0 errors`（187+113=300，旧 113 errors 全部转为 passed，旧 6 个部分 passed 保留）；新增 4 个文件 44 passed，合计 344。

关键变化示例：

- `test_p0b_postgres_integration.py`：旧 18 errors → 本轮 18 passed
- `test_p2_c2_1_canary_postgres.py`：旧 3 passed / 13 errors → 本轮 16 passed
- `test_p0d_capacity_postgres.py`：旧 2 passed / 3 errors（guard 拒绝）→ 本轮 socket 专用库 5 passed
- `test_p3_c2_1_rehydration_postgres.py`：旧 1 passed / 12 errors → 本轮 13 passed
- `test_p0c_full_runtime_chain_postgres.py`：旧 12 errors → 本轮 12 passed
- 16 个旧 exit-0 文件计数全部保持一致（如 c7=50、c9 backend=38、p5c1=9）

上一轮未纳入的 4 个文件本轮补齐：`test_p0b_uow_blob.py` 36、`test_p0c_production_composition_root.py` 3、`test_p0c_typed_submission_payloads.py` 3、`test_p0d_cw12_rolling_deploy.py` 2。

## 6 风险与边界

1. 共享工作树存在并发写入：上一轮观察到的 `successor-runtime.ts` / P1P3 工件漂移已在更晚的证据文件（07:16）重绑后消失；当前哈希与绑定一致，但本报告只证明本轮快照下全绿，不排除后续并发改动再次引入漂移。
2. teardown 0 仅覆盖本轮：38 次运行前后库清单一致、最终无 `mrw_*`/`codex_*` 新增角色；两个基线库为运行前遗留，本轮未删除（无授权）。
3. 38/38 全绿是本地专用库运行证据，不构成 provider 证明、线上运行、生产验收或 03/04 主线整合结论；guard 通过不等于运行时/权威性完成。
4. `run_successor_postgres_validation.py` 对 p0d capacity 结构不兼容（固定库名无 test 标记），需扩展 runner 支持 test 命名专用库或维持手动 socket 专用库路径；本报告不提出修改方案。
