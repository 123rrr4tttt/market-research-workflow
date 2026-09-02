# P4 采用准备度缺口报告 v1

- 分析对象：`/Users/wangyiliang/.codex/manual-worktrees/mrw-functorial-successor-p0`
- 报告日期：2026-09-02（只读分析；本报告未运行任何测试）
- 基线：branch `codex/functorial-successor-p0`，HEAD `35ca039c59d2efae8038a678995e8a0812032e43`；successor 产物均为 worktree untracked 内容
- 证据口径：文件 SHA-256 为本轮 `shasum -a 256` 现场计算；`content_digest` 以工件内嵌值为主并做了交叉核对；03/04 为可变台账，报告之后仍可能继续变化

## 缺口摘要

1. P4 采用未授权：冻结契约的 `next_authorized_stage` 是“P4 capability-spec pilot after semantic-movement completeness gate”，当前 03/04 均声明 `P4_START_NOT_AUTHORIZED` / `PAUSED_NOT_PROMOTED`。
2. 30 个 cell 中只有 3 个存在 capability cell spec（C7.1、C8.2、C9.1）和 build manifest，27 个 cell 无 spec；三个 pilot spec 也全部是 `UNADOPTED`，0 个 cell 已采用。
3. C2-C6 共 16 个 cell 无 spec，且 family 配置走 body-builder 路径、`cell_spec_path` 为空，不满足“capability cell spec + compiler + runtime_kernel_abi 共享输入”门禁。
4. C7 两份独立 review 与 P3 aggregate review 绑定的是边界修复前的旧 bundle/review 字节，未随 C1/C8/C9 一起重绑；04 ledger 中 C7.1 spec/build、route decision/ownership、C7 matrix/inventory 哈希与磁盘不一致。
5. PG 证据均为历史引用，当前边界未重跑；03 与 SUPERVISOR_REVIEW_REQUEST 的全量非 PG 计数（1320 vs 1284）和边界导入风险状态互相冲突，需先收敛再作为门禁输入。

## 1. P4 采用在冻结文档中的确切条款与前置条件

### 1.1 01 合同索引（`01_functorial-successor-migration-development-contract.md`，`授权与禁止` 一节）

- “当前续作授权边界为同一 Goal 的 `semantic movement completeness gate`，通过后进入 `P4 capability-spec pilot`”。
- 强制输入：legacy/donor semantic movement inventory 与 successor movement matrix 是 P1/P3/P4/P5、CapabilitySpec pilot 与 candidate review 的强制输入；cell/file/test/hash closure 不能替代 movement closure。
- 晋级条件：movement matrix、legacy decision parity（`STRUCTURED_JSON` / `long-report` / `derived-report` / `pass-through`）、`UNASSIGNED_BLOCKER == 0`、独立双门 review 全部完成前不晋级。
- 回填条款：“在任何 P4 family/aggregate/candidate/authority claim 前，必须为 P1–P3 已完成 scope 做 retrospective movement-matrix backfill；backfill 发现的 `UNASSIGNED_BLOCKER` 只阻断依赖它的 promotion/candidate”。
- C7 pilot 必须先完成 20/21 指定的 C7 matrix、legacy decision parity、zero-unassigned 与独立双门 review。
- 授权上限：v2.3 不授权 live provider、external delivery、cutover、authority transfer 或 candidate；production canonical write 仍受 02 authority exclusions 约束。

### 1.2 02 冻结 manifest（`02_functorial-successor-migration-development-contract.freeze.json`，SHA-256 `895de0a699d472a84cd1f6661e5257e01bdbaed0da6cb3af9ddd3e0d04f07524`）

- `next_authorized_stage`：`"P4 capability-spec pilot after semantic-movement completeness gate"`。
- `implementation_recheck_required` 中与 P4 相关的条目：`backfill retrospective movement matrix for P1-P3 completed scope before any P4 family aggregate candidate or authority claim`、`reach UNASSIGNED_BLOCKER == 0`、`pass independent declared-scope correctness and predecessor-to-successor movement completeness review`、C7 matrix / legacy decision parity / zero-unassigned / dual review 等。
- `authority_exclusions`：无 production canonical write（successor project tables 外）、无 live provider/external network、无 external delivery、无 cutover/authority transfer、无 legacy/successor 双写、无 dashboard/broker 状态作为完成权威。
- `semantic_movement_amendment_refs`：20/21 为规范修正成员。

