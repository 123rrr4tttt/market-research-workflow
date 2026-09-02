# I2 Exact-Candidate 独立终审记录

## 审查身份

- 审查类型：`I2_EXACT_CANDIDATE_FINAL_REVIEW`（独立 reviewer，字节级取证）
- 候选 commit：`9fa8aefaae8f30a080f3d2dcac6dfb6ff9f773e0`
- 候选 tree：`709719ca27e5c8c88b0de00e862d2996bb850a82`
- 候选 branch：`codex/functorial-successor-p0`
- 临时 worktree：`/tmp/i2_candidate_903f248b`（detached，仅读运行，未 commit/push）
- 解释器：`/Users/wangyiliang/.local/bin/python3.11`（Python 3.11.14 / pytest 9.0.2）
- PostgreSQL：localhost:5432（18.3），PG 测试使用 disposable 库，teardown 后删除
- 日期：2026-09-02

## Verdict

**BLOCK**。候选字节集不完整且无法复现其自身 evidence 声明的测试结果；存在 3 项 P0。

## P0 Findings

### P0-1：候选缺失 `main/backend/scripts/generate_runtime_kernel_abi_pilot.py`

候选 tree 中不存在该文件，但候选 tree 中的 `main/backend/tests/successor_runtime/test_capability_spec_runtime_kernel_abi_artifact.py` 顶层 `from scripts.generate_runtime_kernel_abi_pilot import build_bytes`。因此 `pytest -k i1` 与全量非 PG `tests/successor_runtime` 均在收集阶段失败（exit 2，`ModuleNotFoundError`）。该文件在源工作树中是 untracked 文件（`?? main/backend/scripts/generate_runtime_kernel_abi_pilot.py`），未被纳入候选 commit。

- 证据：`git ls-tree -r --name-only HEAD | rg generate_runtime_kernel_abi_pilot` = 空
- 官方命令结果：`python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime -k i1` = exit 2，collection error
- 排除该模块后：`-k i1` = 55 passed / 1458 deselected / 0 failed（仅用于说明其余 I1 测试；不改变 BLOCK）

### P0-2：候选未挂载 successor router，路由挂载测试失败

`main/backend/app/api/__init__.py` 在候选中的 SHA-256 为 `25c68af353dec9b10899fef32252d82490a4910db1872fc099cc0e0e3acb56ac`，不包含 successor runtime router 的 import/include。源工作树当前文件 SHA 为 `aa164ad37bbe13fee08cb15492453f24f5144de4318fdea0e6818ca86b6b297b`，与候选内嵌的 `evidence/i1-successor-assembly/I1RouteMountEvidence.v1.json` 记录的 SHA 一致，但该 SHA 是未提交的工作树状态，不是候选字节。

- `python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime/test_api_successor_runtime_mount.py tests/successor_runtime/test_c9_movement_closure_backend.py` = exit 1，`1 failed, 34 passed`
- 失败项：`test_mount_preserves_legacy_routes_and_adds_only_new_prefix`（`/successor-runtime/v2/commands` 不在路由表中）
- 一致性：`I1RouteMountEvidence.v1.json` 声明 `MOUNTED_LOCAL_ONLY_NOT_PROMOTED`，其文件 SHA 与候选字节不符

### P0-3：候选缺失 `main/backend/migrations/versions/_snapshots/20260830_000001_successor_schema.py`

候选 tree 的 `_snapshots/` 为空（0 个文件），但 `test_p0b_schema_contract.py` 读取该 snapshot 文件。源工作树中该目录为 untracked（`?? main/backend/migrations/versions/_snapshots/`）。

- 全量非 PG（排除 P0-1 模块后）：`env -u SUCCESSOR_TEST_DATABASE_URL -u SUCCESSOR_PG -u SUCCESSOR_PG_DSN python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime --ignore=tests/successor_runtime/test_capability_spec_runtime_kernel_abi_artifact.py` = exit 1，`3 failed, 1393 passed, 117 skipped`
- 失败项：
  - `test_api_successor_runtime_mount.py::test_mount_preserves_legacy_routes_and_adds_only_new_prefix`（P0-2）
  - `test_p0b_schema_contract.py::test_alembic_revision_is_self_contained_and_has_explicit_downgrade`（FileNotFoundError: `_snapshots/20260830_000001_successor_schema.py`）
  - `test_p0b_schema_contract.py::test_alembic_snapshot_is_schema_equivalent_to_frozen_p0b_models`（同上缺失）

## 逐项验收记录

