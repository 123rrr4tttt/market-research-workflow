# C1 Capability Cell Spec 语义契约 v1

## 文档身份

- 文档 ID: `C1CapabilitySpecContract.v1`
- 目标 schema: `mrw.functorial_successor.capability_cell_spec.v1`（`main/backend/app/successor_runtime/specification/capability_cell_spec.py`）
- 目标 schema 版本: `1.0.0`
- 状态: `DRAFT_CONTRACT_NOT_GENERATED`（不构成 promotion、cutover、live authority 或候选接受）
- 日期: 2026-09-02（工作树本地起草日期）
- 范围: C1.1、C1.2、C1.3，共 3 个 cell
- authority 约定: 所有 cell 的 `authority_ceiling` 五标志全部为 `false`，且 `commutativity_claim` 一律为 `NOT_CLAIMED`

## 输入证据（本契约只读引用，不修改）

- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/P1FunctorizationEligibility.v1.json`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/p1-fragments/C1.json`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/semantic-movement/P1P3SuccessorMovementMatrix.v1.json`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/semantic-movement/P1P3LegacyDonorSemanticMovementInventory.v1.json`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/semantic-movement/fragments/C1.v1.json`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/p5-c1-slices/C1SliceA.v1.json`、`C1SliceB.v1.json`、`C1SliceC.v1.json`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/P5C1SliceAcceptance.v1.json`
- `main/backend/app/successor_runtime/specification/capability_cell_spec.py`
- `main/backend/app/successor_runtime/capabilities/c1_legacy_dsl.py`
- `main/backend/app/successor_runtime/capabilities/c1_slice_acceptance.py`
- `main/backend/app/successor_migration/legacy_workflow_graph.py`
- `main/backend/app/successor_runtime/runtime/node.py`
- `main/backend/app/successor_runtime/substrate/postgres/node_adapter.py`
- `main/backend/app/successor_runtime/substrate/postgres/nodes.py`
- `docs/governance/semantic-movement-completeness-standard.md`

## 引用状态约定

- `RESOLVED`: ref 名称与来源文件均已在本工作树验证存在（含代码常量或 ABI 协议常量）。
- `RESOLVED_BY_CONTRACT`: ref 名称由本契约从 movement 行/实现角色机械命名，语义完全取自输入证据，不在本契约外新增含义。
- `MISSING_REF`: 当前磁盘上没有同名常量或契约文件；只给出推荐命名，机械生成必须 fail-closed，不得自动补值。
- `NOT_APPLICABLE`: 该 cell 语义上不适用；由于 `capability_cell_spec.py` 要求非空字符串，生成前必须显式批准替代 ref 或阻断。
- `EXACT_HASH_PENDING`: 路径存在；生成阶段由机械编译器按 `ExactFileBinding` 计算 `file_sha256`。

## 1. capability_cell_spec.py 最小必填字段（机械生成唯一字段来源）

每个 cell 的 spec JSON 必须包含 `capability_cell_spec.py` 的全部字段，类型与约束以该模块为准；本契约只提供每个字段的语义值或显式 MISSING/NOT_APPLICABLE 状态。机械生成器必须只读 `from_dict/to_dict` 校验，不对 tuple 排序，不做 authority 提升，对任何 `MISSING_REF` 字段 fail-closed。

## 2. 全局限定

1. 所有 cell 的 `commutativity_claim = "NOT_CLAIMED"`。
2. 所有 cell 的 `authority_ceiling` 全 false；C1 的 P1 遗留风险、disposable PostgreSQL 证据、未来-owner 回滚都只作为局部证据，不进入 authority。
3. `entrypoint_kind` 映射：
   - PROGRAM（2 个）: C1.1、C1.2
   - FACADE_VALIDATION（1 个）: C1.3（store/replay rehydration facade，无自有 Program Atom）
4. C1 legacy oracle 统一为 `legacy.workflow-graph.named-observation-oracle.v1`（`legacy_workflow_graph.py` 的 `oracle_id`）。该 oracle 是只读 named-observation 比较 facade，不执行 legacy 编译器/runtime/store；本契约明确它不构成 legacy execution 证据。
5. `declared_lossy_projection_refs` 只引用已声明 loss 的 ref；movement 未声明 loss 时为零 loss 声明，不进入 loss refs。

## 3. C1.1

### 3.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C1.1 |
| family_id | C1 |
| owner_capability_id | `workflow_graph.c1.1`（`C1_OPERATION_OWNER`，RESOLVED） |
| entrypoint_kind | PROGRAM |
| commutativity_claim | NOT_CLAIMED |

### 3.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object 1 | `C1-M001`: LegacyWorkflowGraphDSL plus node and edge validation behavior |
| source object 2 | `C1-M002`: Validated legacy workflow graph with node kinds, configs and ordered dependencies |
| target object | Typed successor Program acceptance object via `c1_legacy_dsl` parse/validate/compile；typed ExecutionPlan with complete semantic digest |
| named transform | `C1-M001`: parse/validate legacy graph DSL into typed successor Program；`C1-M002`: compile validated Program into ordered ExecutionPlan with digest over kind/config/payload/dependencies/catalog/policy |
| movement 行引用 | matrix `#C1-M001`、`#C1-M002`；inventory `#/source_capabilities` 对应行；fragment `#/movements/C1-M001`、`#/movements/C1-M002` |

