# Astra 全量原生贡献迁移执行计划 v1

日期：2026-09-22。工作根：`/Users/wangyiliang/market-research-workflow`；已现场核对分支 `codex/mrw-native-functorial-migration`。本文替代 23 号文档中未绑定路径的执行安排；22 号评估保留背景和范围。状态为 **实现计划，尚未完成全量迁移**。本次只写本文，未运行业务、数据库测试或构建。

已读取根 `AGENTS.md`、生产计划 19 号全文（包括 09-13 补充）、06 号顶部、22/23 号、`functorial-kit.json`、四个 `registries/*.json`、`sketches.json` 及当前 tracked diff。06 顶部当前事实是 Stage 4–6 本地已接受、清理完成、停止；不重开旧阶段。执行沿用“直接修复→最小相关验证→真实交付需要时批次封存”。历史候选、exact bindings、snapshot、receipt 和已冻结证据不改写。

## 1. 路径、权威与 owner 约定

以下路径缩写是精确前缀，不是待发现项；拼接后即仓库根相对路径：

| 缩写 | 完整前缀 |
| --- | --- |
| `R/` | `main/backend/app/successor_runtime/` |
| `A/` | `main/backend/app/successor_runtime/assembly/` |
| `C/` | `main/backend/app/successor_runtime/capabilities/` |
| `P/` | `main/backend/app/successor_runtime/substrate/postgres/` |
| `V/` | `main/backend/app/successor_runtime/substrate/projections/` |
| `S/` | `main/backend/app/successor_runtime/specification/` |
| `T/` | `main/backend/tests/successor_runtime/` |
| `K/` | `src/mrw_functorial_kit/contributions/` |
| `F/` | `main/frontend-modern/` |

表外以 `api/`、`services/`、`composition/`、`contracts/` 开头的路径均相对 `main/backend/app/`；同一列连续省略前缀的文件继承该列已经明确的目录。

`新增` 明确表示尚不存在、由本计划指定的目标文件/符号；其他路径均已现场通过文件枚举、AST 或 rg 核对。不会把预定名字说成现存能力。

owner 是独占写面角色，不增加管理层：`I` 为主线/现有集成 owner，维护共享 catalog、所有 assembly、共同配置和产品接线；`R3` 为 C3 首个规则 owner；`Cn` 为该族贡献实现 owner；`H` 为横向定义 owner；`FE` 为前端 owner；`OPS` 为现有 Docker/依赖集成 owner。一个执行者可兼任角色，但一个文件在一个批次中只能有一个写 owner。主线保留语义、架构和最终审查；规则使用不再各造编译器。GLM Flash 工具未暴露时主线按当前模型目录实际路由，Terra 中间层必须返回 `GLM_FLASH_ROUTE_UNAVAILABLE`，不能虚报执行模型。

权威保持：领域 dataclass/closed vocabulary/不可推导函数拥有语义；项目 `NativeContributionRule` 只降低为现有 bundle/profile/contract/codec/handler；同一 typed native handle 同时供装配、投影、verification 消费。`FamilyAssembly`、`CellBinding`、`CapabilityCellSpec` 和 registry 是派生表示。PostgreSQL writer、effect gateway、scope/admission/facade 仍是原权威边界。catalog 顺序不替代 Program 内 `Then`/`TraverseOrdered` 的业务顺序。

## 2. C8：当前实际改动和收口

本次检查时 tracked diff 恰为下面五个文件；未将它们覆盖、重写或算作已接受实现：

| 已改文件 | 当前变化 | 尚不能推导的结论 |
| --- | --- | --- |
| `C/c8_native_contribution.py` | 新增 `verify_c8_native_definition`、`C8_NATIVE_RULE_ID`、inputs；通过 `replace` 给 `C8_NATIVE_CONTRIBUTION_RULE` 加 verification slot | 回调只检查定义、operation refs、authority 对应；不证明实际 handler 行为 |
| `C/c8_graph_projection_contribution.py` | 新增 `verify_c8_graph_projection_definition`；规则先加 verification 后再 compile 默认 native | 不能证明 per-run source key、实际 graph projection/offset 写入 |
| `K/c8.py` | `c8_verification_plan_for` 从同一 `c8_native_catalog` 规划；`register_verification_plan` 接入 witness；新增 verification witnesses | `complete=True` 仅可表示声明的 coverage，不能把定义检查当作整个能力的完整行为覆盖 |
| `contributions/c8_catalog.py` | 重导出上述 plan/registration/witness | CLI 仍仅绑定 C8，未成为全项目 catalog |
| `T/test_c8_native_catalog.py` | 新增同 catalog 派生、unknown changes 全选、惰性定义 law 执行检查 | 本计划未运行这些测试；22 号的 70 passed 是旧输入证据 |

已存在的原生路径：`C/c8_typed_knowledge_contribution.py`、`c8_writing_contribution.py`、`c8_report_contribution.py` 复用 `C8_NATIVE_CONTRIBUTION_RULE`；graph 独立使用 `C8_GRAPH_PROJECTION_NATIVE_RULE`。`C/c8_program.py` 与 `A/c8_assembly.py::build_c8_assembly` 已消费 native；保留 `C8_1DemandReadRouteHandler`、`C8_2WritingComposeStageRouteHandler`、`P/c8_production.py`、`P/c8_export_token_state_handler.py`、`V/c8_handler_bindings.py` 的真实 effect 边界。

C8 收口具体剩余项（C8 owner 改本族定义/测试，I 改装配/共享项）：

1. 对五个 diff 运行本节 focused；核对 definition-only checks 的 coverage/input 标识。实际程序、失败、codec、scope 的独立行为测试必须继续在 pytest 选择中，不能因 plan `complete=True` 删除。
2. `S/c8_p4.py::_operation_bindings/_build_body` 中可由 native 定义确定的 operation/profile/owner/rollback declaration 读取同一 native；其 `_c8_*_observations`、actual hashes、运行摘要继续来自实际观察，不从声明生成 PASS。`T/test_capability_spec_pilot_c8_2.py` 和 `test_p4_c8_evidence_generator.py` 核对 mutable specification；冻结 evidence 不重写。
3. `A/c8_assembly.py` 中 `_installed_c8_3_cell/_installed_c8_3_export_token_cell` 的确定字段从 source/rule 派生；真实 delivery closure、token state store、run source key 仍由 assembly context 输入。不得将这些 context 固化成全局默认。
4. `K/c8.py` 的 plan 由 I 纳入有效全项目 catalog；原 `contributions/c8_catalog.py` 保留为定向兼容入口，不能另拥有一套 C8 清单。
5. 回归 `T/test_i1_c8_3_delivery_assembly.py`、`test_s2b_c8_export_token_state.py`、`test_c8_movement_closure_pure.py`；数据库批再运行 `test_c8_movement_closure_postgres.py`、`test_c8_research_artifact_delivery_bridge_postgres.py`。C8 数据库失败不阻塞无数据库依赖的 C3 规则建设。