| 验收项 | 命令 | exit | 结果 |
| --- | --- | --- | --- |
| 01/02/20/21 冻结成员存在且不可变 | SHA-256/bytes/lines 校验（自写 read-only 校验） | 0 | PASS，16/16 冻结成员与 02 manifest 一致 |
| manifest SHA 与 02 一致 | 02 自 SHA 与 03 声明比对 | 0 | PASS，`895de0a699d472a84cd1f6661e5257e01bdbaed0da6cb3af9ddd3e0d04f07524` |
| semantic movement generator | `python3.11 scripts/generate_successor_p1_p3_semantic_movement.py --check` | 0 | PASS，`CHECK_OK` 60/0（inline 40 + C7 20，exact blockers 0） |
| semantic movement validator | `python3.11 scripts/validate_successor_semantic_movement.py` | 0 | PASS，14/14 checks；evidence refs `323 resolved / 0 unresolved` |
| semantic movement 聚焦测试 | `pytest tests/successor_runtime/test_i1_micro_specimens.py tests/successor_runtime/test_semantic_movement_p1_p3_evidence.py -q` | 0 | PASS，9 passed |
| capability 30/30 CLI | 30 个 `generate_capability_spec_pilots.py --check` | 0/30 全部 0 | PASS，30/30 `MATCH` |
| capability `CapabilityCellSpec.from_dict` | `test_i1_micro_specimens.py`（30 cell matrix） | 0 | PASS，30/30 from_dict + manifest exact |
| I1 suite `pytest -k i1` | 官方命令（候选字节） | 2 | FAIL，collection error（P0-1） |
| I1 suite（排除缺失模块） | 同上 + `--ignore=test_capability_spec_runtime_kernel_abi_artifact.py` | 0 | 55 passed（仅信息性） |
| I1AssemblyCoverage 30/30 INSTALLED | `pytest tests/successor_runtime/test_i1_assembly_composition_root.py -v` | 0 | PASS，11 passed；`I1AssemblyCoverage.v1.json` INSTALLED=30 |
| C7 canonical write/projector PG | `SUCCESSOR_TEST_DATABASE_URL=postgresql+psycopg2://localhost/postgres python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime/test_c7_canonical_write_projector_postgres.py tests/successor_runtime/test_c7_movement_admission_postgres.py` | 0 | PASS，59 passed（9 + 50），disposable DB teardown |
| successor router 挂载测试 | `pytest tests/successor_runtime/test_api_successor_runtime_mount.py tests/successor_runtime/test_c9_movement_closure_backend.py -q` | 1 | FAIL，1 failed / 34 passed（P0-2） |
| C9.2 frontend 测试 | 未执行 | - | NOT_EXECUTED：临时 detached worktree 无 `main/frontend-modern/node_modules`；候选内 4 个 frontend 文件的 SHA 与 `C9_2FrontendMilestone.v1.json` 记录一致（`cfd390ee…` / `c88c30aa…` / `0c822a1b…` / `f3d423b6…`） |
| 全量非 PG `tests/successor_runtime` | `env -u SUCCESSOR_* python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime` | 2 | FAIL，collection error（P0-1） |
| 全量非 PG（排除 P0-1 模块） | 同上 + `--ignore=test_capability_spec_runtime_kernel_abi_artifact.py` | 1 | FAIL，3 failed / 1393 passed / 117 skipped（P0-2、P0-3） |
| authority 一致性 | evidence 扫描 + 候选字节比对 | - | FAIL，`I1RouteMountEvidence.v1.json` 文件 SHA 与候选不符；`I1TestEvidence.v1.json` 的 50 passed / 1370 passed 无法在候选字节复现 |
| live provider 边界冻结文件 | `evidence/i1-successor-assembly/LiveProviderBoundaryFreeze.v1.json` | - | PASS，文件存在；authority 全 false，provider_calls=0 |

## Open Findings

- P0-1：候选缺失 `main/backend/scripts/generate_runtime_kernel_abi_pilot.py`，官方 I1/全量套件无法收集。
- P0-2：候选未挂载 successor router；`test_api_successor_runtime_mount.py` 失败；`I1RouteMountEvidence.v1.json` 记录的是未提交工作树状态。
- P0-3：候选缺失 `migrations/versions/_snapshots/20260830_000001_successor_schema.py`，`test_p0b_schema_contract.py` 两项失败。
- P1：`I1TestEvidence.v1.json`、`I1RouteMountEvidence.v1.json` 的 runs 结果与候选字节不可复现，不能作为候选验收证据。
- P2：`I1SuccessorAssembly.v1.json` 仍记录 `NOT_STARTED` / head `35ca039c`，与候选的 30/30 local-only closure 状态并存，evidence 时序未收敛。
- P2：`I1TestEvidence.v1.json` 记录的 registry smoke 命令缺少 import/engine 参数，无法按原样复现。
- P2：C9.2 frontend 测试在 detached 候选 worktree 未执行（无 node_modules）；文件字节绑定与 milestone evidence 一致。

## 风险

- 即使上述 P0 修复后复跑全绿，本 verdict 只表示候选字节可接受，不授权 live provider、external delivery、cutover、authority transfer 或 canonical production write；`LiveProviderBoundaryFreeze.v1.json` 与 02 authority exclusions 继续生效。
- PG 通过（59 passed）只覆盖 disposable 库上的 successor-owned 表写入，不等同于生产 canonical write 或 legacy 行为验收。
- C9.2 frontend 的 node-env e2e 结果（60 passed）在候选字节下未重跑，需在依赖安装后的候选树中复跑或明确降级为 NOT_EXECUTED。

## 结论

候选 `9fa8aefa` 未通过 I2 exact-candidate 验收：3 项 P0 导致官方要求的 I1 suite 与全量非 PG 套件失败，且 evidence 声明的路由挂载与测试结果与候选字节不一致。修复方式是把缺失的 generator 脚本与 alembic snapshot 纳入候选，并把 router 挂载变更纳入候选后重新生成 commit，再以新候选重复本终审流程。
