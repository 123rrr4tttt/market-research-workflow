# I2 Exact-Candidate 独立终审记录（v4 复评）

## 审查身份

- 审查类型：`I2_EXACT_CANDIDATE_FINAL_REVIEW_V4`（独立 reviewer，字节级取证，对照 v1/v2/v3 BLOCK 的 P0 逐项复验）
- 候选 commit：`452611fccb69188477f277550a7f8b6c98b4724c`
- 候选 tree：`94a4038390ea8aeb70864ea67720d225576129d8`
- 候选 branch：`codex/functorial-successor-p0`
- source-identical commit：`1825870a9623dd256fa075053ab89d786c84b6bd`
- source-identical tree：`63bcc270edf9e880ef04dfeb9413b9c634956bbb`
- 审查 worktree：`/tmp/i2_v4_review.jZdalC`（detached，仅读运行，未 commit/push）
- 解释器：`/Users/wangyiliang/.local/bin/python3.11`（Python 3.11.14 / pytest 9.0.2）
- PostgreSQL：localhost:5432，PG 测试仅 disposable 库，teardown 后无新增残留
- 前端：`main/frontend-modern/node_modules` 从主工作树软链至临时 worktree；tsc / Playwright chromium
- 日期：2026-09-02

## Verdict

**PASS_EXACT_CANDIDATE**。全部验收项在候选字节上复跑全绿，v3 两项 P0 已按 `I1EvidenceCandidateBindingConvention.v1.json` 的 source-bound 约定闭合；本 verdict 只评估候选字节能否作为 exact candidate 接受，不授权 live/cutover/provider/canonical production write。

## 绑定约定确认

- `I1EvidenceCandidateBindingConvention.v1.json` 存在，文件 SHA-256 `2afc006edc1d527548c0fbd0438091dcac111a442273a6bcf316130157ec08b6`，git blob `0c841451025908518ffa2b1346a3e7a34145d023`。
- 按约定复算 content digest（排除 content_digest 键、canonical JSON、ensure_ascii、sort_keys、compact）得到 `ff3a969c663397ba70b3389754504a0724f55802e37dbc2c9725901f2c155202`，与文件内记录一致。
- 7 份 I1 evidence 的 `head/commit/tree` 均为 source-identical commit `1825870a9623dd256fa075053ab89d786c84b6bd` / tree `63bcc270edf9e880ef04dfeb9413b9c634956bbb`，符合约定。
- `I1C8_3DeliveryEvidence.v1.json` 顶层 `route_mounted=true`，risks 与测试记录不再声称未挂载。
- 候选相对 source-identical commit 的 diff 仅含 7 份 I1 evidence（M）+ 1 份 binding convention（A），全部位于迁移目录 `evidence/` 下；非 evidence 字节全等。
- 实际候选 commit/tree 由本 I2 review 工件外部绑定，不受 evidence 内 `instance`（仍记录上一候选 `a48acbee/6315e002`）约束。

## 上三轮 P0 修复确认（字节级）

- v1 三项 P0 已闭合：`scripts/generate_runtime_kernel_abi_pilot.py` 在候选树；`app/api/__init__.py` SHA-256 `aa164ad37bbe13fee08cb15492453f24f5144de4318fdea0e6818ca86b6b297b` 与 evidence 一致且 router 已挂载；`migrations/versions/_snapshots/20260830_000001_successor_schema.py` 在候选树。
- v2 两项 P0 已闭合：evidence 文件 SHA 声明与候选字节一致；run 计数（55/1399/128/59/60/209）与实测一致；`I1AssemblyCoverage`/`I1RouteMountEvidence` 顶层 `route_mounted=true`。
- v3 两项 P0 已闭合：source-bound 绑定约定正式写入契约证据；`I1C8_3DeliveryEvidence` 顶层 `route_mounted=true`。

## 逐项验收记录