### 3.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program digest | `10716c6c1979edcf1a910ed8511269522e8e6277fd84797dcdf820e7c2c90e80`（Slice A `program_plan_exact_closure`）；B/C 分别 `f8e1b454…`、`4b3b89ee…` |
| plan digest | `44a83ec41718f710ec35a213b68bdd7cf9b47e5a6f02cfc53c8220d9f9ef2d25`（Slice A）；B/C 分别 `21329d83…`、`287bff84…` |
| program_shape_ref | `mrw.successor.c1.c1-1.program-shape.v1`（RESOLVED_BY_CONTRACT，本契约创建 `evidence/contracts/c1/`） |
| ordered_composition_refs | (`workflow.vector_search.v1`, `workflow.llm_call.v1`, `workflow.join.v1`)（`C1_CONTRACT_KINDS` 声明顺序；编译产物按图序绑定 exact Program/Plan digest，本 cell 不声明固定运行组合） |
| successor interpreter | `successor.c1.legacy-dsl.parse-validate-compile.v1`（RESOLVED_BY_CONTRACT，源于 `C1_SEMANTIC_IDENTITY`；实现面 `c1_legacy_dsl.py`） |
| legacy interpreter | `legacy.workflow-graph.named-observation-oracle.v1`（`legacy_workflow_graph.py`） |
| legacy_oracle_ref | `legacy.workflow-graph.named-observation-oracle.v1` |
| shadow_observation_ref | `evidence/p5-c1-slices/C1SliceA.v1.json#/cell_coverage/C1.1`（compile-closure；B/C 同构） |

### 3.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `mrw.successor.c1.legacy-dsl.v1`、`mrw.successor.c1.legacy-dsl.project-scope.v1`、`mrw.successor.c1.legacy-dsl.program-metadata.v1`（`c1_legacy_dsl.py` metadata 构造，RESOLVED） |
| output | `mrw.functorial-successor.c1.legacy-dsl-receipt.v1`（`C1_LEGACY_DSL_RECEIPT_SCHEMA`）、`mrw.functorial-successor.program-spec.v1`（`C1_PROGRAM_CONTRACT_VERSION`）、`mrw.successor.execution-plan.v1`（ABI） |
| object | `LegacyWorkflowGraphDSL.v1`、`LegacyWorkflowNode.v1`、`LegacyWorkflowEdge.v1`、`WorkflowContext.v1`（eligibility object_types + `C1_WORKFLOW_CONTEXT_TYPE.type_id`） |
| operation | `workflow.vector_search.v1`、`workflow.llm_call.v1`、`workflow.join.v1`（`C1_CONTRACT_KINDS`） |
| profile | `mrw.successor.c1.legacy-dsl.observation.v1`（`C1_OBSERVATION_PROFILE`）、`mrw.successor.c1.c1-1.effect.pure.v1`、`mrw.successor.c1.c1-1.resource.v1`（本契约创建） |
| effect | 纯 CPU/memory 校验与确定性编译；`effect_policy_ref = mrw.successor.c1.c1-1.effect.pure.v1`（RESOLVED_BY_CONTRACT） |
| resource | `O(V+E)` + canonical serialization + SHA-256，显式图/载荷 ceilings 仍为必填；`resource_policy_ref = mrw.successor.c1.c1-1.resource.v1`（RESOLVED_BY_CONTRACT） |
| recovery | 校验失败不留下 artifact/runtime fact，可安全重试；从 exact Program/catalog 重编译，stale digest 拒绝而非静默修复；`recovery_policy_ref = mrw.successor.c1.c1-1.recovery.v1`（RESOLVED_BY_CONTRACT） |
| readback | 不适用（编译为进程内确定性变换，receipt 无持久化 readback 面）；`readback_policy_ref` MISSING_REF/NOT_APPLICABLE，生成必须 fail-closed；按 C2-C6 sentinel 先例申请监督批准（见第 9 节） |
| failure | `C1_DSL_MALFORMED_PAYLOAD`、`C1_DSL_DUPLICATE_NODE_ID`、`C1_DSL_UNSUPPORTED_NODE_TYPE`、`C1_DSL_MISSING_ENDPOINT`、`C1_DSL_CYCLE`、`C1_DSL_COMPILE_FAILURE`、`UNKNOWN_OPERATION_CONTRACT`（`c1_legacy_dsl.py` + `language/validate.py`） |

