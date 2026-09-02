# AllLines 全量 PostgreSQL 专用库证据报告（2026-09-02）

- 工作树：`/Users/wangyiliang/.codex/manual-worktrees/mrw-functorial-successor-p0`
- 分支：`codex/functorial-successor-p0`；HEAD：`38acdee8862af0971ca063507b8355812894fbce`
- 运行前 dirty 行数：106（`git status --porcelain`）；本轮仅新增本报告，未 commit/push/reset/clean
- 执行目录：`main/backend`；解释器：`/opt/homebrew/bin/python3.11`（Python 3.11.15）；pytest 8.4.2；SQLAlchemy 2.0.35；psycopg2 2.9.9
- PostgreSQL：localhost:5432，PostgreSQL 18.3（Homebrew）；本机超管用户连接；运行日志目录 `/tmp/pg_all_lines_logs.12L3bV/`
- 基线库（保留未删）：`codex_p0c_full_chain_test`、`mrw_p0b_rereview_test_01a0504c`
- 基线角色：无 `mrw_*` / `codex_*` 角色

## 结果摘要

- 非 PG 全量对照：exit 0，`1565 passed / 119 skipped / 0 failed / 0 errors / 3 warnings in 69.29s`
- PG opt-in 逐文件专用库：39 个文件、39/39 exit 0，合计 `353 passed / 0 skipped / 0 failed / 0 errors / 2 warnings`
- teardown：39/39 次运行 pre/post `pg_database`（过滤 `^(mrw_|codex_)`）与 `pg_roles` 均等于基线；最终库清单等于基线，新增残留库 0、新增角色 0
- p0d capacity：继续走 Unix socket 专用库（fixture 强制 host 为空），专用库名含 `test` 标记，运行中创建/删除 `mrw_p0d_capacity_runner`，运行后不存在

## 1 非 PG 全量对照

命令（未设置 `SUCCESSOR_*` 环境变量）：

```text
env -u SUCCESSOR_TEST_DATABASE_URL -u SUCCESSOR_P3_C5_DATABASE_URL -u SUCCESSOR_DATABASE_URL PYTHONDONTWRITEBYTECODE=1 python3.11 -m pytest tests/successor_runtime -q -p no:cacheprovider
```

- rc=0；`1565 passed, 119 skipped, 3 warnings in 69.29s (0:01:09)`；无 failed、无 errors

## 2 PG opt-in 文件集定义

- 文件集与 `ProductionCutoverRehearsalEvidence.v1.json` 的 39 行 PG dedicated 清单一致：35 个 `*_postgres.py` + 4 个非 `_postgres` 命名但消费 PG fixture/env 的文件（`test_p0b_uow_blob.py`、`test_p0c_production_composition_root.py`、`test_p0c_typed_submission_payloads.py`、`test_p0d_cw12_rolling_deploy.py`）
- 已确认当前工作树中 39 个文件全部存在；没有新增的 PG opt-in 测试文件
- S2b/S2c 文件不在 PG opt-in 清单内（见第 4 节边界）

统一建库/删库命令（每文件替换 `<db>` 与 `<file>`）：

```text
psql -h localhost -d postgres -q -c 'CREATE DATABASE "<db>"'
env -u SUCCESSOR_P3_C5_DATABASE_URL -u SUCCESSOR_DATABASE_URL SUCCESSOR_TEST_DATABASE_URL=postgresql+psycopg2://localhost/<db> PYTHONDONTWRITEBYTECODE=1 python3.11 -m pytest -q -p no:cacheprovider <file>
psql -h localhost -d postgres -q -c 'DROP DATABASE IF EXISTS "<db>" WITH (FORCE)'
```

库名规则：`mrw_all_<file_basename>_test`（如 `mrw_all_test_c7_movement_admission_postgres_test`），每文件一个唯一专用库，串行执行，均含 `test` 标记。p0d capacity 例外：URL 为 `postgresql+psycopg2:///<db>?host=/tmp`（Unix socket）。每文件运行前确认库不存在、运行后删除，并做 pre/post 库与角色快照比较。

## 3 PG 专用库逐文件结果（39 个文件，串行）