| 验收项 | 命令（cwd=`main/backend`，python=`/Users/wangyiliang/.local/bin/python3.11`） | exit | 结果 |
| --- | --- | --- | --- |
| 冻结家族不可变 | SHA-256/bytes/lines 对 02 manifest 16/16 复算 | 0 | PASS，`ALL_MATCH 16/16` |
| I1 suite 官方命令 | `env -u SUCCESSOR_TEST_DATABASE_URL -u SUCCESSOR_DATABASE_URL python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime -k i1` | 0 | PASS，`55 passed / 1461 deselected / 0 failed`，无 collection error |
| router 挂载聚焦 | `python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime/test_api_successor_runtime_mount.py` | 0 | PASS，`15 passed` |
| router 挂载 + C9 合并 | `python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime/test_api_successor_runtime_mount.py tests/successor_runtime/test_c9_movement_closure_backend.py` | 0 | PASS，`35 passed` |
| I1/API-mount/C9 合并 | `python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime -k "i1 or api_successor_runtime or c9_movement_closure"` | 0 | PASS，`128 passed / 1388 deselected / 0 failed` |
| p0b schema contract | `python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime/test_p0b_schema_contract.py` | 0 | PASS，`6 passed` |
| 全量非 PG | `env -u SUCCESSOR_TEST_DATABASE_URL -u SUCCESSOR_DATABASE_URL python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime` | 0 | PASS，`1399 passed / 117 skipped / 0 failed`；环境无 `SUCCESSOR_*` 变量 |
| semantic movement generator | `python3.11 scripts/generate_successor_p1_p3_semantic_movement.py --repo-root ../.. --output-root ../.. --check` | 0 | PASS，`CHECK_OK` 60/0（inline 40 + external_c7 20，exact_blockers 0） |
| semantic movement validator | `python3.11 scripts/validate_successor_semantic_movement.py --repo-root ../.. --output-root ../..` | 0 | PASS，`PASS` 14/14；evidence refs `323/323` resolved，unresolved 0，unassigned_blocker_count 0 |
| capability 30/30 CLI | 30 个 `generate_capability_spec_pilots.py --spec <cell> --runtime-kernel-abi RuntimeKernelABI.v1.json --output <cell>.BuildManifest.v1.json --check` | 0×30 | PASS，30/30 `MATCH` |
| C7 canonical write/projector PG | `SUCCESSOR_TEST_DATABASE_URL=postgresql+psycopg2://localhost/postgres python3.11 -m pytest -q -p no:cacheprovider tests/successor_runtime/test_c7_canonical_write_projector_postgres.py tests/successor_runtime/test_c7_movement_admission_postgres.py` | 0 | PASS，`59 passed`（9 + 50）；before/after `pg_database` 清单一致，无新增残留库 |
| C9.2 frontend typecheck | `./node_modules/.bin/tsc -b --pretty false`（cwd=`main/frontend-modern`） | 0 | PASS |
| C9.2 frontend focused e2e | `./node_modules/.bin/playwright test tests/e2e/successor-runtime-observation.spec.ts tests/e2e/successor-runtime-client.spec.ts --reporter=line --workers=1`（cwd=`main/frontend-modern`） | 0 | PASS，`60 passed`（44 + 16） |
| 依赖边界 | `python3.11 scripts/check_successor_runtime_dependencies.py` | 0 | PASS，`ok=true`，`files_checked=209 / 43 / violations=0` |
| 候选 worktree 洁净 | `git rev-parse HEAD HEAD^{tree}` / `git status --porcelain` | 0 | PASS，detached HEAD=`452611fc…`，tree=`94a40383…`，tracked 状态干净 |
| evidence 绑定与计数一致性 | 7 份 I1 evidence 全量扫描 + binding convention digest 复算 + 候选 diff 范围 | - | PASS，7 份 head/commit/tree=source-identical；`I1C8_3` `route_mounted=true`；run 计数与实测一致；文件 SHA 声明与候选字节一致；diff 仅 evidence 文件 |
| live provider 边界冻结 | `evidence/i1-successor-assembly/LiveProviderBoundaryFreeze.v1.json` | - | PASS，`LIVE_PROVIDER_DIMENSION_FROZEN_AS_BLOCKED`；authority 全 false、`candidate: null` |