### 1.3 20/21 semantic movement completeness amendment

- 20 文件 §3：movement inventory 与 movement matrix 是 P4（C7-C9 迁移）、CapabilitySpec pilot、candidate review 的强制输入。
- 20 文件 §12 “当前 C7 pilot 晋级 gate”：① 生成 legacy/donor semantic movement inventory 与 successor movement matrix；② 补齐 legacy decision parity（四模式）；③ `UNASSIGNED_BLOCKER == 0`；④ 独立 review 双门通过。全部满足前不得晋级。
- 20 文件 §14：任何 P4 family/aggregate/candidate/authority claim 前必须完成 P1-P3 retrospective backfill。
- 21 JSON `retrospective_backfill.required_before`：`["P4 family promotion", "P4 aggregate promotion", "candidate acceptance", "authority claim"]`。
- 21 JSON `mandatory_input_consumers` 明确包含 `"P4 C7-C9 migration"`。

### 1.4 06 架构合同（`06_functorial-successor-runtime-architecture-correction.draft.zh-CN.md`）

“第四阶段 P4：C7–C9”原文：“在 durable/admission/projection 路径稳定后迁移写入、知识、报告、API 与前端。”该阶段不改变 C7-C9 30-cell 拓扑，也不授予 live/authority。

### 1.5 治理标准（`docs/governance/semantic-movement-completeness-standard.md`）

- `UNASSIGNED_BLOCKER > 0` 禁止：capability/family promotion、phase/milestone 完成、candidate 进入 canonical target、legacy retirement/freeze、generator/worker 输出视为 promotion。
- 每个 phase gate 必须检查 movement inventory 完整性、必填字段、合法 disposition、runtime authority inventory 与 locator 分离、declared-scope 与 predecessor-to-successor 双门。
- Generator 规则：generator/parallel worker 只能消费已通过 completeness gate 的 spec。

### 1.6 当前 03/04 状态声明

- 03：`P0_P3_LOCAL_ONLY_PROMOTIONS_RETAINED_NOT_REPROVED · SEMANTIC_MOVEMENT_COMPLETENESS_GATE_IN_PROGRESS · P4_START_NOT_AUTHORIZED · NOT_CODE_COMPLETE · NOT_LIVE`；“Next authorized action: P4 adoption boundary request has been filed … P4 adoption, candidate, live provider and production cutover remain unauthorized”。
- 04：`P4.state = PAUSED_BY_SEMANTIC_MOVEMENT_COMPLETENESS_GATE_NOT_PROMOTED`；pilot `UNADOPTED_BUILD_GREEN_REPAIRED`；`ahead_of_time_preparation` 仅到 `READY_FOR_P4_ADOPTION_REVIEW_UNADOPTED`。

结论：截至本报告，P4 采用没有任何正式授权记录；前置条件的契约条款齐备，但证据层面仍有第 4 节的漂移与缺口未闭合。

## 2. C1-C9 每 family 每 cell 的 capability cell spec 存在性

cell 拓扑取自 `evidence/P1FunctorizationEligibility.v1.json`（`cell_count=30`）与 04 ledger `capability_families`，并与 p1/p3/p4 fragments 交叉核对。spec 路径均为 `evidence/capability-specs/` 下文件；build manifest 均为 `evidence/capability-spec-builds/` 下文件。

### C1（3 cells；状态 ELIGIBILITY_REVIEWED / C1 slices 为 P5 acceptance）

| cell_id | spec | build manifest | fragment/evidence | 已采用 | 缺失项 |
| --- | --- | --- | --- | --- | --- |
| C1.1 | 无 | 无 | p1-fragments/C1.json；p5-c1-slices/C1SliceA.v1.json（`ad4bfc92…`） | 未采用 | spec、build、P4/CapabilitySpec 采用 |
| C1.2 | 无 | 无 | p5-c1-slices/C1SliceB.v1.json（`8950c1fe…`） | 未采用 | spec、build、采用 |
| C1.3 | 无 | 无 | p5-c1-slices/C1SliceC.v1.json（`38e2cf14…`） | 未采用 | spec、build、采用 |