### 3.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json` (`p1_eligibility`)、`evidence/p1-fragments/C1.json` (`p1_fragment`)、`evidence/semantic-movement/P1P3SuccessorMovementMatrix.v1.json` (`movement_matrix`)、`evidence/semantic-movement/P1P3LegacyDonorSemanticMovementInventory.v1.json` (`donor_inventory`)、`evidence/semantic-movement/fragments/C1.v1.json` (`movement_fragment`)、`main/backend/app/successor_runtime/capabilities/c1_legacy_dsl.py` (`successor_compiler`)、`main/backend/app/successor_migration/legacy_workflow_graph.py` (`legacy_workflow_graph_oracle`)、`evidence/p5-c1-slices/C1SliceA.v1.json`、`C1SliceB.v1.json`、`C1SliceC.v1.json` (`compile_closure_slice_a/b/c`) |
| test | `main/backend/tests/successor_runtime/test_p5_c1_legacy_dsl_parity.py` (`c1_1_legacy_dsl_parity`)、`test_p5_c1_slice_programs.py` (`c1_slice_programs`)、`test_p5_c1_evidence_generator.py` (`c1_evidence_generator`) |
| rollback | `evidence/semantic-movement/fragments/C1.v1.json` (`rollback_movement_fragment`)、`main/backend/app/successor_migration/legacy_workflow_graph.py` (`legacy_rollback_route`)、`test_p5_c1_legacy_dsl_parity.py` (`rollback_parity`) |
| generated | `evidence/semantic-movement/fragments/C1.v1.json`、`evidence/P5C1SliceAcceptance.v1.json` |
| handwritten | `main/backend/app/successor_runtime/capabilities/c1_legacy_dsl.py`、`main/backend/app/successor_runtime/capabilities/c1_slice_acceptance.py`、`main/backend/app/successor_migration/legacy_workflow_graph.py` |

### 3.6 声明 loss、authority、前置与闭合状态

- declared lossy projection: `c1.legacy-dsl.graph-json.loss.v1`（本契约创建；来自 `C1-M001` projection_loss：legacy DSL 不作为第二份 graph JSON 再水合）。
- authority_ceiling: `canonical_write=false, live_provider=false, external_delivery=false, cutover=false, authority_transfer=false`。
- adoption_prerequisites: `C1_SOURCE_PATH_UNDER_CURRENT_DEV_TREE`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。
- 闭合状态: `BLOCKED`。唯一 blocker 为 `readback_policy_ref` MISSING_REF/NOT_APPLICABLE，等待监督 sentinel 批准；本任务不生成 C1.1 spec/manifest。

## 4. C1.2

### 4.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C1.2 |
| family_id | C1 |
| owner_capability_id | `runtime.c1.2.node.v1`（RESOLVED_BY_CONTRACT，源于 movement owner `runtime-core/C1` 与 `RuntimeNode`） |
| entrypoint_kind | PROGRAM |
| commutativity_claim | NOT_CLAIMED |

