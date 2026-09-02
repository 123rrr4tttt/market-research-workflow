# I1 Successor Assembly 设计证据摘要

Status: `DESIGN_EVIDENCE_ONLY_NOT_IMPLEMENTED_NOT_PROMOTION`

机器可读版本：[I1SuccessorAssembly.v1.json](./I1SuccessorAssembly.v1.json)

工作树：`/Users/wangyiliang/.codex/manual-worktrees/mrw-functorial-successor-p0`，分支 `codex/functorial-successor-p0`，HEAD `35ca039c`。

## 结论

1. I1 尚无正式定义，只有高层要求：`00_functorial-successor-migration-development-contract.draft.md:490` 规定 C1-C9 达到至少 `SHADOW_PARITY` 后，经 adapter 集成 successor 路径且 legacy 保持可用。03/04/SUPERVISOR_REVIEW_REQUEST 均记录 `P5/I1/I2 未开始`。
2. 30/30 cell 已有 CapabilityCellSpec + BuildManifest，但全部为 `UNADOPTED_BUILD_GREEN` 证据层：`candidate_created=false`、`handler_implementation_generated=false`、`rollback_implementation_generated=false`、`registration_is_authority_adoption=false`、`commutativity_claim=NOT_CLAIMED`。
3. 现有 `PostgresFirstSpecimenRuntime` 组合根是基础设施无关内核，handler 全部靠调用方注入；`build_postgres_first_specimen_assembly`（P0C 6 ops）与 `build_postgres_c8_delivery_assembly`（C8.3 5 kinds）均无 app 调用方；`create_successor_runtime_router` 未挂载。
4. 按严格组合根注册判定：0/30 cell 被 app 可调用组合体直接注册；C1.2/C1.3 仅内核机制推断覆盖（标 `UNRESOLVED_WIRING`）；C8.3 有 assembly 定义但无调用方；C9.2 仅 design-only 契约；其余 26 个 cell 有模块但未接线。
5. 本证据不构成 promotion/candidate/live/权威完成证据；live provider、external delivery、cutover、authority transfer、production canonical write 均未授权。

## 装配拓扑与覆盖统计

现有组合根：

| 名称 | 路径 | 角色 | app 调用方 |
| --- | --- | --- | --- |
| `compose_postgres_first_specimen_runtime` | `substrate/postgres/composition_root.py:435` | RuntimeNode 内核组合根 | 无 |
| `build_postgres_first_specimen_assembly` | `substrate/postgres/first_specimen_assembly.py:172` | P0C first-specimen 6 ops | 无 |
| `build_postgres_c8_delivery_assembly` | `substrate/postgres/c8_production.py:551` | C8.3 报告链 5 kinds | 无 |
| `create_successor_runtime_router` | `app/api/successor_runtime.py:199` | C9.1 facade 路由 | 未挂载 |

覆盖统计（30 cells）：

- 严格组合根直接注册：0
- 内核机制推断覆盖：2（C1.2、C1.3）
- assembly 已定义但无调用方：1（C8.3）
- 有模块未接线：26
- 仅 spec/fragment 证据：1（C9.2）
- `UNRESOLVED_WIRING`：C1.2、C1.3

维度级 unresolved：live provider（C2.3/C3.1/C3.2/C6.2）、C7 rollback binding（C7.1-C7.4 全空）、`C9.API_UI_REPORT_PROJECTION`（不在 30-cell 正式清单）。

## Gap 清单

- C1.1：纯 compile facade，无 RuntimeHandler/Program 接线。
- C1.2/C1.3：无显式 cell 绑定，接线语义未确定（UNRESOLVED_WIRING）。
- C2.1：handler/canary 完整，缺 activation catalog 条目与 `additional_handlers` 注入。
- C2.2/C2.3：仅 canary/worker 形态 handler；C2.3 缺生产 provider/readback port。
- C2.4：projector 未注册进 `ProjectorRegistry`，offset 无生产驱动。
- C3/C4/C6：canary/store-rehydrated handler 均未进 assembly；C4.3/C6 已有生产形状。
- C5：projection 未注册；C5.2 仅被 first-specimen RECONCILE 间接覆盖。
- C7：candidate values/movement admission/document readback 齐全，但无 assembly、无 `AdmissionCoordinator` 注册、无 reconcile handler 注入，rollback_bindings 为空。
- C8.1/C8.2/C8.4：生产函数在测试-only `C8ProductionRoot` 内，未 RuntimeHandler 化；C8.3 bridge 无 app 实例化。
- C9：facade/command/query/projector registry 存在但无生产注册和路由挂载；C9.2 frontend 零字节未采纳。

## I1 验收计划

