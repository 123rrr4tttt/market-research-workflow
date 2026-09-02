# I1 全量 PostgreSQL 证据报告（2026-09-02）

- 工作树：`/Users/wangyiliang/.codex/manual-worktrees/mrw-functorial-successor-p0`
- 分支：`codex/functorial-successor-p0`；初始 git status 48 行 dirty，本轮未 commit/push/reset/clean
- 执行目录：`main/backend`
- 解释器：`python3.11` 3.11.15；pytest 8.4.2；SQLAlchemy 2.0.35；psycopg2 2.9.9
- PostgreSQL：localhost:5432，PostgreSQL 18.3（Homebrew），本机用户连接
- 本轮只写本报告；未修改生产代码
- 基线测试库（运行前已存在，未删除）：`codex_p0c_full_chain_test`、`mrw_p0b_rereview_test_01a0504c`

## 结果摘要

- 非 PG 全量对照：exit 1，`1364 passed / 117 skipped / 6 failed / 3 warnings`（两次复跑一致）
- I1 PG 聚焦：exit 0，`50 passed / 1437 deselected`
- PG opt-in 34 个文件串行（统一 `SUCCESSOR_TEST_DATABASE_URL=postgresql+psycopg2://localhost/postgres`）：`187 passed / 0 skipped / 0 failed / 113 errors`；其中 16 个文件 exit 0，18 个文件因专用 test 库 guard 报 errors（exit 1）
- teardown：34 个 PG 文件每个运行前/后 `pg_database` 均等于基线，本轮新增残留库 0
- 与 `I1TestEvidence.v1.json` 差异：非 PG 从 `1370/117/0` 变为 `1364/117/6`（-6 passed、+6 failed）；I1 聚焦 50 一致；PG canary 可比项一致，C2.1 在 mandated `postgres` URL 下被 guard 拒绝（历史使用专用 `mrw_i1_c2_canary_test`）

## 1 非 PG 全量对照

命令（未设置 `SUCCESSOR_*` 环境变量）：

```text
env -u SUCCESSOR_TEST_DATABASE_URL -u SUCCESSOR_P3_C5_DATABASE_URL PYTHONDONTWRITEBYTECODE=1 python3.11 -m pytest tests/successor_runtime -q -p no:cacheprovider
```

- 第 1 次：rc=1，`6 failed, 1364 passed, 117 skipped, 3 warnings in 61.63s`
- 第 2 次（`--tb=line -rf`）：rc=1，同一 6 个失败，`61.73s`

失败清单：

1. `tests/successor_runtime/test_i1_micro_specimens.py::test_i1_micro_specimen_matrix_is_30_of_30_and_manifest_exact`
2. `tests/successor_runtime/test_i1_micro_specimens.py::test_i1_micro_rows_record_declared_no_atom_shapes`
3. `tests/successor_runtime/test_i1_micro_specimens.py::test_i1_micro_specimen_evidence_rows_are_reproducible`
4. `tests/successor_runtime/test_semantic_movement_generator.py::test_persisted_artifacts_match_regenerated_bytes`
5. `tests/successor_runtime/test_semantic_movement_generator.py::test_cli_check_ok_is_read_only`
6. `tests/successor_runtime/test_semantic_movement_review_gate.py::test_validator_cli_passes_against_canonical_roots`

根因：

- 1-3：`_verify_exact_bindings` 对 `C9.2.v1.json` 绑定的 `main/frontend-modern/src/lib/api/domains/successor-runtime.ts` 做 SHA-256 核对，记录值为 `58a68f046dc7720713b76d519b0ead29de9afb0b1a682ce4f579d22c7b2d2e0e`，当前实际为 `cfd390ee67a183e9052a802e79ed0e33da492c3bafb7bdbf27c757a500901436`。该文件 mtime 为 07:02:37，晚于 `C9.2.v1.json` 的 04:13:28；文件为未跟踪、共享工作树并发变更，非本轮测试写入。
- 4-6：12 个 P1P3 semantic-movement 工件（`fragments/C1..C9.v1.json`、`P1P3LegacyDonorSemanticMovementInventory.v1.json`、`P1P3SuccessorMovementMatrix.v1.json`、`P1P3SemanticMovementGate.v1.json`）整体 DRIFT。`C1.v1.json` 具体差异为 `content_digest` 与 `matrix_content_digest`（actual=`eb688af7...`，expected=`1cbc544e...`）。生成器脚本 mtime 02:42:48，`C1.v1.json` mtime 02:42:54；当前输入再生成结果与持久工件不一致，属 canonical-rebuild drift。

## 2 I1 PG 聚焦

命令：