### 4.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object | `C1-M003`: Legacy graph runtime execution, dependency order and failure behavior |
| target object | Successor RuntimeNode execution with typed outcome, cancellation observation and journal facts |
| named transform | interpret the exact ExecutionPlan under explicit effect, claim and failure boundaries |
| movement 行引用 | matrix `#C1-M003`；fragment `#/movements/C1-M003` |

### 4.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program/plan digest | Slice A/B/C exact digests（`C1Slice*.v1.json` `program_plan_sameness`，legacy/successor same exact Program/Plan） |
| program_shape_ref | `mrw.successor.runtime.c1-2.program-shape.v1`（RESOLVED_BY_CONTRACT，本契约创建） |
| ordered_composition_refs | (`ingest_index.stage_candidate.v1`, `c8.writing.compose.v1`, `c8.writing.stage.v1`, `c8.report.stage.v1`, `c8.report.verify.v1`, `c8.report.admission.v1`, `c8.delivery_intent_prepare.v1`, `delivery.internal_export.v1`)（Slice A/B/C 证据声明顺序；按 slice 的 exact ExecutionPlan 绑定顺序，不构成跨 slice 组合声明） |
| successor interpreter | `successor.c1.runtime-node.v1`（RESOLVED_BY_CONTRACT，实现面 `runtime/node.py` + `substrate/postgres/node_adapter.py`） |
| legacy interpreter | `legacy.workflow-graph.named-observation-oracle.v1` |
| legacy_oracle_ref | `legacy.workflow-graph.named-observation-oracle.v1` |
| shadow_observation_ref | `evidence/p5-c1-slices/C1SliceA.v1.json#/cell_coverage/C1.2`（runtime-replay；B/C 同构） |

### 4.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `mrw.successor.runtime-assignment.v1`、`mrw.successor.execution-plan.v1`、`mrw.successor.program.v1`（ABI 协议常量）、`mrw.runtime.work_item.v1`（runtime 代码） |
| output | `mrw.runtime.run-projection.v1`、`mrw.runtime.ordered-event-closure.v1`、`mrw.runtime.event.authoritative_readback.v1`（runtime 代码）、`mrw.successor.runtime-work-item.v1`（ABI） |
| object | `C1NamedStepObservation.v1`、`C1RuntimeEvidenceRefs.v1`、`C1RollbackBeforeAfter.v1`、`C1SliceAcceptance.v1`（`c1_slice_acceptance.py` 类型）、`RuntimeNode.v1`、`RuntimeAssignment.v1`（`runtime/node.py`、`runtime/assignments.py`） |
| operation | 4.3 的 8 个 slice operation kinds（`_SLICE_OPERATION_KINDS`/切片 ordered_kinds） |
| profile | `mrw.successor.ingest-c7.c7-1.observation.v1`（Slice A）、`mrw.successor.c8.observation.v1`（Slice B/C）、`mrw.successor.runtime.c1-2.effect.v1`、`mrw.successor.runtime.c1-2.resource.v1`（本契约创建） |
| effect | Runtime claim、step activation、effect attempt 与 journal writes；不 implied provider；`effect_policy_ref = mrw.successor.runtime.c1-2.effect.v1`（RESOLVED_BY_CONTRACT） |
| resource | Queue、concurrency、timeout、memory、effect budgets 需要显式绑定；`resource_policy_ref = mrw.successor.runtime.c1-2.resource.v1`（RESOLVED_BY_CONTRACT） |
| recovery | durable journal restart；outcome unknown 需 readback 或 non-start proof 才可 retry；rollback 保留 journal、改变 future-owner epoch；`recovery_policy_ref = mrw.successor.runtime.c1-2.recovery.v1`（RESOLVED_BY_CONTRACT） |
| readback | 适用；`readback:c1:run`、`projector:c1:*:readback` 证据 refs；OUTCOME_UNKNOWN reconcile 不重复 effect；`readback_policy_ref = mrw.successor.runtime.c1-2.readback.v1`（RESOLVED_BY_CONTRACT） |
| failure | `EFFECT_FAILED`、`OUTCOME_UNKNOWN`、`CANCELED`、`REQUIRED_STEP_FAILED`、`LEASE_LOST`、`EXACT_HANDLER_MISMATCH`、`CLAIM_BINDING_MISMATCH`（`runtime/node.py`、`node_adapter.py`、P0C state machine；`CANCELED` 来自 return contract cancel mode） |