| 文件 | exit | passed | skipped | failed | errors | pytest 用时 |
|---|---:|---:|---:|---:|---:|---:|
| test_c7_canonical_write_projector_postgres.py | 0 | 9 | 0 | 0 | 0 | 1.14s |
| test_c7_movement_admission_postgres.py | 0 | 50 | 0 | 0 | 0 | 4.72s |
| test_c8_movement_closure_postgres.py | 0 | 23 | 0 | 0 | 0 | 4.88s |
| test_c8_research_artifact_delivery_bridge_postgres.py | 0 | 2 | 0 | 0 | 0 | 2.71s |
| test_c9_movement_closure_backend_postgres.py | 0 | 38 | 0 | 0 | 0 | 4.90s |
| test_c9_projection_sources_postgres.py | 0 | 17 | 0 | 0 | 0 | 1.48s |
| test_c9_typed_source_evolution_postgres.py | 0 | 5 | 0 | 0 | 0 | 0.90s |
| test_p0b_postgres_integration.py | 0 | 18 | 0 | 0 | 0 | 1.53s |
| test_p0b_uow_blob.py | 0 | 36 | 0 | 0 | 0 | 0.49s |
| test_p0c_delivery_recovery_postgres.py | 0 | 4 | 0 | 0 | 0 | 0.98s |
| test_p0c_full_runtime_chain_postgres.py | 0 | 12 | 0 | 0 | 0 | 66.80s |
| test_p0c_postgres_activation.py | 0 | 4 | 0 | 0 | 0 | 0.51s |
| test_p0c_postgres_lifecycle.py | 0 | 9 | 0 | 0 | 0 | 0.52s |
| test_p0c_postgres_reconciliation.py | 0 | 4 | 0 | 0 | 0 | 0.45s |
| test_p0c_production_composition_root.py | 0 | 3 | 0 | 0 | 0 | 1.66s |
| test_p0c_submission_postgres.py | 0 | 7 | 0 | 0 | 0 | 3.97s |
| test_p0c_two_nodes_postgres.py | 0 | 5 | 0 | 0 | 0 | 3.48s |
| test_p0c_typed_submission_payloads.py | 0 | 3 | 0 | 0 | 0 | 0.98s |
| test_p0c_vertical_specimen_postgres.py | 0 | 3 | 0 | 0 | 0 | 1.39s |
| test_p0d_capacity_postgres.py | 0 | 5 | 0 | 0 | 0 | 1.30s |
| test_p0d_cw11_postgres.py | 0 | 1 | 0 | 0 | 0 | 0.89s |
| test_p0d_cw12_rolling_deploy.py | 0 | 2 | 0 | 0 | 0 | 1.47s |
| test_p0d_gap_successor_postgres.py | 0 | 8 | 0 | 0 | 0 | 6.15s |
| test_p0d_research_projection_postgres.py | 0 | 2 | 0 | 0 | 0 | 2.12s |
| test_p0d_runtime_projection_postgres.py | 0 | 4 | 0 | 0 | 0 | 12.83s |
| test_p2_c2_1_canary_postgres.py | 0 | 16 | 0 | 0 | 0 | 1.46s |
| test_p3_c2_1_rehydration_postgres.py | 0 | 13 | 0 | 0 | 0 | 1.99s |
| test_p3_c2_23_runtime_canary_postgres.py | 0 | 1 | 0 | 0 | 0 | 2.44s |
| test_p3_c2_4_postgres.py | 0 | 2 | 0 | 0 | 0 | 0.45s |
| test_p3_c3_canary_postgres.py | 0 | 7 | 0 | 0 | 0 | 2.03s |
| test_p3_c4_4_postgres.py | 0 | 3 | 0 | 0 | 0 | 0.51s |
| test_p3_c4_5_runtime_postgres.py | 0 | 3 | 0 | 0 | 0 | 1.74s |
| test_p3_c5_2_reconciliation_postgres.py | 0 | 5 | 0 | 0 | 0 | 0.73s |
| test_p3_c5_3_projection_postgres.py | 0 | 4 | 0 | 0 | 0 | 0.76s |
| test_p3_c6_runtime_canary_postgres.py | 0 | 4 | 0 | 0 | 0 | 2.90s |
| test_p3_c6_worker_postgres.py | 0 | 6 | 0 | 0 | 0 | 0.40s |
| test_p3_shared_idempotency_postgres.py | 0 | 2 | 0 | 0 | 0 | 0.93s |
| test_p4_c7_6_postgres.py | 0 | 4 | 0 | 0 | 0 | 0.60s |
| test_p5_c1_slice_acceptance_postgres.py | 0 | 9 | 0 | 0 | 0 | 7.15s |

