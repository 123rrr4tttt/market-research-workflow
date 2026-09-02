# P4 PG 证据重跑记录 2026-09-02

## 证据口径

- 工作树：`/Users/wangyiliang/.codex/manual-worktrees/mrw-functorial-successor-p0`
- Branch：`codex/functorial-successor-p0`；HEAD：`35ca039c59d2efae8038a678995e8a0812032e43`
- 运行环境：Python 3.11.14（`/Users/wangyiliang/.local/bin/python3.11`）、sqlalchemy 2.0.35、psycopg2 2.9.9、pytest 9.0.2；本地 PostgreSQL `/tmp:5432`；Node v26.4.0、Playwright 1.62.1
- PG 连接：`SUCCESSOR_TEST_DATABASE_URL=postgresql+psycopg2://localhost/postgres`；非 PG 全量运行不设置该变量
- 本报告仅记录当前字节下的测试执行证据；不构成 P4 采用、promotion、live/authority 或 production 完成声明
- 历史引用来源：`P4AdoptionReadinessGap.v1.md` 第 4.5/5 节、`03_functorial-successor-migration-development-progress.md`、`04_functorial-successor-capability-ledger.json`

## 逐套件结果

### C1 PG（Slice A/B/C acceptance）

- 命令（工作目录 `main/backend`）：

```text
SUCCESSOR_TEST_DATABASE_URL="postgresql+psycopg2://localhost/postgres" /Users/wangyiliang/.local/bin/python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime/test_p5_c1_slice_acceptance_postgres.py
```

- 结果：exit 0；`9 passed in 5.11s`（首轮复跑 `9 passed in 4.76s`）
- 数据库名（运行期轮询 `pg_database` 捕获）：`mrw_c1_slice_acceptance_test_7e64e65a`（fixture 生成随机后缀）
- Teardown：运行结束后该库不存在，残余计数 0
- 与历史差异：与 03/04 引用 `C1 PG 9 passed / teardown 0` 一致；测试文件 SHA-256 `1bea9f4f44714f625153d8f661335e01996fd965272b75208bd32534f544aa54` 与台账绑定一致

### C7 PG（admission）

- 命令：

```text
SUCCESSOR_TEST_DATABASE_URL="postgresql+psycopg2://localhost/postgres" /Users/wangyiliang/.local/bin/python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime/test_c7_movement_admission_postgres.py
```

- 结果：exit 0；`50 passed in 4.40s`
- 数据库名：`mrw_c7_movement_admission_test`（固定名，fixture 模块级创建/销毁）
- Teardown：运行结束后该库不存在，残余计数 0
- 与历史差异：与 03“Ledger consistency and boundary import closure”的 `C7 admission PG = 50 passed` 及 ledger `PG 50` 一致；早期 v2/v3 引用 `43 passed` 为边界修复前字节，已被当前 50 取代

### C7 组合（107）

- 命令：

```text
SUCCESSOR_TEST_DATABASE_URL="postgresql+psycopg2://localhost/postgres" /Users/wangyiliang/.local/bin/python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime/test_c7_movement_admission_postgres.py tests/successor_runtime/test_c7_movement_decision_parity.py tests/successor_runtime/test_c7_movement_failure_reverse.py tests/successor_runtime/test_c7_semantic_movement_completeness.py
```

- 组成（当前字节 collect 计数）：admission 50 + decision parity 22 + failure reverse 27 + semantic completeness 8 = 107
- 结果：exit 0；`107 passed in 4.56s`
- 数据库名：`mrw_c7_movement_admission_test`（仅 admission 文件创建 PG 库；其余三文件为纯测试）
- Teardown：运行结束后该库不存在，残余计数 0
- 与历史差异：与 ledger/03 的 `combined 107`、`50/107 tests` 一致

### C8 PG（movement closure + delivery bridge + pure closure）

- 命令：

```text
SUCCESSOR_TEST_DATABASE_URL="postgresql+psycopg2://localhost/postgres" /Users/wangyiliang/.local/bin/python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime/test_c8_movement_closure_postgres.py tests/successor_runtime/test_c8_research_artifact_delivery_bridge_postgres.py tests/successor_runtime/test_c8_movement_closure_pure.py
```