### 4.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json` (`p1_eligibility`)、`evidence/p1-fragments/C1.json` (`p1_fragment`)、`evidence/semantic-movement/P1P3SuccessorMovementMatrix.v1.json` (`movement_matrix`)、`evidence/semantic-movement/P1P3LegacyDonorSemanticMovementInventory.v1.json` (`donor_inventory`)、`evidence/semantic-movement/fragments/C1.v1.json` (`movement_fragment`)、`main/backend/app/successor_runtime/capabilities/c1_slice_acceptance.py` (`c1_acceptance_pure_api`)、`main/backend/app/successor_runtime/runtime/node.py` (`successor_runtime_node`)、`main/backend/app/successor_runtime/substrate/postgres/node_adapter.py` (`successor_postgres_node_adapter`)、`main/backend/app/successor_runtime/substrate/postgres/nodes.py` (`successor_postgres_node_store`) |
| test | `main/backend/tests/successor_runtime/test_p5_c1_slice_acceptance_postgres.py` (`c1_2_postgres_gate`)、`c1_slice_postgres_fixture.py` (`c1_2_postgres_fixture`)、`test_p5_c1_legacy_oracle.py` (`c1_legacy_oracle`)、`test_p5_c1_slice_programs.py` (`c1_slice_programs`) |
| rollback | `evidence/p5-c1-slices/C1SliceA.v1.json` (`c1_2_rollback_slice_a`)、`C1SliceB.v1.json` (`c1_2_rollback_slice_b`)、`C1SliceC.v1.json` (`c1_2_rollback_slice_c`)、`main/backend/app/successor_migration/legacy_workflow_graph.py` (`legacy_rollback_route`) |
| generated | `evidence/p5-c1-slices/C1SliceA/B/C.v1.json`、`evidence/P5C1SliceAcceptance.v1.json` |
| handwritten | `main/backend/app/successor_runtime/runtime/node.py`、`main/backend/app/successor_runtime/substrate/postgres/node_adapter.py`、`main/backend/app/successor_runtime/capabilities/c1_slice_acceptance.py`、`main/backend/app/successor_migration/legacy_workflow_graph.py` |

### 4.6 声明 loss、authority 与前置

- declared lossy projection: 无；`C1-M003` 的 projection_loss 是 disposable PostgreSQL/live-provider 限制，不是投影 loss。
- authority_ceiling: 全 false。
- adoption_prerequisites: `C1_M003_TIMEOUT_FAILURE_NOT_EXERCISED`、`C1_SOURCE_PATH_UNDER_CURRENT_DEV_TREE`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 5. C1.3

### 5.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C1.3 |
| family_id | C1 |
| owner_capability_id | `runtime.c1.3.store.v1`（RESOLVED_BY_CONTRACT，源于 movement owner `runtime-storage/C1`） |
| entrypoint_kind | FACADE_VALIDATION |
| commutativity_claim | NOT_CLAIMED |

### 5.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object | `C1-M004`: Legacy compiled-graph store and replay behavior |
| target object | Project-scoped Program, Plan, payload and journal rehydration closure with future-owner rollback |
| named transform | persist exact semantic identities and rehydrate them without hidden cache or global-key drift |
| movement 行引用 | matrix `#C1-M004`；fragment `#/movements/C1-M004` |

### 5.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program/plan digest | Slice A/B/C exact digests；store 只 rehydrate 既有 Program/Plan，不创建新 Program Atom |
| program_shape_ref | `mrw.successor.store.c1-3.surface.v1`（RESOLVED_BY_CONTRACT，rehydration/readback facade surface） |
| ordered_composition_refs | (`runtime.store.rehydrate.v1`,)（RESOLVED_BY_CONTRACT，源于 `C1-M004` named_transform） |
| successor interpreter | `successor.c1.store-replay.v1`（RESOLVED_BY_CONTRACT，实现面 `substrate/postgres/node_adapter.py`、`nodes.py`） |
| legacy interpreter | `legacy.workflow-graph.named-observation-oracle.v1` |
| legacy_oracle_ref | `legacy.workflow-graph.named-observation-oracle.v1` |
| shadow_observation_ref | `evidence/p5-c1-slices/C1SliceA.v1.json#/cell_coverage/C1.3`（store-rollback；B/C 同构） |

