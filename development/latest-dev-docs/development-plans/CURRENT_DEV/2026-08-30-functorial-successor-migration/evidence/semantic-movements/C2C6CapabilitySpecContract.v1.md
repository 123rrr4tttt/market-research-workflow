# C2-C6 Capability Cell Spec 语义契约 v1

## 文档身份

- 文档 ID: `C2C6CapabilitySpecContract.v1`
- 目标 schema: `mrw.functorial_successor.capability_cell_spec.v1`（`main/backend/app/successor_runtime/specification/capability_cell_spec.py`）
- 目标 schema 版本: `1.0.0`
- 状态: `DRAFT_CONTRACT_NOT_GENERATED`（不构成 promotion、cutover、live authority 或候选接受）
- 日期: 2026-09-02（工作树本地起草日期）
- 范围: C2.1-C2.4、C3.1-C3.2、C4.1-C4.3、C5.1-C5.4、C6.1-C6.3，共 16 个 cell
- authority 约定: 所有 cell 的 `authority_ceiling` 五标志全部为 `false`，且 `commutativity_claim` 一律为 `NOT_CLAIMED`

## 输入证据（本契约只读引用，不修改）

- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/P1FunctorizationEligibility.v1.json`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/P2C21CapabilityPacket.v5.json`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/p1-fragments/C2.json` 至 `C6.json`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/p3-fragments/C2.json` 至 `C6.json`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/semantic-movement/P1P3SuccessorMovementMatrix.v1.json`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/semantic-movement/P1P3LegacyDonorSemanticMovementInventory.v1.json`
- `main/backend/app/successor_runtime/specification/capability_cell_spec.py`
- `main/backend/app/successor_runtime/specification/c2_p3.py` 至 `c6_p3.py`
- `main/backend/app/successor_runtime/specification/shared_family_generator.py`
- `docs/governance/semantic-movement-completeness-standard.md`

## 引用状态约定

- `RESOLVED`: ref 名称与来源文件均已在本工作树验证存在。
- `MISSING_REF`: 当前磁盘上没有同名常量或契约文件；只给出推荐命名，机械生成必须 fail-closed，不得自动补值。
- `RESOLVED_INTENTIONAL_ABSENT`: 引用明确指向不存在的路径，且语义上是有意排除（例如 C5.4 的脏源排除）。
- `NOT_APPLICABLE`: 该 cell 语义上不适用；由于 `capability_cell_spec.py` 要求非空字符串，生成前必须显式批准替代 ref 或阻断。
- `EXACT_HASH_PENDING`: 路径存在；生成阶段由机械编译器按 `ExactFileBinding` 计算 `file_sha256`。

## 1. capability_cell_spec.py 最小必填字段（机械生成唯一字段来源）

每个 cell 的 spec JSON 必须包含下列字段；类型与约束以 `capability_cell_spec.py` 为准：

| 字段 | 类型/约束 | 说明 |
| --- | --- | --- |
| `schema` | 固定 `mrw.functorial_successor.capability_cell_spec.v1` | 常量 `SPEC_SCHEMA` |
| `version` | 固定 `1.0.0` | 常量 `SPEC_VERSION` |
| `cell_id` | 非空字符串 | 例如 `C2.1` |
| `family_id` | 非空字符串 | 例如 `C2` |
| `owner_capability_id` | 非空字符串 | 必须与 family bundle/operation owner 一致 |
| `entrypoint_kind` | `PROGRAM` 或 `FACADE_VALIDATION` | 见各 cell |
| `commutativity_claim` | 仅允许 `NOT_CLAIMED` | pilot 不声明交换律 |
| `input_contract_refs` | 非空 tuple/list | 输入 schema/payload refs |
| `output_contract_refs` | 非空 tuple/list | 输出 schema/result refs |
| `object_contract_refs` | 非空 tuple/list | ObjectType refs |
| `operation_contract_refs` | 非空 tuple/list | operation kind refs |
| `program_shape_ref` | 非空字符串 | PROGRAM 用程序形状 ref；FACADE_VALIDATION 用 surface ref |
| `ordered_composition_refs` | 非空 tuple/list；过滤 identity 后必须仍有非 identity ref | 保持声明顺序，不做排序/去重/交换 |
| `interpreter_refs` | 非空 tuple/list | successor 与 legacy interpreter ids |
| `profile_refs` | 非空 tuple/list | observation/interpreter profile refs |
| `deployment_binding_refs` | 非空 tuple/list | catalog/scope/deployment refs |
| `legacy_oracle_ref` | 非空字符串 | legacy interpreter id |
| `shadow_observation_ref` | 非空字符串 | 证据文件内 observation 指针 |
| `failure_union_refs` | 非空 tuple/list | typed failure union |
| `declared_lossy_projection_refs` | tuple/list，允许空 | 声明 loss 的 ref |
| `effect_policy_ref` | 非空字符串 | 缺失时 MISSING_REF |
| `resource_policy_ref` | 非空字符串 | 缺失时 MISSING_REF |
| `recovery_policy_ref` | 非空字符串 | 缺失时 MISSING_REF |
| `readback_policy_ref` | 非空字符串 | 缺失时 MISSING_REF |
| `authority_ceiling` | 恰好 5 个 bool 字段 | `canonical_write`、`live_provider`、`external_delivery`、`cutover`、`authority_transfer` 全 false |
| `adoption_prerequisites` | 非空 tuple/list | 来自 open findings |
| `source_bindings` | 非空 tuple/list of `ExactFileBinding` | 规范化相对路径 + 小写 sha256 + role；全部绑定路径唯一 |
| `test_bindings` | 非空 tuple/list of `ExactFileBinding` | 同上 |
| `rollback_bindings` | 非空 tuple/list of `ExactFileBinding` | 同上 |
| `generated_ownership_refs` | 非空 tuple/list | 生成产物所有权 |
| `handwritten_ownership_refs` | 非空 tuple/list | 手写实现所有权 |

机械生成器必须：只读 `capability_cell_spec.py` 的 `from_dict/to_dict` 校验；不对上述 tuple 排序；不做任何 authority 提升；对任何 `MISSING_REF` 字段 fail-closed。

## 2. 全局限定

1. 所有 cell 的 `commutativity_claim = "NOT_CLAIMED"`。并行/顺序的 effect trace 不声明交换。
2. 所有 cell 的 `authority_ceiling` 全 false；open findings 中任何 `P3_AUTHORITY_RECORD_DIVERGENCE`、live provider、production store/cutover、canonical write 均不进入本契约。
3. `entrypoint_kind` 映射：
   - PROGRAM（11 个）: C2.1、C2.2、C2.3、C3.1、C3.2、C4.1、C4.2、C4.3、C6.1、C6.2、C6.3
   - FACADE_VALIDATION（5 个）: C2.4、C5.1、C5.2、C5.3、C5.4（projector/reconciliation read-model 表面，无 Program Atom）
4. `declared_lossy_projection_refs` 只允许引用已声明 loss 的 ref；零 loss 声明写在 movement 行中，不进入 loss refs。

## 3. C2.1

### 3.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C2.1 |
| family_id | C2 |
| owner_capability_id | `source_library.c2_1.v1` |
| entrypoint_kind | PROGRAM |
| commutativity_claim | NOT_CLAIMED |

### 3.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object 1 | `C2-M001`: Legacy source item taxonomy, search parameters, frontdoor protocol and warnings |
| source object 2 | `C2-M002`: Legacy ordered source-mode precedence including generic-web rejection |
| target object | Typed `SourceResolutionPayload.v1` -> `SourceResolutionResult.v1`（canonical resolved request） |
| named transform | `C2-M001`: legacy normalization helpers + sibling adapter 投影到 canonical typed resolution；`C2-M002`: 冻结的有序 mode precedence 与 generic-web rejection |
| movement 行引用 | `evidence/semantic-movement/P1P3SuccessorMovementMatrix.v1.json#C2-M001`、`#C2-M002`；inventory `#/source_capabilities` 对应行 |

### 3.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program digest | `760a5c374fdcd07a7ee51dede4d558f9cf42ec137fcc4f6b4e997103e6ecb968`（P2 packet `interpreters.same_program_digest`） |
| plan digest | `0f3d7a95ac4e7bfb95cb89a2d449ed8e97c6686936372e65eba01417287155a3`（P2 packet `interpreters.same_plan_digest`） |
| program_shape_ref | MISSING_REF（推荐 `mrw.successor.source-library.c2-1.program-shape.v1`） |
| ordered_composition_refs | (`source_library.resolve_execution_request.v1`,) |
| successor interpreter | `successor.source_library.c2_1.resolve.v1`（`capabilities/source_library_c2_1_interpreters.py`、P2 packet `interpreters.successor.id`） |
| legacy interpreter | `legacy.source_library.c2_1.resolve.v1`（同上） |
| legacy_oracle_ref | `legacy.source_library.c2_1.resolve.v1`；实现来源 `successor_migration/legacy_source_library.py`、`app/services/source_library/item_resolver.py`、`resolver.py` |
| shadow_observation_ref | `evidence/P2C21CapabilityPacket.v5.json#/interpreters`（same_program/same_plan digest 对） |

### 3.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `SOURCE_ITEM_DEFINITION_SCHEMA_REF`、`SOURCE_TAXONOMY_SCHEMA_REF`、`SOURCE_MODE_SCHEMA_REF`、`SOURCE_EXECUTION_REQUEST_SCHEMA_REF`、`SOURCE_LIBRARY_C2_1_PAYLOAD_SCHEMA`（`capabilities/source_library_c2_shared.py`、`source_library_c2_1.py`；P2 packet `schema_contracts`） |
| output | `SOURCE_RESOLUTION_OBSERVATION_SCHEMA_REF`、`SOURCE_WARNING_SCHEMA_REF`、`SOURCE_REJECTION_SCHEMA_REF`（`source_library_c2_shared.py`） |
| object | `SourceItemDefinition.v1`、`SourceTaxonomy.v1`、`SourceMode.v1`、`SourceExecutionRequest.v1`、`SourceResolutionPayload.v1`、`SourceResolutionResult.v1`（`source_library_c2_shared.py`、`source_library_c2_1.py`） |
| operation | `source_library.resolve_execution_request.v1`（`source_library_c2_1.py`） |
| profile | `SOURCE_RESOLUTION_OBSERVATION_PROFILE`；legacy/successor interpreter profile digests `db46ef67733afa45bf3976c56d085b7a9c4cf1496818f8f49f128f1dc26d3c45`/`b162fd1284ae7517c962c448ca7e9265b0f3591d6a9bb093c458f795be19f264`（P2 packet `interpreters`） |
| effect | 纯确定性 normalization；`effect_policy_ref` MISSING_REF（推荐 `mrw.successor.source-library.c2-1.effect.pure.v1`） |
| resource | `RESOURCE_CEILING_SCHEMA_REF`、`mrw.successor.source-library.c2-1.resource-ceiling.v1`（P2 packet `resource_ceiling.schema_ref`）、`mrw.functorial-successor.deadline.c2-1.v1`（`source_library_c2_1.py`） |
| recovery | 确定性 replay；`recovery_policy_ref` MISSING_REF（推荐 `mrw.successor.source-library.c2-1.recovery.v1`） |
| readback | 不适用；`readback_policy_ref` MISSING_REF/NOT_APPLICABLE，生成必须 fail-closed |
| failure | `INVALID_INPUT`、`INVALID_ITEM`、`INVALID_MODE`、`FORBIDDEN_INTERNAL_ADAPTER`、`RESOURCE_CEILING_EXCEEDED`（`source_library_c2_1.py`）；required successor union `Resolved | Rejected | ResolutionWarning`（eligibility C2.1） |