| 类型 | 代表性现有测试 | 新建边界 | 验收标准 |
| --- | --- | --- | --- |
| micro specimen | `test_p3_c3_micro.py`、`test_p3_c4_1_program.py`、`test_p4_c8_5_program.py`、`test_p5_c1_slice_programs.py` | `test_i1_micro_specimens.py`（30 rows） | 30/30 非 PG 通过；from_dict + manifest `--check MATCH`；每 cell 至少一条 failure/reverse trace |
| legacy trace replay | `test_p2_c2_1_parity.py`、`test_p3_c3_replay_shadow.py`、`test_p5_c1_legacy_oracle.py`、`test_c7_movement_decision_parity.py` | `test_i1_legacy_trace_replay.py` | 同 trace 确定性重放；zero double effect；C7 legacy writer 保持 zero |
| shadow parity | `test_p3_c6_legacy_shadow.py`、`test_p3_c4_1_parity.py`、`test_c8_movement_closure_pure.py`、`test_c9_movement_closure_backend.py` | `test_i1_shadow_parity_matrix.py`（A/B/C slice + 全矩阵） | named observation 一致；failure union parity；declared loss 记账；zero double effect |
| rollback rehearsal | `test_p3_c3_rollback.py`、`test_p2_c2_1_canary_postgres.py`、`test_c9_generalized_rollback_identity.py`、`test_p0d_cw12_rolling_deploy.py` | `test_i1_rollback_rehearsal.py` | journal 保留、owner epoch 改变、legacy 可回选、无 dual claim；C7 阻断至 rollback_bindings 补齐 |
| canary | `test_p2_c2_1_canary_postgres.py`、`test_p3_c3_canary_postgres.py`、`test_p3_c4_canary.py`、`test_p3_c6_runtime_canary_postgres.py`、`test_p5_c1_slice_acceptance_postgres.py` | `test_i1_canary_assembly.py`（补 C5/C8/C9） | parity 闭合后才选 successor；legacy 默认；teardown residue 0 |

运行命令（cwd = `main/backend`）：

```sh
python3.11 -m pytest tests/successor_runtime -q
SUCCESSOR_TEST_DATABASE_URL=postgresql+psycopg2://<user>@/<test_db> python3.11 -m pytest tests/successor_runtime -q
SUCCESSOR_POSTGRES_VALIDATION_DATABASE_URL=postgresql+psycopg2://admin@/mrw_admin_test?host=/var/run/postgresql \
  python3.11 scripts/run_successor_postgres_validation.py -- python3.11 -m pytest -q tests/successor_runtime
```

## 推荐工作包

| 包 | 类型 | 并行 | 允许读写 | 验收 |
| --- | --- | --- | --- | --- |
| WP-I1-01 micro specimen 套件 | evidence-only | A | `test_i1_micro_specimens.py` + `evidence/i1-successor-assembly/` | 30/30 通过，生产代码零改动 |
| WP-I1-02 家族 assembly builder | production | B（8 条 lane） | 每 lane 新模块+新测试；禁改 composition_root/`__init__` | focused pytest + dependency lint |
| WP-I1-03 串行整合 | production | C（serial） | `composition_root.py`（或新 `successor_assembly.py`）+ 测试 | 30 binding 可安装、缺 cell fail-closed、不挂路由 |
| WP-I1-04 replay/parity 矩阵 | evidence-only | A | 新测试 + `evidence/i1-successor-assembly/` | 矩阵全可执行、zero double effect |
| WP-I1-05 rollback rehearsal + C7 binding | evidence-only | C（serial） | 生成器重生成 C7 spec/build + 新测试 | rollback receipt 覆盖、C7 bindings 非空 |
| WP-I1-06 app 入口挂载 | production | D（blocked） | `app/api/__init__.py` + 新入口 | 仅本地/离线；live 另立 authority 里程碑 |

冲突面：`composition_root.py`、`substrate/postgres/__init__.py`、`app/api/__init__.py` 只允许 WP-I1-03/06 串行触碰；C7 spec/build 与 WP-I1-04 串行。机械化 lane 按 AGENTS.md 交给 DeepSeek worker，架构/整合/authority 由主线独占。

## Fail-closed

- I1 未开始；本证据不构成 promotion/candidate/live 证据。
- C1.2/C1.3：`UNRESOLVED_WIRING`，未臆造接线。
- `C9.API_UI_REPORT_PROJECTION`：不在 30-cell 正式清单，无法映射。
- C7.1-C7.4：`rollback_bindings` 为空，rollback 验收阻断。
- C2.3/C3.1/C3.2/C6.2：live provider 接线语义未冻结。
- P1 open risks（`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`、`C1_M003_TIMEOUT_FAILURE_NOT_EXERCISED`、`C1_SOURCE_PATH_UNDER_CURRENT_DEV_TREE`）未清零前 I1 执行不应开始。
- PG 测试动态 skip；非 PG 绿套件不证明 PG 覆盖。
- 两个现有 assembly 均无 app 调用方，组合根覆盖只到 factory 层。