当前可执行 focused（cwd 为工作根）：

```sh
python3 scripts/dev.py check
python3 scripts/dev.py test
PYTHONPATH=src:main/backend main/backend/.venv311/bin/python -m pytest -q -p no:cacheprovider main/backend/tests/successor_runtime/test_i1_c8_3_delivery_assembly.py main/backend/tests/successor_runtime/test_s2b_c8_export_token_state.py main/backend/tests/successor_runtime/test_c8_movement_closure_pure.py
```

## 3. C3 首批：确定实现路径和接口

### 3.1 已有权威与消费链

- `C/collect_c3.py`：`CollectBatchElementPayload`、`CollectFoldPayload`、`OrderedCollectElementOutcomeSequence`、`CollectC3CapabilityBundle`；不可推导内核 `build_collect_batch_plan`、`fold_ordered_results`；现有 `build_collect_c3_bundle` 在 3060 行附近手工构造两组七类 profiles、两份 operation contracts 和 codecs，随后 `build_collect_c3_catalog/registry` 构造投影。
- `C/collect_c3_program.py`：`build_collect_c3_composed_program` 构造 `Then(MapOutput(TraverseOrdered(element), sequence_to_fold_payload), FoldAtom)`；`build_collect_c3_transform_registry`、`compile_collect_c3_program`。真实实现已支持 traversal；文件顶部“compiler still rejects”的旧注释须按实际行为纠正，不能据旧注释禁用路径。
- 隐性默认依赖已经定位：`_element_atom_root` 与 `build_collect_c3_composed_program` 内部直接调用默认 `build_collect_c3_bundle`；前者又被 `family_payload_sequence_type`、`build_collect_c3_transform_registry`、`_family_refs` 使用。非默认贡献必须把 bundle/contract 贯穿这些调用，不能只在最外层换 catalog。
- `A/c3_assembly.py::_build_composed_handler` 建 bundle→catalog→registry→program→plan→successor binding，创建 `P/collect_c3_canary.py::C3CollectComposedRuntimeHandler`；`build_c3_assembly` 返回两个共享 handler 的 cells。`A/base.py::C3AssemblyOptions.element_payloads` 为空时 **不安装 handler**，保留 `FIXTURE_CLOSURE_REQUIRED`。
- 上层 `A/successor_assembly.py::assemble_successor_runtime` 将 FamilyAssembly 加入现有 `compose_postgres_first_specimen_runtime`；不得另造 runtime。
- 产品实际入口另外在 `main/backend/app/services/collect_runtime/runtime.py::run_collect/_run_successor_collect/register_successor_collect_effect_gateway` 和 `successor_bridge.py::project_successor_aggregate`。首批贯通 assembly 不等于该 gateway 已实际注册并执行；产品批处理这条明确的独立消费链。

### 3.2 首批新增与改动契约

新增文件与符号是本计划的实现目标：

| 文件/owner | 精确输出与接口 |
| --- | --- |
| `C/collect_c3_native_source.py`，R3 | 新增 frozen `C3OperationSource`、`C3NativeSource`、`DEFAULT_C3_NATIVE_SOURCE`。每 operation 声明现有 owner/kind/input/output/payload class+codec id、七类 profile 的语义输入、原观察与 failure facts；source 声明有序二元 operation tuple、catalog identity、rollback refs。引用原类型/常量，不复制 codec/failure enum/schema。 |
| `C/collect_c3_native_rule.py`，R3 | 新增 `C3NativeDefinition`（source 与派生 `CollectC3CapabilityBundle`）、`C3AssemblyContext`（uow_factory、project_scope_digest、C3AssemblyOptions）、`C3NativeBinding`（bundle、operation catalog/registry、可选 program/plan/handler、FamilyAssembly）；`C3_NATIVE_CONTRIBUTION_RULE` 的 lower/project/assemble/validate_binding/verification 五槽；`compile_c3_native_contribution(source)` 返回具体 typed handle 或 Failure。 |
| `C/collect_c3.py`，R3 | 保留 payload/结果类型、fold/traversal 内核；将原 `build_collect_c3_bundle()` 变为同 source/rule 派生 bundle 的兼容入口，允许显式 source。catalog/registry 按传入 bundle 派生；删除被规则替代的二次逐 operation 构造。允许在函数内部导入 rule 破除循环；禁止 import 时 build handler。 |
| `C/collect_c3_program.py`，R3 | 现有 builder/transform helper 增加可选 typed bundle 输入；默认 API 兼容，显式 bundle 一路到 element ref/fold ref/transform registry/compile resolver。不能在已传非默认 bundle 后重新读取 singleton。 |
| `K/c3.py`，R3 | 新增 `c3_native_contribution`、`c3_native_catalog=(c3_native_contribution,)`、投影 catalog；一次 compile，同一个 handle 导出给生产和 CLI。C3.1/C3.2 是同一有序贡献的两个对象，不靠两个清单伪造执行顺序。 |
| `A/c3_assembly.py`，I | `build_c3_assembly` 委托上面 typed handle `.assemble(C3AssemblyContext(...))` 并返回其 `FamilyAssembly`；`_build_composed_handler` 的确定接线移入规则一次，移除重复 `CellBinding`/rollback 表。`build_deterministic_element_payloads` 保留。 |
| `contributions/project_catalog.py`，I，新增 | 唯一有效项目 catalog，组合 K/c8.py 与 K/c3.py，此后逐族加入；导出 `contribution_catalog`。旧 C8 CLI 保留子集投影。 |
| `T/test_c3_native_contribution.py`，R3，新增 | default/non-default source→实际 binding→Program/plan 检查；工厂惰性、codec contract 对应、空 closure、scope 错配、reference tampering、顺序和失败见证。 |
| `T/test_i1_c1_c3_assembly.py`、`S/c3_p3.py`，I | 原 assembly 测试继续观察行为；mutable spec 的确定 operation bindings 读取 native；不生成历史观察。 |

规则的 `assemble` 必须直接构造既有 `C3CollectComposedRuntimeHandler`，复用现有 compiler 和 transforms；声明及 check/sync 不调用 assemble。禁止 `Any` 抹除 definition/context/binding 对应，禁止在异构 catalog 通过字符串 lookup 冒充 typed handle。原接口仍用原 structured Failure/边界转换，不能吞成空 tuple 或 fallback legacy。