### 3.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json` (`p1_eligibility`)、`evidence/p1-fragments/C2.json` (`p1_fragment`)、`evidence/P2C21CapabilityPacket.v5.json` (`p2_packet`)、`main/backend/app/successor_migration/legacy_source_library.py` (`legacy_donor`)、`main/backend/app/services/source_library/item_resolver.py` (`legacy_donor_c2_1`)、`main/backend/app/services/source_library/resolver.py` (`legacy_donor_c2_1`) |
| test | `main/backend/tests/successor_runtime/test_p2_c2_1_contracts.py` (`c2_1_contracts`)、`test_p2_c2_1_parity.py` (`c2_1_parity`)、`test_p3_c2_1_rehydration_postgres.py` (`c2_1_rehydration_postgres`) |
| rollback | `evidence/P2C21CapabilityPacket.v5.json` (`rollback_evidence`)、`main/backend/app/successor_migration/legacy_source_library.py` (`legacy_rollback_route`)、`test_p2_c2_1_parity.py` (`rollback_parity`) |
| generated | `evidence/P2C21CapabilityPacket.v5.json` |
| handwritten | `capabilities/source_library_c2_1.py`、`capabilities/source_library_c2_1_interpreters.py`、`capabilities/source_library_c2_shared.py`、`successor_migration/legacy_source_library.py` |

### 3.6 声明 loss、authority 与前置

- declared lossy projection: 无；movement `C2-M001/M002` 建议 explicit zero loss。
- authority_ceiling: `canonical_write=false, live_provider=false, external_delivery=false, cutover=false, authority_transfer=false`。
- adoption_prerequisites: `P3_AUTHORITY_RECORD_DIVERGENCE`、`P3_C2_CHAIN_REHYDRATION_LOCAL_ONLY`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 4. C2.2

### 4.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C2.2 |
| family_id | C2 |
| owner_capability_id | `source_library.c2_2.v1` |
| entrypoint_kind | PROGRAM |
| commutativity_claim | NOT_CLAIMED |

### 4.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object | `C2-M003/M004/M005/M006`: legacy protocol-search、provider-harvest、site-search、URL-execution orchestration |
| target object | 四种 typed ordered plan: `source_library.protocol_search.v1`、`source_library.provider_harvest.v1`、`source_library.site_search.v1`、`source_library.url_execution.v1` |
| named transform | compile 各 mode 为 exact ordered source task plan；site-search 强制 handler.cluster；generic-web 内部拒绝 |
| movement 行引用 | matrix `#C2-M003`、`#C2-M004`、`#C2-M005`、`#C2-M006` |

### 4.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program digest | `e04de866cc5ba84631aa6fae35426c4c0e3655f59f34d2f07cd05e059d607db8`（fragment C2 `/cells/0/program_digest/value`） |
| plan digest | `65a7947b255644b3267dcad3bf263896819e2dd4bb09e7dd3d9a5e9ccd17c371`（fragment `/cells/0/plan_digest/value`） |
| program_shape_ref | MISSING_REF（推荐 `mrw.successor.source-library.c2-2.program-shape.v1`） |
| ordered_composition_refs | (`source_library.protocol_search.v1`, `source_library.provider_harvest.v1`, `source_library.site_search.v1`, `source_library.url_execution.v1`) 或按 fragment `operation_bindings` 的声明顺序 |
| successor interpreter | `successor.source_library.c2_2.plan.v1`（`source_library_c2_2_interpreters.py`） |
| legacy interpreter | `legacy.source_library.c2_2.four_modes.v1`（`successor_migration/legacy_source_library_c2_2.py`） |
| legacy_oracle_ref | `legacy.source_library.c2_2.four_modes.v1` |
| shadow_observation_ref | `evidence/p3-fragments/C2.json#/cells/0/successor_observation` |

### 4.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `SOURCE_EXECUTION_REQUEST_SCHEMA_REF`、`SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA`、`PROVIDER_HANDOFF_SCHEMA`（`source_library_c2_shared.py`） |
| output | `SOURCE_MODE_PLAN_SCHEMA`、`SOURCE_MODE_TASK_SCHEMA`、`COLLECTION_TERMINAL_SCHEMA`（`source_library_c2_shared.py`） |
| object | `SourceModePlanningPayload.v1`、`SourceModePlan.v1`、`SourceModePlanningResult.v1`、`SourceCollectionTerminal.v1`（`source_library_c2_shared.py`） |
| operation | 四个 mode kinds（`source_library_c2_shared.py`） |
| profile | `SOURCE_MODE_PLANNING_OBSERVATION_PROFILE`（`source_library_c2_shared.py`） |
| effect | 纯 plan 构造；`effect_policy_ref` MISSING_REF（推荐 `mrw.successor.source-library.c2-2.effect.pure.v1`）；`orchestration_policy_ref=mrw.successor.source-library.c2-2.policy.v1`（`c2_p3.py`） |
| resource | `C2_2_RESOURCE_CEILING_REF`、`mrw.successor.source-library.c2-2.deadline.v1`（`source_library_c2_2.py`） |
| recovery | plan retained、future-owner rollback；`recovery_policy_ref` MISSING_REF（推荐 `mrw.successor.source-library.c2-2.recovery.v1`） |
| readback | 不适用；`readback_policy_ref` MISSING_REF/NOT_APPLICABLE |
| failure | `C2_2_PLANNING_FAILURE_CODES`（`source_library_c2_shared.py`）；eligibility required union `Completed | PartiallyCompleted | ProviderAccepted | Rejected | Failed | Cancelled | OutcomeUnknown` |

### 4.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json` (`p1_eligibility`)、`evidence/p1-fragments/C2.json` (`p1_fragment`)、`evidence/P2C21CapabilityPacket.v5.json` (`p2_packet`)、`app/services/source_library/orchestrators/protocol_search.py` (`legacy_donor_c2_2`)、`provider_harvest.py`、`site_search.py`、`url_execution.py`、`single_channel.py`、`app/services/source_library/runner.py` (`legacy_donor_c2_3`) |
| test | `test_p3_c2_2_contracts.py` (`c2_2_contracts`)、`test_p3_c2_2_parity.py` (`c2_2_parity`)、`test_p3_c2_23_runtime_canary_postgres.py` (`c2_23_runtime_canary`) |
| rollback | `evidence/p3-fragments/C2.json` (`/cells/0/rollback_observation`)、`successor_migration/legacy_source_library_c2_2.py` (`legacy_rollback_route`)、`test_p3_c2_2_parity.py` (`rollback_parity`) |
| generated | `evidence/p3-fragments/C2.json`、`scripts/generate_successor_p3_c2_fragment.py` 输出面 |
| handwritten | `capabilities/source_library_c2_shared.py`、`source_library_c2_2.py`、`source_library_c2_2_interpreters.py`、`source_library_c2_2_program.py`、`successor_migration/legacy_source_library_c2_2.py`、`substrate/postgres/source_library_c2_23_canary.py`、`specification/c2_p3.py` |

### 4.6 声明 loss、authority 与前置

- declared lossy projection: 无；movement 建议 explicit zero loss。
- authority_ceiling: 全 false。
- adoption_prerequisites: `P3_AUTHORITY_RECORD_DIVERGENCE`、`C2_2_DURABLE_RUNTIME_NODE_LOCAL_ONLY`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 5. C2.3

### 5.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C2.3 |
| family_id | C2 |
| owner_capability_id | `source_library.c2_3.v1` |
| entrypoint_kind | PROGRAM |
| commutativity_claim | NOT_CLAIMED |

### 5.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object | `C2-M007`: Legacy provider credential resolution, dispatch outcome and recovery behavior |
| target object | `source_library.execute_provider_effect.v1` with opaque credential ref、attempt、receipt、readback |
| named transform | 通过 explicit provider-effect port 执行，并以 exact readback reconcile 后才 retry |
| movement 行引用 | matrix `#C2-M007` |

### 5.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program digest | `e9b287a359518ccdc125327f8880530cf27b89f2ba197771a5989b1cf066a0f0`（fragment `/cells/1/program_digest/value`） |
| plan digest | `eb057bcd5191df4daf88099ee4958b3435035bec93fe5e2e4c26c668fa103907`（fragment `/cells/1/plan_digest/value`） |
| program_shape_ref | MISSING_REF（推荐 `mrw.successor.source-library.c2-3.program-shape.v1`） |
| ordered_composition_refs | (`source_library.execute_provider_effect.v1`,) |
| successor interpreter | `successor.source_library.c2_3.provider_effect.v1`（fragment `/cells/1/successor_observation`） |
| legacy interpreter | `legacy.source_library.c2_3.provider_effect.v1`（`successor_migration/legacy_source_library_c2_3.py`） |
| legacy_oracle_ref | `legacy.source_library.c2_3.provider_effect.v1` |
| shadow_observation_ref | `evidence/p3-fragments/C2.json#/cells/1/successor_observation` |

### 5.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `CREDENTIAL_REF_SCHEMA`、`PROVIDER_EFFECT_REQUEST_SCHEMA`（= `SOURCE_LIBRARY_C2_3_PAYLOAD_SCHEMA`）、`RESOURCE_POLICY_SCHEMA`（`source_library_c2_shared.py`） |
| output | `PROVIDER_RECEIPT_SCHEMA`、`CAPTURED_SOURCE_RECORD_REF_SCHEMA`、`STAGED_ARTIFACT_REF_SCHEMA`（`source_library_c2_shared.py`） |
| object | `ProviderEffectRequest.v1`、`ProviderEffectOutcome.v1`、`CredentialRef.v1`、`ProviderReceipt.v1`、`CapturedSourceRecordRef.v1`、`StagedArtifactRef.v1`（`source_library_c2_shared.py`） |
| operation | `source_library.execute_provider_effect.v1` |
| profile | `SOURCE_PROVIDER_EFFECT_OBSERVATION_PROFILE`（`source_library_c2_shared.py`） |
| effect | provider effect boundary（fixture only）；`effect_policy_ref` MISSING_REF（推荐 `mrw.successor.source-library.c2-3.effect.v1`） |
| resource | `C2_3_RESOURCE_POLICY_REF`、`mrw.successor.source-library.c2-3.deadline.v1`（`source_library_c2_3.py`） |
| recovery | 终端 readback adopt once、非 start proof 后才可 redispatch；`recovery_policy_ref` MISSING_REF（推荐 `mrw.successor.source-library.c2-3.recovery.v1`） |
| readback | `ProviderReceipt`/`OUTCOME_UNKNOWN reconcile` 证据在 fragment `/cells/1`；`readback_policy_ref` MISSING_REF（推荐 `mrw.successor.source-library.c2-3.readback.v1`） |
| failure | `C2_3_FAILURE_CODES`（`source_library_c2_shared.py`）；eligibility required union `Completed | Accepted | PartiallyCompleted | Rejected | Failed | Cancelled | OutcomeUnknown | Reconciled` |