## Open Findings

- P1-1（延续 v3）：`I1AssemblyCoverage.v1.json` 内部漂移。顶层 `route_mounted=true`、coverage 30 INSTALLED，但多个 cell owner 注释仍写 “WP-I1-06 route mounting remains closed”，且 `unresolved_dimensions` 仍含未知 cell `C9.API_UI_REPORT_PROJECTION`（同时为 P2-2）。
- P2-1（延续）：`I1TestEvidence.v1.json` runs[0] registry smoke 命令缺少 import/engine 参数，不能按原样复现。
- P2-2（延续）：`I1AssemblyCoverage.unresolved_dimensions` 含不在 30-cell inventory 的 `C9.API_UI_REPORT_PROJECTION`。
- P2-3（更新）：`P2C21CapabilityPacket.v1-v4` 的 `source_bindings` 仍与候选字节不符（v1 2 项、v2/v3 3 项、v4 1 项）；v5 全量 17 项一致。
- P2-4（延续）：候选内嵌 `05_functorial-successor-final-review.md` 仍为 v1 记录（`9fa8aefa`），`evidence/SUPERVISOR_REVIEW_REQUEST.md` 未含 I2 v1/v2/v3 BLOCK 与修复记录；v4 记录只写主工作树（按本轮指令）。
- P2-5（延续）：`I1C7CanonicalWriteEvidence.v1.json` 的 `content_sha256_before_self_field` 在 head 变更后未重算且仓库内无校验器，无法机器核验。

## Authority / 状态

- `live_provider: false`、`external_delivery: false`、`cutover: false`、`authority_transfer: false`、`production_canonical_write: false`。
- canonical write 证据：仅 successor-owned 表在 disposable PG 上 `59 passed`，不等同生产 canonical write 或 legacy 行为验收。
- `candidate_created=true` 仅表示候选 commit `452611fc` 存在；`promotion=false`。
- `LiveProviderBoundaryFreeze.v1.json` 存在：`LIVE_PROVIDER_DIMENSION_FROZEN_AS_BLOCKED`，authority 全 false，`candidate: null`。
- 本 verdict 不授权 live/cutover/provider/canonical production write；02 authority exclusions 继续生效。

## 风险

- `tsc -b` 与 Playwright 使用主工作树 `node_modules` 软链，未重跑 `pnpm install`。
- PG 通过只覆盖 C7 两个文件（59 passed）；其余 PG opt-in 文件未在本轮重跑。
- `I1PgEvidence.I1.2026-09-02.md`、`I1PgEvidence.Dedicated.2026-09-02.md`、`I1SuccessorAssembly.v1.md` 仍记录早期 head/计数（如 `35ca039c`、50/1370 等），属历史证据，不在 7 份 JSON 绑定集内，不构成本轮候选矛盾。
- binding convention `instance` 记录上一候选 `a48acbee/6315e002`；实际候选 `452611fc/94a40383` 由本 review 工件外部绑定。
- P1-1 提示 I1 evidence 家族内部文案尚未完全收敛，建议在后续整合/晋升前清理，不影响 exact-candidate 字节验收。

## 结论

候选 `452611fc/94a40383` 在候选字节上复现全部功能与证据一致性验收项；v1/v2/v3 的 P0 已全部闭合，verdict 为 `PASS_EXACT_CANDIDATE`。残留 P1/P2 为文档一致性与可复现性观察，不阻断 exact-candidate 字节接受，但不得据本 verdict 主张 live/cutover/provider/canonical production write 授权。