默认 source 必须保持现有 operation/profile/codec/catalog digest、Program 有序性和 authority；非默认 source 至少改变一个确实影响 contract 的语义 profile 输入并改变 contribution/catalog instance identity，在 `build_c3_assembly` 接受显式 native 的测试路径或 rule 组装出的原 handler 上验证变更到达 contract/plan/binding。closed operation kind、payload schema 和 owner 不为测试任意发明。测试不能用同一新 helper 的两个别名自证兼容；沿用旧行为 oracle，迁移前可保存少量稳定 contract 值断言，不能更新冻结历史以迎合新输出。

### 3.3 首批直接验证命令

已现场确认 `main/backend/.venv311/bin/python` 存在且可导入 pytest、sqlalchemy、native compiler、verification；kit 实际导入 `/Users/wangyiliang/Desktop/functorial-kit/python/functorial_kit/__init__.py`。本次仅执行这个只读 import 探针，未执行以下测试。

```sh
cd /Users/wangyiliang/market-research-workflow
PYTHONPATH=src:main/backend main/backend/.venv311/bin/python -m pytest -q -p no:cacheprovider main/backend/tests/successor_runtime/test_p3_c3_contracts.py main/backend/tests/successor_runtime/test_p3_c3_micro.py main/backend/tests/successor_runtime/test_p3_traversal_foundation.py main/backend/tests/successor_runtime/test_p3_c3_replay_shadow.py main/backend/tests/successor_runtime/test_p3_c3_rollback.py main/backend/tests/successor_runtime/test_i1_c1_c3_assembly.py
# 新测试落地后执行：
PYTHONPATH=src:main/backend main/backend/.venv311/bin/python -m pytest -q -p no:cacheprovider main/backend/tests/successor_runtime/test_c3_native_contribution.py main/backend/tests/functorial_debt/test_w05_n5_c3.py
# I 接入 project_catalog 后执行，生成物只有 I 写：
PYTHONPATH=src:main/backend main/backend/.venv311/bin/python -m functorial_kit contributions check --catalog contributions/project_catalog.py --root .
```

关键现存断言：`test_composed_program_binds_traverse_epoch_and_fold_contract`、`test_payload_codecs_round_trip_c3_1_and_c3_2`、`test_queued_ack_never_implies_completion`、`test_parallel_fail_fast_preserves_all_executed_outcomes`、`test_serial_parallel_ordered_observation_with_noncommuting_trace`、`test_c3_assembly_without_payloads_requires_fixture_closure`、`test_c3_assembly_with_payloads_installs_shared_composed_handler`。它们分别约束顺序、codec、ACK/完成边界、失败后已执行 outcome 保留及装配状态。

## 4. C1–C9 路径和后续工作包

下面“新 rule”均为预定新增文件；只有 C8 rule 已存在。`K/cN.py` 是每族唯一 native 清单；`contributions/project_catalog.py` 的 inclusion、`registries/{ports,codecs,failures,vocabularies}.json`、`sketches.json`、`.functorial/contributions.json` 全由 I 通过规则同步，族作者不得直接编辑。每族 rule 默认与非默认实例均经该族原消费者；不能将 bundle wrapper 本身当作完成。