```text
SUCCESSOR_TEST_DATABASE_URL=postgresql+psycopg2://localhost/postgres env -u SUCCESSOR_P3_C5_DATABASE_URL PYTHONDONTWRITEBYTECODE=1 python3.11 -m pytest tests/successor_runtime -q -k i1 -p no:cacheprovider
```

- rc=0；`50 passed, 1437 deselected, 3 warnings in 7.86s`；运行前后 `pg_database` 一致，新增库 0

## 3 PG opt-in 逐文件记录（34 个文件，串行）

统一命令前缀，每行文件均以此命令替换 `<file>` 执行：

```text
SUCCESSOR_TEST_DATABASE_URL=postgresql+psycopg2://localhost/postgres env -u SUCCESSOR_P3_C5_DATABASE_URL PYTHONDONTWRITEBYTECODE=1 python3.11 -m pytest -q -p no:cacheprovider <file>
```

每文件运行前/后执行：

```text
psql -h localhost -d postgres -tAc "SELECT datname FROM pg_database WHERE datname ~ '^(mrw_|codex_)' ORDER BY 1"
```

34 次运行 pre 与 post 均等于基线 `codex_p0c_full_chain_test,mrw_p0b_rereview_test_01a0504c`，故 teardown 新增残留库为 0。数据库列：可建独立库的模块记录其 `DATABASE_NAME`；p0c activation/lifecycle/reconciliation 使用 URL 库（postgres）内建 schema；guard 报错文件记录其 guard 要求。

| 文件 | exit | passed | skipped | failed | errors | 数据库 |
|---|---:|---:|---:|---:|---:|---|
| test_c7_movement_admission_postgres.py | 0 | 50 | 0 | 0 | 0 | mrw_c7_movement_admission_test |
| test_c8_movement_closure_postgres.py | 0 | 23 | 0 | 0 | 0 | mrw_c8_movement_closure_test |
| test_c8_research_artifact_delivery_bridge_postgres.py | 0 | 2 | 0 | 0 | 0 | mrw_c8_delivery_bridge_test |
| test_c9_movement_closure_backend_postgres.py | 0 | 38 | 0 | 0 | 0 | mrw_c9_movement_closure_test |
| test_c9_projection_sources_postgres.py | 0 | 17 | 0 | 0 | 0 | mrw_c9_projection_sources_test |
| test_c9_typed_source_evolution_postgres.py | 0 | 5 | 0 | 0 | 0 | mrw_c9_typed_source_evolution_test |
| test_p0c_postgres_activation.py | 0 | 4 | 0 | 0 | 0 | postgres（URL 库内 schema） |
| test_p0c_postgres_lifecycle.py | 0 | 9 | 0 | 0 | 0 | postgres（URL 库内 schema） |
| test_p0c_postgres_reconciliation.py | 0 | 4 | 0 | 0 | 0 | postgres（URL 库内 schema） |
| test_p3_c2_23_runtime_canary_postgres.py | 0 | 1 | 0 | 0 | 0 | mrw_p3_c2_worker_test |
| test_p3_c2_4_postgres.py | 0 | 2 | 0 | 0 | 0 | mrw_p3_c2_worker_test（串行避免同名冲突） |
| test_p3_c3_canary_postgres.py | 0 | 7 | 0 | 0 | 0 | mrw_p3_c3_worker_test |
| test_p3_c4_4_postgres.py | 0 | 3 | 0 | 0 | 0 | mrw_p3_c4_worker_test |
| test_p3_c4_5_runtime_postgres.py | 0 | 3 | 0 | 0 | 0 | mrw_p3_c4_worker_test（串行避免同名冲突） |
| test_p4_c7_6_postgres.py | 0 | 4 | 0 | 0 | 0 | mrw_p4_c7_worker_test |
| test_p5_c1_slice_acceptance_postgres.py | 0 | 9 | 0 | 0 | 0 | 随机唯一 `mrw_c1_slice_acceptance_test_<hex>` |
| test_p0b_postgres_integration.py | 1 | 0 | 0 | 0 | 18 | guard：需 test/ci 命名专用库 |
| test_p0c_delivery_recovery_postgres.py | 1 | 0 | 0 | 0 | 4 | guard：需 test/ci 命名专用库 |
| test_p0c_full_runtime_chain_postgres.py | 1 | 0 | 0 | 0 | 12 | guard：需 test/ci 命名专用库 |
| test_p0c_submission_postgres.py | 1 | 0 | 0 | 0 | 7 | guard：需 test/ci 命名专用库 |
| test_p0c_two_nodes_postgres.py | 1 | 0 | 0 | 0 | 5 | guard：需 test/ci 命名专用库 |
| test_p0c_vertical_specimen_postgres.py | 1 | 0 | 0 | 0 | 3 | guard：需 test/ci 命名专用库 |
| test_p0d_capacity_postgres.py | 1 | 2 | 0 | 0 | 3 | guard：Unix socket + 非超管 `mrw_capacity_runner` + `codex_p0d_capacity_test` |
| test_p0d_cw11_postgres.py | 1 | 0 | 0 | 0 | 1 | guard：需 test/ci 命名专用库 |
| test_p0d_gap_successor_postgres.py | 1 | 0 | 0 | 0 | 8 | guard：需 test/ci 命名专用库 |
| test_p0d_research_projection_postgres.py | 1 | 0 | 0 | 0 | 2 | guard：需 test/ci 命名专用库 |
| test_p0d_runtime_projection_postgres.py | 1 | 0 | 0 | 0 | 4 | guard：需 test/ci 命名专用库 |
| test_p2_c2_1_canary_postgres.py | 1 | 3 | 0 | 0 | 13 | guard：需 test/ci 命名专用库（历史用 mrw_i1_c2_canary_test） |
| test_p3_c2_1_rehydration_postgres.py | 1 | 1 | 0 | 0 | 12 | guard：需 test/ci 命名专用库 |
| test_p3_c5_2_reconciliation_postgres.py | 1 | 0 | 0 | 0 | 5 | guard：需 test/ci 命名专用库 / `mrw_p3_c5_worker_test` |
| test_p3_c5_3_projection_postgres.py | 1 | 0 | 0 | 0 | 4 | guard：需 test/ci 命名专用库 / `mrw_p3_c5_worker_test` |
| test_p3_c6_runtime_canary_postgres.py | 1 | 0 | 0 | 0 | 4 | guard：需 test/ci 命名专用库 |
| test_p3_c6_worker_postgres.py | 1 | 0 | 0 | 0 | 6 | guard：需 test/ci 命名专用库 |
| test_p3_shared_idempotency_postgres.py | 1 | 0 | 0 | 0 | 2 | guard：需 test/ci 命名专用库 |