C1 双门 review 已按当前 bundle 重绑（declared `0af51b3e…`、predecessor `731f0ada…`），但这是 movement review，不是 capability cell spec。

### C2（4 cells）

| cell_id | spec | build manifest | fragment/evidence | 已采用 | 缺失项 |
| --- | --- | --- | --- | --- | --- |
| C2.1 | 无 | 无 | P2C21CapabilityPacket.v5.json | 未采用 | spec、build、采用 |
| C2.2 | 无 | 无 | p3-fragments/C2.json（`5274116a…`） | 未采用 | spec、build、采用 |
| C2.3 | 无 | 无 | p3-fragments/C2.json | 未采用 | spec、build、采用 |
| C2.4 | 无 | 无 | p3-fragments/C2.json | 未采用 | spec、build、采用 |

### C3（2 cells）

| cell_id | spec | build manifest | fragment/evidence | 已采用 | 缺失项 |
| --- | --- | --- | --- | --- | --- |
| C3.1 | 无 | 无 | p3-fragments/C3.json（`915aee69…`） | 未采用 | spec、build、采用 |
| C3.2 | 无 | 无 | p3-fragments/C3.json | 未采用 | spec、build、采用 |

### C4（3 cells）

| cell_id | spec | build manifest | fragment/evidence | 已采用 | 缺失项 |
| --- | --- | --- | --- | --- | --- |
| C4.1 | 无 | 无 | p3-fragments/C4.json（`058b0234…`） | 未采用 | spec、build、采用 |
| C4.2 | 无 | 无 | p3-fragments/C4.json | 未采用 | spec、build、采用 |
| C4.3 | 无 | 无 | p3-fragments/C4.json | 未采用 | spec、build、采用 |

### C5（4 cells）

| cell_id | spec | build manifest | fragment/evidence | 已采用 | 缺失项 |
| --- | --- | --- | --- | --- | --- |
| C5.1 | 无 | 无 | p3-fragments/C5.json（`38ce2188…`） | 未采用 | spec、build、采用 |
| C5.2 | 无 | 无 | p3-fragments/C5.json | 未采用 | spec、build、采用 |
| C5.3 | 无 | 无 | p3-fragments/C5.json | 未采用 | spec、build、采用 |
| C5.4 | 无 | 无 | p3-fragments/C5.json | 未采用 | spec、build、采用 |

### C6（3 cells）

| cell_id | spec | build manifest | fragment/evidence | 已采用 | 缺失项 |
| --- | --- | --- | --- | --- | --- |
| C6.1 | 无 | 无 | p3-fragments/C6.json（`de997e28…`） | 未采用 | spec、build、采用 |
| C6.2 | 无 | 无 | p3-fragments/C6.json | 未采用 | spec、build、采用 |
| C6.3 | 无 | 无 | p3-fragments/C6.json | 未采用 | spec、build、采用 |

### C7（4 cells；p4-fragments/C7.json `d3a7aaf1…`，status `AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED`，open finding `C7_P4_NOT_STARTED`）

| cell_id | spec | build manifest | 已采用 | 缺失项 |
| --- | --- | --- | --- | --- |
| C7.1 | capability-specs/C7.1.v1.json（磁盘 SHA-256 `80d4fea15508a30537155acf7e0fd4e19a6a38404d222d7f0b3744312b718df5`） | capability-spec-builds/C7.1.BuildManifest.v1.json（磁盘 SHA-256 `87ef60432176edc6aa137a269e75af7547010dbf89375a447d5c07b0e1c2e181`） | 未采用（pilot `UNADOPTED`） | P4 采用、独立 P4 adoption review、C7 review 当前 bundle 重绑 |
| C7.2 | 无 | 无 | 未采用 | spec、build、采用 |
| C7.3 | 无 | 无 | 未采用 | spec、build、采用 |
| C7.4 | 无 | 无 | 未采用 | spec、build、采用 |