| 族/owner | authoritative source 与不可推导内核 | 项目 rule / native catalog | assembly / consumer / mutable spec | focused 测试（T/ 下） | 依赖与集成命令 |
| --- | --- | --- | --- | --- | --- |
| C1 / C1，I 接线 | `C/c1_legacy_dsl.py::build_c1_operation_contracts/parse_and_validate_legacy_dsl`；`R/language/{program,compile,validate}.py`；`R/runtime/{replay,reducer}.py` 的控制语义 | 新 `C/c1_native_contribution.py`；新 `K/c1.py`；以 command/compile/kernel binding 为形状，不硬套 effect atom | `A/c1_assembly.py::build_c1_assembly/C1_1PureCompileValidateRouteHandler`；`C/c1_slice_acceptance.py`；`S/runtime_kernel_abi.py` 只读取 ABI | `test_p5_c1_legacy_oracle.py`、`test_p5_c1_legacy_dsl_parity.py`、`test_p5_c1_slice_programs.py`、`test_i1_c1_c3_assembly.py` | catalog 共同接口后可与 C3 并行；最终 slice 持久化依赖 C7/C9。运行 Q-C1，最终 DB-C1 |
| C2 / C2 | `C/source_library_c2_1.py`、`source_library_c2_2.py`、`source_library_c2_3.py` 各 `build_source_library_c2_*_bundle`；`source_library_c2_shared.py`；`source_library_c2_4_projection.py::project_source_collection` | 新 `C/source_library_c2_native_contribution.py`；新 `K/c2.py`；显式区分 resolve/plan/provider effect/terminal projection | `A/c2_assembly.py::build_c2_assembly`；`P/source_library_c2_1_handler.py`、`source_library_c2_23_canary.py`；`V/source_library_terminal.py`；`S/c2_p3.py` | `test_p2_c2_1_contracts.py`、`test_p3_c2_2_contracts.py`、`test_p3_c2_3_contracts.py`、`test_p3_c2_4_projection.py`、`test_p3_c2_3_recovery.py` | 同 C6 可并行；provider 不因迁移自动 live。Q-C2，DB-C2 |
| C3 / R3 | 第 3 节精确路径与符号 | 第 3 节 source/rule；`K/c3.py` | `A/c3_assembly.py`、`P/collect_c3_canary.py`、`S/c3_p3.py`；产品 gateway 在第 5 节 | 第 3 节及新 `test_c3_native_contribution.py` | 首个 ordered family；只阻塞拟复用该新规则的包。第 3 节命令，DB-C3 |
| C4 / C4 | `C/agent_batch_c4.py::AgentBatchC4CapabilityBundle/build_agent_batch_c4_bundle`、`BatchPlanPayload`、`RetryReducerInput/RetryTransition`、`AgentBatchSubmission`；`agent_batch_c4_program.py`、`agent_batch_c4_interpreters.py` | 新 `C/agent_batch_c4_native_contribution.py`；新 `K/c4.py`；plan/retry/submit 三种语义保留 typed slots | `A/c4_assembly.py::build_c4_assembly`；`P/agent_batch_c4_canary.py`、`agent_batch_c4_3_handler.py`、`agent_batch_c4_quality_promotion_handler.py`；`S/c4_p3.py` | `test_p3_c4_1_plan.py`、`test_p3_c4_1_program.py`、`test_p3_c4_2_retry_reducer.py`、`test_p3_c4_3_submission.py`、`test_i1_c4_c6_assembly.py` | 使用 C2 candidate 接口及 S1 quality promotion，不要求 C2 live。Q-C4，DB-C4 |
| C5 / C5 | `R/runtime/reconciliation.py::EffectReconciler`；`V/agent_session.py`、`legacy_process.py`、`runtime_run.py`；`C/line_event_readback_port.py` | 新 `R/runtime/c5_native_contribution.py`；新 `K/c5.py`；source 持有 reconciler/readback/projector 的原生引用，不能伪造 Program | `A/c5_assembly.py::C5_2ReconcileRouteHandler/C5_4LineEventReadbackRouteHandler/build_c5_assembly`；`S/c5_p3.py` | `test_p3_c5_1_session_projection.py`、`test_p3_c5_2_attempt_replay_reconciliation.py`、`test_p3_c5_4_process_observations.py` | S1 line-event 接口确定后独立实现；持久化和 C1 recovery 联测收敛。Q-C5，DB-C5 |
| C6 / C6 | `C/agent_core_c6_1.py::AgentTurnRequest/AgentTurnEpisode/ModelStepSource/ToolSpecimen`；`agent_core_c6_2.py::ProviderPort/AgentModelStepResult`；`agent_core_c6_3.py::RedactionEvidencePayload`；各 bundle/program/interpreters | 新 `C/agent_core_c6_native_contribution.py`；新 `K/c6.py`；保留 model/tool/permission/redaction failure 区别 | `A/c6_assembly.py::build_c6_assembly/build_deterministic_fixtures`；`P/agent_core_c6_handler.py`；`S/c6_p3.py` | `test_p3_c6_1_episode.py`、`test_p3_c6_2_provider.py`、`test_p3_c6_3_redaction.py`、`test_p3_c6_legacy_shadow.py`、`test_i1_c4_c6_assembly.py` | 同 C2 并行；真实 provider 只按已配置授权测试，不用 fixture PASS 代替。Q-C6，DB-C6 |
| C7 / C7 | `C/ingest_c7_common.py::C7IngestCapabilityBundle/build_ingest_c7_bundle`；`ingest_c7_movements.py` 四模式判断；`ingest_c7_registry.py`；`ingest_c7_program.py::build_ingest_c7_1_program` | 新 `C/ingest_c7_native_contribution.py`；新 `K/c7.py`；原 `src/mrw_functorial_kit/core/c7_semantics.py` 的 vocabulary/failure 直接引用 | `A/c7_assembly.py::build_c7_assembly/C7_2CanonicalCommitWriteHandler/C7_3ProjectorDriverHandler`；`P/c7_canonical_write.py`、`c7_projector_driver.py`、`ingest_c7_movement_admission.py`；`S/c7_p4.py` | `test_c7_movement_decision_parity.py`、`test_c7_semantic_movement_completeness.py`、`test_p4_c7_1_program.py`、`test_p4_c7_legacy_writer_spy.py`、`test_i1_c7_c9_assembly.py` | 独立定义可并行，canonical writer 与 C9 offset 联合验收。Q-C7，DB-C7 |
| C8 / C8 | `C/c8_*_contribution.py` 的 author sources；`c8_typed_knowledge.py`、`c8_writing.py`、`c8_report.py`、`c8_graph.py` 内核 | 现有 `C/c8_native_contribution.py`、`c8_graph_projection_contribution.py`；现有 `K/c8.py` | 第 2 节实际消费者及 `S/c8_p4.py` | 第 2 节；`test_c8_typed_knowledge_contribution.py`、`test_c8_writing_contribution.py`、`test_c8_report_contribution.py`、`test_c8_graph_projection_contribution.py` | 定义收口独立；canonical handle/交付读回与 C7 联测。Q-C8，DB-C8 |
| C9 / C9 | `R/runtime/facade_contracts.py`、`facade.py`；`V/registry.py::ProjectorContract/ProjectorRegistry/ProjectionOffset/OffsetExpectation`；`V/c9_sources.py`；`P/c9_projection_sources.py::build_semantic_source_closure`、`projection_offsets.py` | 新 `R/runtime/c9_native_contribution.py`；新 `K/c9.py`；facade、投影、offset/CAS 是不同原生操作，不同 typed binding | `A/c9_assembly.py::build_c9_assembly/C9_1FacadeValidationRouteHandler`、`A/app_assembly.py`；`main/backend/app/api/successor_runtime.py`、`main/backend/app/contracts/successor_runtime.py`；`S/c9_p4.py` | `test_p4_c9_1_facade_contracts.py`、`test_p4_c9_2_projector_registry.py`、`test_p4_c9_3_transport_dto.py`、`test_c9_typed_projection_payloads.py`、`test_c9_generalized_rollback_identity.py` | facade 纯定义独立；C7/C8/C5 结果和 offset 完成后整链验证。Q-C9，DB-C9 |

每族新增 native 测试名固定为 `T/test_cN_native_contribution.py`（C8 沿用现存四类 contribution tests）。这些新增文件归族 owner。每族最小完成条件相同：旧 API 兼容、default 与第二个 source 贯通表中消费者、definition/assembly/projection/verification 同源、失败/权限/顺序原断言保持、I 完成 catalog 同步和该族 assembly 合入。DB 未执行时只能标注“静态与纯行为闭合，DB 未验证”。

精确 Q 命令如下；在工作根执行首段定义后，各行可直接运行。它只是 shell 简写，不创建 runner：