### 5.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json`、`evidence/p1-fragments/C2.json`、`evidence/P2C21CapabilityPacket.v5.json`、`app/services/source_library/runner.py` (`legacy_donor_c2_3`) |
| test | `test_p3_c2_3_contracts.py` (`c2_3_contracts`)、`test_p3_c2_3_recovery.py` (`c2_3_recovery`)、`test_p3_c2_3_parity.py` (`c2_3_parity`)、`test_p3_c2_23_runtime_canary_postgres.py` (`c2_23_runtime_canary`) |
| rollback | `evidence/p3-fragments/C2.json` (`/cells/1/rollback_observation`)、`successor_migration/legacy_source_library_c2_3.py` (`legacy_rollback_route`)、`test_p3_c2_3_recovery.py` (`recovery_rollback`) |
| generated | `evidence/p3-fragments/C2.json` |
| handwritten | `capabilities/source_library_c2_3.py`、`source_library_c2_3_ports.py`、`source_library_c2_3_test_interpreters.py`、`source_library_c2_shared.py`、`successor_migration/legacy_source_library_c2_3.py`、`substrate/postgres/source_library_c2_23_canary.py`、`specification/c2_p3.py` |

### 5.6 声明 loss、authority 与前置

- declared lossy projection: 无；movement 建议 explicit zero loss for typed local receipt/failure state。
- authority_ceiling: 全 false。
- adoption_prerequisites: `P3_AUTHORITY_RECORD_DIVERGENCE`、`C2_3_LIVE_PROVIDER_AUTHORITY_NOT_FROZEN`、`C2_2_DURABLE_RUNTIME_NODE_LOCAL_ONLY`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 6. C2.4

### 6.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C2.4 |
| family_id | C2 |
| owner_capability_id | `source_library.c2_4.v1` |
| entrypoint_kind | FACADE_VALIDATION |
| commutativity_claim | NOT_CLAIMED |

### 6.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object | `C2-M008`: Legacy terminal output and compatibility status |
| target object | Non-authoritative C2.4 terminal compatibility read model |
| named transform | 把 admitted journal closure 投影为 terminal/compat views，绑定 source-bound offsets |
| movement 行引用 | matrix `#C2-M008`（DECLARED_LOSS） |

### 6.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program/plan digest | `null`；projection 无 Program Atom（fragment `/cells/2`） |
| program_shape_ref | `successor.source_library.c2_4.terminal_compat.v1`（`SOURCE_LIBRARY_C2_4_PROJECTOR_ID`，`capabilities/source_library_c2_4_projection.py`）作为 facade surface |
| ordered_composition_refs | (`source_library.project_terminal_compat.v1`,)（fragment `operation_bindings` role `projector_registry`） |
| successor projector | `successor.source_library.c2_4.terminal_compat.v1` version `1.0.0`（fragment `/cells/2/successor_observation`） |
| legacy interpreter | `legacy.source_library.c2_4.terminal_compat.v1`（`successor_migration/legacy_source_library_c2_4.py`） |
| legacy_oracle_ref | `legacy.source_library.c2_4.terminal_compat.v1` |
| shadow_observation_ref | `evidence/p3-fragments/C2.json#/cells/2/successor_observation` |

### 6.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `COLLECTION_TERMINAL_SCHEMA`、`PROVIDER_RECEIPT_SCHEMA`、`SourceCollectionProjectionSource`（`source_library_c2_4_projection.py`、`source_library_c2_shared.py`） |
| output | `SOURCE_LIBRARY_TERMINAL_OBSERVATION_PROFILE`（terminal/compat/authority summary 输出，`source_library_c2_4_projection.py`） |
| object | `SourceLibraryTerminalOutput.v1`、`SourceLibraryCompatProjection.v1`、`SourceLibraryAuthorityOutput.v1`、`FrontdoorIngress.v1`（eligibility C2.4 + `source_library_c2_4_projection.py`） |
| operation | `source_library.project_terminal_compat.v1`（fragment `operation_bindings`，`contract_digest=null`） |
| profile | `SOURCE_LIBRARY_TERMINAL_OBSERVATION_PROFILE` |
| effect | 纯 projector + projection-store apply/delete/rebuild；`effect_policy_ref` MISSING_REF（推荐 `mrw.successor.source-library.c2-4.effect.pure.v1`） |
| resource | `mrw.functorial-successor.deadline.c2-4.v1`（`source_library_c2_4_projection.py`）；`resource_policy_ref` MISSING_REF（推荐 `mrw.successor.source-library.c2-4.resource.v1`） |
| recovery | delete/rebuild digest-equivalent；`rollback_read_routing()`（`substrate/projections/source_library_terminal.py`）；`recovery_policy_ref` MISSING_REF（推荐 `mrw.successor.source-library.c2-4.recovery.v1`） |
| readback | 不适用；`readback_policy_ref` MISSING_REF/NOT_APPLICABLE |
| failure | `ProjectionRejected(MALFORMED_OBSERVATION|UNSUPPORTED_VERSION)`、`ProjectionFailed(PROJECTOR_ERROR)`、`ProjectionStale`（eligibility C2.4） |

### 6.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json`、`evidence/p1-fragments/C2.json`、`evidence/P2C21CapabilityPacket.v5.json`、`app/services/source_library/terminal_output.py` (`legacy_donor_c2_4`) |
| test | `test_p3_c2_4_projection.py` (`c2_4_projection`)、`test_p3_c2_4_postgres.py` (`c2_4_postgres`) |
| rollback | `evidence/p3-fragments/C2.json` (`/cells/2/rollback_observation`)、`substrate/projections/source_library_terminal.py` (`rollback_read_routing`)、`successor_migration/legacy_source_library_c2_4.py` (`legacy_rollback_route`)、`test_p3_c2_4_postgres.py` (`rollback_postgres`) |
| generated | `evidence/p3-fragments/C2.json` |
| handwritten | `capabilities/source_library_c2_4_projection.py`、`substrate/projections/source_library_terminal.py`、`successor_migration/legacy_source_library_c2_4.py`、`specification/c2_p3.py` |

### 6.6 声明 loss、authority 与前置

- declared lossy projection: `source_library.c2_4.compat.loss.v1`（`DECLARED_LOSS_PROFILE_REF`，RESOLVED；fragment `/cells/2/successor_observation/loss_profile_ref`）。
- authority_ceiling: 全 false；projection 永远非 canonical/control authority。
- adoption_prerequisites: `P3_AUTHORITY_RECORD_DIVERGENCE`、`C2_4_SOURCE_CLOSURE_AND_OFFSET_NOT_LIVE`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 7. C3.1

### 7.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C3.1 |
| family_id | C3 |
| owner_capability_id | `collect.c3_1.v1` |
| entrypoint_kind | PROGRAM |
| commutativity_claim | NOT_CLAIMED |

### 7.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object 1 | `C3-M001`: Legacy ordered collection batch plan and element traversal |
| source object 2 | `C3-M002`: Legacy serial or parallel element execution and fail-fast policy |
| target object | `Then(TraverseOrdered, MapOutput(sequence_to_fold_payload), FoldAtom)` Program 与 exact ExecutionPlan |
| named transform | materialize ordered batch elements with exact occurrence/payload closure；有序执行 + typed cancellation receipts |
| movement 行引用 | matrix `#C3-M001`、`#C3-M002` |

### 7.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program digest | `71edc28643bd713685bda9dc0fcd54b797c61c6e6c1ac3450965862223407070`（fragment `/cells/0`） |
| plan digest | `88b1d08664edb4f95cdf4b3c0b2b32cd4d1367277a408149f418f727094f76a0`（fragment `/cells/0`） |
| program_shape_ref | MISSING_REF（推荐 `mrw.successor.collect.c3-1.program-shape.v1`；shape 为 composed Then+MapOutput+Fold） |
| ordered_composition_refs | (`collect.execute_batch_element.v1`, `mrw.traverse_ordered.materialize`, `collect.fold_ordered_results.v1`)（fragment `operation_bindings` 顺序） |
| successor interpreter | `successor.collect_runtime.batch_traverse.v1`（`collect_c3_interpreters.py`） |
| legacy interpreter | `legacy.collect_runtime.batch_traverse.v1`（`legacy_collect_runtime.py`） |
| legacy_oracle_ref | `legacy.collect_runtime.batch_traverse.v1` |
| shadow_observation_ref | `evidence/p3-fragments/C3.json#/cells/0/successor_observation` |

### 7.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `COLLECT_REQUEST_SCHEMA_REF`、`COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF`、`COLLECT_BATCH_ELEMENT_SCHEMA_REF`、`COLLECT_BATCH_PLAN_SCHEMA_REF`、`COLLECT_RESOURCE_POLICY_SCHEMA_REF`（`collect_c3.py`） |
| output | `COLLECT_ELEMENT_OUTCOME_SCHEMA_REF`、`COLLECT_TRAVERSAL_OBSERVATION_SCHEMA_REF`、`COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF`（`collect_c3.py`） |
| object | `CollectBatchElement.v1`、`CollectBatchPlan.v1`、`OrderedCollectElementOutcomeSequence.v1`、`CollectElementSucceeded|CollectElementFailed`（`collect_c3.py`） |
| operation | `collect.execute_batch_element.v1`、`mrw.traverse_ordered.materialize` |
| profile | `COLLECT_TRAVERSAL_OBSERVATION_PROFILE` |
| effect | element effects explicit；`effect_policy_ref` MISSING_REF（推荐 `mrw.successor.collect.c3-1.effect.v1`） |
| resource | `COLLECT_RESOURCE_POLICY_SCHEMA_REF`、`mrw.functorial-successor.deadline.collect-c3.v1`（`collect_c3.py`）；`resource_policy_ref` 使用 `CollectResourcePolicy` 的 `policy_digest` 绑定（MISSING_REF 若需独立常量） |
| recovery | journal/payload closure rehydrate；`recovery_policy_ref` MISSING_REF（推荐 `mrw.successor.collect.c3-1.recovery.v1`） |
| readback | 不适用（元素 effect 由 C2.3 类 readback 承接）；`readback_policy_ref` MISSING_REF/NOT_APPLICABLE |
| failure | `COLLECT_ELEMENT_ERROR_CODES`、`BatchBypassed | SingletonIdentity | OrderedTraversalCompleted | OrderedTraversalAborted`（`collect_c3.py` + eligibility C3.1） |

### 7.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json`、`evidence/p1-fragments/C3.json`、`evidence/P2C21CapabilityPacket.v4.json`、`app/services/collect_runtime/runtime.py`、`contracts.py`、`display_meta.py`、`adapters/crawler_scrapy.py`、`adapters/source_library.py`、`language/compile.py|program.py|plan.py|normalize.py|validate.py|transforms.py`（role `legacy_donor_c3`/`shared_dependency_traverse_ordered`） |
| test | `test_p3_c3_contracts.py`、`test_p3_c3_micro.py`、`test_p3_c3_replay_shadow.py`、`test_p3_c3_rollback.py`、`test_p3_c3_canary_postgres.py`、`test_p3_c3_fragment.py` |
| rollback | `evidence/p3-fragments/C3.json` (`/cells/0/rollback_observation`)、`successor_migration/legacy_collect_runtime.py` (`legacy_rollback_route`)、`test_p3_c3_rollback.py` (`rollback_tests`) |
| generated | `evidence/p3-fragments/C3.json` |
| handwritten | `capabilities/collect_c3.py`、`collect_c3_program.py`、`collect_c3_interpreters.py`、`successor_migration/legacy_collect_runtime.py`、`substrate/postgres/collect_c3_canary.py`、`specification/c3_p3.py` |