### C8（4 cells；p4-fragments/C8.json `206e69ad…`，status `AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED`）

| cell_id | spec | build manifest | 已采用 | 缺失项 |
| --- | --- | --- | --- | --- |
| C8.1 | 无 | 无 | 未采用 | spec、build、采用 |
| C8.2 | capability-specs/C8.2.v1.json（磁盘 SHA-256 `38acc21ee86934121249e4561ea4880c9af69d1fea94d2d40ed8df220c2613d2`） | capability-spec-builds/C8.2.BuildManifest.v1.json（磁盘 SHA-256 `5cdd54ca336dcbb77612b2cf44fce1c78047e95b3ebc347949d5c49480807877`） | 未采用 | P4 采用、独立 P4 adoption review |
| C8.3 | 无 | 无 | 未采用 | spec、build、采用 |
| C8.4 | 无 | 无 | 未采用 | spec、build、采用 |

### C9（3 cells；p4-fragments/C9.json `fdc4b2ab…`，status `AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED`，`p4_status=P4_NOT_STARTED`）

| cell_id | spec | build manifest | 已采用 | 缺失项 |
| --- | --- | --- | --- | --- |
| C9.1 | capability-specs/C9.1.v1.json（磁盘 SHA-256 `008a4ea359a962108172ef8d939d16cf4655a7ea62982924d705c769613edda7`） | capability-spec-builds/C9.1.BuildManifest.v1.json（磁盘 SHA-256 `66b33dffcb73a49386fa60a54d76c1ff8b9a81e4632ad0f05416b591896a2b35`） | 未采用 | P4 采用、独立 P4 adoption review |
| C9.2 | 无 | 无 | 未采用 | spec、build、采用 |
| C9.3 | 无 | 无 | 未采用 | spec、build、采用 |

汇总：30 cells 中 `3/30` 有 capability cell spec，`3/30` 有 build manifest，`0/30` 已采用；`27/30` 无 spec（C1 3、C2 4、C3 2、C4 3、C5 4、C6 3、C7 3、C8 3、C9 2）。

## 3. C2-C6 缺 spec 具体清单与 capability_cell_spec.py 推导的最小必填字段

### 3.1 缺 spec 清单（16 cells）

`C2.1`、`C2.2`、`C2.3`、`C2.4`、`C3.1`、`C3.2`、`C4.1`、`C4.2`、`C4.3`、`C5.1`、`C5.2`、`C5.3`、`C5.4`、`C6.1`、`C6.2`、`C6.3`。

代码证据：`specification/c2_p3.py`、`c3_p3.py`、`c4_p3.py`、`c5_p3.py`、`c6_p3.py` 均走 `FamilyFragmentConfig.body_builder` 路径，不设置 `cell_spec_path`（`c3_p3.py` 显式 `cell_spec_path=None`）；`shared_family_generator.validate_config` 在该路径下不要求 cell spec。这与 04 ledger“C2-C6 仍无 capability cell spec 输入，按门禁不可 promotion”一致。

### 3.2 `capability_cell_spec.py`（`CapabilityCellSpec`）最小必填字段

必填（非空）字段：

- 身份与入口：`schema`（`mrw.functorial_successor.capability_cell_spec.v1`）、`version`（`1.0.0`）、`cell_id`、`family_id`、`owner_capability_id`、`entrypoint_kind`（仅 `PROGRAM` / `FACADE_VALIDATION`）、`commutativity_claim`（仅 `NOT_CLAIMED`）。
- 契约引用：`input_contract_refs`、`output_contract_refs`、`object_contract_refs`、`operation_contract_refs`、`program_shape_ref`、`ordered_composition_refs`（去 identity 后必须含非 identity 项）、`interpreter_refs`、`profile_refs`、`deployment_binding_refs`、`legacy_oracle_ref`、`shadow_observation_ref`、`failure_union_refs`、`generated_ownership_refs`、`handwritten_ownership_refs`、`adoption_prerequisites`。
- 策略引用：`effect_policy_ref`、`resource_policy_ref`、`recovery_policy_ref`、`readback_policy_ref`。
- 损失声明：`declared_lossy_projection_refs`（可为空，但仍需数组）。
- 权限：`authority_ceiling` 必须恰好含五个 bool 且全部为 false：`canonical_write`、`live_provider`、`external_delivery`、`cutover`、`authority_transfer`。
- 精确绑定：`source_bindings`、`test_bindings`、`rollback_bindings` 均为非空 `ExactFileBinding` 数组；每项 `path`（规范化相对路径，禁绝对/`..`）、`file_sha256`（64 位小写 hex）、`role`（非空）。