- 结果：exit 0；`44 passed in 5.97s`
- 数据库名：`mrw_c8_movement_closure_test`、`mrw_c8_delivery_bridge_test`
- Teardown：运行结束后两个库均不存在，残余计数 0
- 与历史差异：历史引用为 `C8 disposable PG 43 passed`；当前字节该三文件 collect 为 44（closure postgres 23 + delivery bridge 2 + pure closure 19），本轮实测 44 passed。差异为 +1 条当前字节用例计数，未发现失败；03/ledger 需以当前字节口径收敛（WP1 范围）

### C9 backend（148）

- 命令：

```text
SUCCESSOR_TEST_DATABASE_URL="postgresql+psycopg2://localhost/postgres" /Users/wangyiliang/.local/bin/python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime/test_c9_movement_closure_backend.py tests/successor_runtime/test_c9_movement_closure_backend_postgres.py tests/successor_runtime/test_c9_projection_sources_postgres.py tests/successor_runtime/test_c9_typed_source_evolution_postgres.py tests/successor_runtime/test_c9_generalized_rollback_identity.py tests/successor_runtime/test_c9_legacy_named_observations.py tests/successor_runtime/test_c9_typed_projection_payloads.py tests/successor_runtime/test_p4_c9_1_facade_contracts.py tests/successor_runtime/test_p4_c9_2_projector_registry.py tests/successor_runtime/test_p4_c9_3_transport_dto.py tests/successor_runtime/test_p4_c9_4_evidence_generator.py tests/successor_runtime/test_p4_c9_5_p1_consistency_and_public_payload.py tests/successor_runtime/test_p4_c9_6_fragment_stability.py tests/successor_runtime/test_capability_spec_pilot_c9_1.py
```

- 组成（当前字节 collect 计数）：13 个 C9 文件 144 + C9.1 pilot 4 = 148
- 结果：exit 0；`148 passed, 3 warnings in 13.63s`（warnings 为 pydantic `max_items` 与 class-based `config` 弃用警告）
- 数据库名：`mrw_c9_movement_closure_test`、`mrw_c9_projection_sources_test`、`mrw_c9_typed_source_evolution_test`
- Teardown：运行结束后三个库均不存在，残余计数 0
- 与历史差异：与 03/ledger `backend 148` 一致；本报告同时给出 144+4 的组成还原

### C9 frontend（44）

- 命令（工作目录 `main/frontend-modern`）：

```text
npx playwright test tests/e2e/successor-runtime-client.spec.ts --reporter=line --workers=1
```

- 结果：exit 0；`44 passed (1.1s)`
- 与历史差异：与 03/ledger `frontend 44` 一致

### 全量非 PG `tests/successor_runtime`

- 命令（不设置 `SUCCESSOR_TEST_DATABASE_URL`；C1/C7/C8/C9 fixture 走本地默认 URL，p0c/p0d/p2/p3 系列 PG fixture 因缺环境变量 skip）：

```text
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime
```

- 结果：exit 0；`1320 passed, 117 skipped, 3 warnings in 62.23s`（0 failed）
- 与历史差异：与 03 最终快照及 `SUPERVISOR_REVIEW_REQUEST.md` 的 `1320 passed / 117 skipped / 0 failed / 3 warnings` 一致；03 后段 `1284 passed / 117 skipped` 为该边界修复后的另一历史快照，本轮当前字节实测为 1320/117

## Teardown 汇总

- 全部套件运行后，`pg_database` 中不存在本轮创建的 disposable 库（`mrw_c1_*`、`mrw_c7_*`、`mrw_c8_*`、`mrw_c9_*`），每套件 teardown 残余计数均为 0
- 运行前已存在、非本轮创建的库保持原样：`codex_p0c_full_chain_test`、`mrw_p0b_rereview_test_01a0504c`
- 所有 PG 套件串行执行；C7/C8/C9 使用模块固定库名，C1 使用随机后缀；本轮无同库名并发碰撞

## 边界与风险

- C8 历史引用为 43，本轮当前字节实测 44（+1）；计数差异需由 WP1 在台账/文档收敛时统一
- C9 backend 148 的还原包含 C9.1 capability-spec pilot 测试；若后续分片口径不同，需按本报告组成对齐
- 本报告为 local/disposable 证据；不构成 P4 采用、provider/live、candidate、cutover 或 production 权威声明
- 本轮未修改生产代码，未修改 01/02/03/04 与冻结成员；唯一新增文件为本报告