### 7.6 声明 loss、authority 与前置

- declared lossy projection: 无（movement 建议 zero loss for ordered element identity/occurrence）。
- authority_ceiling: 全 false。
- adoption_prerequisites: `P3_AUTHORITY_RECORD_DIVERGENCE`、`C3_POSTGRES_CANARY_DISPOSABLE_ONLY`、`C3_LIVE_PROVIDER_AUTHORITY_NOT_FROZEN`、`C3_DURABLE_RUNTIME_NODE_NOT_PROVEN`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 8. C3.2

### 8.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C3.2 |
| family_id | C3 |
| owner_capability_id | `collect.c3_2.v1` |
| entrypoint_kind | PROGRAM |
| commutativity_claim | NOT_CLAIMED |

### 8.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object | `C3-M003`: Legacy heterogeneous results, errors and dispatch acknowledgements |
| target object | Typed ordered aggregate preserving successes, failures and receipts |
| named transform | left-to-right fold by input_index；queued acknowledgement 不等于 completion |
| movement 行引用 | matrix `#C3-M003` |

### 8.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program digest | `d08516c54d193b4b87c8a2b8452a9743f213bd36b7b85be43a94a245674bf493`（fragment `/cells/1`） |
| plan digest | `caa0f3c4183c53401e798ba8ff70d9741e87ec622b3c2766b4259dcd9f336f80`（fragment `/cells/1`） |
| program_shape_ref | MISSING_REF（推荐 `mrw.successor.collect.c3-2.program-shape.v1`；named pure fold realized as TRANSFORM） |
| ordered_composition_refs | (`collect.fold_ordered_results.v1`,)（fragment `operation_bindings`） |
| successor interpreter | `successor.collect_runtime.result_fold.v1`（`collect_c3_interpreters.py`） |
| legacy interpreter | `legacy.collect_runtime.result_fold.v1` |
| legacy_oracle_ref | `legacy.collect_runtime.result_fold.v1` |
| shadow_observation_ref | `evidence/p3-fragments/C3.json#/cells/1/successor_observation` |

### 8.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `COLLECT_ELEMENT_OUTCOME_SCHEMA_REF`、`COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF`、`OrderedCollectElementOutcomeSequence`（`collect_c3.py`） |
| output | `COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF`（`collect_c3.py`） |
| object | `CollectElementOutcome.v1`、`CollectAttemptReceipt.v1`、`CollectAggregateOutcome.v1`（`collect_c3.py`） |
| operation | `collect.fold_ordered_results.v1` |
| profile | `COLLECT_FOLD_OBSERVATION_PROFILE` |
| effect | 确定性纯 fold；`effect_policy_ref` MISSING_REF（推荐 `mrw.successor.collect.c3-2.effect.pure.v1`） |
| resource | `COLLECT_FOLD_RESOURCE_CEILING_SCHEMA_REF`、`COLLECT_RECEIPT_DEDUPE_STABLE_FIRST_REF`、`COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF|FAIL_FAST_REF`（`collect_c3.py`） |
| recovery | unconsumed outcomes returned on fold-contract failure；`recovery_policy_ref` MISSING_REF（推荐 `mrw.successor.collect.c3-2.recovery.v1`） |
| readback | receipt 保留但 readback 不属于 fold；`readback_policy_ref` MISSING_REF/NOT_APPLICABLE |
| failure | `FOLD_CONTRACT_FAILURE`、`AGGREGATE_ALL_FAILED`、`QUEUED_ACK_NOT_COMPLETION`（`collect_c3.py`）+ eligibility union `CollectAggregateSucceeded|Partial|Failed|FoldContractFailure` |

### 8.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | 同 C3.1 family source bindings |
| test | `test_p3_c3_contracts.py`、`test_p3_c3_micro.py`、`test_p3_c3_replay_shadow.py`、`test_p3_c3_rollback.py`、`test_p3_c3_canary_postgres.py`、`test_p3_c3_fragment.py` |
| rollback | `evidence/p3-fragments/C3.json` (`/cells/1/rollback_observation`)、`successor_migration/legacy_collect_runtime.py`、`test_p3_c3_rollback.py` |
| generated | `evidence/p3-fragments/C3.json` |
| handwritten | `capabilities/collect_c3.py`、`collect_c3_program.py`、`collect_c3_interpreters.py`、`successor_migration/legacy_collect_runtime.py`、`specification/c3_p3.py` |

### 8.6 声明 loss、authority 与前置

- declared lossy projection: 本 cell 无；下游 display/compat 投影的 ownership/loss 由 C2.4 等声明。
- authority_ceiling: 全 false。
- adoption_prerequisites: 同 C3.1 列表。

## 9. C4.1

### 9.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C4.1 |
| family_id | C4 |
| owner_capability_id | `agent_batch.c4.v1` |
| entrypoint_kind | PROGRAM |
| commutativity_claim | NOT_CLAIMED |

### 9.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object 1 | `C4-M001`: Legacy natural-language batch plan with source supplementation |
| source object 2 | `C4-M002`: Legacy branching and task-cardinality expansion |
| target object | Typed C4 batch plan with explicit no-match、ordered tasks、optional branching |
| named transform | base plan + eligible-mode supplementation；broad-before-precision branching；source_mode 不写入 C4 vocabulary |
| movement 行引用 | matrix `#C4-M001`、`#C4-M002` |

### 9.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program digest | `487e6787551bdad4579d9d4cbfc369b09173bdffecfef129b096d79d4a742d9c`（fragment `/cells/0`） |
| plan digest | `a1563476c3ae48b20410827234192ac73719fb6ba34225e9ee1f56100700b233`；traversal plan `d35eed6440cd8bab1e6ca10e43b94890ef95dbbcbefb4c6066944c886c31171a`；shape `bf88c549b568a178bf6f9e2ec770fed64141254fb4cff4684bde55d593e25fd2` |
| program_shape_ref | MISSING_REF（推荐 `mrw.successor.agent-batch.c4-1.program-shape.v1`；single-Atom + STATIC_SHAPE TraverseOrdered） |
| ordered_composition_refs | (`agent_batch.build_batch_plan.v1`,)（fragment `operation_bindings`） |
| successor interpreter | `successor.agent_batch.batch_plan.pure.v1`（`agent_batch_c4_interpreters.py`） |
| legacy interpreter | `legacy.agent_batch.nl_command.plan.v1` |
| legacy_oracle_ref | `legacy.agent_batch.nl_command.plan.v1` |
| shadow_observation_ref | `evidence/p3-fragments/C4.json#/cells/0/successor_observation` |

### 9.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `BATCH_PLAN_PAYLOAD_SCHEMA`（`mrw.successor.agent-batch.c4-1.payload.v1`）、`C2ProducerSnapshotView`（`agent_batch_c4.py`、`tests/successor_runtime/p3_c4_fixture.py`） |
| output | `BatchPlan.v1`、`SearchBrief.v1`、`SupplementationDecision.v1`、`BranchingDecision.v1`（`agent_batch_c4.py`） |
| object | `AgentBatchTask.v1`、`SourceCandidateSet.v1`、`SupplementationDecision.v1`、`BranchingDecision.v1`、`BatchPlan.v1` |
| operation | `agent_batch.build_batch_plan.v1` |
| profile | `BATCH_PLAN_OBSERVATION_PROFILE` |
| effect | 纯 plan 构造；`effect_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-batch.c4-1.effect.pure.v1`） |
| resource | task/query/candidate ceilings；`mrw.functorial-successor.deadline.c4.v1`（`agent_batch_c4.py`）；`resource_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-batch.c4-1.resource.v1`） |
| recovery | exact input replan、retained plan；`recovery_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-batch.c4-1.recovery.v1`） |
| readback | 不适用；`readback_policy_ref` MISSING_REF/NOT_APPLICABLE |
| failure | `INVALID_PLAN`、`SOURCE_CANDIDATE_READ_FAILED`、`SOURCE_MODE_WRITE_FORBIDDEN`（`agent_batch_c4.py`）+ eligibility union `BatchPlanReady|SupplementationSkipped|SourceCandidateReadFailed|InvalidPlan` |

### 9.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json`、`evidence/p1-fragments/C4.json`、`app/services/agent_batch/agent_loop.py` (`legacy_donor_c4_1_c4_2`)、`task_contract.py`、`app/api/agent_batch.py` |
| test | `test_p3_c4_1_plan.py`、`test_p3_c4_1_program.py`、`test_p3_c4_1_parity.py` |
| rollback | `evidence/p3-fragments/C4.json` (`/cells/0/rollback_observation`)、`successor_migration/legacy_agent_batch.py` (`legacy_rollback_route`)、`test_p3_c4_1_parity.py` |
| generated | `evidence/p3-fragments/C4.json` |
| handwritten | `capabilities/agent_batch_c4.py`、`agent_batch_c4_program.py`、`agent_batch_c4_interpreters.py`、`successor_migration/legacy_agent_batch.py`、`specification/c4_p3.py`、`tests/successor_runtime/p3_c4_fixture.py` |

### 9.6 声明 loss、authority 与前置

- declared lossy projection: legacy `source_mode` rewrite 有意不投影进 C4 vocabulary（movement `C4-M001` 声明；无现有 ref 常量，MISSING_REF 推荐 `agent_batch.c4.source_mode_rewrite.loss.v1`）。
- authority_ceiling: 全 false。
- adoption_prerequisites: `P3_AUTHORITY_RECORD_DIVERGENCE`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 10. C4.2

### 10.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C4.2 |
| family_id | C4 |
| owner_capability_id | `agent_batch.c4.v1` |
| entrypoint_kind | PROGRAM |
| commutativity_claim | NOT_CLAIMED |

### 10.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object | `C4-M003`: Legacy retry action, task rewrites and reconstructed budget |
| target object | Typed retry reducer with durable budget and fresh AttemptIntent |
| named transform | reduce prior outcome/policy 为至多一个 ordered retry；不提交 |
| movement 行引用 | matrix `#C4-M003` |

### 10.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program digest | `80bc00bb19ffbce8983a14a5dcdf17130ad48140d111efdfeca407186e55ad94`（fragment `/cells/1`） |
| plan digest | `c863bf9542a6415a9bc0f1c0ba5147be61c271fb94bb64a206091b148c5e3141`（fragment `/cells/1`） |
| program_shape_ref | MISSING_REF（推荐 `mrw.successor.agent-batch.c4-2.program-shape.v1`） |
| ordered_composition_refs | (`agent_batch.reduce_retry_action.v1`,) |
| successor interpreter | `successor.agent_batch.retry_action.reducer.v1` |
| legacy interpreter | `legacy.agent_batch.retry_loop.v1` |
| legacy_oracle_ref | `legacy.agent_batch.retry_loop.v1` |
| shadow_observation_ref | `evidence/p3-fragments/C4.json#/cells/1/successor_observation` |