`route decision` 中 `capability_cell_spec.minimum_fields` 的 9 组分组与本 dataclass 一致。

## 4. PG/独立 review 证据缺口与 review 重绑 / content_digest 状态

### 4.1 已重绑到当前 bundle：C1/C8/C9 六份 review

当前 bundle 磁盘字节：spec `2a96bb63…` / canonical `431488da…`；inventory `38ad71f4…` / content `be1fcf7c…`；matrix `957d2bb8…` / content `e8aa68a4…`；gate `89c77589…` / content `e432ff63…`；C1 fragment `ccbb50ee…`、C8 fragment `35c43e7f…`、C9 fragment `04fcd2d4…`；C1 slices `ad4bfc92…/8950c1fe…/38e2cf14…`；route decision `f64899db…` / content `c103952f…`。

| review | 磁盘 file SHA-256 | content_digest | verdict | 重绑记录 |
| --- | --- | --- | --- | --- |
| C1 declared | `0af51b3e3a…` | `32c9e11da0…` | PASS_DECLARED_SCOPE | `mainline_rebind` 2026-09-02 |
| C1 predecessor | `731f0ada56…` | `95fa6e130a…` | PASS_CURRENT_EXACT_PREDECESSOR_COMPLETENESS | `mainline_rebind` 2026-09-02 |
| C8 declared | `7f52d49409…` | `c39042f733…` | PASS_DECLARED_SCOPE | `mainline_rebind` 2026-09-02 |
| C8 predecessor | `299b698b03…` | `fed13cdf3e…` | PASS_PREDECESSOR_COMPLETENESS | `mainline_rebind` 2026-09-02 |
| C9 declared | `e489958f3e…` | `10a5eb565f…` | PASS_DECLARED_SCOPE | `mainline_rebind` 2026-09-02 |
| C9 predecessor | `4bf63405ba…` | `4fdaa8caa6…` | PASS_CURRENT_EXACT_PREDECESSOR_COMPLETENESS | `mainline_rebind` 2026-09-02 |

04 ledger 的 C1/C8/C9 重绑记录与磁盘一致。C1 仍保留两项非阻塞 P1：`C1-M003_TIMEOUT_FAILURE_NOT_EXERCISED`、`C1_SOURCE_PATH_UNDER_CURRENT_DEV_TREE`。

### 4.2 未重绑：C7 两份 review 绑定旧 bundle 字节

- 磁盘文件：`reviews/C7DeclaredScopeCorrectnessReview.v1.json`（SHA `81d147552b…`，content `8f64798f68…`）、`reviews/C7PredecessorCompletenessReview.v1.json`（SHA `0388659c63…`，content `3af96aeddf…`）；两者均无 `mainline_rebind` 字段。
- 它们绑定的 C7 inventory/matrix 为旧字节：inventory `ef5788d3…`（content `180838b3…`）、matrix `96d6e8fd…`（content `33b9ae4e…`）；绑定的 P1P3 gate/inventory/matrix 也为旧字节（`c9861cd6…` / `e60f52ee…` / `e1d9b690…`）。
- 磁盘当前 C7 字节：inventory `8ca654e374…`（content `4c92fef4f3…`）、matrix `b9d877f024…`（content `b4d15c086a…`）；当前 P1P3 为 `89c77589…` / `38ad71f4…` / `957d2bb8…`。
- C7 declared review 内嵌 `exact_blockers_for_this_spec: 14`、`gate_status: BLOCK_DEPENDENT_SCOPE`，属于旧 bundle 状态，已被后续 60 movements / 0 blockers 取代。

结论：C7 双门 review 需要按当前 C7 matrix/inventory 与当前 P1P3 bundle 重跑或机械重绑，否则不能作为 P4 C7 family 采用输入。