### 5.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `mrw.runtime.ordered-event-closure.v1`、`mrw.runtime.event-chain.v1`（runtime 代码）、`mrw.successor.runtime-work-item.v1`（ABI） |
| output | `mrw.runtime.run-projection.v1`、`mrw.runtime.legacy-observation-set.v1`（runtime 代码）、`mrw.functorial-successor.c1-slice-acceptance.v1`（`c1_slice_acceptance.py`） |
| object | `C1NamedStepObservation.v1`、`C1RollbackBeforeAfter.v1`、`C1SliceAcceptance.v1`（`c1_slice_acceptance.py` 类型）、`RuntimeNodeRepository.v1`、`PostgresRuntimeNodeAdapter.v1`（`nodes.py`、`node_adapter.py`） |
| operation | `runtime.store.rehydrate.v1`（RESOLVED_BY_CONTRACT） |
| profile | `mrw.functorial-successor.c1-slice-evidence.v1`（evidence schema）、`mrw.successor.store.c1-3.effect.v1`、`mrw.successor.store.c1-3.resource.v1`（本契约创建） |
| effect | Project-scoped durable store reads/writes；`effect_policy_ref = mrw.successor.store.c1-3.effect.v1`（RESOLVED_BY_CONTRACT） |
| resource | Storage bytes、row count、transaction、replay cost 需显式 ceilings；`resource_policy_ref = mrw.successor.store.c1-3.resource.v1`（RESOLVED_BY_CONTRACT） |
| recovery | exact content 确定性 reload/replay；rollback 改变 future owner 但不删除 journal facts；`recovery_policy_ref = mrw.successor.store.c1-3.recovery.v1`（RESOLVED_BY_CONTRACT） |
| readback | 适用；`readback:c1:run` 证据 refs，rollback 保留 readback refs；`readback_policy_ref = mrw.successor.store.c1-3.readback.v1`（RESOLVED_BY_CONTRACT） |
| failure | `STALE_REVISION`、`INCARNATION_ABA`、`DIGEST_DRIFT`、`BINDING_MISMATCH`、`STORE_UNAVAILABLE`（`C1-M004` failure 文本派生；PG 测试覆盖 ABA/stale-revision） |

### 5.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json` (`p1_eligibility`)、`evidence/p1-fragments/C1.json` (`p1_fragment`)、`evidence/semantic-movement/P1P3SuccessorMovementMatrix.v1.json` (`movement_matrix`)、`evidence/semantic-movement/P1P3LegacyDonorSemanticMovementInventory.v1.json` (`donor_inventory`)、`evidence/semantic-movement/fragments/C1.v1.json` (`movement_fragment`)、`main/backend/app/successor_runtime/capabilities/c1_slice_acceptance.py` (`c1_acceptance_pure_api`)、`main/backend/app/successor_runtime/substrate/postgres/nodes.py` (`successor_postgres_node_store`)、`main/backend/app/successor_runtime/substrate/postgres/node_adapter.py` (`successor_postgres_node_adapter`)、`evidence/P5C1SliceAcceptance.v1.json` (`slice_aggregate_acceptance`) |
| test | `main/backend/tests/successor_runtime/test_p5_c1_slice_acceptance_postgres.py` (`c1_3_postgres_gate`)、`c1_slice_postgres_fixture.py` (`c1_3_postgres_fixture`)、`test_p5_c1_legacy_oracle.py` (`c1_legacy_oracle`) |
| rollback | `evidence/p5-c1-slices/C1SliceA.v1.json` (`c1_3_rollback_slice_a`)、`C1SliceB.v1.json` (`c1_3_rollback_slice_b`)、`C1SliceC.v1.json` (`c1_3_rollback_slice_c`)、`main/backend/app/successor_migration/legacy_workflow_graph.py` (`legacy_rollback_route`) |
| generated | `evidence/p5-c1-slices/C1SliceA/B/C.v1.json`、`evidence/P5C1SliceAcceptance.v1.json` |
| handwritten | `main/backend/app/successor_runtime/substrate/postgres/nodes.py`、`main/backend/app/successor_runtime/substrate/postgres/node_adapter.py`、`main/backend/app/successor_runtime/runtime/node.py`、`main/backend/app/successor_runtime/capabilities/c1_slice_acceptance.py`、`main/backend/app/successor_migration/legacy_workflow_graph.py` |