### 10.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `RETRY_REDUCER_PAYLOAD_SCHEMA`（`mrw.successor.agent-batch.c4-2.payload.v1`）、`RetryAction.v1`、`RetryBudget.v1`（`agent_batch_c4.py`） |
| output | `RetryTransition.v1`、`RetryAttemptIntent.v1` |
| object | `RetryAction.v1`、`RetryBudget.v1`、`RetryReducerInput.v1`、`RetryTransition.v1`、`RetryAttemptIntent.v1` |
| operation | `agent_batch.reduce_retry_action.v1` |
| profile | `RETRY_REDUCE_OBSERVATION_PROFILE` |
| effect | 纯 reducer；`effect_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-batch.c4-2.effect.pure.v1`） |
| resource | budget monotone non-increasing、at most one retry；`mrw.functorial-successor.deadline.c4.v1`；`resource_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-batch.c4-2.resource.v1`） |
| recovery | fresh attempt intent 交给 submission owner；prior attempt 保持 durable；`recovery_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-batch.c4-2.recovery.v1`） |
| readback | 不适用；`readback_policy_ref` MISSING_REF/NOT_APPLICABLE |
| failure | `RETRY_ACTION_INVALID`（`agent_batch_c4.py`）+ eligibility union `RetryScheduled|RetrySkipped|RetryRejected|RetryEffectFailed` |

### 10.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | 同 C4 family source bindings |
| test | `test_p3_c4_2_retry_reducer.py`、`test_p3_c4_1_parity.py` |
| rollback | `evidence/p3-fragments/C4.json` (`/cells/1/rollback_observation`)、`successor_migration/legacy_agent_batch.py`、`test_p3_c4_2_retry_reducer.py` |
| generated | `evidence/p3-fragments/C4.json` |
| handwritten | `capabilities/agent_batch_c4.py`、`agent_batch_c4_program.py`、`agent_batch_c4_interpreters.py`、`successor_migration/legacy_agent_batch.py`、`specification/c4_p3.py` |

### 10.6 声明 loss、authority 与前置

- declared lossy projection: source-mode rewriting 在 C4 边界显式拒绝（movement `C4-M003`；MISSING_REF 推荐同上 `agent_batch.c4.source_mode_rewrite.loss.v1`）。
- authority_ceiling: 全 false。
- adoption_prerequisites: `P3_AUTHORITY_RECORD_DIVERGENCE`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 11. C4.3

### 11.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C4.3 |
| family_id | C4 |
| owner_capability_id | `agent_batch.c4.v1` |
| entrypoint_kind | PROGRAM |
| commutativity_claim | NOT_CLAIMED |

### 11.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object 1 | `C4-M004`: Legacy submit API and process-local idempotency behavior |
| source object 2 | `C4-M005`: Legacy restart, ambiguous dispatch and rollback behavior |
| target object | Typed `agent_batch.submit.v1` request、durable idempotency record、receipt、readback adoption |
| named transform | reserve exact capability-scoped logical request；STARTED -> TERMINAL；crash replay adopts persisted receipt |
| movement 行引用 | matrix `#C4-M004`、`#C4-M005` |

### 11.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program digest | `084912d66057ebf47389385d9defacfab3db1708e5b75cd43a1fb9ed3a0e6a35`（fragment `/cells/2`） |
| plan digest | `90417c684e2ce1772fc1d5742038be37e7ec0eb98dbec61ba0a7ca1a3764f5a1`（fragment `/cells/2`） |
| program_shape_ref | MISSING_REF（推荐 `mrw.successor.agent-batch.c4-3.program-shape.v1`） |
| ordered_composition_refs | (`agent_batch.submit.v1`,) |
| successor interpreter | `successor.agent_batch.submission.typed.v1`（`agent_batch_c4_interpreters.py`；fragment successor observation 记录 `contract_owner=agent_batch.c4.v1` 与 typed receipt-only acceptance） |
| legacy interpreter | `legacy.agent_batch.submit_api.v1`（fragment `/cells/2/legacy_observation`） |
| legacy_oracle_ref | `legacy.agent_batch.submit_api.v1` |
| shadow_observation_ref | `evidence/p3-fragments/C4.json#/cells/2/successor_observation` |

### 11.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `AgentBatchSubmission.v1`（`mrw.successor.agent-batch.c4-3.payload.v1`）、`authority_snapshot_ref`、`resource_request_ref=resource:request:p3-c4-fragment`（`agent_batch_c4.py`、`c4_p3.py`） |
| output | `BatchSubmitReceipt.v1`、`IdempotencyBinding.v1`、`DispatchAttempt.v1`（eligibility C4.3 + `agent_batch_c4.py`） |
| object | `AgentBatchSubmission.v1`、`AgentBatchSubmissionItem.v1`、`AgentBatchSubmissionDigest.v1`、`IdempotencyBinding.v1`、`BatchRunRef.v1`、`DispatchAttempt.v1`、`BatchSubmitReceipt.v1` |
| operation | `agent_batch.submit.v1` |
| profile | `SUBMISSION_OBSERVATION_PROFILE` |
| effect | durable idempotency/receipt store writes；reviewed provider calls zero；`effect_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-batch.c4-3.effect.v1`） |
| resource | PostgreSQL transaction/row/payload ceilings；`substrate/postgres/idempotency.py` (`shared_IdempotencyRepository_adapter`)；`resource_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-batch.c4-3.resource.v1`） |
| recovery | crash-before-terminal replay、rollback rehearsal `successor_disabled_legacy_enabled_no_dual_claim`；`recovery_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-batch.c4-3.recovery.v1`） |
| readback | `persisted_receipt_readback_adoption`（fragment `/cells/2/successor_observation`）；`readback_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-batch.c4-3.readback.v1`） |
| failure | `IDEMPOTENCY_CONFLICT`（`agent_batch_c4.py`）+ eligibility union `SubmissionAccepted|PartiallyAccepted|Rejected|Replay|IdempotencyConflict|AuthorityRejected|ResourceRejected|DispatchEffectFailed|OutcomeUnknown` |

### 11.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json`、`evidence/p1-fragments/C4.json`、`app/api/agent_batch.py` (`legacy_donor_c4_3`)、`app/services/agent_batch/task_contract.py` |
| test | `test_p3_c4_3_submission.py`、`test_p3_c4_canary.py`、`test_p3_c4_4_postgres.py`、`test_p3_c4_5_runtime_postgres.py` |
| rollback | `evidence/p3-fragments/C4.json` (`/cells/2/rollback_observation`)、`successor_migration/legacy_agent_batch.py`、`test_p3_c4_5_runtime_postgres.py`、`substrate/postgres/agent_batch_c4_3_handler.py` |
| generated | `evidence/p3-fragments/C4.json` |
| handwritten | `capabilities/agent_batch_c4.py`、`agent_batch_c4_program.py`、`agent_batch_c4_interpreters.py`、`successor_migration/legacy_agent_batch.py`、`substrate/postgres/agent_batch_c4.py|agent_batch_c4_canary.py|agent_batch_c4_3_handler.py|idempotency.py`、`specification/c4_p3.py` |

### 11.6 声明 loss、authority 与前置

- declared lossy projection: acceptance status 只存在于 typed receipt，不从 generic DB enum 投影（movement `C4-M004` 声明；MISSING_REF 推荐 `agent_batch.c4.generic_enum.loss.v1`）。
- authority_ceiling: 全 false。
- adoption_prerequisites: `P3_AUTHORITY_RECORD_DIVERGENCE`、`C4_3_DURABLE_ADOPTION_NOT_PROMOTED`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 12. C5.1

### 12.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C5.1 |
| family_id | C5 |
| owner_capability_id | `agent_session.task_transition.v1` |
| entrypoint_kind | FACADE_VALIDATION |
| commutativity_claim | NOT_CLAIMED |

### 12.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object | `C5-M001`: Legacy AgentSession and AgentTask read model |
| target object | Journal-derived non-authoritative session and task projection |
| named transform | fold exact runtime events into bounded session/task status |
| movement 行引用 | matrix `#C5-M001`（MOVED_TO） |

### 12.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program/plan digest | `null`；read-only projection（fragment `/cells/0`） |
| program_shape_ref | `successor.agent_session.journal_projection.v1`（fragment `/cells/0/successor_observation/projector_id`）作为 facade surface |
| ordered_composition_refs | (`agent_session.task_transition.v1`,)（fragment `operation_bindings` role `projector_registry`） |
| successor projector | `successor.agent_session.journal_projection.v1` version `1.0.0` |
| legacy interpreter | `legacy.agent_sessions.read_only_replay.v1`（`c5_p3.py`；`successor_migration/legacy_agent_sessions.py`） |
| legacy_oracle_ref | `legacy.agent_sessions.read_only_replay.v1` |
| shadow_observation_ref | `evidence/p3-fragments/C5.json#/cells/0/successor_observation` |

### 12.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `ReplayEvent`/runtime event schemas（`runtime/replay.py`）；legacy read model schemas `mrw.migration.legacy-agent-session.v1`、`mrw.migration.legacy-agent-task.v1`（`successor_migration/legacy_agent_sessions.py`） |
| output | `AgentSessionSnapshot.v1`（`mrw.successor.agent-session-snapshot.v1`）、`AgentTaskSnapshot.v1`（`mrw.successor.agent-task-snapshot.v1`）（`substrate/projections/agent_session.py`） |
| object | `AgentSession`、`AgentTask`、`TaskDependency`、`TaskLease`、`TaskStatus`、`SessionStatus`（eligibility C5.1 + `agent_session.py`） |
| operation | `agent_session.task_transition.v1`（candidate；fragment `operation_bindings`，`contract_digest=null`） |
| profile | projector version `1.0.0`；无独立 profile 常量，MISSING_REF（推荐 `mrw.successor.agent-session.journal-projection.v1`） |
| effect | 纯 fold + projection-store write；legacy rows 保持 read-only；`effect_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-session.c5-1.effect.pure.v1`） |
| resource | event count/replay/projection row ceilings（eligibility C5.1）；`resource_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-session.c5-1.resource.v1`） |
| recovery | rebuild from exact journal source digest；`recovery_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-session.c5-1.recovery.v1`） |
| readback | 不适用；`readback_policy_ref` MISSING_REF/NOT_APPLICABLE |
| failure | eligibility C5.1 union `TransitionApplied|InvalidTransition|TaskNotFound|SessionNotFound|DependencyUnresolved|WriteSetConflict|StaleRevision|LeaseExpired|StoreUnavailable` |

### 12.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json`、`evidence/p1-fragments/C5.json`、`evidence/C5_4LocatorAdjudication.v1.json`、`app/services/agent_sessions/service.py|store.py` (`legacy_donor_c5_1_c5_3`) |
| test | `test_p3_c5_1_session_projection.py` |
| rollback | `evidence/p3-fragments/C5.json` (`/cells/0/rollback_observation`)、`successor_migration/legacy_agent_sessions.py`、`test_p3_c5_1_session_projection.py` |
| generated | `evidence/p3-fragments/C5.json` |
| handwritten | `substrate/projections/agent_session.py`、`runtime/replay.py`、`successor_migration/legacy_agent_sessions.py`、`specification/c5_p3.py` |

### 12.6 声明 loss、authority 与前置

- declared lossy projection: legacy control-plane mutability 有意不进入 projection（movement `C5-M001` 声明；MISSING_REF 推荐 `agent_session.c5-1.control_mutability.loss.v1`）。
- authority_ceiling: 全 false。
- adoption_prerequisites: `P3_AUTHORITY_RECORD_DIVERGENCE`、`C5_1_SESSION_TASK_CONTROL_NOT_MIGRATED`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 13. C5.2