### 4.3 P3 aggregate review 绑定旧 bundle 与旧 family review

`evidence/reviews/P3AggregateExactReview.current.json`（SHA `03cf5e292e…`，content `2c43a9f936…`，verdict `ALLOW_P3_AGGREGATE_LOCAL_ONLY_PROMOTION`）：

- `scope.bundle_authoritative` 绑定的是 pre-boundary-fix bundle：inventory `3c0f96be…/f98f74b3…`、matrix `b70aea27…/f918795f…`、gate `abd69656…/76ac0792…`（spec `2a96bb63…` 为当前）。
- `artifact_bindings` 中 family review 为旧字节：C1 declared `b8a03668…` / predecessor `03e4397d…`；C8 declared `daa0130b…` / predecessor `585601d4…`；C9 declared `4770110f…` / predecessor `bbaa7384…`。
- 该文件对 P3 aggregate 工件本身绑定当前字节（`a80c4f2af1…/83e56d32cf…`），但它引用的 bundle/review 已与磁盘当前状态不一致。
- 其 `promotion_scope` 明确：aggregate 仍为 `REVIEW_COMPLETE_DECISION_PENDING_NOT_PROMOTED`，直到 root supervisor promotion record 存在。

结论：aggregate review 需要机械重绑或重新验证其 `artifact_bindings` / `bundle_authoritative`，才能作为 P4 门禁输入。

### 4.4 04 ledger 哈希漂移（磁盘为准）

| ledger 字段 | ledger 记录值 | 磁盘当前值 |
| --- | --- | --- |
| `capability_spec_pilot.c7_1_spec_sha256` | `acb37598…` | `80d4fea155…` |
| `capability_spec_pilot.c7_1_build_sha256` | `4eb5513a…` | `87ef604321…` |
| `capability_spec_pilot.route_decision_sha256` | `d3396fa7…` | `f64899dbd5…` |
| `capability_spec_pilot.ownership_sha256` | `8bc0783d…` | `e0bffd1441…` |
| `semantic_movement_completeness.c7_gate.inventory_*` | file `66967a3d…` / content `b0e24fcd…` | file `8ca654e3…` / content `4c92fef4…` |
| `semantic_movement_completeness.c7_gate.matrix_*` | file `d7dfad83…` / content `e8072374…` | file `b9d877f0…` / content `b4d15c08…` |
| `current_exact_rebind.c7_value_handoff.inventory/matrix` | `ef5788d3…` / `96d6e8fd…` | `8ca654e3…` / `b9d877f0…` |

另：04 ledger 将 C2-C6 记为 `PROMOTED_LOCAL_ONLY`，而 p3-fragments 状态为 `IMPLEMENTED_CANDIDATE_NOT_PROMOTED`、P3 aggregate 为 `REVIEW_COMPLETE_DECISION_PENDING_NOT_PROMOTED`；这与既有 open finding `P3_AUTHORITY_RECORD_DIVERGENCE` 一致，需要 root/supervisor authority record 收敛。

### 4.5 PG 证据与测试计数缺口

- C1/C7/C8/C9 的 PG 证据均为历史引用，未在当前 bundle/当前字节边界重跑：C1 PG `9 passed`、C7 PG `43/50 passed`、C8 PG `43 passed`、C9 backend `148 passed` / frontend `44 passed` 均记录为历史；P3 aggregate review 明确 `postgres: false`。
- 03 全量非 PG 快照先后记录 `1274 passed / 10 failed / 117 skipped` → `1320 passed / 117 skipped / 0 failed / 3 warnings` → `1284 passed / 117 skipped / 0 failed / 3 warnings`；`SUPERVISOR_REVIEW_REQUEST.md` 仍写 `1320 passed / 117 skipped / 0 failed / 3 warnings`，且把 `P0C_BOUNDARY_LEGACY_MIGRATION_IMPORT_IN_C7_ADMISSION` 列为未决风险。
- 03 后续“Ledger consistency and boundary import closure”记录该边界已修复（`test_p0c_boundaries.py = 6 passed`、C7 admission PG `50 passed`）。本报告只读静态核验 `main/backend/app/successor_runtime/substrate/postgres/ingest_c7_movement_admission.py`：文件不再导入 `app.successor_migration.document_repository_c7` 或 `successor_migration`，与该风险描述不符；说明 SUPERVISOR 请求相对 03 已过期，需重跑并统一。
- 历史碰撞记录：并发 C7/C9 同名单次 PostgreSQL disposable 数据库被判定为测试干扰；当前边界 PG 证据必须唯一命名并串行执行。