```sh
mrw_q() { PYTHONPATH=src:main/backend main/backend/.venv311/bin/python -m pytest -q -p no:cacheprovider "$@"; }
# Q-C1
mrw_q main/backend/tests/successor_runtime/test_p5_c1_legacy_oracle.py main/backend/tests/successor_runtime/test_p5_c1_legacy_dsl_parity.py main/backend/tests/successor_runtime/test_p5_c1_slice_programs.py main/backend/tests/successor_runtime/test_i1_c1_c3_assembly.py
# Q-C2
mrw_q main/backend/tests/successor_runtime/test_p2_c2_1_contracts.py main/backend/tests/successor_runtime/test_p3_c2_2_contracts.py main/backend/tests/successor_runtime/test_p3_c2_3_contracts.py main/backend/tests/successor_runtime/test_p3_c2_4_projection.py main/backend/tests/successor_runtime/test_p3_c2_3_recovery.py
# Q-C4
mrw_q main/backend/tests/successor_runtime/test_p3_c4_1_plan.py main/backend/tests/successor_runtime/test_p3_c4_1_program.py main/backend/tests/successor_runtime/test_p3_c4_2_retry_reducer.py main/backend/tests/successor_runtime/test_p3_c4_3_submission.py main/backend/tests/successor_runtime/test_i1_c4_c6_assembly.py
# Q-C5
mrw_q main/backend/tests/successor_runtime/test_p3_c5_1_session_projection.py main/backend/tests/successor_runtime/test_p3_c5_2_attempt_replay_reconciliation.py main/backend/tests/successor_runtime/test_p3_c5_4_process_observations.py
# Q-C6
mrw_q main/backend/tests/successor_runtime/test_p3_c6_1_episode.py main/backend/tests/successor_runtime/test_p3_c6_2_provider.py main/backend/tests/successor_runtime/test_p3_c6_3_redaction.py main/backend/tests/successor_runtime/test_p3_c6_legacy_shadow.py main/backend/tests/successor_runtime/test_i1_c4_c6_assembly.py
# Q-C7
mrw_q main/backend/tests/successor_runtime/test_c7_movement_decision_parity.py main/backend/tests/successor_runtime/test_c7_semantic_movement_completeness.py main/backend/tests/successor_runtime/test_p4_c7_1_program.py main/backend/tests/successor_runtime/test_p4_c7_legacy_writer_spy.py main/backend/tests/successor_runtime/test_i1_c7_c9_assembly.py
# Q-C8
python3 scripts/dev.py test
# Q-C9
mrw_q main/backend/tests/successor_runtime/test_p4_c9_1_facade_contracts.py main/backend/tests/successor_runtime/test_p4_c9_2_projector_registry.py main/backend/tests/successor_runtime/test_p4_c9_3_transport_dto.py main/backend/tests/successor_runtime/test_c9_typed_projection_payloads.py main/backend/tests/successor_runtime/test_c9_generalized_rollback_identity.py
```

## 5. 横向和产品入口的实际接线

### S1 / S2c

H 新增 `C/horizontal_native_contribution.py` 和 `K/horizontal.py`，只复用已存在的 typed port/surface 定义。I 独占 `A/s1_horizontal_port_assembly.py`、`A/s2c_ops_domain_surface_assembly.py` 和 `A/successor_assembly.py`，从同一贡献导出原 `S1HorizontalPortContract`/`S2cOpsDomainSurfaceContract`；无 runtime binding 的状态和 authority ceiling 不升格。

S1 四个权威文件精确为 `C/request_identity_port.py`、`single_source_guard_port.py`、`quality_promotion_port.py`、`line_event_readback_port.py`。S2c 权威文件精确为 `R/ops_domain/{base,dashboard_admin_surface,health_matrix_surface,ops_misc_surface,projects_config_surface,runtime_ops_surface}.py`，以及 `C/source_library_worker_readback.py`、`c9_2_search_retrieval_panel.py`、`c8_report_export_audit_evidence_surface.py`、`c8_report_quality_trend_evidence_surface.py` 和 `quality_promotion_port.py`。11 条 surface registration 引用这些定义，不另抄 schema/authority 表。

直接验证：

```sh
mrw_q main/backend/tests/successor_runtime/test_s1_assembly_wiring.py main/backend/tests/successor_runtime/test_s1_request_identity.py main/backend/tests/successor_runtime/test_s1_single_source_guard.py main/backend/tests/successor_runtime/test_s1_quality_promotion.py main/backend/tests/successor_runtime/test_s1_line_event_readback.py main/backend/tests/successor_runtime/test_s2c_surface_assembly_wiring.py main/backend/tests/successor_runtime/test_s2c_ops_domain_surfaces.py main/backend/tests/successor_runtime/test_s2c_worker_and_retrieval_surfaces.py main/backend/tests/successor_runtime/test_s2c_evidence_consumption.py
```

### services / API / Celery

I 维护下列真实 composition/route/task 接缝；族 owner 只改对应 source/rule。产品接线先复用现有 binder，不把普通 SQL、纯函数和 HTTP endpoint 全包成新 runtime。

| 产品路径 | 必须接到的既有消费者 | 验收含义 |
| --- | --- | --- |
| collect/source | `main/backend/app/composition/collect_runtime.py::default_collect_adapters/configure_default_collect_adapters`；`composition/source_library.py`；`services/collect_runtime/runtime.py::register_successor_collect_effect_gateway/run_collect`；`services/collect_runtime/successor_bridge.py`；`api/ingest.py` | catalog 派生已确定 adapter/handler 绑定；实际 gateway 必须安装。successor mode 不可 silent fallback。 |
| raw import/ingest | `api/admin.py::RawImportRequest/raw_import_documents` → `services/tasks.py::task_raw_import_documents`（必须保持 Celery task 注册）→ `services/ingest/raw_import.py::run_raw_import_documents` → 已有 ingestion writer；C7 movements 通过原业务 operator 消费 | async HTTP ACK 后必须到 worker terminal、Process/document 持久读回；不把原有 writer 换成测试写入脚本。 |
| agent batch/core | `services/agent_batch/{routing,task_contract,agent_loop,planner,approval_binding}.py`；`services/agent_runtime/{interactive_agent,run_loop,tool_execution,tool_policy,capability_registry}.py`；`services/tasks.py` | 只派生 capability/operation/tool binding 的确定部分；真实模型与 permission/quality policy 继续各自 owning。 |
| writing/report/graph | `api/writing.py`、`api/llm_report.py`、`api/reports.py`；`services/writing/{primary_loop_service,document_service,llm_action_service}.py`；`services/llm_report_generator.py`、`llm_report_export.py`、`llm_report_export_token_state.py`；`services/workflow_graph/runtime.py` | C8 原生定义到页面提交/生成/保存/刷新读回，export/token-state 保留实际存储边界。 |
| facade/process | `api/successor_runtime.py`、`api/process.py`、`api/business_lines.py`；`contracts/successor_runtime.py`；`A/app_assembly.py::build_successor_runtime_app_dependencies/build_successor_registry_app_dependencies/initialize_successor_registry_mount` | 保持 envelope、request digest、actor/project scope、read-only projection 与 canonical command 区分。 |
| 应用/worker 根 | `main/backend/app/main.py`、`startup_hooks.py`、`celery_app.py`、`composition/production.py`、`composition/production_route_bindings.json` | API 与 worker 消费同 catalog 下的确定 binding；启动时不得自动获得未授权 provider/写入权限。JSON 若由声明确定只能生成，不再独立维护同一事实。 |