合计：`187 passed / 0 skipped / 0 failed / 113 errors`；16 个文件 exit 0，18 个文件 exit 1（全部来自 guard 报错）。每个文件运行前后 `pg_database` 无新增，teardown 0。

## 4 与既有 I1TestEvidence 记录的差异

`I1TestEvidence.v1.json` 非 PG 记录为 `1370 passed / 117 skipped / 0 failed`，本轮对照为 `1364 passed / 117 skipped / 6 failed`：-6 passed、+6 failed，失败根因见第 1 节。

I1 聚焦记录 `50 passed, 1437 deselected, 0 failed`，本轮 PG 环境复跑 `50 passed, 1437 deselected`，一致。

PG canary 对照：

| 历史 run | 历史结果 | 本轮结果 |
|---|---|---|
| PG canary C1（test_p5_c1_slice_acceptance_postgres.py） | 9 passed | 9 passed |
| PG canary C2.1（test_p2_c2_1_canary_postgres.py，专用 mrw_i1_c2_canary_test） | 16 passed | mandated postgres URL 下 3 passed / 13 errors（guard 拒绝） |
| PG canary C2.2-C2.4（test_p3_c2_23_runtime_canary_postgres.py） | 1 passed | 1 passed |
| PG canary C4.3（test_p3_c4_4_postgres.py + test_p3_c4_5_runtime_postgres.py） | 3 + 3 passed | 3 + 3 passed |

历史 `not_run` 中的 full PostgreSQL opt-in 本轮已执行：mandated `postgres` URL 下，18 个要求专用 test 库的文件报 113 errors；其余 PG 项 187 passed；未发现本轮新增残留库。

## 5 风险与边界

1. 共享工作树存在并发写入：运行期间观察到新增未跟踪前端文件（`SuccessorRuntimeObservation.tsx`、`successor-runtime-observation.spec.ts`），且 `successor-runtime.ts` 在 `C9.2.v1.json` 记录哈希之后被修改，直接导致 3 个 I1 micro exact-binding 失败。证据存在时间竞争，需在冻结输入后再判。
2. P1P3 semantic-movement 12 个工件与当前输入不可重现（`content_digest` / `matrix_content_digest` drift），导致 3 个非 PG 失败；这是工件/输入漂移，不是测试随机失败。
3. 全量 PG 绿需要为 18 个专用 test 库套件提供 `test/ci` 命名库；部分套件（如 p0d capacity）还要求 Unix socket 与非超管角色。mandated `postgres` URL 不能满足这些 guard，本轮 113 errors 属于环境 guard 结果，不能作为生产代码失败证据。
4. teardown 0 仅覆盖本轮运行：34 个 PG 文件前后库清单一致，无新增残留；两个基线库为运行前遗留，本轮未删除（无授权）。
5. 本报告不写 03/04 主线整合，不提供权威性/线上结论。