## 5. 推荐下一里程碑工作包

### WP1：状态与证据一致性收敛（必须串行，主线/root supervisor 独占）

- 目标：消除 03/04/SUPERVISOR_REVIEW_REQUEST、C7 reviews、P3 aggregate review、ledger pilot hashes 的漂移，形成当前 bundle 的统一门禁输入。
- 输入：当前 03/04、C1/C8/C9 六份 review、C7 两份 review、P3AggregateExactReview.current.json、semantic-movement bundle、capability-specs/builds、route decision/ownership。
- 输出：更新后的 03/04、SUPERVISOR_REVIEW_REQUEST v2、重绑/重跑的 C7 review、重绑的 aggregate review、一致性校验记录。
- 允许读写：仅 `2026-08-30-functorial-successor-migration/03`、`04`、`evidence/` 下的可变证据；禁止修改冻结成员（01/02/20/21 等）与生产代码。
- 验收：semantic movement validator `PASS`；全部 review `content_digest` 与磁盘一致；aggregate review 的 `artifact_bindings`/`bundle_authoritative` 与当前六份 review 及当前 bundle 一致；ledger 中所有 SHA 与磁盘一致；非 PG 全量 0 failed 且计数唯一。
- 冲突面：03/04/SUPERVISOR 必须单写者串行；六份 review 的机械重绑可并行，但写台账必须串行。

### WP2：当前边界 PG 与回归证据重跑（PG 必须串行；机械执行）

- 目标：把 C1/C7/C8/C9 的 PG 证据从“历史引用”升级为当前字节/当前 bundle 下可复现证据；重跑全量非 PG。
- 输入：当前 production bytes、bundle/fragments、tests/successor_runtime 测试、唯一 disposable 数据库方案。
- 输出：每套件的 passed/skipped/teardown 记录、数据库名与时间戳、验证摘要。
- 允许读写：只读代码；创建并销毁 disposable PG 数据库；可写 evidence 验证记录。
- 验收：C1 PG 9、C7 PG 50/107 组合、C8 PG 43、C9 backend 148/frontend 44 在当前字节重跑通过且 teardown 0；全量非 PG 0 failed；无同数据库名并发碰撞。
- 冲突面：所有 PG 用例必须串行或使用唯一数据库名；不得与 WP1 同时写同一证据文件。

### WP3：C7/C8/C9 剩余 8 个 cell 的 CapabilityCellSpec 编写（按 family 可并行；语义由主线/高推理模型撰写）

- 目标：补齐 `C7.2-C7.4`、`C8.1/C8.3/C8.4`、`C9.2/C9.3` 共 8 份 `capability_cell_spec.v1` JSON，字段完整、绑定当前字节、authority 全 false。
- 输入：P1FunctorizationEligibility 对应 cell 记录、当前 movement inventory/matrix、p4-fragments、`capability_cell_spec.py` schema、对应 family 薄配置。
- 输出：`evidence/capability-specs/C7.2.v1.json … C9.3.v1.json`（每 lane 只写本 family 文件）。
- 允许读写：每 lane 仅写自己 family 的 spec 文件；禁止改 `capability_cell_spec.py`、`compiler.py`、`shared_family_generator.py`、`runtime_kernel_abi.py` 或其它 family 文件。
- 验收：`CapabilityCellSpec.from_dict` 全部通过；source/test/rollback 绑定与磁盘字节一致；`semantic_digest` 可复算；聚焦 pilot 测试通过。
- 冲突面：spec 文件按 family 分离、无跨 lane 写冲突；与 WP4 集成阶段必须串行。

### WP4：CapabilitySpec build / route decision 集成（必须串行；单写者）