### 13.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C5.2 |
| family_id | C5 |
| owner_capability_id | `runtime.effect.reconcile.v1` |
| entrypoint_kind | FACADE_VALIDATION |
| commutativity_claim | NOT_CLAIMED |

### 13.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object 1 | `C5-M002`: Legacy effect-attempt record and readback locator |
| source object 2 | `C5-M003`: Legacy ambiguous provider outcome and authoritative readback |
| target object | Typed exact AttemptObservation -> `EffectReconciler`/`PostgresReconciliationOwner` adoption result |
| named transform | replay legacy attempt into exact binding；exact readback 一次 adopt |
| movement 行引用 | matrix `#C5-M002`、`#C5-M003` |

### 13.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program/plan digest | `null`；reuse existing reconciler，无新 Program Atom（fragment `/cells/1`） |
| program_shape_ref | `runtime.effect.reconcile.v1`（fragment `operation_bindings` kind）作为 facade surface |
| ordered_composition_refs | (`runtime.effect.reconcile.v1`,) |
| successor interpreter | `successor.c5.reconciliation.v1`（fragment `/cells/1/successor_observation`） |
| legacy interpreter | `legacy.c5.attempt_replay.v1`（fragment `/cells/1/legacy_observation`；profile `legacy.c5.interpreter`） |
| legacy_oracle_ref | `legacy.c5.attempt_replay.v1` |
| shadow_observation_ref | `evidence/p3-fragments/C5.json#/cells/1/successor_observation` |

### 13.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `ExactLegacyAttemptBinding`（`mrw.migration.exact-legacy-attempt-binding.v1`）、`RuntimeAssignment`（`runtime/assignments.py`）、`LegacyInterpreterProfile`（`successor_migration/legacy_effect_attempts.py`） |
| output | `EffectAttemptObservation`、`AuthoritativeEffectReadback`、`ReconciliationResult`（`runtime/reconciliation.py`）；`LegacyAttemptReplayEvidence`（`mrw.migration.legacy-attempt-evidence.v1`） |
| object | `CapabilityCall`、`ToolCallExecutionRecord`、`EffectAttemptObservation`、`AuthoritativeEffectReadback`（eligibility C5.2 + `reconciliation.py`） |
| operation | `runtime.effect.reconcile.v1` |
| profile | `LegacyInterpreterProfile`；readback profile `readback-profile:p3-c5`（`c5_p3.py`） |
| effect | read-only replay + durable reconciliation transition；provider calls zero；`effect_policy_ref` MISSING_REF（推荐 `mrw.successor.runtime.c5-2.effect.v1`） |
| resource | bounded readback/PostgreSQL transaction；`resource_policy_ref` MISSING_REF（推荐 `mrw.successor.runtime.c5-2.resource.v1`） |
| recovery | `RecoveryBinding(recovery_handler_id="authoritative-readback")`；adoption idempotent、no duplicate dispatch；`recovery_policy_ref` MISSING_REF（推荐 `mrw.successor.runtime.c5-2.recovery.v1`） |
| readback | `AuthoritativeEffectReadback` + `readback-profile:p3-c5`（RESOLVED in `c5_p3.py`）；`readback_policy_ref` MISSING_REF（推荐 `mrw.successor.runtime.c5-2.readback.v1`） |
| failure | eligibility C5.2 union `EffectSucceeded|EffectFailed|OutcomeUnknown|AuthoritativeReadbackSucceeded|Failed|ReadbackUnavailable|NonStartProven|NonStartUnprovable|BindingMismatch|ApprovalRequired|CanceledBeforeEffect` |

### 13.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json`、`evidence/p1-fragments/C5.json`、`app/services/agent_runtime/run_loop.py|interactive_agent.py` (`legacy_donor_c5_2`) |
| test | `test_p3_c5_2_attempt_replay_reconciliation.py`、`test_p3_c5_2_reconciliation_postgres.py` |
| rollback | `evidence/p3-fragments/C5.json` (`/cells/1/rollback_observation`)、`successor_migration/legacy_effect_attempts.py`、`test_p3_c5_2_reconciliation_postgres.py` |
| generated | `evidence/p3-fragments/C5.json` |
| handwritten | `runtime/reconciliation.py`、`runtime/assignments.py`、`successor_migration/legacy_effect_attempts.py`、`specification/c5_p3.py` |

### 13.6 声明 loss、authority 与前置

- declared lossy projection: 无；movement 建议 explicit zero loss for exact attempt identity/outcome uncertainty。
- authority_ceiling: 全 false。
- adoption_prerequisites: `P3_AUTHORITY_RECORD_DIVERGENCE`、`C5_2_DURABLE_ATTEMPT_NODE_NOT_PROVEN`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 14. C5.3

### 14.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C5.3 |
| family_id | C5 |
| owner_capability_id | `runtime.event.project.v1` |
| entrypoint_kind | FACADE_VALIDATION |
| commutativity_claim | NOT_CLAIMED |

### 14.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object | `C5-M004`: Legacy session event feed and mutable terminal snapshots |
| target object | Journal replay、fold snapshot、source-bound projector |
| named transform | replay canonical runtime events into digest-bound session/task read model |
| movement 行引用 | matrix `#C5-M004`（MOVED_TO） |

### 14.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program/plan digest | `null`（fragment `/cells/2`） |
| program_shape_ref | `successor.agent_session.fold_snapshot.v1`（fragment projector_id）作为 facade surface |
| ordered_composition_refs | (`runtime.event.project.v1`,) |
| successor projector | `successor.agent_session.fold_snapshot.v1` version `1.0.0` |
| legacy interpreter | `legacy.agent_sessions.event_feed.v1`（`c5_p3.py`） |
| legacy_oracle_ref | `legacy.agent_sessions.event_feed.v1` |
| shadow_observation_ref | `evidence/p3-fragments/C5.json#/cells/2/successor_observation` |

### 14.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `ReplayEvent`（`mrw.runtime.event.*.v1`，`runtime/replay.py`） |
| output | `RuntimeReplayProjection`、`AgentSessionSnapshot.v1`、`AgentTaskSnapshot.v1`（`runtime/replay.py`、`substrate/projections/agent_session.py`） |
| object | `AgentEvent`、`AgentSessionSnapshot`、`AgentTaskSnapshot`、`ProjectionOffset`、`RuntimeReplayProjection`（eligibility C5.3 + `runtime/replay.py`） |
| operation | `runtime.event.project.v1` |
| profile | projector version `1.0.0`；MISSING_REF（推荐 `mrw.successor.agent-session.fold-snapshot.v1`） |
| effect | read-only journal replay + projection-store write；`effect_policy_ref` MISSING_REF（推荐 `mrw.successor.runtime.c5-3.effect.pure.v1`） |
| resource | replay event/projection rebuild ceilings；`resource_policy_ref` MISSING_REF（推荐 `mrw.successor.runtime.c5-3.resource.v1`） |
| recovery | delete/rebuild digest-equivalent、source incarnation exact；`recovery_policy_ref` MISSING_REF（推荐 `mrw.successor.runtime.c5-3.recovery.v1`） |
| readback | 不适用；`readback_policy_ref` MISSING_REF/NOT_APPLICABLE |
| failure | eligibility C5.3 union `ProjectionApplied|ProjectionUnchanged|ProjectionRebuilt|EventGap|SequenceConflict|SourceDigestMismatch|ProjectionDigestMismatch|UnsupportedEvent|StoreUnavailable` |

### 14.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json`、`evidence/p1-fragments/C5.json`、`app/services/agent_sessions/service.py|store.py` |
| test | `test_p3_c5_3_projection_postgres.py` |
| rollback | `evidence/p3-fragments/C5.json` (`/cells/2/rollback_observation`)、`successor_migration/legacy_agent_sessions.py`、`test_p3_c5_3_projection_postgres.py` |
| generated | `evidence/p3-fragments/C5.json` |
| handwritten | `runtime/replay.py`、`substrate/projections/agent_session.py`、`successor_migration/legacy_agent_sessions.py`、`specification/c5_p3.py` |

### 14.6 声明 loss、authority 与前置

- declared lossy projection: projection 只含 bounded session/task status、不含 full journal（movement `C5-M004` 声明；MISSING_REF 推荐 `runtime.c5-3.journal_detail.loss.v1`）。
- authority_ceiling: 全 false。
- adoption_prerequisites: `P3_AUTHORITY_RECORD_DIVERGENCE`、`C5_3_SESSION_PROJECTION_OFFSET_NOT_OWNED`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 15. C5.4

### 15.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C5.4 |
| family_id | C5 |
| owner_capability_id | `legacy.runtime_observation.project.v1` |
| entrypoint_kind | FACADE_VALIDATION |
| commutativity_claim | NOT_CLAIMED |

### 15.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object 1 | `C5-M005`: Legacy Celery AsyncResult, ETL job and process-log observations |
| source object 2 | `C5-M006`: Multiple legacy process observations with possible contradiction or no runtime binding |
| target object | Typed offline `LegacySourceObservation` 与 join projection（OBSERVED/CONTRADICTORY/STALE/UNBOUND） |
| named transform | capture each source independently with exact source digest；join without terminal authority |
| movement 行引用 | matrix `#C5-M005`、`#C5-M006` |

### 15.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program/plan digest | `null`（fragment `/cells/3`） |
| program_shape_ref | `successor.legacy_process_observation_join.v1`（fragment projector_id）作为 facade surface |
| ordered_composition_refs | (`legacy.runtime_observation.project.v1`,) |
| successor projector | `successor.legacy_process_observation_join.v1` version `1.0.0` |
| legacy interpreter | `legacy.process_readback.v1`（fragment `/cells/3/legacy_observation`） |
| legacy_oracle_ref | `legacy.process_readback.v1` |
| shadow_observation_ref | `evidence/p3-fragments/C5.json#/cells/3/successor_observation` |

### 15.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `LegacySourceObservation`（`mrw.runtime.legacy-observation.v1`）、`ObservationSourceKind`（`runtime/observations.py`） |
| output | `ProcessTaskObservationJoin`（`mrw.runtime.process-task-join.v1`）、`LegacyProcessObservationProjection`（`mrw.runtime.legacy-process-projection.v1`）（`runtime/observations.py`、`substrate/projections/legacy_process.py`） |
| object | `CeleryTaskObservation`、`CeleryWorkerObservation`、`EtlJobRunObservation`、`ProcessLogObservation`、`ObservationSourceBinding`（eligibility C5.4 + `runtime/observations.py`） |
| operation | `legacy.runtime_observation.project.v1` |
| profile | `ObservationClass`（OBSERVED/UNAVAILABLE/STALE/CONTRADICTORY/UNBOUND）、`ObservationFreshness`（`runtime/observations.py`） |
| effect | offline read-only capture + pure join projection；`effect_policy_ref` MISSING_REF（推荐 `mrw.successor.runtime.c5-4.effect.pure.v1`） |
| resource | bounded source count/join memory；`resource_policy_ref` MISSING_REF（推荐 `mrw.successor.runtime.c5-4.resource.v1`） |
| recovery | recapture/rejoin from captured observations；`recovery_policy_ref` MISSING_REF（推荐 `mrw.successor.runtime.c5-4.recovery.v1`） |
| readback | readback never control；`readback_policy_ref` MISSING_REF（推荐 `mrw.successor.runtime.c5-4.readback.v1`） |
| failure | `SourceBindingMismatch`、`ObservationUnavailable|Stale|Contradictory|Unbound`、`UnsupportedSourceState`、`ProjectionWriteFailed`（`substrate/projections/legacy_process.py` + eligibility C5.4） |