产品 focused：`main/backend/tests/unit/test_collect_runtime_composition_unittest.py`、`test_collect_runtime_auto_batch_unittest.py`、`test_raw_import_structuring_unittest.py`、`test_module_wiring_unittest.py`，以及 `T/test_successor_production_wiring.py`；用 `mrw_q` 加完整路径直接执行。集成 owner 还运行第 7 节的真实链，单靠这些 unit tests 不完成产品批。

### frontend-modern

FE 独占以下文件（与后端 I 无共享写文件）：

- `F/src/app/kernel/moduleManifest.ts` 继续是模块语义源；`F/src/app/platform/modules/registry.ts` 已从 manifest 派生，禁止再建平行 module catalog。
- 改 `F/src/app/kernel/renderKernelModuleContent.tsx::renderModuleNode/renderKernelModuleContent`：把当前独立 render 分派接到 manifest 可引用的 typed renderer binding；新增 `F/src/app/kernel/moduleContributionRule.ts` 只用于这一现实形状，原 React 页面保留。
- `F/src/app/platform/modules/types.ts`、`F/src/app/kernel/moduleChrome.ts` 和 `F/src/app/platform/modules/index.ts` 接收同一派生结果；default/隐藏模块/未知 route/禁用模块保留行为。
- `F/src/lib/api/client.ts` 与 `endpoints.ts` 保留 transport；`F/src/lib/api/domains/{successor-runtime,writing,llm-report,clue-chains,graph-workflow,project-admin,codex-auth,resource-source}.ts` 逐一清除与后端权威 schema 机械重复的 wire 字段。`main/backend/app/contracts/successor_runtime.py`、`contracts/schemas/writing.py`、`contracts/schemas/workflow_graph.py` 是已经核对的 owner；其他 domain 从当前 FastAPI OpenAPI 对应模型投影，UI 局部 view model/乐观状态不伪称 wire schema。
- I 的后端 OpenAPI/export 入口与 FE 的生成 TypeScript 接口约定先在 successor-runtime 域打通；新增 `F/scripts/generate_api_contracts.mjs` 读取同次本地 app OpenAPI 导出，不从远端动态接口猜测、不执行业务、不复制一份业务 schema。生成物放 `F/src/lib/api/generated/contracts.ts`（新增）；domain wrapper 只做真实边界转换。
- 如采用 kit TypeScript native compiler，FE/OPS 明确修改 `F/package.json`、现有 lockfile 和构建输入；不得在尚无 frontend kit dependency 时写代码假定可导入。前端不因项目采用 kit 就为每个组件建 contribution。

直接命令（cwd=`main/frontend-modern`）：`npm run build`、`npm run lint`、`npm run check:topology-platform`、`npm run check:layer-shell-contract`、`npm run check:writing-workbench-typed-fetch`、`npm run check:writing-workbench-persisted-typed-card-readback`；实际页面链用第 7 节 Playwright 命令。

## 6. 批次、独占写面与故障归属

| 批次 | 可并行工作与严格依赖 | 独占写面 | 批次结束条件 |
| --- | --- | --- | --- |
| A | C8 当前 diff 收口；I 创建 project_catalog；OPS 核对 actual kit 输入；H/FE 可独立开始现有形状 | C8 五个 dirty 文件归原 owner，新增修复只交同 owner；I 独占 `scripts/dev.py`、`tests/test_architecture.py`、`tests/checkers/test_dev_entry.py`、`contributions/project_catalog.py`、全部 registries/sketches/`.functorial`；OPS 独占依赖/镜像文件 | check/test 真实通过；定义 verification 与行为 coverage 边界清楚；正式入口默认有效项目 catalog，保留 focused，不再把 C8 九文件 selector 叫全量 |
| B | R3 完成第 3 节 source→rule→旧消费者；C1 的独立 compile 语义与 H/FE 可继续 | R3 仅第 3 节列出的 source/rule/collect_c3/program/K/c3/new test；I 单独修改 A/c3/S/c3 和 assembly test | 默认+非默认实际消费者通过、空 closure/顺序/Failure 见证通过；原机械构造删除，唯一 catalog 接入 |
| C | C2、C4、C6 各包并行；仅确实复用 C3 新机制的部分等待 B；C1 并行收口 | C2/C4/C6 独占第 4 节各族 C 文件、新 K 文件、新/本族旧测试；I 串行改 A/c2,c4,c6 与 S/c2,c4,c6；共享测试 test_i1_* 只归 I | Q-C1/C2/C4/C6 与受影响语义登记通过；实际 bundle/handler 对应，不以 native wrapper 数量计完成 |
| D | C5/C7/C9 定义可并行，最终事务/恢复/offset 与 C1/C8 联合收敛 | C5/C7/C9 独占各新规则和本族原 source；I 独占全部 A、P/composition_root.py、P/node_adapter.py、V/registry.py 与共享投影装配；族内 P 文件只有明确交给该族后才可改，禁止双 writer | I1 30-cell 与每族 DB selector 通过，canonical write、reconcile、idempotency、offset CAS/ABA/权限拒绝保持；未调用 provider 明示 |
| E | H、FE、产品接线可开发并行；真实用户链依赖对应后端包 D/已完成的族 | H 本节 source/rule/K/horizontal；FE 上述 F 文件；I 单写 services/tasks.py、celery_app.py、main.py、composition/API 接缝；多个业务包不得各改同一 tasks.py | 7 条业务线的实际 consumer 可追溯；导入/检索/图谱/写作等适用提交→worker/operator→持久读回闭合，UI 刷新一致 |
| F | 全部需要的声明和消费者合入后统一验证；不在每个小修重复 | I 同步生成物、跑共同 gates；OPS 改 `pyproject.toml`、`main/backend/requirements.txt`、`main/backend/Dockerfile`、`Dockerfile.test`、`main/ops/docker-compose*.yml` 和必要 CI 输入；FE own package/lock 与 OPS 协调后单写 | 第 7 节全部适用验收完成；剩余 declared loss/环境缺口单列，不能宣称全量已完成；只在真实交付边界统一封存 |

共享接口变更由 I 发一次精确符号/调用变更通知，不能让所有包反复追逐设计。作者发现需要复制 lower/project/binding 时报告规则缺口及调用点；R3 或相应 rule owner 解决后复用。批次普通修复不等待新审批。