合计：`353 passed / 0 skipped / 0 failed / 0 errors / 2 warnings`（warnings 仅来自 `test_p3_c6_runtime_canary_postgres.py`）；39/39 exit 0，39/39 teardown_zero=1。

## 4 S2b/S2c 纯 surface 边界（如实标注）

`test_s2_line_event_readback.py`、`test_s2_quality_promotion.py`、`test_s2_request_identity.py`、`test_s2_single_source_guard.py`、4 个 `test_s2b_*` 文件与 4 个 `test_s2c_*` 文件均为 `pytest.mark.unit`：

- 均不读取 `SUCCESSOR_TEST_DATABASE_URL`，也未进入本报告的 39 个 PG opt-in 文件清单
- `test_s2b_cell_extension_wiring.py`、`test_s2c_surface_assembly_wiring.py` 中的引擎仅为 `sqlite+pysqlite:///:memory:`
- 因此这些本地纯 surface 用例（S2b 44 个、S2c 21 个）只被非 PG 全量对照覆盖；它们不证明 C7.2/C8.3/C9.1 handler 或 ops-domain surface 的 live PostgreSQL handler 行为
- 对上述无 PG handler 或仅有 sqlite/local 实现的部分，本报告不宣称已获得 PG 运行证据

## 5 与既有记录差异

### 5.1 非 PG 对照

| 记录 | passed | skipped | failed | 备注 |
|---|---:|---:|---:|---|
| `I1PgEvidence.Dedicated.2026-09-02.md` | 1370 | 117 | 0 | 同一工作树较早字节快照 |
| `P4PgEvidenceRerun.2026-09-02.md` | 1320 | 117 | 0 | P4 范围快照 |
| 本轮 AllLines | 1565 | 119 | 0 | 当前字节，新增 +195 passed/+2 skipped（相对 I1 Dedicated）；相对 P4 为 +245 passed/+2 skipped |

计数增长来源未逐文件归因到单一改动；本报告只证明当前字节下的结果，不把历史快照差异解释为某一文件新增。

### 5.2 PG 逐文件

相对 `I1PgEvidence.Dedicated.2026-09-02.md`（38 个文件、344 passed）：

- 38 个共有文件行逐项与既有表格完全一致（0 mismatches）
- 本轮唯一新增行：`test_c7_canonical_write_projector_postgres.py`，9 passed，故文件数 38→39、总数 344→353

相对 `P4PgEvidenceRerun.2026-09-02.md`（只覆盖选定套件，未含 canonical write/projector）：

- 重叠行一致：C1 PG 9、C7 admission PG 50、C8 movement closure PG 23、C8 delivery bridge PG 2
- C9 后端三个 PG 文件当前为 38+17+5=60，可覆盖 P4 C9 backend 148 组合中的 PG 部分；P4 组合还含多个纯测试文件，纯文件部分已由非 PG 全量覆盖
- P4 未记录 canonical write/projector；本轮为 9 passed

与 `ProductionCutoverRehearsalEvidence.v1.json`（39 文件、353 passed）相比，本轮 39 行文件名与计数全部一致。

## 6 风险与边界

1. 本报告是本地专用库运行证据；不构成 provider 证明、线上运行、canonical/live/cutover/authority 完成或 03/04 主线整合结论。
2. 共享工作树 pre-existing dirty（106 行）且可能并发写入；本报告只证明 HEAD `38acdee` 下本轮快照，不排除后续漂移。
3. S2b/S2c 纯 surface 与无 PG handler 部分已如实标为非 PG 证据；不可从全绿非 PG 套件推出 live PostgreSQL handler 结论。
4. teardown 0 依据 pre/post 过滤快照；两个 pre-existing 基线库未删除，非本轮创建。
5. `test_p0d_capacity_postgres.py` 强制 Unix socket + `test|testing|ci` 库名；本轮以手动 socket 专用库完成，与既有报告一致。
6. 本轮未修改生产代码、未修改 01/02/03/04 或冻结成员；唯一新增文件为本报告。