- 目标：为 8 份新 spec 生成/更新 build manifests，刷新 route decision/ownership，全部 `--check` MATCH。
- 输入：WP3 产物、`RuntimeKernelABI.v1.json`、compiler/generator、当前 route decision/ownership。
- 输出：`evidence/capability-spec-builds/*.json`、`CapabilitySpecCompilationAndVerticalSlicesDecision.v1.json`、`CapabilitySpecGeneratedHandwrittenOwnership.v1.json`。
- 允许读写：只写 generated artifacts；禁止手改 generated 文件（`generated_files_manual_edit: PROHIBITED`）。
- 验收：`generate_capability_spec_pilots.py --check` 与 route decision `--check` 均为 MATCH；focused pilot/route decision 测试通过；authority 全 false、candidate 仍 null。
- 冲突面：单写者，与 WP3 串行；与 WP1 的台账写入串行。

### WP5：C2-C6 capability cell spec backfill（按 family 可并行；先由主 Agent 固定语义契约）

- 目标：为 16 个 P3 cell 补齐 capability cell spec，满足“capability cell spec + compiler + runtime_kernel_abi 共享路径”门禁，为 C2-C6 未来 promotion/candidate 提供输入。
- 输入：P1-P3 movement inventory/matrix（60 movements）、p1/p3 fragments、P2C21CapabilityPacket.v5、legacy adapters、`capability_cell_spec.py` schema。
- 输出：`evidence/capability-specs/C2.1…C6.3.v1.json`（16 份）及对应 family build manifests。
- 允许读写：每 lane 只写自己 family 的 spec 文件；集成阶段才写 build/decision；03/04 更新由主 Agent 串行。
- 验收：`from_dict` 通过、绑定一致、共享生成器以 cell spec 为输入后 `MATCH`、movement matrix 与 spec 的 cell/owner 映射一致。
- 冲突面：与 WP3 共享 `evidence/capability-specs/` 目录但文件名不重叠；共享生成器/CLI/台账均为串行集成点。

### WP6：P4 family/aggregate 采用门（必须串行；主线/root supervisor 独占）

- 目标：在 WP1-WP4 通过后，逐 family 完成 P4 采用 review 与 authority record，更新 ledger/progress，明确 P4 aggregate 与 P5 边界。
- 输入：WP1-WP4 产物、当前 03/04、冻结合同。
- 输出：03/04 更新、P4 family/aggregate 采用记录、SUPERVISOR_REVIEW_REQUEST v2、candidate 仍为 null。
- 允许读写：03/04 与 evidence adoption records；不得扩大 authority。
- 验收：`P4_START_NOT_AUTHORIZED` 被明确的 supervisor 授权记录替换；authority ceiling 仍全 false；candidate/live/cutover 仍为 false；P5 未授权。
- 冲突面：03/04 单写者；不得与 WP2 PG 并行写同名证据。

### 并行与串行总览

- 可并行：WP3 三 family lanes、WP5 五 family lanes、WP1 内六份 review 的机械重绑（写文件互不重叠）。
- 必须串行：WP1 台账写入；WP2 全部 PG 用例（同数据库名历史碰撞）；WP3→WP4 依赖链；WP1→WP6 门禁顺序；03/04/SUPERVISOR 任何写入。
- 同文件冲突面：03/04/SUPERVISOR_REVIEW_REQUEST（单写者）；`capability-spec-builds/*` 与 route decision/ownership（单写者）；`shared_family_generator.py`/`capability_cell_spec.py`/`compiler.py`（spec lanes 只读，仅主 Agent 可改）；p4-fragments 与 C1 slices（绑定更新后需串行重生成）。

## 证据边界

- 本报告的“磁盘当前”断言基于 2026-09-02 现场读盘与 `shasum -a 256` 计算；未执行 pytest/PG/生成器。
- 03/04 是可变当前状态工件；本报告只做事实核对，不构成 promotion/adoption 判断。
- 所有 movement review 的双门 PASS 只证明 declared movement scope；CapabilitySpec 采用、P4 family promotion、candidate 与 live authority 仍分别需要第 1 节契约门禁。