失败分类：`RULE`（lower/对应关系，共同 rule owner）；`SEMANTICS`（有序性/权限/失败定义，族 owner + 主线）；`CONSUMER`（assembly/API/worker 接线，I）；`PROJECTION`（同步冲突/生成漂移，I）；`CHECKER`（真实覆盖/selector 错误，I，禁止删断言改绿）；`ENVIRONMENT`（kit 路径、Docker、DB、provider，OPS）。每个未闭合项写明准确文件、影响族、复现命令及 blocked_by。一个 DB 环境失败只诊断一次，不在所有族重复失败；无依赖工作继续。

## 7. 全量完成与实际验证边界

### 7.1 声明、删除和共同检查

全量完成需要同时满足：C1–C9、S1/S2c、表中产品消费者和 frontend 全部接入或有明确保留理由；每个确定事实有一个声明 owner；新规则不是包裹旧平行手工表。I 逐项删除被替代的 assembly cell/profile/codec/registry wiring；保留普通纯算法、SQL、外部适配器实现、真实观察、冻结历史、legacy parity/rollback oracle，理由写在本文件对应族的交付状态。保留 legacy runtime 业务 fallback 必须说明真实 consumer 和权限原因，不能称“暂留”而算全量结束。

I 完成 project catalog 后调整 `scripts/dev.py` 的 `CATALOG` 与有效验证选择、`tests/test_architecture.py::CATALOG`；`tests/checkers/test_dev_entry.py` 已存在 `PILOT_TESTS` 固定尾片段断言，需要按真正 selector 合同修复，不能把旧尾五项假设当规范。rule 产生 verification obligations，pytest/既有 runner 执行；async 行为保留 pytest-asyncio。不引入调度器或结果缓存。

```sh
python3 scripts/dev.py sync
python3 scripts/dev.py check
python3 scripts/dev.py test
python3 scripts/dev.py gates
PYTHONPATH=src:main/backend main/backend/.venv311/bin/python -m pytest -q -p no:cacheprovider tests main/backend/tests/successor_runtime
bash scripts/test-standardize.sh ci-pr -q
PYTHONPATH=src:main/backend main/backend/.venv311/bin/python main/backend/scripts/check_successor_runtime_dependencies.py
git diff --check
```

`gates` 必须机械执行七项 `import-direction/no-throw-in-core/registry-complete/one-representation/fakes-run-laws/derived-marked/sketch-valid`；不手审替代、不新增 baseline 豁免。最后一个完整 pytest 与 ci-pr 覆盖有交集：在真实 scope/marker 证明相同输入覆盖后复用同次结果，不重复完整 suite。上面的命令列表是覆盖要求，不要求无差别连续重复执行。各命令保留原退出码；skip/环境缺失单列。

根 `pyproject.toml` 的 pyright 当前只覆盖 src/tests，I 必须把新规则、生产消费者和必要 fixtures 纳入适用检查；`main/backend/.venv311/bin/python -m pyright` 只有在该环境实际装有 pyright 后执行，缺依赖归 OPS，不谎称类型覆盖。changed-file ruff/现有 lint 不代替原七 gate。kit 机制若修改，要在 sibling kit 的独立 compiler tests 验证，MRW case 不能替代它。

### 7.2 PostgreSQL 与 Docker：精确测试输入

DB-C1–C9 对应的已有测试文件：

| selector | T/ 下具体文件 |
| --- | --- |
| DB-C1 | `test_p5_c1_slice_acceptance_postgres.py` |
| DB-C2 | `test_p3_c2_1_rehydration_postgres.py`、`test_p3_c2_23_runtime_canary_postgres.py`、`test_p3_c2_4_postgres.py` |
| DB-C3 | `test_p3_c3_canary_postgres.py` |
| DB-C4 | `test_p3_c4_4_postgres.py`、`test_p3_c4_5_runtime_postgres.py` |
| DB-C5 | `test_p3_c5_2_reconciliation_postgres.py`、`test_p3_c5_3_projection_postgres.py` |
| DB-C6 | `test_p3_c6_worker_postgres.py`、`test_p3_c6_runtime_canary_postgres.py` |
| DB-C7 | `test_c7_canonical_write_projector_postgres.py`、`test_c7_production_admission_runner_postgres.py`、`test_c7_canonical_migration_parity_postgres.py` |
| DB-C8 | `test_c8_movement_closure_postgres.py`、`test_c8_research_artifact_delivery_bridge_postgres.py` |
| DB-C9 | `test_c9_projection_sources_postgres.py`、`test_c9_typed_source_evolution_postgres.py`、`test_c9_movement_closure_backend_postgres.py` |

每项在下面命令末尾替换为 `tests/successor_runtime/<表内精确文件>`，多文件一条 pytest 运行，I 串行占用有固定 DB 名的测试，不让两个包争库。已查实 C3 fixture 会 DROP/CREATE 固定 `mrw_p3_c3_worker_test`，不能指向用户实际服务。

采用独立 Compose project `mrw-native-migration-tests`，只起数据库/Redis/ES 与 backend-test；不使用 `mrw-local-user` 的 volumes。OPS 先 `config` 确认 bind/volume/ports 没有引用用户数据，输入 kit 必须为本次实际支持 compiler/verification 的版本。下面是可执行 C3 例子，cwd=工作根：

```sh
docker compose -p mrw-native-migration-tests -f main/ops/docker-compose.yml --profile test config
docker compose -p mrw-native-migration-tests -f main/ops/docker-compose.yml --profile test up -d db redis es
docker compose -p mrw-native-migration-tests -f main/ops/docker-compose.yml --profile test build backend-test
docker compose -p mrw-native-migration-tests -f main/ops/docker-compose.yml --profile test run --rm -e SUCCESSOR_TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/postgres backend-test tests/successor_runtime/test_p3_c3_canary_postgres.py
```

`backend-test` 的 ENTRYPOINT 已是 `python -m pytest -q`，不能再错误追加 `python -m pytest`。正式依赖仍固定旧 Git revision，而本地 editable kit 有未提交差异；OPS 必须先让 test image 消费明确支持新 API 的确切输入（可用受控源码 mount 验证开发输入，最终构建必须包含所需实现），不能把旧镜像与宿主成功混为一谈。父 Compose 的当前 backend-test 仅 bind backend，src 是镜像 COPY，更新 src 后需构建或明确只读 overlay。

`main/backend/scripts/run_successor_postgres_validation.py` 只接受 Unix socket、创建非超级用户临时数据库；不能直接拿它套 C3 这种另行建库 fixture。`scripts/test-standardize.sh docker` 会在退出时 `down -v`，只允许显式隔离测试 project 使用，不对 local-user 栈调用。上述环境障碍属于有界输入/测试设施问题，不是业务已通过。

### 7.3 真实本地用户链