### 5.6 声明 loss、authority 与前置

- declared lossy projection: `c1.store.legacy_compiled_record.loss.v1`（本契约创建；来自 `C1-M004` projection_loss：legacy globally keyed compiled records 不作为第二份 graph store 迁移）。
- authority_ceiling: 全 false。
- adoption_prerequisites: `C1_M003_TIMEOUT_FAILURE_NOT_EXERCISED`、`C1_SOURCE_PATH_UNDER_CURRENT_DEV_TREE`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 6. 覆盖统计与缺失清单

- 目标 cell 数: 3
- 已覆盖 cell 数: 3（契约覆盖）
- 已闭合 cell 数（本任务生成 spec/manifest）: 2（C1.2、C1.3）
- 未闭合 cell 数: 1（C1.1，仅 `readback_policy_ref`）
- movement 行引用: 4（C1-M001..C1-M004）
- `authority_ceiling` 全 false: 3/3
- `commutativity_claim = NOT_CLAIMED`: 3/3

显式缺失引用清单：

| cell | 字段/引用 | 状态 |
| --- | --- | --- |
| C1.1 | `readback_policy_ref` | MISSING_REF/NOT_APPLICABLE；监督 sentinel 批准前 fail-closed |

## 7. 生成门禁

机械生成 `CapabilityCellSpec` JSON 前必须满足：

1. 本契约中任何 `MISSING_REF` 字段不得自动补值；需独立 review 批准推荐命名后才可解析。
2. `source_bindings`、`test_bindings`、`rollback_bindings` 中每条路径必须存在且路径唯一；`file_sha256` 由机械编译器按 `ExactFileBinding` 规则计算。
3. `authority_ceiling` 必须精确为五个 false 标志；`entrypoint_kind` 必须匹配第 2 节映射。
4. `ordered_composition_refs` 保持声明顺序；`compose_ordered` 只过滤 identity，不做排序/去重/交换。
5. 生成结果只是 `candidate_created=false` 的机械 manifest，不构成 promotion、canonical adoption、live cutover 或 legacy retirement。

## 8. 契约来源与验证记录

- 所有路径以本工作树根为基准；本契约创建时已验证全部 RESOLVED 路径存在。
- `capability_cell_spec.py` 的字段清单来自 `main/backend/app/successor_runtime/specification/capability_cell_spec.py`。
- movement 行来自 `P1P3SuccessorMovementMatrix.v1.json` 与 `semantic-movement/fragments/C1.v1.json`；loss/authority 措辞来自 `P1P3LegacyDonorSemanticMovementInventory.v1.json` 与 `semantic-movement-completeness-standard.md`。
- C1.2/C1.3 的 readback/effect/recovery/resource/program-shape contract refs 由本契约按 movement 行与实现代码派生并创建于 `evidence/contracts/c1/`，`content_digest` 按 C2-C6 同一约定复算。
- 本文档本身不产生或修改任何 spec JSON；后续机械生成器必须以此文档为唯一语义契约输入之一（另一输入为 `capability_cell_spec.py` 校验器本身）。

## 9. 监督 sentinel 申请（C1.1 readback）

按 `ReadbackNotApplicableSentinel.adjudication.v1.json`（C2-C6）先例，申请监督批准 `readback_policy_ref = mrw.successor.runtime.readback.not-applicable.v1` 扩展用于 C1.1，或批准独立 C1 sentinel ref。理由与条件：

- C1.1 是进程内确定性 parse/validate/compile，`C1LegacyDSLReceipt` 不持久化、无 authoritative readback 面；`C1-M001/M002` 的 recovery 是重试/重编译，不是 readback。
- sentinel 只用于 `readback_policy_ref`；`recovery_policy_ref` 保持具体契约（`mrw.successor.c1.c1-1.recovery.v1`）。
- authority_ceiling 保持全 false；candidate null；不构成 promotion/live 证据。
- 批准前 C1.1 spec/manifest 保持 fail-closed 未生成。