### 15.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json`、`evidence/p1-fragments/C5.json`、`evidence/C5_4LocatorAdjudication.v1.json`、`app/api/agent_batch.py|process.py` (`legacy_donor_c5_4_supplementary`)、`app/services/tasks.py`、`app/celery_app.py` (`legacy_donor_c5_4_normative`)、`app/models/entities.py` (`legacy_donor_c5_4`) |
| test | `test_p3_c5_4_process_observations.py`、`test_p3_c5_0_evidence_generator.py` |
| rollback | `evidence/p3-fragments/C5.json` (`/cells/3/rollback_observation`)、`successor_migration/legacy_process_observations.py`、`test_p3_c5_4_process_observations.py` |
| generated | `evidence/p3-fragments/C5.json` |
| handwritten | `runtime/observations.py`、`substrate/projections/legacy_process.py`、`successor_migration/legacy_process_observations.py`、`specification/c5_p3.py` |

### 15.6 声明 loss、authority 与前置

- declared lossy projection: raw backend detail 被 normalized，但 provenance/contradiction/unbound 必须保留（movement `C5-M005/M006` 声明；MISSING_REF 推荐 `runtime.c5-4.raw_detail.loss.v1`）。
- 显式未采用路径（RESOLVED_INTENTIONAL_ABSENT）: `main/backend/app/services/task_readback_metadata.py`（脏源排除，禁止绑定）。
- authority_ceiling: 全 false。
- adoption_prerequisites: `P3_AUTHORITY_RECORD_DIVERGENCE`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 16. C6.1

### 16.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C6.1 |
| family_id | C6 |
| owner_capability_id | `agent_core.c6_1.v1` |
| entrypoint_kind | PROGRAM |
| commutativity_claim | NOT_CLAIMED |

### 16.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object | `C6-M001`: Legacy AgentCore synchronous model and tool loop |
| target object | Bounded `agent_core.episode_interpret.v1` Program 与 RuntimeNode episode |
| named transform | interpret ordered model steps、tool calls、permission pause/resume、cancellation、final answer |
| movement 行引用 | matrix `#C6-M001` |

### 16.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program digest | `aa9174d1023cc7bb5d1973a97c83fec5c639d4f18d169e47676cd9dcd82cead5`（fragment `/cells/0`） |
| plan digest | `3a8dad0148dda36e2ae1ddcf7c7d8ee18dc912014997bf70deb9b976cdd00103`（fragment `/cells/0`） |
| program_shape_ref | MISSING_REF（推荐 `mrw.successor.agent-core.c6-1.program-shape.v1`） |
| ordered_composition_refs | (`agent_core.episode_interpret.v1`,) |
| successor interpreter | `successor.agent_core.c6_1.episode.v1`（`agent_core_c6_1_interpreters.py`） |
| legacy interpreter | `legacy.agent_core.c6_1.episode.v1` |
| legacy_oracle_ref | `legacy.agent_core.c6_1.episode.v1`；实现 `successor_migration/legacy_agent_core.py` |
| shadow_observation_ref | `evidence/p3-fragments/C6.json#/cells/0/successor_observation` |

### 16.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `AGENT_CORE_C6_1_PAYLOAD_SCHEMA`、`AGENT_TURN_REQUEST_SCHEMA_REF`、`AGENT_MODEL_STEP_SCHEMA_REF`、`AGENT_TOOL_CALL_SCHEMA_REF`（`agent_core_c6_1.py`、`agent_core_c6_common.py`） |
| output | `AGENT_TURN_EVENT_SCHEMA_REF`、`AGENT_TURN_EPISODE_SCHEMA_REF`（`agent_core_c6_1.py`） |
| object | `AgentTurnRequest.v1`、`AgentTurnEvent.v1`、`AgentTurnEpisode.v1`、`CoreModelStep`、`CoreToolCall`、`CoreToolResult`（`agent_core_c6_common.py`、`agent_core_c6_1.py`） |
| operation | `agent_core.episode_interpret.v1` |
| profile | `AGENT_CORE_C6_1_OBSERVATION_PROFILE` |
| effect | model/tool-loop interpretation；raw-value persistence 禁止；`effect_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-core.c6-1.effect.v1`） |
| resource | tool-call/iteration ceilings；`mrw.successor.agent-core.c6-1.deadline.v1`（`agent_core_c6_1.py`）；`resource_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-core.c6-1.resource.v1`） |
| recovery | permission pause resume same call；journal retained、future owner legacy；`recovery_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-core.c6-1.recovery.v1`） |
| readback | 不适用（durable effects 由 capability interpreter 承接）；`readback_policy_ref` MISSING_REF/NOT_APPLICABLE |
| failure | eligibility C6.1 union `tool_schema_validation_failed|tool_permission_denied|tool_not_registered|unsupported_model_step|session_canceled` 及 `FINAL_ANSWER|NO_MORE_TOOLS|PERMISSION_REQUESTED|MAX_TOOL_CALLS_EXCEEDED|MAX_ITERATIONS_EXCEEDED|...` |

### 16.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json`、`evidence/p1-fragments/C6.json`、`app/services/agent_core/core.py` (`legacy_donor_c6_1`)、`contracts.py`、`fake_provider.py|native_provider.py|json_provider.py` (`legacy_donor_c6_2`)、`provider_trace.py`、`app/services/agent_runtime/run_loop.py` |
| test | `test_p3_c6_1_episode.py`、`test_p3_c6_legacy_shadow.py`、`test_p3_c6_evidence.py` |
| rollback | `evidence/p3-fragments/C6.json` (`/cells/0/rollback_observation`)、`successor_migration/legacy_agent_core.py`、`test_p3_c6_legacy_shadow.py` |
| generated | `evidence/p3-fragments/C6.json` |
| handwritten | `capabilities/agent_core_c6_common.py`、`agent_core_c6_1.py|agent_core_c6_1_program.py|agent_core_c6_1_interpreters.py`、`successor_migration/legacy_agent_core.py`、`substrate/postgres/agent_core_c6_worker.py|agent_core_c6_handler.py|agent_core_c6_canary.py`、`specification/c6_p3.py` |

### 16.6 声明 loss、authority 与前置

- declared lossy projection: 无；movement 建议 zero loss for local fixtures。
- authority_ceiling: 全 false。
- adoption_prerequisites: `P3_AUTHORITY_RECORD_DIVERGENCE`、`P3C6_PRODUCTION_RUNTIME_NODE_NOT_PROVEN`、`P3C6_LOOP_LIVE_MODEL_NOT_PROVEN`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 17. C6.2

### 17.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C6.2 |
| family_id | C6 |
| owner_capability_id | `agent_core.c6_2.v1` |
| entrypoint_kind | PROGRAM |
| commutativity_claim | NOT_CLAIMED |

### 17.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object | `C6-M002`: Legacy provider/model invocation and fallback behavior |
| target object | `agent.model_step.v1` explicit provider port with attempt receipt and readback |
| named transform | invoke bound provider step without global settings；exact typed outcome；fallback 不静默投影 |
| movement 行引用 | matrix `#C6-M002` |

### 17.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program digest | `423c84b2aa16c6506eccde75ef756790ea5e053e3e6d56798a4ca3849057a370`（fragment `/cells/1`） |
| plan digest | `b784116ed5c0a033a6725f3b18436616ffd2fa8bdf6022c49444dc545eb31759`（fragment `/cells/1`） |
| program_shape_ref | MISSING_REF（推荐 `mrw.successor.agent-core.c6-2.program-shape.v1`） |
| ordered_composition_refs | (`agent.model_step.v1`,) |
| successor interpreter | `successor.agent_core.c6_2.provider.v1`（`agent_core_c6_2_interpreters.py`） |
| legacy interpreter | `legacy.agent_core.c6_2.provider.v1` |
| legacy_oracle_ref | `legacy.agent_core.c6_2.provider.v1` |
| shadow_observation_ref | `evidence/p3-fragments/C6.json#/cells/1/successor_observation` |

### 17.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `AGENT_CORE_C6_2_PAYLOAD_SCHEMA`、`AGENT_MODEL_STEP_REQUEST_SCHEMA_REF`、`tool_contract_refs`、`provider_profile_ref`、`credential_ref`（`agent_core_c6_2.py`） |
| output | `AGENT_MODEL_STEP_RESULT_SCHEMA_REF`、`PROVIDER_ATTEMPT_RECEIPT_SCHEMA_REF`、`PROVIDER_READBACK_SCHEMA_REF`（`agent_core_c6_2.py`） |
| object | `ProviderAttemptReceipt.v1`、`ProviderReadback.v1`、`AgentModelStepRequest.v1`、`AgentModelStepResult.v1`（`agent_core_c6_2.py`） |
| operation | `agent.model_step.v1` |
| profile | `AGENT_CORE_C6_2_OBSERVATION_PROFILE`、`readback_profile_ref=PROVIDER_READBACK_SCHEMA_REF` |
| effect | provider effect boundary；当前 fixture/scripted、live provider calls zero；`effect_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-core.c6-2.effect.v1`） |
| resource | `mrw.successor.agent-core.c6-2.deadline.v1`（`agent_core_c6_2.py`）；token/cost/concurrency ceilings；`resource_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-core.c6-2.resource.v1`） |
| recovery | exact readback resolves outcome unknown；non-start proof permits retry；`recovery_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-core.c6-2.recovery.v1`） |
| readback | `PROVIDER_READBACK_SCHEMA_REF`、`readback_status`（AUTHORITATIVE_READBACK_SUCCEEDED/FAILED/NON_START_PROOF）；`readback_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-core.c6-2.readback.v1`） |
| failure | `PROVIDER_FAILURE_CODES`（`ProviderUnavailable|ProviderInvocationFailed|ProviderProtocolInvalid|ProviderTimeout|ProviderRateLimited|ProviderCredentialRejected|ProviderFallbackSelected|ProviderOutcomeUnknown`，`agent_core_c6_2.py`） |

### 17.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json`、`evidence/p1-fragments/C6.json`、`app/services/agent_core/contracts.py`、`fake_provider.py|native_provider.py|json_provider.py` (`legacy_donor_c6_2`) |
| test | `test_p3_c6_2_provider.py`、`test_p3_c6_legacy_shadow.py` |
| rollback | `evidence/p3-fragments/C6.json` (`/cells/1/rollback_observation`)、`successor_migration/legacy_agent_core.py`、`test_p3_c6_2_provider.py` |
| generated | `evidence/p3-fragments/C6.json` |
| handwritten | `capabilities/agent_core_c6_2.py|agent_core_c6_2_program.py|agent_core_c6_2_interpreters.py`、`agent_core_c6_common.py`、`successor_migration/legacy_agent_core.py`、`substrate/postgres/agent_core_c6_*.py`、`specification/c6_p3.py` |

### 17.6 声明 loss、authority 与前置