使用现有 `main/ops/docker-compose.local-user.yml`，项目 `mrw-local-user`；已核对 backend `127.0.0.1:18132`、frontend `127.0.0.1:15132`、worker 单并发、sibling kit/src/app overlays。OPS 先确认实际镜像、当前端口和服务归属后执行：

```sh
docker compose -p mrw-local-user -f main/ops/docker-compose.yml -f main/ops/docker-compose.local-user.yml config
docker compose -p mrw-local-user -f main/ops/docker-compose.yml -f main/ops/docker-compose.local-user.yml up -d db redis es backend celery-worker frontend-modern
docker compose -p mrw-local-user -f main/ops/docker-compose.yml -f main/ops/docker-compose.local-user.yml exec -T celery-worker celery -A app.celery_app inspect registered
```

注册检查后实际 POST `/api/v1/admin/documents/raw-import`，`async_mode=true`，使用明确测试项目、唯一文本标记、`enable_extraction=false`、`infer_from_links=false`、`fetch_url_when_text_empty=false`、`fetch_url_also_when_text_present=false`；只走本地 raw 数据路径。由正式 task 执行，读回 task terminal、`api/process.py` 对应 Process、`/api/v1/admin/documents/list` 持久 Document 内容。不得把独立 SQL insert 或 Celery noop 当作该链完成。API request 结构已在 `RawImportRequest/RawImportItem` 核对；测试项目必须实际创建/存在且所有读回使用同一 project_key。

下面脚本入口已核对参数；执行者将变量设为本轮的真实项目和原有证据目录，按运行产生的事实维护结果，不新建证据平台：

```sh
python3 scripts/run_business_line_user_flow_smoke.py --base-url http://127.0.0.1:18132 --feedback-project-key "$MRW_TEST_PROJECT_KEY" --output "$MRW_RESULT_DIR/user-flow.json" --json
python3 scripts/run_business_line_worker_readback_smoke_triggers.py --api-base http://127.0.0.1:18132 --project-key "$MRW_TEST_PROJECT_KEY" --output "$MRW_RESULT_DIR/worker-triggers.json" --json
python3 scripts/run_business_line_worker_readback_evidence_chain.py --api-base http://127.0.0.1:18132 --project-key "$MRW_TEST_PROJECT_KEY" --artifact-dir "$MRW_RESULT_DIR/worker-chain" --json
```

这些脚本有 probe/contract reachable 和 worker-readback 等不同证据层次；必须检查 JSON 中实际断言和 completion，不能只看 exit 0。不传 `--allow-blocked` 来制造通过。需要外部抓取/模型的动作只按已有配置权限执行，缺凭据/无 provider 记具体链未验证；纯页面 GET 成功不顶替该动作。

前端真实链（cwd=`main/frontend-modern`）：

```sh
FRONTEND_E2E_PROJECT_KEY="$MRW_TEST_PROJECT_KEY" VITE_API_PROXY_TARGET=http://127.0.0.1:18132 VITE_CODEX_PROXY_TARGET=http://127.0.0.1:1 npm run test:e2e:real-backend-business-lines
```

已核对 Playwright 自启 4173 隔离 Vite，`reuseExistingServer=false`；不能把 15132 上旧 dist 的截图当新源码浏览器验收。不设置 backend bypass；上述 CodeX proxy 明确 fail-closed，依赖 Codex 服务的链单列其真实环境需求。补充以实际页面完成导入、检索、graph、writing 保存与刷新读回，并验证 worker/operator 使用的是新 native binding。源代码迁移完成、用户链通过和生产发布是三个不同事实；本计划不授权 live provider 扩权、远端 push/发布或 authority transfer。

## 8. 下一位 GLM Flash 的直接派发文本

> cwd=/Users/wangyiliang/market-research-workflow，分支 codex/mrw-native-functorial-migration。你不是独自在仓库，保留所有其他改动，不递归 spawn。任务为本文件第 3 节 C3 首批规则实现，严格保持现有 ordered traversal→fold、typed Failure、codec/contract identity 和空 closure fail-closed。只读输入是 collect_c3.py 的 payload/结果类型和现有 build_collect_c3_bundle、collect_c3_program.py、assembly/c3_assembly.py、substrate/postgres/collect_c3_canary.py，以及列出的旧测试。独占写面是 capabilities/collect_c3_native_source.py（新增）、collect_c3_native_rule.py（新增）、collect_c3.py、collect_c3_program.py、src/mrw_functorial_kit/contributions/c3.py（新增）、tests/successor_runtime/test_c3_native_contribution.py（新增）；所有 capabilities/tests 前缀按本文件路径表展开。不要改 assembly、specification、共享 catalog、registries、sketches、dev.py、dependency 或 frozen evidence，I 将据你的 typed handle 完成它们。实现 C3NativeSource/C3NativeDefinition/C3AssemblyContext/C3NativeBinding、C3_NATIVE_CONTRIBUTION_RULE 和 compile_c3_native_contribution，source 的语义值来自原 bundle 构造；rule 用现有 runtime/compiler 构造真实 handler，不再造 runtime。新 K/c3.py 导出一次 compile 的 c3_native_contribution 和单项 c3_native_catalog，失败在既有边界明确处理。现有 Program helpers 必须贯穿显式 bundle，不能回读默认 singleton。使用 main/backend/.venv311/bin/python，PYTHONPATH=src:main/backend，kit 已现场解析到 /Users/wangyiliang/Desktop/functorial-kit/python；运行第 3.3 节旧行为命令和新增 native tests，不运行 DB、不执行 sync。新增测试直接通过 rule binding 的原 handler/Program 验证第二个非默认 source，不能仅比较投影字典。回传结果、改动文件、实际命令/退出码、I 需要接入的导出符号和剩余风险；规则无法表达的具体缺口报告主线，不新增相同适配器。

派发模型请求 `glm-5.3-flash-zhipu-glm-en` / `low` 以实际工具 schema 为准。本规划不声称已派发该模型。I 在收到结果后继续第 3.2 节自己的接线，运行整个首批命令并按本计划推进 C–F，不在普通回传点停止等待。

## 9. 本文交付与进度记录

本文实际完成的是路径/符号只读核对和执行计划；没有业务代码改动，没有当前测试 PASS 声明。后续进度直接追加本文对应批次状态或复用 22 号记录，不另建 schema/审批链。I 按实际日志报告每批完成包/派发包、首次共同验收耗时、失败次数、手写机械接线剩余、各 owner 调用/token 可得值；rule 建设、主线补修和环境等待成本计入或标缺失，不记作零。不因缺少可比样本宣称加速幅度。