- declared lossy projection: fallback semantic drift 显式拒绝而非静默投影（movement `C6-M002` 声明；MISSING_REF 推荐 `agent_core.c6-2.fallback.loss.v1`）。
- authority_ceiling: 全 false。
- adoption_prerequisites: `P3_AUTHORITY_RECORD_DIVERGENCE`、`C6_2_LIVE_PROVIDER_AUTHORITY_NOT_FROZEN`、`P3C6_LOOP_LIVE_MODEL_NOT_PROVEN`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 18. C6.3

### 18.1 身份

| 字段 | 值 |
| --- | --- |
| cell_id | C6.3 |
| family_id | C6 |
| owner_capability_id | `agent_core.c6_3.v1` |
| entrypoint_kind | PROGRAM |
| commutativity_claim | NOT_CLAIMED |

### 18.2 语义对象与 movement

| 项 | 值 |
| --- | --- |
| source object 1 | `C6-M003`: Legacy post-hoc redaction and raw runtime evidence |
| source object 2 | `C6-M004`: Legacy redaction evidence and self-asserted no-raw-persistence claim |
| target object | `observability.redact_evidence.v1` pre-persistence redacted value + policy-bound `RedactionReceipt` |
| named transform | redact/omit policy-selected fields before durable persistence；bind policy/source/redacted digests |
| movement 行引用 | matrix `#C6-M003`、`#C6-M004` |

### 18.3 program/plan/interpreter/oracle/shadow

| 项 | 契约值 |
| --- | --- |
| program digest | `993ec2e60869ac14bcbec65f1008cc77a3aaad1ba375527b7e1165a0afbdf67e`（fragment `/cells/2`） |
| plan digest | `392214208fc1857ae3bbeaace50ced818206fc238490dc4c15d0e57b3cb22e13`（fragment `/cells/2`） |
| program_shape_ref | MISSING_REF（推荐 `mrw.successor.agent-core.c6-3.program-shape.v1`） |
| ordered_composition_refs | (`observability.redact_evidence.v1`,) |
| successor interpreter | `successor.agent_core.c6_3.redaction.v1`（`agent_core_c6_3_interpreters.py`） |
| legacy interpreter | `legacy.agent_core.c6_3.redaction.v1` |
| legacy_oracle_ref | `legacy.agent_core.c6_3.redaction.v1` |
| shadow_observation_ref | `evidence/p3-fragments/C6.json#/cells/2/successor_observation` |

### 18.4 契约 refs

| 类别 | 命名（来源） |
| --- | --- |
| input | `AGENT_CORE_C6_3_PAYLOAD_SCHEMA`、`REDACTION_POLICY_SCHEMA_REF`、`REDACTION_SOURCE_SCHEMA_REF`（`agent_core_c6_3.py`） |
| output | `REDACTED_EVIDENCE_SCHEMA_REF`、`REDACTION_RECEIPT_SCHEMA_REF`（`agent_core_c6_3.py`） |
| object | `RedactionPolicyRef.v1`、`RedactedEvidence.v1`、`RedactionReceipt.v1`、`RedactionSource.v1`（`agent_core_c6_3.py`） |
| operation | `observability.redact_evidence.v1` |
| profile | `AGENT_CORE_C6_3_OBSERVATION_PROFILE`、`interpreter_profile_ref=successor.agent_core.c6_3.redaction.v1` |
| effect | 纯 redaction before storage boundary；`effect_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-core.c6-3.effect.pure.v1`） |
| resource | `REDACTION_RESOURCE_CEILING_SCHEMA_REF`、`REDACTION_RESOURCE_CEILING`（`agent_core_c6_3.py`）、`mrw.successor.agent-core.c6-3.deadline.v1` |
| recovery | deterministic replay from authorized source；raw 永不可从 redacted storage 恢复；`recovery_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-core.c6-3.recovery.v1`） |
| readback | receipt digest/provenance（`REDACTION_RECEIPT_SCHEMA_REF`）；`readback_policy_ref` MISSING_REF（推荐 `mrw.successor.agent-core.c6-3.readback.v1`） |
| failure | eligibility C6.3 union `RedactionSucceeded|RedactionPolicyMissing|RedactionPolicyUnsupported|SensitiveFieldUnclassified|SerializationFailed|SourceDigestMismatch|RedactedDigestMismatch|ForbiddenRawValueDetected` |

### 18.5 bindings 与所有权

| 类型 | 路径 + role |
| --- | --- |
| source | `evidence/P1FunctorizationEligibility.v1.json`、`evidence/p1-fragments/C6.json`、`app/services/agent_core/provider_trace.py` (`legacy_donor_c6_3`)、`app/services/agent_runtime/run_loop.py` |
| test | `test_p3_c6_3_redaction.py`、`test_p3_c6_legacy_shadow.py`、`test_p3_c6_worker_postgres.py`、`test_p3_c6_runtime_canary_postgres.py` |
| rollback | `evidence/p3-fragments/C6.json` (`/cells/2/rollback_observation`)、`successor_migration/legacy_agent_core.py`、`test_p3_c6_worker_postgres.py` |
| generated | `evidence/p3-fragments/C6.json` |
| handwritten | `capabilities/agent_core_c6_3.py|agent_core_c6_3_program.py|agent_core_c6_3_interpreters.py`、`agent_core_c6_common.py`、`successor_migration/legacy_agent_core.py`、`substrate/postgres/agent_core_c6_*.py`、`specification/c6_p3.py` |

### 18.6 声明 loss、authority 与前置

- declared lossy projection: 字段 redaction/omission 是有意 loss，绑定 policy digest（movement `C6-M003/M004`；`REDACTION_POLICY_SCHEMA_REF` RESOLVED；raw 值永不进入 receipt）。
- authority_ceiling: 全 false。
- adoption_prerequisites: `P3_AUTHORITY_RECORD_DIVERGENCE`、`P3C6_PRODUCTION_REDACTION_PERSISTENCE_NOT_PROVEN`、`P3C6_PRODUCTION_STORE_NOT_PROVEN`、`P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED`。

## 19. 覆盖统计与缺失清单

### 覆盖统计

- 目标 cell 数: 16
- 已覆盖 cell 数: 16（C2.1-C2.4、C3.1-C3.2、C4.1-C4.3、C5.1-C5.4、C6.1-C6.3）
- movement 行引用: 26（C2-M001..C2-M008、C3-M001..C3-M003、C4-M001..C4-M005、C5-M001..C5-M006、C6-M001..C6-M004）
- `authority_ceiling` 全 false: 16/16
- `commutativity_claim = NOT_CLAIMED`: 16/16
- 每 cell 提供 `capability_cell_spec.py` 全字段契约值或显式 MISSING 状态: 16/16
- 引用文件存在性: 除下列显式缺失项外全部验证存在

### 显式缺失引用清单（MISSING_REF / 有意缺失）

| cell | 字段/引用 | 状态 |
| --- | --- | --- |
| C2.1 | `program_shape_ref`、`effect_policy_ref`、`recovery_policy_ref`、`readback_policy_ref` | MISSING_REF（推荐命名见 3.4） |
| C2.2 | `program_shape_ref`、`effect_policy_ref`、`recovery_policy_ref`、`readback_policy_ref` | MISSING_REF |
| C2.3 | `program_shape_ref`、`effect_policy_ref`、`recovery_policy_ref`、`readback_policy_ref` | MISSING_REF |
| C2.4 | `effect_policy_ref`、`resource_policy_ref`、`recovery_policy_ref`、`readback_policy_ref` | MISSING_REF |
| C3.1 | `program_shape_ref`、`effect_policy_ref`、`resource_policy_ref`（独立常量）、`recovery_policy_ref`、`readback_policy_ref` | MISSING_REF |
| C3.2 | `program_shape_ref`、`effect_policy_ref`、`recovery_policy_ref`、`readback_policy_ref` | MISSING_REF |
| C4.1 | `program_shape_ref`、`effect_policy_ref`、`resource_policy_ref`、`recovery_policy_ref`、`readback_policy_ref`、`agent_batch.c4.source_mode_rewrite.loss.v1` | MISSING_REF |
| C4.2 | `program_shape_ref`、`effect_policy_ref`、`resource_policy_ref`、`recovery_policy_ref`、`readback_policy_ref` | MISSING_REF |
| C4.3 | `program_shape_ref`、`effect_policy_ref`、`resource_policy_ref`、`recovery_policy_ref`、`readback_policy_ref`、`agent_batch.c4.generic_enum.loss.v1` | MISSING_REF |
| C5.1 | `profile`（独立常量）、`effect_policy_ref`、`resource_policy_ref`、`recovery_policy_ref`、`readback_policy_ref`、`agent_session.c5-1.control_mutability.loss.v1` | MISSING_REF |
| C5.2 | `effect_policy_ref`、`resource_policy_ref`、`recovery_policy_ref`、`readback_policy_ref` | MISSING_REF |
| C5.3 | `profile`（独立常量）、`effect_policy_ref`、`resource_policy_ref`、`recovery_policy_ref`、`readback_policy_ref`、`runtime.c5-3.journal_detail.loss.v1` | MISSING_REF |
| C5.4 | `effect_policy_ref`、`resource_policy_ref`、`recovery_policy_ref`、`readback_policy_ref`、`runtime.c5-4.raw_detail.loss.v1` | MISSING_REF |
| C6.1 | `program_shape_ref`、`effect_policy_ref`、`resource_policy_ref`、`recovery_policy_ref`、`readback_policy_ref` | MISSING_REF |
| C6.2 | `program_shape_ref`、`effect_policy_ref`、`resource_policy_ref`、`recovery_policy_ref`、`readback_policy_ref`、`agent_core.c6-2.fallback.loss.v1` | MISSING_REF |
| C6.3 | `program_shape_ref`、`effect_policy_ref`、`recovery_policy_ref`、`readback_policy_ref` | MISSING_REF |
| C5.4 | `main/backend/app/services/task_readback_metadata.py` | RESOLVED_INTENTIONAL_ABSENT（脏源排除，禁止绑定） |

## 20. 生成门禁

机械生成 `CapabilityCellSpec` JSON 前必须满足：

1. 本契约中任何 `MISSING_REF` 字段不得自动补值；需独立 review 批准推荐命名后才可解析。
2. `source_bindings`、`test_bindings`、`rollback_bindings` 中每条路径必须存在且路径唯一；`file_sha256` 由机械编译器按 `ExactFileBinding` 规则计算。
3. `authority_ceiling` 必须精确为五个 false 标志；`entrypoint_kind` 必须匹配第 2 节映射。
4. `ordered_composition_refs` 保持声明顺序；`compose_ordered` 只过滤 identity，不做排序/去重/交换。
5. 生成结果只是 `candidate_created=false` 的机械 manifest，不构成 promotion、canonical adoption、live cutover 或 legacy retirement。

## 21. 契约来源与验证记录

- 所有路径以本工作树根为基准；本契约创建时已验证全部 RESOLVED 路径存在。
- `capability_cell_spec.py` 的字段清单来自 `main/backend/app/successor_runtime/specification/capability_cell_spec.py`（`CapabilityCellSpec`、`AuthorityCeiling`、`ExactFileBinding`）。
- movement 行来自 `P1P3SuccessorMovementMatrix.v1.json`；loss/authority 措辞来自 `P1P3LegacyDonorSemanticMovementInventory.v1.json` 与 `semantic-movement-completeness-standard.md`。
- 本文档本身不产生或修改任何 spec JSON；后续机械生成器必须以此文档为唯一语义契约输入之一（另一输入为 `capability_cell_spec.py` 校验器本身）。
