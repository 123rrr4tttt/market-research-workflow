# MRW 综合信息研究函子化后继架构与运行时修正合同

Status: `FROZEN_FOR_IMPLEMENTATION · USER_APPROVED_2026-08-30 · HASH_BOUND_BY_02_MANIFEST`

Version: `1.0.0-frozen`

Date: `2026-08-30`

Repository: `market-research-workflow`

Source topic: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration`

Production target root: `main/backend/app/successor_runtime`

Development spike root: `experiments/functorial-kernel`

## 1. 修正目的与优先级

本文是对既有函子化后继迁移合同的架构修正。既有合同继续提供工作树清点、能力保全、权限上限、迁移状态和验收纪律，但它既没有冻结“综合信息研究”这一项目语义，也没有冻结一个可直接实现且足够化简的目标运行时。本文补充并优先裁决以下内容：

- 项目的稳定定义、研究对象、关系、基本运动与回返条件；
- 市场、政策、社交、商品等来源域与通用信息研究内核的边界；
- 旧 C1–C9 模块如何下沉为领域 operator 的实现、解释器、权威库或投影；

- 后继运行时的生产模块树；
- 领域对象、typed IR、编译结果和运行状态的确切关系；
- 模块 API 与 Port 签名；
- PostgreSQL、可选 Redis/Celery、FastAPI、Elasticsearch 与前端的职责；
- 持久化表、事务、work item、lease、assignment envelope 和 event sequence；
- scheduler、并发、资源、取消、超时、重试与 backpressure；
- effect interpreter、receipt、verification、admission 与 canonical fact 的边界；
- crash/recovery/replay/reconciliation 状态机；
- C1–C9 每个能力进入统一运行时的具体接线位置；
- feature flag、shadow、canary、cutover 与 rollback 的部署形式；
- 生产依赖、开发依赖和明确禁止引入的基础设施。

本修正采用 greenfield successor 原则：先在新的 production package 中独立建立综合信息研究对象、函子化程序内核、编译器、运行时状态机、持久化、work items、同构 RuntimeNode、恢复和投影；旧 MRW service 不作为新内核的构造材料。现有设施和能力只有通过“函子语境可迁移性”判定后，才以 sibling adapter/interpreter 接入。其余能力先抽取语义对象、operation algebra、组合与失败，再在新架构中重写并迁移。

在本文被独立审查、内容寻址冻结并加入合同 manifest 前：

- C1–C9 不得恢复实现、采纳或状态晋级；
- `experiments/functorial-kernel` 只作为 architecture spike 和反例输入；
- 既有 F0 的 `MIGRATED` 记录保持历史，但 forward adoption 为 `INVALIDATED`；
- 已中断子任务生成的文件保持 `UNADOPTED_DRAFT`；
- 不得创建 candidate、closure、final review、authority transfer 或 live cutover。

## 2. 已确认的前次架构缺陷

既有 F0 不是完全空字段，但它不是生产运行时基础：

- `Program` 只是 `Operation{name, payload, effect_family}` 的通用列表，没有 typed input/output、dependency edge、resource requirement 和 capability schema；
- `combine_independent` 只保存子程序 digest，无法恢复或执行子程序；
- `AttemptJournal` 是进程内字典，不是 durable journal；
- `LegacyCallbackInterpreter` 只是 callback 包装，不是 MRW legacy execution replay；
- `StructuralObservation` 与 `Projection` 是任意 callable，没有版本、schema、source identity 和 declared-loss validator；
- `AuthorizationBinding` 无法表达一个多 step program 的逐 step authority；
- canonical codec 使用非冻结的通用 JSON/default-string 行为；
- property/law tests 大多只验证同义表达，没有对真实编译、调度、存储和恢复路径构成反例；
- 没有 Postgres schema、durable assignment/work item、lease、heartbeat、resource scope、backpressure 或 deployment wiring。

因此，F0 中的 `CanonicalRef`、`VerificationBinding`、`EffectAttemptRef` 等概念可以保留为设计候选，但字段、codec、持久化和运行语义必须以本文为准重新实现。

## 3. 当前基础设施与后继采用决定

### 3.1 当前已存在的生产依赖

后继第一阶段复用当前仓库已安装的生产依赖：

| 能力 | 当前依赖 | 后继职责 |
| --- | --- | --- |
| HTTP/API | `FastAPI 0.120.4`、`Starlette 0.49.1`、`Uvicorn 0.30.6` | command/query/SSE 边界 |
| 主持久化 | `PostgreSQL`、`SQLAlchemy 2.0.35`、`Alembic 1.13.2` | Research Ledger、runtime journal、work items、lease、approval、idempotency、projection offset |
| 内部工作分配 | `PostgreSQL` row claim | `runtime_work_items`、due time、lease、retry 与节点 claim；属于 greenfield core |
| 兼容队列 | `Celery 5.4.0`、`Redis 7.4` | legacy/migration transport interpreter；不作为 greenfield core 必需依赖，不拥有完成事实 |
| 检索 | `Elasticsearch 8.15.3`、`pgvector 0.3.4` | capability handler 与可重建索引投影 |
| Provider/HTTP | `httpx`、`requests`、`openai`、现有 LangChain 包 | 具体 effect handler；不进入 core |
| Metrics | `prometheus-client 0.20.0` | runtime metrics |
| 前端 | React 19、TanStack Query、Axios、Vite | bounded read-model consumer |

### 3.2 第一阶段不得新增的生产基础设施

第一阶段不引入：

- Temporal、Dagster、Prefect；
- Kafka、RabbitMQ、Redis Streams；
- 新 event-store 产品；
- 新的分布式锁服务；
- 新 LLM orchestration framework；
- 新数据库、向量库或图数据库；
- 由 Redis lock 承担的 canonical authority；
- 第二个生产控制面。

PostgreSQL 事务、row claim、lease 与同构 `RuntimeNode` 已足够表达第零阶段运行语义。只有实际容量、隔离、恢复或吞吐证据证明不足时，才可把 Celery/Redis 或其他 transport 作为外部 assignment transport interpreter 接入；该接入不得改变 Program、authority、completion、admission 或 recovery 语义。

### 3.3 可新增的开发依赖

以下依赖只能作为 dev/test dependency，并须单独写入开发依赖清单：

- `hypothesis`：生成 valid program、状态转换、replay、idempotency 与 failure-preservation 反例；
- `import-linter` 或等价仓库脚本：执行依赖方向门禁。

若不新增依赖，必须提供具有 seed/replay/minimal-counterexample 保留能力的确定性生成器；不能用同义表达测试代替 property test。

### 3.4 设施复用与能力迁移资格

第零阶段只复用基础设施 library/runtime，不复用旧 service topology：

可直接复用的设施：

- Python 3.11 与标准库；
- SQLAlchemy/Alembic/PostgreSQL driver；
- PostgreSQL row claim/work-item transport；
- Celery/Redis 只作为 legacy/migration transport adapter；
- FastAPI/Pydantic 作为外部 adapter；
- Prometheus metrics；
- Elasticsearch/pgvector client 作为 capability effect adapter；
- 现有 Docker image/build/test toolchain。

任何旧能力进入新架构前，必须通过 `FunctorizationEligibility`：

```python
@dataclass(frozen=True, slots=True)
class FunctorizationEligibility:
    capability_id: str
    typed_input_output_identified: bool
    operation_algebra_defined: bool
    identity_and_ordered_composition_defined: bool
    effect_boundary_explicit: bool
    failure_and_return_contract_explicit: bool
    authority_boundary_explicit: bool
    canonical_owner_identified: bool
    observation_profile_defined: bool
    hidden_global_state_removed_or_isolated: bool
    legacy_adapter_boundary_defined: bool
    source_evidence_refs: tuple[str, ...]
    object_schema_digests: tuple[str, ...]
    algebra_contract_digest: str
    observation_profile_digest: str
    counterexample_refs: tuple[str, ...]
    unresolved_loss_refs: tuple[str, ...]
    reviewer_identity: str
    disposition_rationale: str
    disposition: Literal["ADAPT", "EXTRACT_AND_REWRITE", "REIMPLEMENT", "REJECT"]
```

处置规则：

- `ADAPT`：现有接口已经具有稳定 typed IO、显式 effect 和可替换实现，只写包外 adapter；
- `EXTRACT_AND_REWRITE`：从大函数/route/service 中抽取语义对象和 algebra，在新包重写；
- `REIMPLEMENT`：旧结构严重依赖全局状态、内存 registry、API 反向 import、不可恢复 callback 或多真相源；只保留行为证据和 fixture，不复用实现；
- `REJECT`：历史/实验/不再需要的能力不进入 successor。

未通过资格判定的旧模块不得被新内核 import，也不得因“已有测试”自动成为 donor。

布尔字段只是 deterministic envelope check，不构成资格结论。`disposition` 必须由绑定源码/测试/对象 schema/algebra/观察/反例/损失的 reasoned review 支撑；缺少任一必要证据时状态保持 `ELIGIBILITY_PENDING`。

## 4. 函子化程序基底

后继架构的第一性对象不是 queue、worker、service、database row 或 workflow stage，而是有类型的领域对象与可组合程序。runtime 只解释这些程序，不定义它们的语义。

### 4.0 综合信息研究领域宪法

MRW 后继的稳定定义是：在项目作用域和人类授权边界内，把开放世界来源持续转化为可追溯、可质疑、可恢复、可交付的综合信息研究成果。市场、政策、社交、商品、电商、报告等只是来源域，不是稳定领域内核。

领域对象分为三组，并共享统一的 identity/provenance 制度：

- inquiry objects：`ResearchIntent`、`Inquiry`、`ResearchPlan`；
- research objects/relations：`SourceRef`、`MaterialRef`、`EvidenceQualification`、`Claim`、`Gap`；`CounterEvidence` 是 contradicting qualification 的 projection；
- product/effect objects：`ResearchArtifact`、`DeliveryIntent`、runtime `DeliveryAttempt`、provider-witnessed `DeliveryReceiptRef`。

基础关系至少包括：`derived_from`、`supports`、`contradicts`、`answers`、`opens`、`cites`、`included_in`、`supersedes`、`delivered_as`。关系必须绑定 source/target identity、project scope、content digest、provenance、qualification 与时间语义。

领域只需要以下生成运动：

```text
frame    : Need -> ResearchIntent + Inquiry + ResearchPlan
seek     : Inquiry/Plan -> SourceRef
observe  : SourceRef -> CapturedMaterialSnapshot + MaterialRef
qualify  : MaterialRef + Inquiry/Claim -> EvidenceQualification
relate   : EvidenceQualificationSet -> Claim | Gap
compose  : Claims + EvidenceQualificationSet -> ResearchArtifact
deliver  : ResearchArtifact -> DeliveryIntent -> DeliveryAttempt -> DeliveryReceipt
reopen   : Gap | CounterEvidence | ReviewFailure | SourceDelta
           -> successor Inquiry/Plan/Program
```

这些运动可用 `Identity/Then/MapOutput/ZipOrdered/TraverseOrdered/Decide/MaterializeSuccessor` 组合，但次序不默认可交换。特别是：

- `MaterialRef` 不是自动成立的 evidence；`EvidenceQualification` 是材料相对于某个 inquiry/claim 的有方向、有限定、可追溯 canonical relation；
- effect 成功、qualification/claim 被采纳、artifact admission、delivery receipt 是不同事实；
- gap、反证、零结果、来源失效与不确定性必须保持可见，并能形成 successor inquiry；
- 人类最终接受权、不可逆交付、project scope、credential、成本和 canonical owner 不因接口对称而消失。

`CapabilitySubject` 只描述“哪个实现可以解释某个领域 operator”，不再充当项目的第一性主体。旧 C1–C9 是领域运动的历史实现族、组合器、权威库或投影，不决定后继模块边界。

`Project Research Space` 是上述对象与关系的语义名称；`Research Ledger` 是其持久化身份/provenance 合同。它与 `Execution Journal` 共享 project-scoped identity，但不共享事实权威：前者保存研究对象和关系，后者保存运行、attempt、receipt 与 recovery。

### 4.0.1 程序运行元语言的同质化边界

后继架构的核心不是消灭异构任务，而是把异构任务的复杂性转换成同一套可编译、可调度、可恢复、可观测的程序协议：

控制元语言是小而闭合的；领域 object/operation contract family 是开放但必须版本化、内容寻址并带 owner 的。开放领域词汇不得通过修改 runtime switch 扩张控制语言。

```text
Heterogeneous task semantics
  --declare-->
OperationContract
  --encode-->
Program AST
  --compile-->
ExecutionPlan
  --bind current authority/resource/interpreter-->
RuntimeAssignment
  --claim through one protocol-->
RuntimeNode
  --interpret-->
Heterogeneous effect / outcome / failure / canonical owner
```

同质化只发生在以下结构：

- object/codec identity；
- operation contract 引用；
- Program 的恒等、有序复合、有限遍历和显式分支；
- plan occurrence、dependency、return barrier 与 source map；
- assignment 的 claim、lease、heartbeat、cancel、retry、reconcile 与 receipt；
- authority/resource/interpreter binding 的版本化引用；
- event、snapshot、idempotency、projection 与恢复协议。

异构性必须保留在以下 profile 中：

- `SemanticProfile`：该任务改变什么领域对象和关系；
- `EffectProfile`：网络、model、crawler、DB、filesystem、process 或纯变换；
- `ResourceProfile`：资源类、并发键、预算、deadline 与部署要求；
- `FailureProfile`：typed failure、retry、degraded、unknown 与补偿/readback；
- `AuthorityProfile`：grant、approval、project scope、credential 和 canonical owner；
- `InterpreterProfile`：具体实现、版本、依赖、凭据需求与 authoritative readback。

`RuntimeNode` 的“同构”仅表示共享 `claim -> validate binding -> interpret -> commit transition` 协议和相同 reducer/UoW，不表示所有节点安装全部 interpreter、持有全部凭据、拥有相同资源或可以交换执行顺序。部署可以有不同 `RuntimeNodeProfile`，但新增 profile 不得新增新的状态机、完成语义或控制真相源。

元语言的主要扩展性验收是：新增一个异构任务时，只增加 capability-owned `OperationContract`、codec、interpreter/profile 与针对性测试，不修改 Program AST、compiler fold、RuntimeAssignment 根类型、通用 reducer 或 `runtime_work_items` schema。若必须修改这些共享结构，必须说明是元语言表达能力缺口，而不是用 central switch 吞并新的业务分支。

上述保证分级如下：

- strict structure：Program 的 typed identity 与 ordered composition preservation；
- testable engineering regularity：不同 interpreter 在具名 observation profile 下的 compatibility、failure/authority preservation；
- heuristic only：将所有任务视作同一“函子”的直觉。没有对象/态射/规律证据时不得把 heuristic 升格为 naturality。

### 4.1 语义对象族

程序对象由版本化 codec 标识，而不是由任意 Python type 或 JSON 字典隐式决定：

```python
@dataclass(frozen=True, slots=True)
class ObjectType:
    type_id: str
    schema_version: str
    codec_id: str
    canonical_codec_version: str
```

```python
@dataclass(frozen=True, slots=True)
class ObjectContract:
    object_type: ObjectType
    identity_schema_ref: str
    content_schema_ref: str
    lifecycle_schema_ref: str
    owner_mode: Literal["CANONICAL_OWNED", "IMMUTABLE_EXTERNAL_REF", "DECLARED_LOSS_PROJECTION"]
    owner_binding_ref: str
    provenance_requirement_ref: str
    migration_profile_ref: str
    declared_loss_profile_ref: str | None
    contract_digest: str

@dataclass(frozen=True, slots=True)
class DomainContractSnapshot:
    snapshot_id: str
    snapshot_version: str
    object_contract_refs: tuple[str, ...]
    relation_contract_refs: tuple[str, ...]
    operation_contract_refs: tuple[str, ...]
    first_specimen_contract_ref: str
    snapshot_digest: str
```

任何“领域对象已冻结”的声明必须绑定 `DomainContractSnapshot`；只列对象名称不构成冻结。

第一纵向 specimen 的最小内容合同：

| 对象 | 必填语义 |
| --- | --- |
| `ResearchIntent` | purpose、audience/use、scope、as-of、constraints、expected delivery |
| `Inquiry` | question/hypothesis、acceptance/stop conditions、uncertainty ceiling |
| `ResearchPlan` | inquiry ref、ordered/partial-order work、budget、deadline、replan policy |
| `SourceRef` | owner、locator、source class、access/credential profile、source time |
| `MaterialRef` | source canonical identity、submission-time immutable snapshot ref/digest、source observed version/time |
| `EvidenceQualification` | material/inquiry/optional claim、direction、scope、uncertainty、validity、verifier、provenance closure |
| `Claim` | statement ref、scope、support/contradiction refs、uncertainty、status、base revision |
| `Gap` | inquiry requirement、reason、missing evidence/decision、reopen policy、closure condition |
| `ResearchArtifact` | content ref/digest、claim/evidence closure、citation closure、format、revision/status |
| `DeliveryIntent` | artifact revision、audience/channel/format、approval/authority、idempotency、irreversibility |
| `DeliveryAttempt/Receipt` | runtime occurrence；provider locator/readback；receipt digest/outcome time |

`SemanticProfile/EffectProfile/ResourceProfile/FailureProfile/AuthorityProfile` 均为独立 versioned contract：

- `SemanticProfile` 冻结允许读取/产生的 object/relation contract 与 declared loss；
- `EffectProfile` 冻结 execution class、external visibility、cancellation points 与 irreversible flag；
- `ResourceProfile` 冻结 resource classes、units、concurrency key、budget/deadline 与 node-profile requirements；
- `FailureProfile` 冻结 failure union、retryability、degraded/unknown、readback/compensation；
- `AuthorityProfile` 冻结 grant scopes、approval requirements、credential refs、canonical owner 与 revalidation points。

每个 profile 使用统一 `ContractProfileRef{profile_id, profile_version, profile_digest}`；profile 内容由 capability-owned package发布，catalog 只保存内容寻址引用。

MRW 初始类型分为领域对象、领域关系与 runtime/effect 对象。领域对象至少包括：

- `ResearchIntent.v1`、`Inquiry.v1`、`ResearchPlan.v1`；
- `SourceRef.v1`、`MaterialRef.v1`；
- `Claim.v1`、`Gap.v1`；
- `ResearchArtifact.v1`、`DeliveryIntent.v1`。

领域关系至少包括 `EvidenceQualification.v1` 与其 `SUPPORTS|CONTRADICTS|CONTEXT|INSUFFICIENT` direction；`CounterEvidence` 是 `CONTRADICTS` relation 的 bounded projection，不是独立 canonical object。

runtime 对象至少包括：

- `ProgramSpec.v1`、`ExecutionPlan.v1`、`RuntimeAssignment.v1`；
- `ValueRef.v1`、`RuntimeReceipt.v1`、`CommitIntent.v1`；
- `RunSnapshot.v1`、`AttemptRef.v1`、`CanonicalRef.v1`、`DeliveryAttempt.v1`、`DeliveryReceiptRef.v1`。

所有 canonical-owned 或 ledger-owned 领域对象共享：

```python
@dataclass(frozen=True, slots=True)
class ResearchObjectRef:
    object_id: str
    object_type: ObjectType
    project_key: str
    revision: int
    incarnation: str
    owner_binding_ref: str
    content_ref: str
    content_digest: str
    provenance_closure_digest: str
    valid_from: datetime | None
    valid_to: datetime | None
    lifecycle_state: Literal["DRAFT", "ADMITTED", "SUPERSEDED", "RETRACTED"]
```

`Evidence` 不再是一个含义不明的通用内容对象。它冻结为材料相对于 inquiry 或 claim 的资格关系：

```python
@dataclass(frozen=True, slots=True)
class EvidenceQualification:
    qualification_id: str
    project_key: str
    material_ref: ResearchObjectRef
    inquiry_ref: ResearchObjectRef
    claim_ref: ResearchObjectRef | None
    direction: Literal["SUPPORTS", "CONTRADICTS", "CONTEXT", "INSUFFICIENT"]
    scope_statement_ref: str
    uncertainty_profile_ref: str
    source_time: datetime | None
    observed_at: datetime
    valid_from: datetime | None
    valid_to: datetime | None
    verifier_profile_ref: str
    provenance_closure_digest: str
    qualification_digest: str
```

`EvidenceQualification` 只写入 `research_relations`；`qualification_id` 即 relation identity。不得再为同一 qualification 写 `research_objects` row。`supports/contradicts` 是该 relation 的 `direction`，不是第二份 canonical edge。

`MaterialRef` 不假设现有 Document 已有 revision/incarnation。第一 specimen 在 submission transaction 中通过 `DocumentCanonicalReadPort` 读取 `document_id/text_hash/updated_at + exact bytes`，把 exact bytes 固化为 project `successor_values` 的 immutable `CapturedMaterialSnapshot`，再生成同时绑定 source row observation 与 snapshot digest 的 `MaterialRef`。该 snapshot 只是可重放的 runtime input，不是 Research Ledger 对 Document canonical content 的复制，也不获得 Document 更新 authority。未来只有在 Document 提供真实 versioned readback 后，才可直接引用其 revision/incarnation。`Claim` 是可被支持、反驳、修订、supersede 或 retract 的 canonical research object；`Gap` 表示尚未闭合的 inquiry requirement；`CounterEvidence` 是 `direction=CONTRADICTS` 的资格关系及其 bounded interpretation，不再和 `Finding` 建立第四套 canonical identity。

`Finding` 和 `Insight` 仅是 API/UI 的 union projection 名称，展开为 `Claim | Gap | CounterEvidence`；合同、Ledger 与 Program 不注册 `Finding.v1` 或 `Insight.v1`。

不可逆或外部 Delivery 必须拆分：

- `DeliveryIntent`：artifact、受众、channel、format、authority/approval、idempotency 与不可逆性声明；
- `DeliveryAttempt`：一次 effect occurrence、external locator、lease、interpreter 与 disposition；
- `DeliveryReceipt`：authoritative readback 或 provider receipt，证明具体交付结果；
- artifact admission、delivery attempt 与 delivery success 是三个不同状态，不共享一个 `Delivery` 布尔字段。

旧 `SearchBrief`、`SourceDefinition`、`ExecutionRequest`、`CollectBatch`、`DocumentCandidate`、`TypedKnowledgeRef`、`WorkflowValue`、`AgentTaskState` 和 `ReportArtifact` 只能作为上述对象的 adapter DTO、legacy codec 或 bounded projection；它们不得各自建立新的 canonical identity。

对象 codec 必须定义 canonical serialization、版本迁移、解码失败和 declared loss。禁止把 `Mapping[str, Any]` 或 `default=str` 当作稳定对象身份。

### 4.2 程序态射

`Program[A, B]` 表示从对象 `A` 到对象 `B` 的有向程序。它不是一次函数调用，也不自动等于一次模型调用或一次 Celery task。

```python
class ProgramNode(Protocol, Generic[A, B]):
    node_kind: str
    @property
    def input_type(self) -> ObjectType: ...
    @property
    def output_type(self) -> ObjectType: ...
    @property
    def return_contract(self) -> ReturnContract: ...

@dataclass(frozen=True, slots=True)
class Identity(ProgramNode[A, A]):
    node_kind: Literal["identity"]
    object_type: ObjectType

@dataclass(frozen=True, slots=True)
class Pure(ProgramNode[A, B]):
    node_kind: Literal["pure"]
    input_type_ref: ObjectType
    output_type_ref: ObjectType
    literal_codec: str
    literal_digest: str
    literal_value: FrozenJsonValue

@dataclass(frozen=True, slots=True)
class Atom(ProgramNode[A, B]):
    node_kind: Literal["atom"]
    operation: OperationSpec[A, B]

@dataclass(frozen=True, slots=True)
class Then(ProgramNode[A, C]):
    first: ProgramNode[A, B]
    second: ProgramNode[B, C]

@dataclass(frozen=True, slots=True)
class MapOutput(ProgramNode[A, C]):
    source: ProgramNode[A, B]
    transform_id: str
    target_type: ObjectType

@dataclass(frozen=True, slots=True)
class ZipOrdered(ProgramNode[A, tuple[B, C]]):
    left: ProgramNode[A, B]
    right: ProgramNode[A, C]
    merge_id: str

@dataclass(frozen=True, slots=True)
class TraverseOrdered(ProgramNode[tuple[A, ...], tuple[B, ...]]):
    element_program: ProgramNode[A, B]
    traversal_policy: str

@dataclass(frozen=True, slots=True)
class Decide(ProgramNode[A, B]):
    discriminator_id: str
    branches: tuple[DecisionBranch[A, B], ...]
```

这些节点构成 inspectable initial AST。AST 必须保存完整子程序，而不是只保存 digest；否则不能重新编译、解释、恢复或审计。

每个 dataclass variant 都必须有固定 JSON discriminator `node_kind`，并通过 versioned codec 派生 input/output/return properties；不能依赖基类 annotation 自动生成字段。其余 `Then/MapOutput/ZipOrdered/TraverseOrdered/Decide` 同样拥有各自 literal discriminator。

### 4.3 恒等与有序复合

对每个对象 `A`，存在 `Identity[A]`。对类型相接的程序 `f: A -> B` 与 `g: B -> C`，`Then(f, g)` 表示有序复合。

必须验证：

- left identity：`Then(Identity[A], f)` 与 `f` 的结构观察一致；
- right identity：`Then(f, Identity[B])` 与 `f` 的结构观察一致；
- associativity：`Then(Then(f, g), h)` 与 `Then(f, Then(g, h))` 在 canonical normalization 后一致；
- failure/return order：前一程序失败、等待、取消或产生不可接受 qualifier 时，后一程序不能被静默执行；
- composition is ordered：以上规律不推出 `Then(f, g) == Then(g, f)`。

### 4.4 Functor-like output mapping

`MapOutput(program, transform_id)` 只允许使用注册、版本化、可序列化的纯 transform。禁止把任意 Python callable 写入可持久化程序。

`map_output` 必须满足：

- identity preservation：映射 `identity_transform` 不改变选定结构观察；
- ordered composition preservation：先映射 `f` 再映射 `g`，与映射注册的 `g_after_f` 等价；
- failure preservation：map 不执行被包裹 program 的外部 effect，也不把 failure/wait/cancel 改成 success；
- declared loss：有损 transform 必须有 `loss_profile_id`，不能冒充无损函子映射。

### 4.5 Applicative-like independent combination

`ZipOrdered` 表示两条值依赖形状在执行前已知的分支。它保留左/右位置和 merge order；它只暴露潜在批处理/并行信息，不授权并行。`Pure` 提供无 effect 的 typed value/unit 构造，使 product/merge identity 可以被精确定义。

编译器只有在以下信息都存在时，才可把 `ZipOrdered` 标记为 parallel eligible：

- 两分支没有数据依赖；
- effect/resource/authority scope 不冲突；
- failure aggregation 与 cancellation propagation 已声明；
- merge order 稳定；
- 外部观察允许并行 realization。

否则 `ZipOrdered` 按声明顺序解释。不存在默认交换律。

Zip 规律只对具名 merge algebra 声明：与 `Pure(Unit)` 组合并通过注册的 left/right-unit merge 后保持原 observation；三路 Zip 的 product associator 由具名 transform 见证。没有 merge algebra/associator 时，不声称 Applicative laws。

### 4.6 Traversable-like stable-shape execution

`TraverseOrdered` 保持输入形状、元素 identity 与访问顺序。它适用于 query terms、URLs、source items、workflow nodes 等稳定有限形状。

必须声明：

- visit order；
- fail-fast 或 error accumulation；
- output shape reconstruction；
- per-element identity；
- resource/backpressure policy；
- 是否允许 bounded parallel realization。

流式或无界输入不得伪装成 `TraverseOrdered`，必须使用另行冻结的 streaming contract。

`TraverseOrdered` 分为两种明确模式：

- `STATIC_SHAPE`：元素集合在 compile time 已知，compiler 为每个 element 生成 stable step occurrence；
- `MATERIALIZED_SHAPE`：输入 `ValueRef` 在 runtime 可得后，由 versioned `ShapeMaterializer` 读取有限形状，生成一个新的 successor Program/Plan epoch；原 plan 本身不在运行中原地扩写。

shape materialization 必须记录 element identity、order、count ceiling、materializer ID/version、source value digest 和 predecessor/successor plan identity。

### 4.7 数据依赖续作

任意 Python `bind`/closure 不可序列化、不可审计，也不能安全恢复。数据依赖路径只允许两种形式：

1. `Decide`：分支集合和 discriminator 在程序中预先可检查；
2. `MaterializeSuccessor`：当前 program 结束后，由具名、版本化 materializer 根据 canonical output 产生一个新的 successor `ProgramSpec`，并保存 predecessor/successor identity。

这对应 monadic sequencing 的工程需求，但不把不可见 continuation 塞入 runtime。

`Decide` 必须为每个 branch 产生显式事件与状态：

- `BRANCH_SELECTED`：记录 discriminator ID/version、input digest 和 selected branch；
- `BRANCH_NOT_SELECTED`：合法但本次未选，保持 branch identity；
- `BRANCH_SKIPPED`：因 guard/authority/typed incompatibility 不可执行；
- `BRANCH_UNRESOLVED`：discriminator 无法形成合法唯一决定，run 进入 WAITING/FAILED 而不是选第一个。

未选 branch 不能被当作成功执行，也不能从 lineage 中消失。

`MaterializeSuccessor` 的冻结对象为：

```python
@dataclass(frozen=True, slots=True)
class SuccessorMaterialization:
    materialization_id: str
    predecessor_run_id: str
    predecessor_step_id: str
    predecessor_plan_digest: str
    source_value_ref: ValueRef
    materializer_id: str
    materializer_version: str
    authority_digest: str
    idempotency_key: str
    successor_program: ProgramSpec
    successor_program_digest: str
    state: Literal["PREPARED", "MATERIALIZED", "REJECTED"]
    reason: str
```

`materialization_id/idempotency_key` 由 predecessor run/step/output digest、materializer ID/version 和 authority digest 确定性生成，并通过 `runtime_idempotency` 保证唯一 successor identity。它创建新 run/epoch/plan identity；不得在已运行 plan 内隐藏动态 closure。

### 4.8 Capability algebra

每个 C1–C9 能力定义自己的 operation algebra，而不是把所有业务塞入一个通用 `Operation{name,payload}`：

```python
class CapabilityAlgebra(Protocol):
    algebra_id: str
    algebra_version: str
    operation_kinds: frozenset[str]

    def validate_atom(self, operation: OperationSpec) -> ValidatedAtom: ...
    def input_type(self, kind: str) -> ObjectType: ...
    def output_type(self, kind: str) -> ObjectType: ...
    def return_contract(self, kind: str) -> ReturnContract: ...
    def effect_contract(self, kind: str) -> EffectSpec: ...
```

共享 runtime 只消费已验证的 atom/plan envelope；source-library、workflow、AgentCore 等领域差异保留在各自 algebra 与 interpreter 中。

### 4.9 编译函子

`Compile` 把 typed `Program[A,B]` 映射为 `ExecutionPlan[A,B]`：

```text
Program objects/morphisms
  --Compile-->
Execution objects/steps
```

它必须保持：

- object codec identity；
- `Identity`；
- `Then` 的有序复合；
- `MapOutput` 的 transform identity/version；
- `ZipOrdered` 与 `TraverseOrdered` 的形状和次序；
- failure/return/authority/resource contract；
- source-span 与 provenance。

编译器不执行 effect、不选择 provider、不提升 authority。

### 4.10 Interpreter 与具名自然变换

一个 interpreter 是 capability algebra 到具体 effect runtime 的具名实现：

```text
Program/ExecutionPlan
  --LegacyInterpreter-->
ObservedOutcome

Program/ExecutionPlan
  --SuccessorInterpreter-->
ObservedOutcome
```

legacy→successor 只有在对同一 atom/program、同一 input、同一 authority scope 和同一 observation profile 成立时，才能提出具名自然变换式兼容主张。默认用 `observational compatibility`，不得仅因两个类都实现 `execute()` 就声称 naturality。

每个兼容主张必须绑定：

- source/target interpreter ID/version；
- operation algebra/kind/version；
- input/output codec；
- observation profile；
- failure/authority/resource semantics；
- declared backend-local difference；
- counterexample fixture。

### 4.11 函子化基础规律矩阵

| 构造 | 必须检查 | 不自动提供 |
| --- | --- | --- |
| `Identity/Pure/Then` | left/right identity、associativity、ordered failure、pure no-effect | commutativity |
| `MapOutput` | identity、ordered composition、failure preservation | arbitrary callable serialization |
| `ZipOrdered` | shape、Pure(Unit) merge identity、具名 product associator、stable merge | parallel safety、commutativity |
| `TraverseOrdered` | identity、composition、shape/order preservation | unbounded streaming |
| `Decide` | branch totality、typed input/output、unselected branch visibility | hidden dynamic bind |
| `Compile` | identity 与 ordered composition preservation | effect execution |
| Interpreter substitution | named observational compatibility、failure/authority preservation | global naturality |
| Projection | source identity、declared loss、rebuild | reverse control authority |

以上构造与规律是后继架构的基础。PostgreSQL、RuntimeNode、可选 transport 与 API 是它们的 runtime realization，而不是架构的语义起点。

## 5. 目标系统的最小生成形式

目标系统先处理“综合信息研究如何从问题形成可追溯成果”，然后才处理程序如何运行。领域运动是主架构；compile/runtime 是它的可替换 realization。

```text
Need
  --frame-->
ResearchIntent + Inquiry + ResearchPlan
  --seek-->
SourceRef
  --observe-->
CapturedMaterialSnapshot + MaterialRef
  --qualify/relate-->
EvidenceQualification + Claim | Gap
  --compose/review/admit-->
ResearchArtifact
  --deliver-->
DeliveryIntent -> DeliveryAttempt -> DeliveryReceiptRef

Gap | CounterEvidence | ReviewFailure | SourceDelta
  --reopen-->
successor Inquiry/Plan/ResearchProgram
```

任意一段领域运动可形成 typed `ResearchProgram[A,B]`，再按下列统一 realization 执行：

```text
ResearchProgram
  --Compile preserving identity and ordered composition-->
ExecutionPlan
  --Qualify current authority/resources-->
RuntimeAssignment*
  --Interpret with one of N symmetric RuntimeNodes-->
Outcome + Receipt + ValueRef
  --Verify/Admit when canonical adoption is required-->
Research Space relation/object or capability-owned CanonicalRef
  --Project with declared loss-->
API / UI / Search / Graph / Writing / Process views
```

领域不变量：

1. inquiry、source、material snapshot/ref、evidence qualification、claim、artifact 与 delivery intent/receipt ref 共享稳定 project-scoped identity 和 provenance closure。
2. `MaterialRef` 到 `EvidenceQualification`、qualification 到 `Claim`、artifact admission 到 delivery receipt 都需要显式 qualification/admission/readback，不能由前一步成功自动推导。
3. gap、反证、拒绝、未知、过期与来源漂移不会在聚合或投影中消失。
4. 删除 Elasticsearch、graph、UI 或 AgentSession 投影后，仍能从 Research Space、capability canonical facts 与 runtime journal 恢复研究依据。

运行不变量：

1. `Program` 的有序组合在 `ExecutionPlan` 中保持。
2. `ExecutionPlan` 不授予 effect authority。
3. work-item claim、可选 broker delivery 或进程退出都不形成 run/step 完成事实。
4. `RuntimeNode` 只提交 typed outcome、receipt、staged artifact 或 authoritative readback。
5. verifier/admitter 不能从 runtime success 推断研究采纳或交付完成。
6. capability-owned canonical store 在逐能力 cutover 前保持原有事实权威。
7. runtime journal 只拥有 run/step/attempt/approval/idempotency 事实，不成为综合信息研究内容的第二真相源。
8. 所有 read model 和 dashboard 都能从 journal/canonical facts 重建。

## 6. 生产模块树

正式采用的代码必须进入以下 production root；生产代码禁止从 `experiments/` import：

```text
main/backend/app/successor_runtime/
  __init__.py

  research/
    __init__.py
    identities.py
    object_types.py
    inquiries.py
    sources.py
    materials.py
    evidence.py
    claims.py
    artifacts.py
    provenance.py
    relations.py
    errors.py

  language/
    __init__.py
    algebra.py
    program.py
    combinators.py
    transforms.py
    object_contracts.py
    profiles.py
    catalog.py
    normalize.py
    validate.py
    compile.py
    plan.py
    checksum.py
    laws.py

  capabilities/
    __init__.py
    contracts.py
    interpreter_profiles.py
    local_handlers.py
    seek.py
    observe.py
    relate.py
    compose.py
    deliver.py
    reopen.py

  runtime/
    __init__.py
    assignments.py
    claims.py
    node.py
    node_profiles.py
    deployment.py
    reducer.py
    transitions.py
    qualification.py
    admission.py
    work_items.py
    recurrence.py
    resources.py
    cancellation.py
    recovery.py
    ports.py

  substrate/
    __init__.py
    postgres/
      session.py
      models.py
      research_ledger.py
      owner_bindings.py
      runtime_journal.py
      programs.py
      plans.py
      values.py
      work_items.py
      schedules.py
      nodes.py
      idempotency.py
      approvals.py
      authority.py
      qualifications.py
      resources.py
      commit_intents.py
      projection_offsets.py
    blob/
      store.py
    projections/
      search.py
      graph.py
      writing.py
      runtime.py

  adapters/
    __init__.py
    http.py
    providers.py
    files.py
    database.py
    models.py
    transport.py
    observability.py


main/backend/app/successor_migration/
  __init__.py
  eligibility.py
  registry.py
  legacy_workflow_graph.py
  legacy_source_library.py
  legacy_collect_runtime.py
  legacy_agent_batch.py
  legacy_agent_session.py
  legacy_agent_core.py
  legacy_ingest.py
  legacy_writing.py
  parity_harness.py
```

目录是职责边界，不是任意 Layer：

- `research`：不可变综合信息研究对象、关系和 provenance；
- `language`：领域 operator 的 typed Program、组合子、编译与规律；
- `capabilities`：`seek/observe/relate/compose/deliver/reopen` operation contracts；
- `runtime`：同构 `RuntimeNode`、assignment、纯 reducer、qualification、admission 与 recovery；
- `substrate`：Research Ledger、Runtime Journal、work items、blob 和可重建 projection；
- `adapters`：HTTP、provider、filesystem、database、model、可选 transport 与 observability realization；
- `successor_migration`：位于新内核包外，唯一允许同时依赖 successor Port 与旧 API/service 的临时兼容层。

进一步裁决：

- `language` 只读取不可变 `OperationContractCatalogSnapshot`，验证 operation contract 是否在该 snapshot 中，不探测当前进程是否安装 handler；
- interpreter deployment availability 属于 qualification/deployment gate；
- sibling `successor_migration/*` 放置所有调用现有 legacy service 的 adapter，并实现 `EffectInterpreter` Port；
- successor-native interpreter 由 `capabilities` contract 与 `adapters` realization 组合，不建立按旧 subsystem 命名的 interpreter 目录；
- capability owner 发布 object/operation/profile contracts；central catalog 只索引内容寻址引用与 owner，不复制 validator、handler、provider routing、authority mutation 或业务事实。local handler mapping 只存在于 composition root，并由 dependency lint 禁止跨 capability import。

## 7. 强制依赖方向

### 7.1 允许依赖

```text
research
  <- language
  <- capabilities
  <- runtime

runtime.ports + capability contracts
  <- substrate
  <- adapters

research/runtime DTO
  <- bounded projections
  <- HTTP/SSE adapters
  <- existing FastAPI routes

migration adapters
  -> successor ports
  -> legacy services
```

外层可以 import 内层；`research/language/capabilities` 不得 import runtime 或具体设施。`runtime` 只能经 Port 访问 substrate/effect。

`main/backend/app/successor_runtime/**` 全包禁止 import 现有 `app.services.workflow_graph`、`source_library`、`collect_runtime`、`agent_batch`、`agent_sessions`、`agent_core`、`ingest`、`writing` 等 legacy service。greenfield 内核必须能在不加载这些模块的条件下独立 import、compile、运行纯测试和启动空 runtime。

### 7.2 禁止依赖

- `research`、`language`、`capabilities` 不得 import FastAPI、SQLAlchemy、Celery、Redis、settings、LangChain、OpenAI 或现有业务 service。
- `runtime` 只能依赖 `ports.py`，不得直接 import `substrate.postgres` 或 `adapters.*`。
- successor core 不得 import `app.api.*`。
- capability/effect adapter 不得直接更新 API/UI/AgentSession/Process read model。
- API route 不得直接选择 provider、写 runtime 表并同时执行 effect。
- 前端、dashboard、Celery `AsyncResult`、Celery inspect、Redis result backend 不得反向形成 scheduler、approval 或 completion authority。
- adapter 之间不得互相 import；共享纯逻辑进入 `research/language`，共享 effect contract 进入 `capabilities` 或 `runtime.ports`。
- legacy 与 successor 不得对同一 logical run 同时拥有 claim/write authority。

必须增加自动依赖门禁，至少验证以上禁止项。

## 8. 函子化 Program AST 与 Compiled IR

### 8.1 `ProgramSpec`

```python
@dataclass(frozen=True, slots=True)
class ProgramSpec:
    program_id: str
    contract_version: str
    project_key: str
    project_registry_revision: int
    project_scope_digest: str
    semantic_identity: str
    input_type: ObjectType
    output_type: ObjectType
    root: ProgramNode
    algebra_refs: tuple[AlgebraRef, ...]
    transform_refs: tuple[TransformRef, ...]
    observation_profile: str
    metadata: FrozenJsonObject
```

规则：

- `program_id` 是逻辑身份，不是内容身份；
- 内容身份由 canonical serialization 后的 `program_digest` 给出；
- `metadata` 必须进入声明了包含/排除字段的 codec，禁止 `default=str`；
- `root` 是第 4 节定义的完整 initial AST，不得退化为 operation digest 列表；
- AST 内的 `Atom` 保留 occurrence identity，同一 operation 可以重复出现；
- `Then/ZipOrdered/TraverseOrdered/Decide` 明确组合、偏序和稳定形状，不默认交换；
- 每个节点携带 success、failure、partial、wait、cancel 与 degraded return contract；
- `algebra_refs/transform_refs` 将程序绑定到具名、版本化 operation/transform registry；
- `observation_profile` 决定 parity/law 中可比较的外部观察，不能由测试临时选择任意字段。

### 8.2 `OperationSpec`

```python
@dataclass(frozen=True, slots=True)
class OperationContractRef:
    kind: str
    contract_version: str
    contract_digest: str

@dataclass(frozen=True, slots=True)
class OperationContract:
    ref: OperationContractRef
    input_type: ObjectType
    output_type: ObjectType
    return_contract_ref: str
    semantic_profile_ref: str
    effect_profile_ref: str
    resource_profile_ref: str
    failure_profile_ref: str
    authority_profile_ref: str
    interpreter_compatibility_ref: str
    observation_profile_ref: str
    allowed_override_schema_ref: str
    owner_capability_id: str

@dataclass(frozen=True, slots=True)
class OperationContractCatalogSnapshot:
    catalog_id: str
    catalog_version: str
    entries: tuple[tuple[str, str, str, str], ...]  # kind, version, digest, owner capability
    catalog_digest: str

@dataclass(frozen=True, slots=True)
class OperationSpec:
    operation_id: str
    contract_ref: OperationContractRef
    input_refs: tuple[ValueRef, ...]
    payload_ref: ValueRef
    allowed_overrides: FrozenJsonObject
```

`OperationContract` 是异构任务进入同质元语言的唯一声明面。Program 中只保存 contract ref、输入/payload ref 与经 contract schema 允许的 instance override；effect、resource、failure、authority 与 interpreter 需求不能被每个 Atom 任意重写。

`payload_ref` 指向 project-scoped value store，禁止在 public control schema、Program metadata 或 work item 中内联业务 payload。payload 禁止包含 secret bytes、API key、token、cookie、session 或数据库密码。需要凭据的 Atom 只能携带：

```python
@dataclass(frozen=True, slots=True)
class CredentialRef:
    provider: str
    project_key: str
    secret_name: str
    required_scope: str
    credential_epoch: int
```

credential resolver 仅在 interpreter effect 边界读取 secret；secret bytes 不进入 Program、ExecutionPlan、RuntimeAssignment、event、receipt、trace、evidence 或 digest。receipt 必须先执行 versioned redaction，再允许持久化。

`kind` 必须使用领域 operator namespace，而不是旧 subsystem 名称。第一纵向 slice 只冻结：

- `material.read_canonical_ref.v1`；
- `evidence.qualify.v1`；
- `claim.form_or_open_gap.v1`；
- `artifact.compose_markdown.v1`；
- `delivery.internal_export.v1`；
- projection operation 不进入普通 Program algebra；`agent_session` 等 read model 由独立 projector registry 处理。

`research.frame`、`source.seek`、`material.observe`、真实 external delivery 以及 C1–C9 其余 kind 在完成 eligibility 前保持 `ELIGIBILITY_PENDING`；不得在第零阶段预先冻结全部 schema。

central `OperationContractCatalogSnapshot` 只索引 `kind/version/digest/owner_capability_id` 和 immutable contract locator，不复制 validator、routing 或 handler 逻辑。contract 内容由 capability-owned package 发布；compiler 按 digest 读取并验证。

具体实现独立注册：

```python
@dataclass(frozen=True, slots=True)
class InterpreterProfile:
    interpreter_id: str
    interpreter_version: str
    supported_contract_refs: tuple[OperationContractRef, ...]
    dependency_digest: str
    security_profile_ref: str
    resource_profile_ref: str
    credential_requirements_ref: str | None
    cancellation_profile_ref: str
    idempotency_profile_ref: str
    authoritative_readback_profile_ref: str | None
    receipt_codec_ref: str

@dataclass(frozen=True, slots=True)
class RuntimeNodeProfile:
    node_profile_id: str
    installed_interpreter_profile_digests: tuple[str, ...]
    installed_capability_ids: tuple[str, ...]
    resource_classes: tuple[str, ...]
    security_profile_refs: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class DeploymentCatalogSnapshot:
    catalog_id: str
    catalog_version: str
    node_profile_digests: tuple[str, ...]
    interpreter_profile_digests: tuple[str, ...]
    runtime_protocol_versions: tuple[str, ...]
    catalog_digest: str

@dataclass(frozen=True, slots=True)
class InterpreterBinding:
    operation_contract_digest: str
    interpreter_profile_digest: str
    deployment_catalog_digest: str
    runtime_protocol_version: str
    project_scope_digest: str
    resource_policy_epoch: int
    authority_requirement_digest: str
    binding_digest: str
```

handler registry 是进程本地、插件式、按 `InterpreterProfile` 注册的 mapping；禁止 central `if kind == ...` switch。compiler 只检查 contract；qualification 选择并冻结 exact `InterpreterBinding`；claim 时节点必须证明自身 profile 匹配 exact interpreter/contract/resource/security binding。`RuntimeNodeProfile.installed_capability_ids` 只说明代码/依赖可用性，不授予运行权限；当前 grant 必须来自 16.1 的 canonical authority sources。

`operation_id` 标识 Program AST 中的逻辑 Atom。compiler 展开组合/遍历后，为每个执行 occurrence 生成 plan-local `step_id`；同一 `operation_id` 可产生多个不同 `step_id`。runtime、queue、lease、attempt 和 event 只使用 `step_id` 定位 occurrence，同时保留 `operation_id` 供 provenance/归并。

`EffectSpec.execution_class` 只能是：

- `PURE_TRANSFORM`：在 RuntimeNode/本地纯 interpreter 中产生 runtime `ValueRef`，不进入 canonical admission；
- `EFFECTFUL`：网络/DB/model/process 等 effect，产生 receipt 与 value/staged artifact；
- `ADMISSION`：显式 canonical verification/commit operation；
- `PROJECTION`：不进入普通 Program algebra，由 projector registry 单独执行。

`ReturnContract.admission_required` 决定 compiler 是否在 effect step 后确定性插入独立 `CompiledAdmission` control/step node。effect step 只负责产生 staged artifact 并完成自身 execution；admission step 拥有独立 `step_id/attempt/authority/CommitIntent`，由任一具备对应 grant 的 RuntimeNode 处理 `VERIFY_ADMIT` assignment。runtime 不得临时生成 plan 外 admission work。pure、MapOutput、runtime-value-only step 在 output codec/digest 验证后直接 `SUCCEEDED`。

`CompiledAdmission` 是原 Atom 的 exported semantic return barrier：

- 原 Atom 的所有普通 downstream edges 重定向到 admission step；
- effect step 的 staged output 只能被该 admission step或显式标注 `staged_internal_only` 的 control node 读取；
- `ProgramPlanSourceMap` 将一个 admission-required Atom 映射为 `effect step + CompiledAdmission` composite；
- `Then(f,g)` 中若 `f` 需要 admission，`g` 依赖 admission composite 的 canonical success，而不是 effect step 的 staged success；
- failure/cancel/wait 从 effect/admission composite 按原 Atom `ReturnContract` 向外传播；
- Compile/Then preservation 的 `NormalizedPlanStructure` 以该 composite 的 terminal semantic return 为准。

### 8.3 `ExecutionPlan`

```python
@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    plan_id: str
    program_id: str
    program_digest: str
    input_type: ObjectType
    output_type: ObjectType
    compiler_id: str
    compiler_version: str
    control_root: CompiledControlNode
    ordered_steps: tuple[CompiledStep, ...]
    dependency_index: FrozenDependencyIndex
    ready_order: tuple[str, ...]
    source_map: tuple[ProgramPlanSourceMap, ...]
    return_policy: PlanReturnPolicy
    completion_policy: CompletionPolicy
    effect_closure_digest: str
    authority_closure_digest: str
    resource_closure_digest: str
    plan_digest: str
```

`CompiledControlNode` 保留 `Identity/Then/MapOutput/ZipOrdered/TraverseOrdered/Decide` 的控制结构；`ordered_steps` 只是调度索引，不能取代 control root。`ProgramPlanSourceMap` 将每个 AST node/Atom/transform/branch 映射到 compiled step/control node，保证 source provenance 与 composition 可回读。

ExecutionPlan 定义与 Program 对应的组合操作：

```python
def identity_plan(object_type: ObjectType) -> ExecutionPlan: ...
def compose_plans(first: ExecutionPlan, second: ExecutionPlan) -> ExecutionPlan: ...
def map_plan_output(plan: ExecutionPlan, transform: TransformRef) -> ExecutionPlan: ...
```

Compile preservation 使用 `NormalizedPlanStructure.v1` 观察检查，而不是比较 operational `plan_id/step_id` 或只比较 flat topo list。`step_id` 由 source AST path + Atom content digest 确定性生成；`plan_id` 不参与结构等价。

- `Compile(Identity[A]) ≃struct identity_plan(A)`；
- `Compile(Then(f,g)) ≃struct compose_plans(Compile(f), Compile(g))`；
- `Compile(MapOutput(p,t)) ≃struct map_plan_output(Compile(p), t)`；
- Zip/Traverse/Decide 的 control root、branch/shape/source map、return/completion policy 保持。

编译必须验证：

- operation schema 与 frozen `OperationContractCatalogSnapshot` 成员资格；
- input/output compatibility；
- step ID/occurrence 唯一性；
- dependency closure、cycle、stable topological order；
- effect、authority、resource、retry 与 timeout 完整性；
- payload canonical codec；
- failure/return contract；
- unsupported version；
- dependency 与 parallel group 不冲突。

任何验证失败必须在 effect 之前返回 typed `CompileFailure`。

compiler 不验证当前部署的 interpreter availability。`QualificationPort` 在已创建 `SUBMITTED` run、exact plan 持久化后，从 immutable deployment catalog 选择 exact compatible `InterpreterProfile` 并生成 `InterpreterBinding`，同时核对 project/capability authority 与 resource ceiling；缺失时返回 `INTERPRETER_UNAVAILABLE`，不得让 compiler import 具体 handler。qualification 只证明可满足性，不预留执行资源。

### 8.4 `QualifiedPlan` 与逐 step authorization

```python
@dataclass(frozen=True, slots=True)
class AuthoritySourceBinding:
    source_kind: Literal["PROJECT_SCOPE", "GRANT", "APPROVAL", "CAPABILITY_AUTHORITY", "CREDENTIAL_REF"]
    source_ref: str
    source_digest: str
    source_epoch: int

@dataclass(frozen=True, slots=True)
class StepAuthorizationBinding:
    run_id: str
    step_id: str
    operation_kind: str
    operation_contract_digest: str
    capability_id: str
    claim_owner: Literal["legacy", "successor"]
    claim_authority_epoch: int
    claim_policy_digest: str
    payload_digest: str
    actor_id: str
    project_key: str
    project_registry_revision: int
    project_scope_digest: str
    interpreter_binding_digest: str
    deployment_catalog_digest: str
    authority_source_bindings: tuple[AuthoritySourceBinding, ...]
    grants_digest: str
    approval_refs: tuple[str, ...]
    resource_ceiling_digest: str
    resource_policy_epoch: int
    queue_eligibility_digest: str
    grant_epoch: int
    expires_at: datetime
    canonical_base_revision: int
    canonical_incarnation: str
    binding_digest: str

@dataclass(frozen=True, slots=True)
class QualifiedPlan:
    plan_digest: str
    authority_context_digest: str
    step_bindings: tuple[StepAuthorizationBinding, ...]
    awaiting_approval_steps: tuple[str, ...]
    denied_steps: tuple[QualificationFailure, ...]
    qualification_digest: str
```

同一个 program 中不同 step 可以具有不同 effect、grant、approval、resource ceiling 和 expiry。禁止用一个 program-level digest 替代逐 step authorization。`QualifiedPlan` 在 run 已存在、ExecutionPlan 已持久化后，通过独立 UoW attach 到 run，并在 work-item creation、claim、effect 前和 admission 时重新读取/验证。具体 `ExecutionReservation` 只在 claim transaction 创建，不进入 qualification binding。

### 8.5 `ValueRef`、`StagedArtifact` 与 data plane

运行时不能只保存 output digest。每个 step 的输入输出通过 typed `ValueRef` 指向可读、可验证的数据：

```python
@dataclass(frozen=True, slots=True)
class ValueRef:
    value_id: str
    project_key: str
    object_type: ObjectType
    codec_id: str
    content_digest: str
    storage_kind: Literal["project_value_ref", "runtime_blob_ref", "artifact_ref", "canonical_ref"]
    store_id: str
    store_version: str
    storage_ref: str
    byte_size: int
    provenance_digest: str

@dataclass(frozen=True, slots=True)
class StagedArtifact:
    artifact_id: str
    run_id: str
    step_id: str
    value_ref: ValueRef
    qualifier: str
    declared_loss_profile: str | None
    receipt_digest: str
```

规则：

- public control schema 的 `runtime_values` 只保存 `ValueRef` metadata、digest 与 opaque storage ref，不保存 inline JSON、bytes、query、prompt、document text 或其他业务 payload；
- 小型结构化 runtime value 保存到 project schema 的 `successor_values`，control row 使用 `project_value_ref`；
- 大文本、PDF、二进制或自然产物使用 project-scoped、content-addressed `runtime_blob.v1`，control row 只保存 `runtime_blob_ref` 与 digest/size/mime/provenance；
- `canonical_ref` 只引用 capability-owned canonical store，不复制事实；
- decoder 必须按 `ObjectType/codec_id` 验证内容；
- staged artifact 在 verify/admit 前不是 canonical fact；
- value/artifact 必须可由 RuntimeNode、verifier、recovery handler 和 projector 跨进程读取；
- 删除临时 value 的清理策略不得删除仍被 run/event/receipt/canonical ref 引用的内容。

`runtime_blob.v1` 第一阶段 realization：新增 Docker named volume `runtime_artifacts`，使用 `/var/lib/mrw/runtime-artifacts/projects/<project-scope-digest>/sha256/<prefix>/<digest>`，挂载到 backend 与获得相应 project grant 的 RuntimeNode；写入使用同目录 temporary file、fsync、digest/size 校验和 atomic rename。项目 schema 先保存 blob metadata/staging intent，文件完成后再由 control journal 记录 opaque `ValueStored` ref/event。备份、retention、orphan reconciliation、project deletion、grant check 和只读 digest verification 必须进入 P0-B。旧 artifact/file service 只有通过 eligibility 后才能作为另一个 `store_id` adapter，不能成为 greenfield 默认依赖。

## 9. 核心 Port API

以下签名必须在冻结实现中保持等价语义；可调整 Python 细节，但不得合并 authority、effect、store 和 projection 职责。

```python
@dataclass(frozen=True, slots=True)
class RuntimeScope:
    project_scope: ProjectScopeRef
    actor_id: str

@dataclass(frozen=True, slots=True)
class ProjectScopeRef:
    project_key: str
    resolved_schema: str
    project_registry_revision: int
    scope_digest: str

class ProjectScopeResolver(Protocol):
    def resolve(self, authenticated_project_key: str) -> ProjectScopeRef: ...
    def resolve_expected(self, project_key: str, registry_revision: int,
                         scope_digest: str) -> ProjectScopeRef | ProjectScopeStale: ...

@dataclass(frozen=True, slots=True)
class ControlPlaneScope:
    system_actor_id: str
    permission: Literal["runtime.cross_project_claim"]
    authority_epoch: int

class ProgramCompiler(Protocol):
    def compile(self, program: ProgramSpec) -> ExecutionPlan: ...

class RuntimeUnitOfWork(Protocol):
    programs: "ProgramRepository"
    plans: "PlanRepository"
    store: "RuntimeStore"
    work_items: "WorkItemPort"
    values: "ValueStorePort"
    qualifications: "QualificationRepository"
    resources: "ResourcePolicyPort"
    approvals: "ApprovalRepository"
    commit_intents: "CommitIntentRepository"

    def __enter__(self) -> "RuntimeUnitOfWork": ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def __exit__(self, exc_type, exc, tb) -> None: ...

class ProgramRepository(Protocol):
    def put_exact(self, scope: RuntimeScope, program: ProgramSpec,
                  expected_digest: str) -> ProgramRecord: ...
    def get(self, scope: RuntimeScope, program_id: str) -> ProgramSpec: ...

class PlanRepository(Protocol):
    def put_exact(self, scope: RuntimeScope, plan: ExecutionPlan,
                  expected_digest: str) -> PlanRecord: ...
    def get(self, scope: RuntimeScope, plan_digest: str) -> ExecutionPlan: ...

class RuntimeStore(Protocol):
    def create_run(self, scope: RuntimeScope, command: CreateRun,
                   program: ProgramSpec) -> RunSnapshot: ...
    def append_events(self, scope: RuntimeScope, run_id: str, expected_revision: int,
                      events: tuple[RuntimeEvent, ...]) -> RunSnapshot: ...
    def claim_step(self, scope: RuntimeScope, claim: StepClaim) -> ClaimedStep | ClaimConflict: ...
    def heartbeat(self, scope: RuntimeScope, heartbeat: LeaseHeartbeat) -> LeaseState: ...
    def stage_outcome(self, scope: RuntimeScope, outcome: StagedOutcome,
                      expected_revision: int) -> RunSnapshot: ...
    def load_run(self, scope: RuntimeScope, run_id: str) -> RunSnapshot: ...
    def attach_plan(self, scope: RuntimeScope, run_id: str,
                    plan: ExecutionPlan, expected_revision: int) -> RunSnapshot: ...
    def load_events(self, scope: RuntimeScope, run_id: str,
                    after_seq: int = 0) -> tuple[RuntimeEvent, ...]: ...

class WorkItemPort(Protocol):
    def enqueue(self, scope: RuntimeScope,
                assignment: RuntimeAssignment) -> WorkItemRecord: ...
    def claim_due(self, control_scope: ControlPlaneScope, limit: int,
                  lease: LeaseRequest,
                  node_profile_digest: str,
                  deployment_catalog_digest: str,
                  authority_snapshot_digest: str) -> tuple[WorkItemRecord, ...]: ...
    def heartbeat(self, control_scope: ControlPlaneScope, work_item_id: str,
                  lease_token: str, new_expiry: datetime) -> WorkItemRecord: ...
    def complete(self, scope: RuntimeScope, work_item_id: str,
                 lease_token: str, expected_revision: int,
                 result_digest: str) -> WorkItemRecord: ...
    def fail_or_reschedule(self, scope: RuntimeScope, work_item_id: str,
                           lease_token: str, expected_revision: int,
                           failure: TypedFailure,
                           next_attempt_at: datetime | None) -> WorkItemRecord: ...
    def claim_expired_reservations(self, control_scope: ControlPlaneScope,
                                   limit: int, now: datetime) -> tuple[ResourceReservation, ...]: ...

class ValueStorePort(Protocol):
    def put_inline(self, scope: RuntimeScope, value: EncodedValue) -> ValueRef: ...
    def prepare_blob(self, scope: RuntimeScope,
                     intent: BlobWriteIntent) -> PreparedValueRef: ...
    def finalize_blob(self, scope: RuntimeScope, value_id: str,
                      expected_revision: int,
                      receipt: BlobWriteReceipt) -> ValueRef: ...
    def mark_blob_failed(self, scope: RuntimeScope, value_id: str,
                         expected_revision: int,
                         failure: BlobWriteFailure) -> PreparedValueRef: ...
    def readback_blob(self, scope: RuntimeScope,
                      value_ref: ValueRef) -> BlobReadback: ...
    def get(self, scope: RuntimeScope, value_ref: ValueRef) -> DecodedValue: ...
    def stage(self, scope: RuntimeScope, artifact: StagedArtifact) -> StagedArtifact: ...

class QualificationRepository(Protocol):
    def save_plan_qualification(self, scope: RuntimeScope,
                                qualified: QualifiedPlan) -> None: ...
    def load_step_binding(self, scope: RuntimeScope, run_id: str,
                          step_id: str) -> StepAuthorizationBinding: ...

class ApprovalRepository(Protocol):
    def decide(self, scope: RuntimeScope, decision: ApprovalDecision,
               expected_revision: int) -> ApprovalRecord: ...
    def load(self, scope: RuntimeScope, approval_id: str) -> ApprovalRecord: ...

class CommitIntentRepository(Protocol):
    def prepare(self, scope: RuntimeScope, intent: CommitIntent,
                expected_revision: int) -> CommitIntent: ...
    def load(self, scope: RuntimeScope, commit_intent_id: str) -> CommitIntent: ...
    def record_result(self, scope: RuntimeScope, commit_intent_id: str,
                      expected_revision: int,
                      result: CanonicalCommit | AdmissionRejected | CommitOutcomeUnknown) -> CommitIntent: ...

class ResourcePolicyPort(Protocol):
    def reserve(self, scope: RuntimeScope, request: ResourceReservationRequest,
                expected_policy_epoch: int) -> ResourceReservation | ResourceLimit: ...
    def release(self, scope: RuntimeScope, reservation_id: str,
                lease_token: str) -> None: ...
    def reap_expired(self, scope: RuntimeScope, now: datetime) -> tuple[str, ...]: ...

class EffectInterpreter(Protocol):
    interpreter_id: str
    operation_kinds: frozenset[str]
    def execute(self, step: ClaimedStep, context: ExecutionContext) -> EffectOutcome: ...
    def readback(self, attempt: EffectAttempt) -> AuthoritativeReadback | ReadbackUnavailable: ...
    def prove_not_started(self, attempt: EffectAttempt) -> NonStartProof | NonStartUnprovable: ...
    def cancel(self, attempt: EffectAttempt) -> CancelReceipt: ...

class QualificationPort(Protocol):
    def qualify(self, plan: ExecutionPlan,
                authority: AuthorityContext) -> QualificationDecision: ...

class AuthorityProvider(Protocol):
    def current_context(self, scope: RuntimeScope, actor_id: str) -> AuthorityContext: ...
    def current_step_binding(self, scope: RuntimeScope, run_id: str,
                             step_id: str) -> StepAuthorizationBinding: ...
    def current_approval(self, scope: RuntimeScope,
                         approval_id: str) -> ApprovalRecord | ApprovalRevoked: ...
    def current_canonical_head(self, scope: RuntimeScope,
                               canonical_owner: str,
                               object_id: str) -> CanonicalRef | CanonicalUnavailable: ...
    def is_revoked(self, scope: RuntimeScope,
                   binding_digest: str, grant_epoch: int) -> bool: ...

class AdmissionPort(Protocol):
    def verify_and_commit(self, scope: RuntimeScope,
                          intent: CommitIntent,
                          candidate: AdoptionCandidate,
                          binding: VerificationBinding) -> CanonicalCommit | AdmissionFailure: ...
    def readback_commit(self, scope: RuntimeScope,
                        commit_intent_id: str) -> CanonicalCommit | CommitNotFound: ...

class Projector(Protocol):
    projector_id: str
    projector_version: str
    source_kind: Literal["runtime_journal", "capability_canonical"]
    def apply(self, scope: RuntimeScope, source: ProjectionSource,
              offset: ProjectionOffset) -> ProjectionOffset: ...
    def rebuild(self, scope: RuntimeScope,
                source: ProjectionSource) -> ProjectionOffset: ...
```

所有写方法必须携带 scope、`expected_revision`、epoch/incarnation、lease token 或等价 CAS 条件。不能用“最后写入者获胜”覆盖 run/step 状态。

`RuntimeUnitOfWork` 定义事务边界：第一事务原子提交 exact Program + SUBMITTED run + initial event + `COMPILE` work item；第二事务原子提交 exact Plan + plan attachment + compile event + `QUALIFY` work item；后续每个 transition 原子提交 events + snapshots + attempts/values/resources + successor work items。对同一 PostgreSQL 实例内的 public control + validated project successor tables，UoW 必须使用同一 connection/transaction 和 schema-qualified table identity；Port 实现不能在内部隐式开启彼此独立的 session 后声称原子性。对于 legacy/external canonical store，只能使用 CommitIntent/readback protocol，不能伪称跨库原子事务。

只有 server-side `ProjectScopeResolver` 可以构造 `ProjectScopeRef`；API payload、transport message 和 RuntimeNode 不得直接提供任意 schema 名。`RuntimeSessionLocal` 固定 public；UoW 只能用经过 digest/revision/incarnation 验证的 `ProjectScopeRef` 构造 schema-qualified successor table handle。legacy 业务 interpreter 通过 capability Port 访问项目 repository，不把任意 schema 字符串传入 ORM。

第零阶段不新增独立 `tenant_id` 维度；MRW 的隔离单位是 `ProjectScopeRef`。未来若引入 tenant，必须另立迁移合同，不能用普通字符串字段提前声称 tenant 隔离。

确定的创建顺序是：API adapter 先分配全局 `run_id`，在一个 UoW 中 `put_exact ProgramSpec + create SUBMITTED run + ProgramAccepted event + COMPILE work item`；任一 RuntimeNode 随后编译并在另一个 UoW 中 `put_exact ExecutionPlan + attach_plan + PlanCompiled event + QUALIFY work item`；再基于已存在的 run_id 生成/持久化 `QualifiedPlan`。同 digest 不同 canonical bytes 必须 fail closed。不得采用“先 qualification 后 create run”的另一套时序。

`WorkItemPort.claim_due` 是唯一跨项目 claim Port。它只接受 system-created `ControlPlaneScope`，返回的每条记录必须携带数据库读取的可信 `project_key`；RuntimeNode 不接受客户端 project key，并为每条记录重新构造 `RuntimeScope` 后调用 transition/UoW。

`ProjectionSource` 必须绑定 source kind、project scope、runtime/canonical identity、revision、incarnation、content/event closure digest 和 codec/version。一个 projector 只能声明一种 source kind；跨 runtime/canonical 的组合 read model 由显式 join projector 处理，不得把两者当成同一事实流。

## 10. Runtime 状态模型

### 10.1 Run state

```text
SUBMITTED
  -> COMPILING
  -> AWAITING_APPROVAL | READY
  -> RUNNING
  -> WAITING | RECONCILING | CANCELLING
  -> COMPLETED | FAILED | CANCELLED | SUPERSEDED
```

规则：

- `COMPLETED` 只表示合同声明的 run completion，不自动表示研究结论正确、canonical research adoption 或 Delivery 完成；
- `WAITING`、`RECONCILING` 与 `DEGRADED` qualifier 不是成功终态；
- `SUPERSEDED` 保留 predecessor/successor identity；
- terminal state 只能由 reducer 根据 admitted events 产生；
- readback/projection 不能直接写 terminal state。
- `DEGRADED` 是 outcome qualifier，不是 Run state；只有 capability completion policy 接受该 qualifier 时，相关 step 才能进入 `SUCCEEDED`。

### 10.2 Step state

```text
PENDING | AWAITING_APPROVAL | READY
CLAIMED | RUNNING | COMMITTING
WAITING_EXTERNAL | RETRY_SCHEDULED | RECONCILING | CANCEL_REQUESTED
SUCCEEDED | FAILED | CANCELLED | SUPERSEDED | NOT_SELECTED | SKIPPED_BY_DECISION
```

该列表是状态全集，不表示任意相邻状态都可转换；唯一合法边只来自 10.5 表。`DISPATCH_PENDING/DISPATCHED/STAGED` 不属于 greenfield StepState，transport observation 只能进入 work-item metadata，staged 是 output/admission disposition。`COMMITTING` 只用于 canonical admission 或 DeliveryAttempt 已开始但 receipt 尚未确认的窗口。

### 10.3 Effect disposition

```text
NOT_STARTED
IN_FLIGHT
SUCCEEDED
FAILED
OUTCOME_UNKNOWN
```

Run state、Step state 与 Effect disposition 是三种不同对象，不得压缩成一个 `status` 字符串。

### 10.4 Run command/event/guard/owner 转换表

| 当前 Run 状态 | Command/Event | Guard | 下一 Run 状态 | Owner |
| --- | --- | --- | --- | --- |
| `SUBMITTED` | `CompileRequested` | program/spec digest 存在 | `COMPILING` | application |
| `COMPILING` | `PlanCompiled` | plan/catalog digest 有效 | `AWAITING_APPROVAL` 或 `READY` | compiler/qualification |
| `AWAITING_APPROVAL` | `RequiredApprovalsGranted` | 所有 required step binding 有效 | `READY` | qualification |
| `READY` | `FirstRequiredStepReady` | reducer fold 有可执行 step | `RUNNING` | RuntimeNode/reducer |
| `RUNNING` | `RunWaitingDerived` | required step 全部 waiting/reconciling/resource-blocked | `WAITING` 或 `RECONCILING` | run reducer |
| `WAITING/RECONCILING` | `RequiredStepRunnable` | 至少一个 required step 重新可执行 | `RUNNING` | run reducer |
| `RUNNING` | `RunCompletionDerived` | 所有 required effect/admission/control returns 满足 completion policy | `COMPLETED` | run reducer |
| 任意非终态 | `RequiredStepFailed` | failure policy 不允许继续 | `FAILED` | run reducer |
| 任意非终态 | `CancellationRequested` | actor/grant 有效；检查 active/unknown effect | 无 active effect 时 `CANCELLED`，否则 `CANCELLING` | application/run reducer |
| `CANCELLING` | `RequiredCleanupAndReadbackSettled` | 所有 required step 已形成 authoritative disposition | `CANCELLED`、`COMPLETED`、`FAILED` 或 `RECONCILING` | run reducer |
| 任意非终态 | `SuccessorRunAdopted` | predecessor/successor binding 有效 | `SUPERSEDED` | application |

### 10.5 Step command/event/guard/owner 转换表

| 当前 Step 状态 | Command/Event | Guard | 下一 Step 状态 | Owner |
| --- | --- | --- | --- | --- |
| `PENDING` | `DependenciesSatisfied` | dependency return contract 满足 | `READY` 或 `AWAITING_APPROVAL` | reducer/qualification |
| `AWAITING_APPROVAL` | `ApprovalGranted` | binding/epoch/expiry 匹配 | `READY` | qualification |
| `READY` | `StepClaimed` | work-item CAS/lease/authority/resource/incarnation 匹配 | `CLAIMED` | RuntimeNode |
| `CLAIMED` | `EffectStarted` | current authority 重验通过 | `RUNNING` | RuntimeNode/interpreter |
| `RUNNING` | `PureValueProduced` | codec/digest 有效且 admission_required=false | `SUCCEEDED` | pure interpreter/reducer |
| `RUNNING` | `RuntimeValueProduced` | receipt/codec 有效且 admission_required=false | `SUCCEEDED` | interpreter/reducer |
| `RUNNING` | `EffectReceiptLost` | effect 可能已发生 | `RECONCILING` | RuntimeNode/recovery handler |
| effect `RUNNING` | `OutcomeStaged` | value/receipt digest 有效且 downstream CompiledAdmission 存在 | `SUCCEEDED` | RuntimeNode/reducer |
| admission `PENDING` | `StagedDependencySatisfied` | staged artifact/binding 完整 | `READY` 或 `AWAITING_APPROVAL` | reducer/qualification |
| admission `RUNNING` | `CommitPrepared` | verifier/authority/base/intent 有效 | `COMMITTING` | RuntimeNode/admission interpreter |
| admission `COMMITTING` | `CommitReadbackConfirmed` | commit intent/idempotency 匹配 | `SUCCEEDED` | canonical owner/admission |
| admission/delivery `COMMITTING` | `CommitOrDeliveryOutcomeUnknown` | external effect 可能已发生 | `RECONCILING` | RuntimeNode/recovery handler |
| admission/delivery `COMMITTING` | `CommitOrDeliveryRejected` | authoritative rejection receipt 匹配 | `FAILED` | canonical owner/provider readback |
| `RECONCILING` | `AuthoritativeReadbackSucceeded` | readback identity 匹配；可返回 staged output disposition | `SUCCEEDED` | RuntimeNode/recovery handler |
| `RECONCILING` | `AuthoritativeReadbackFailed` | readback identity 匹配 | `FAILED` | RuntimeNode/recovery handler |
| `RECONCILING` | `ReadbackUnavailable` | 无终态证明 | `WAITING_EXTERNAL` | RuntimeNode/recovery handler |
| `WAITING_EXTERNAL` | `ReconcileRequested` | next check 到时 | `RECONCILING` | due work item |
| `FAILED` | `RetryAuthorized` | retryable + budget + new epoch | `RETRY_SCHEDULED` | application/authority |
| `RETRY_SCHEDULED` | `RetryDue` | backoff 到时 | `READY` | due work item |
| branch step | `BranchNotSelected` | decision digest 有效 | `NOT_SELECTED` | decision interpreter/reducer |
| branch step | `BranchSkipped` | typed guard/authority 不满足 | `SKIPPED_BY_DECISION` | decision interpreter/reducer |
| `PENDING/AWAITING_APPROVAL/READY/RETRY_SCHEDULED` | `CancellationRequested` | actor/grant 有效且 effect 未开始 | `CANCELLED` | API/reducer |
| `CLAIMED/RUNNING/COMMITTING/WAITING_EXTERNAL/RECONCILING` | `CancellationRequested` | actor/grant 有效 | `CANCEL_REQUESTED` | API/reducer |
| `CANCEL_REQUESTED` | `CleanupOrReadbackConfirmed` | cleanup/readback binding 有效 | `CANCELLED`、`SUCCEEDED`、`FAILED` 或 `WAITING_EXTERNAL` | RuntimeNode/recovery handler |

任何未列入表的转换默认非法并 fail closed。Run reducer 只从 required step states、branch dispositions、ReturnContract 与 CompletionPolicy 折叠 Run state；step 事件不能直接把 run 标为 completed。

## 11. PostgreSQL 持久化合同

后继增加以下 Alembic-managed 表。生产 schema authority 只属于 Alembic；禁止 runtime `create_all` 创建这些表。

### 11.0 schema placement 与真相源裁决

运行控制表位于 PostgreSQL `public` control schema，因为 RuntimeNode 需要跨项目 claim；每一行必须包含 `project_key`，并通过 server-side `RuntimeScope` 强制作用域。客户端 header/query 中的 `project_key` 不能直接成为可信 scope，必须由 authenticated request/project binding 解析。

所有 tenant-scoped `runtime_*` 表的 Alembic schema 必须显式包含 `project_key NOT NULL`、created/updated 时间、必要的 `revision`，并建立 `(project_key, state/due_at/run_id)` 查询索引。跨表引用必须使用数据库级复合 `(project_key, id)` FK、constraint/trigger 或同等级 RLS；repository validation 只能作为附加检查，不能替代数据库隔离。唯一 global-control 例外是 `runtime_nodes` 与 immutable deployment catalog 表：它们不含 `project_key`，也不得含业务 payload、credential、grant 或租户 value ref；节点获得项目访问权仍由每次 claim 的 current authority binding 决定。本文“关键字段”列表不得被实现理解为可以省略 tenant-scoped `project_key`。

实现必须新增固定 `search_path=public` 的 `RuntimeSessionLocal`；不得复用会被 ContextVar 切换到 project schema 的普通 `SessionLocal`。跨项目 claim 只允许 `WorkItemPort + ControlPlaneScope`，返回记录后立即构造逐项目 `RuntimeScope`，后续 reducer/store/value/authority 操作全部回到项目 scope。

项目业务事实、source-library 配置、Document、typed knowledge、report 和 graph 继续位于既有 project schema。exact Program/Plan/payload/value、Research Ledger 与自然 artifact 也位于 project schema 或 project-scoped content store。public control schema 只保存 opaque `ProgramRef/PlanRef/ValueRef/CanonicalRef`、digest、状态和调度元数据，不复制租户业务事实。

### 11.0.1 Research Ledger owner matrix

每类 Research Ledger 领域对象在任一 migration epoch 只能具有一种 owner mode；runtime attempt 和 provider-witnessed fact 不属于领域 `ObjectContract`，必须显式标为 ledger 外部 owner：

- `CANONICAL_OWNED`：Research Ledger 保存该对象的 canonical version/state；
- `IMMUTABLE_EXTERNAL_REF`：Ledger 只保存外部 canonical identity/revision/incarnation/content digest；
- `DECLARED_LOSS_PROJECTION`：可删除重建，不拥有写 authority。

第一纵向 slice 冻结如下：

| 对象/关系 | Owner mode | Canonical owner |
| --- | --- | --- |
| existing `Document` content | legacy mutable canonical source，不能直接作为 immutable ref | 现有 project Document repository |
| `CapturedMaterialSnapshot` bytes | runtime input artifact | project `successor_values`；不属于 Research Ledger object |
| `SourceRef` | `IMMUTABLE_EXTERNAL_REF` | 对应 source/external owner |
| `MaterialRef` | `IMMUTABLE_EXTERNAL_REF` | submission-time `CapturedMaterialSnapshot` + observed Document/source binding |
| `Inquiry/ResearchPlan` | `CANONICAL_OWNED` | Research Ledger |
| `EvidenceQualification` | canonical relation | Research Ledger `research_relations`，不写 `research_objects` |
| `Claim/Gap` | `CANONICAL_OWNED` | Research Ledger |
| `ResearchArtifact` metadata/content ref | `CANONICAL_OWNED` | Research Ledger + project-scoped artifact store |
| `DeliveryIntent` | `CANONICAL_OWNED` | Research Ledger |
| `DeliveryAttempt` | runtime fact，非领域 `ObjectContract` | Execution Journal/runtime attempt store |
| `DeliveryReceipt` 在 Ledger 中的表示 | `IMMUTABLE_EXTERNAL_REF` | project-scoped receipt store + provider authoritative readback；Ledger 只保存 `delivered_as` relation/ref |
| graph/search/writing/process views | `DECLARED_LOSS_PROJECTION` | 无 canonical write authority |

owner binding 由 `(project_key, object_type, owner_epoch)` 唯一标识。改变 owner 必须生成 successor epoch、迁移/rollback evidence 与 base incarnation；禁止 Ledger 与旧 repository 同时 canonical-write 同一 object type。

runtime truth 裁决如下：

- `runtime_events` 是 run/step/attempt 生命周期的 append-only canonical log；
- `runtime_runs` 与 `runtime_steps` 是与 event append 同事务更新的 operational snapshot；
- snapshot 可从 event log 重建，并有 digest/revision consistency checker；
- RuntimeNode 为性能读取 snapshot，但任何状态争议以 admitted event sequence + reducer 为准；
- 不允许单独更新 snapshot 而不追加对应 event；
- 不允许 event append 成功而 snapshot/work-item mutation 在同一 transition 中失败，必须使用 UnitOfWork。

身份规则：

- `program_id`、`run_id`、`attempt_id`、`value_id`、`artifact_id` 使用全局不可复用 UUID/内容派生 ID；
- 即使 ID 全局唯一，所有 Port 仍要求 `RuntimeScope`，防止跨项目读取；
- `step_id` 在一个 `plan_digest` 内唯一，并通过 `(run_id, step_id)` 定位运行 occurrence；
- `program_digest/plan_digest` 是内容身份，但第一阶段按 project scope 存储与去重；唯一约束分别是 `(project_key, program_digest)` 与 `(project_key, plan_digest)`；
- idempotency 唯一约束是 `(project_key, capability_id, logical_request_id)`，不得把用户提供的裸 key 当全局唯一；
- `runtime_runs.run_id` 作为全局主键后，不再声明冗余 `(project_key, run_id)` unique，但 `project_key` 必须索引并进入所有 authorization 查询。

### 11.1 project `research_program_specs` 与 public `runtime_program_refs`

project schema 的 `research_program_specs` 保存 exact canonical Program：

| 字段 | 类型/约束 |
| --- | --- |
| `program_id` | UUID/字符串主键 |
| `project_key` | 非空、索引 |
| `contract_version` | 非空 |
| `program_digest` | `CHAR(64)`，与 `project_key` 组成唯一内容身份 |
| `spec_json` | JSONB，canonical codec 输出 |
| `created_by` | actor identity |
| `created_at` | timestamptz |

public `runtime_program_refs` 只保存 `program_id/project_key/program_digest/project_storage_ref/contract_version/created_at`；不得保存 `spec_json`。

### 11.2 project `research_execution_plans` 与 public `runtime_plan_refs`

project schema 的 `research_execution_plans` 保存 exact canonical ExecutionPlan：

| 字段 | 类型/约束 |
| --- | --- |
| `plan_id` | 全局不可复用主键 |
| `project_key` | 非空 |
| `plan_digest` | `CHAR(64)`，与 `project_key` 组成唯一内容身份 |
| `program_id/program_digest` | 非空外键/绑定 |
| `compiler_id/compiler_version` | 非空 |
| `operation_catalog_id/catalog_version/catalog_digest` | 非空，冻结此次编译使用的 contract snapshot |
| `plan_json` | JSONB，完整 canonical `ExecutionPlan/CompiledStep`，不是摘要列表 |
| `effect_closure_digest` | 非空 |
| `authority_closure_digest` | 非空 |
| `resource_closure_digest` | 非空 |
| `created_at` | timestamptz |

public `runtime_plan_refs` 只保存 `plan_id/project_key/plan_digest/program_digest/project_storage_ref/compiler/catalog/closure digests/created_at`；不得保存 `plan_json`。

RuntimeNode 必须按 run 的 exact `plan_digest` 读取 immutable plan。compiler 升级不允许用新代码重新解释旧 spec 后假装是原计划；需要显式 recompile/successor plan。

### 11.3 `runtime_runs`

| 字段 | 类型/约束 |
| --- | --- |
| `run_id` | 主键 |
| `project_key` | 非空、索引 |
| `project_registry_revision/project_scope_digest` | 创建 run 时的 exact project-schema binding |
| `resolved_schema` | 仅用于 drift/readback 绑定，不接受客户端输入 |
| `program_id/program_digest` | 非空绑定 |
| `plan_id/plan_digest` | `SUBMITTED/COMPILING` 可空；`AWAITING_APPROVAL/READY` 以后非空且 immutable |
| `state` | enum/check constraint |
| `revision` | 非负整数，CAS |
| `execution_epoch` | 非负整数 |
| `incarnation` | 不可复用 UUID |
| `submission_authority_digest` | 非空，只证明 create-run 权限 |
| `qualification_digest` | compile 前可空；可执行状态必须非空 |
| `cancellation_requested` | bool |
| `created_at/updated_at/finished_at` | timestamptz |

`run_id` 是全局主键；`project_key` 非空并建立查询索引。所有 state 变更同时增加 `revision`。

state-dependent check constraint：`SUBMITTED/COMPILING` 允许 `plan_id/plan_digest/qualification_digest IS NULL`；进入 `AWAITING_APPROVAL/READY` 及后续状态前三者必须非空。`attach_plan` 使用 expected revision 一次性设置 plan identity，之后不可修改；recompile 必须创建 successor plan/run，而不是覆盖。

dispatch、claim、effect-before-start 和 admission 使用 `ProjectScopeResolver.resolve_expected` 对比 run/step/envelope 中的 revision/digest。scope drift 产生 `PROJECT_SCOPE_STALE` 并进入 WAITING/显式 project-migration reconciliation；不能静默改用当前 schema。

project migration 必须显式 supersede/rebind 尚未开始且经授权的 run，形成新 incarnation/successor run。已有 `IN_FLIGHT/OUTCOME_UNKNOWN` attempt 只能按原 `ProjectScopeRef` 做 authoritative readback，不能在新 schema 重放 effect。

### 11.4 `runtime_steps`

关键字段：

- `run_id`、`step_id` 复合唯一，`operation_id` 非空并可重复；
- `operation_kind/version`；
- `state`、`revision`、`execution_epoch`；
- `input_digest/output_digest/failure_digest`；
- `effect_class/resource_class/concurrency_key`；
- `capability_id/claim_owner/claim_authority_epoch/claim_policy_digest`；
- `attempt_count/max_attempts/next_retry_at`；
- `lease_token/lease_owner/lease_expires_at/heartbeat_at`；
- `started_at/finished_at`。

### 11.5 `runtime_effect_attempts`

关键字段：

- `attempt_id` 主键；
- `run_id/step_id/execution_epoch/incarnation`；
- `idempotency_key` 唯一；
- `authorization_digest/input_digest`；
- `disposition`；
- `external_provider/external_ref`；
- `receipt_ref/receipt_digest`，receipt body 位于 project-scoped receipt store；
- `failure_ref/failure_digest`，typed failure body 位于 project-scoped value store；
- `dispatched_at/started_at/finished_at`。

### 11.6 `runtime_events`

关键字段：

- `run_id`；
- `seq`；
- `event_type/schema_version`；
- `step_id/attempt_id`；
- `event_metadata_json`，只允许状态、reason code 与 opaque refs；
- `payload_ref/payload_digest`，业务 payload 位于 project store；
- `authority_digest`；
- `created_at`。

唯一约束：`(run_id, seq)`。seq 分配必须在 run row lock 或 expected revision 事务内完成；禁止裸 `max(seq)+1`。

### 11.7 `runtime_work_items`

关键字段：`work_item_id`、`project_key`、`run_id`、`step_id`、`assignment_kind`、`capability_id`、`operation_contract_digest`、`assignment_digest`、`handler_binding_kind/ref/digest`、`deployment_catalog_digest`、`runtime_protocol_version`、`interpreter_profile_digest`（仅 interpreter/recovery kind）、`required_node_profile_selector`、`payload_ref/payload_digest`、`authority_digest`、`resource_policy_digest`、`fairness_key`、`state`、`wait_reason`、`declared_priority`、`enqueue_seq`、`enqueued_at`、`due_at`、`attempt_count`、`lease_token/owner/expires_at`、`deadline_at`、`schedule_occurrence_ref`、`last_failure_ref`、时间戳。

work-item state 冻结为 `PENDING|READY|CLAIMED|WAITING|COMPLETED|FAILED|CANCELLED|SUPERSEDED`，与 StepState 分离。`wait_reason` 至少包括 `RESOURCE_LIMIT|INTERPRETER_UNAVAILABLE|AUTHORITY_STALE|BACKOFF|SCHEDULE_NOT_DUE`。没有 compatible node/interpreter 时必须显式 `WAITING/INTERPRETER_UNAVAILABLE`，不得由任意新版本 handler 接管旧 assignment。

`assignment_kind` 冻结为 `COMPILE|QUALIFY|INTERPRET|VERIFY_ADMIT|PROJECT|RECONCILE|MATERIALIZE_SUCCESSOR`。创建或推进 run/step/events 与对应 work item 必须在同一 PostgreSQL 事务提交。

节点通过受限查询和 `SELECT ... FOR UPDATE SKIP LOCKED` claim due item；claim 必须同时校验 capability grant、project scope、authority/resource epoch、deadline 和 expected revision。重复 claim、lease loss 和 stale result 由 work-item identity、attempt identity、CAS 与 idempotency 阻断。

需要外部 broker 时，由可选 transport adapter 从 work item 生成 envelope；broker ref 只是 delivery observation，不改变 work item、attempt 或 completion authority。

### 11.8 `runtime_values` 与 `runtime_staged_artifacts`

public `runtime_values` 只保存 `ValueRef` metadata 与 opaque project/blob/canonical ref；不得含 inline JSON/bytes。project schema `successor_values` 或 project-scoped `runtime_blob.v1` 保存实际内容。状态为 `PREPARED|AVAILABLE|FAILED|ORPHANED`，并保存 revision、temporary/final storage ref、write intent/receipt digest。`runtime_staged_artifacts` 绑定 run/step/attempt/value/receipt/qualifier/loss profile，并在 admission 前保持 staged。

所有 value 读取必须携带 `project_key`，校验 codec 与 content digest。清理使用 reference count/retention query，不得按时间盲删仍被引用的 staged/canonical input。

### 11.8.1 project Research Ledger

第一纵向 slice 只冻结三张 project-schema 表：

- `research_objects`：`object_id/object_type/revision/incarnation/lifecycle_state/owner_binding_ref/content_ref/content_digest/provenance_closure_digest/valid_from/valid_to`；唯一键 `(project_key, object_id, revision, incarnation)`；
- `research_relations`：`relation_id/relation_type/source_object_ref/target_object_ref/direction/scope_ref/uncertainty_profile_ref/validity/provenance_closure_digest/revision/incarnation/state`；
- `research_owner_bindings`：`object_type/owner_mode/owner_id/owner_epoch/readback_profile_ref/effective_at/superseded_at/approval_ref`。

关系种类第一 slice 只冻结 `derived_from/supports/contradicts/answers/opens/cites/supersedes/delivered_as`。所有 source/target ref 必须可 authoritative readback；外部 ref 删除或 incarnation 变化时，relation 进入 `STALE_SOURCE`，不得静默改绑新内容。

Research Ledger 不复制 existing Document/source-library/typed-knowledge/writing/graph 内容。对于 `IMMUTABLE_EXTERNAL_REF`，`content_ref + content_digest + owner revision/incarnation` 是 relation/admission 的 base binding。对于 `DECLARED_LOSS_PROJECTION`，删除 projection 不影响 Ledger 或 external canonical owner。

### 11.9 `runtime_qualifications` 与 `runtime_step_authorizations`

- `runtime_qualifications` 保存 `QualifiedPlan`、authority context digest、decision 和 qualification digest；
- `runtime_step_authorizations` 保存逐 step `StepAuthorizationBinding`；
- approval refs 必须指向 `runtime_approvals`；
- dispatch/claim/admission 重新核对 step binding、grant epoch、expiry、payload digest、base revision/incarnation。

### 11.10 `runtime_approvals`、`runtime_idempotency`、`runtime_projection_offsets`

- approval 绑定 actor/project/run/step/payload digest/decision/expiry；
- idempotency 绑定 project/operation/request digest/run identity/terminal observation；
- projection offset 绑定 projector ID/version/source revision/source digest。

### 11.10.1 `project_scope_registry` 与 `runtime_authority_grants`

- `project_scope_registry`：`project_key/resolved_schema/registry_revision/scope_digest/incarnation/state/updated_by/approval_ref`；schema delete/recreate 或 project migration 必须产生新 incarnation；
- `runtime_authority_grants`：`grant_id/actor/project/capability/operation scope/resource ceiling/credential ref/epoch/expiry/revoked_at/revision`；
- 所有 mutation 使用 expected revision/CAS，经 `AuthorityAdminPort` 追加 before/after digest 与 actor/reason audit event；
- `AuthorityProvider` 只读这些 rows，不得自行创建、扩张、续期或撤销 grant。

### 11.11 `runtime_capability_authority`

此表是逐 capability/project cutover 的唯一运行 authority registry：

- `capability_id`、`project_key`；
- `mode=off|shadow|canary|on`；
- `authority_epoch`；
- `successor_claim_enabled`、`legacy_claim_enabled`，数据库约束禁止两者同时为 true；
- allowlist/config digest；
- effective_at/updated_by/approval_ref。

环境变量只能提供 bootstrap default。backend 与 RuntimeNode 在 claim 前读取同一个 authority epoch；配置漂移必须 fail closed，不能形成 legacy/successor 双 claim。

`runtime_capability_authority` 的写 owner 是 audited `AuthorityAdminPort`；每次 mode/claim-owner 变更必须提供 expected revision、approval ref、rollback target 与 before/after digest，并追加 authority-change event。普通 RuntimeNode、interpreter、projection 和环境变量不得修改该表。

### 11.12 `runtime_resource_policies` 与 `runtime_resource_reservations`

- policy 绑定 project/capability/resource class、并发上限、budget、provider limit 与 `policy_epoch`；
- qualification 只保存非排他的 `QueueEligibility`：resource requirement、budget ceiling、concurrency key 与 policy epoch；它不占用执行额度；
- `ExecutionReservation` 只在 `READY -> CLAIMED` 的同一 claim transaction 中创建，绑定 run/step/attempt、resource class、concurrency key、units、node lease token/expiry；
- RuntimeNode terminal outcome、cancel、lease expiry 或 recovery handler 必须 release/reap；
- reservation 唯一约束阻止同一 step/epoch 重复占用；
- claim 时无可用额度则不进入 `CLAIMED`，work item 按 bounded resource backoff 保持/回到 `READY` 并记录 `WAITING/RESOURCE_LIMIT` observation；不得形成无 owner 的长期 reservation。

### 11.13 `runtime_commit_intents`

关键字段：`commit_intent_id`、`project_key`、`run_id`、`step_id`、capability canonical owner、object identity、expected base revision/incarnation、content/event/verification/authority digest、idempotency key、state、revision、canonical commit ref/receipt digest、时间戳。

状态：`PREPARED|COMMITTED|REJECTED|OUTCOME_UNKNOWN`。prepare/finalize 使用 CAS；同一 idempotency key 只能对应一个 exact binding。runtime control DB 与 capability canonical store 通常不在同一事务域，因此 protocol 是：

1. control DB 原子写 `CommitIntent PREPARED` + event；
2. 调用 capability `verify_and_commit`；
3. control DB 原子写 canonical receipt + `COMMITTED` + event/snapshot；
4. 第二步后崩溃时，通过 capability `readback_commit` 恢复；
5. capability 无 readback/idempotent commit 时禁止 write cutover。

### 11.14 recurrence、timer 与 lease-expiry work item

approval、node outcome、retry timer、resource release、recurring research、source-delta check 与 reconciliation result 统一创建具名 `runtime_work_items`；不另建 relay-only wakeup 控制面。

`runtime_schedules` 保存：`schedule_id/project_key/schedule_epoch/timezone/schedule_spec/misfire_policy/max_catch_up/max_concurrent/next_due_at/authority_digest/state/revision`。

`runtime_schedule_occurrences` 保存：`occurrence_id/schedule_id/schedule_epoch/scheduled_for/materialized_at/program_ref/run_id/work_item_id/state`；唯一键 `(project_key, schedule_id, schedule_epoch, scheduled_for)`。

due query 必须按 `(state, due_at, declared_priority, enqueue_seq, project_key)` 索引并有 batch ceiling，不允许无界全表扫描。处理完成后按 CAS 标记 terminal 或在 bounded backoff 下形成 successor work item。

节点 claim effectful step 时，在同一 UoW upsert `RECONCILE` 类型的 lease-expiry work item；heartbeat 以 lease token/CAS 推迟它；terminal/release 时取消或 consume。进程 crash 不会产生事件，因此该 work item 是 durable recovery 触发源。resource reservation expiry 同样由受限 due work item 或有界扫描触发。

Redis、Celery backend、Elasticsearch、前端缓存不得替代这些表。

### 11.15 `runtime_nodes` 与 deployment catalog

`runtime_nodes` 保存：`node_id/node_profile_digest/deployment_catalog_digest/runtime_protocol_version/state/heartbeat_at/started_at/drain_requested_at/current_claim_count`。`DeploymentCatalogSnapshot` 是不含业务 payload 的 immutable public control artifact；catalog mutation 产生新 digest，不覆盖旧 snapshot。

节点 claim query 必须绑定 compatible runtime protocol、operation contract、interpreter profile、node profile、security/resource profile 与 deployment catalog。`DRAINING` 节点不得 claim 新 work item；旧 profile 和 catalog artifact 必须保留到所有绑定 backlog terminal、superseded 或经人工裁决。

## 12. RuntimeAssignment 与 delivery 合同

greenfield core 的工作分配对象是 typed `RuntimeAssignment`，不是 broker-specific message：

```python
@dataclass(frozen=True, slots=True)
class CompilerBinding:
    compiler_id: str
    compiler_version: str
    compiler_digest: str
    operation_catalog_digest: str
    domain_contract_snapshot_digest: str
    binding_digest: str

@dataclass(frozen=True, slots=True)
class QualificationBinding:
    authority_reader_id: str
    authority_reader_version: str
    authority_reader_digest: str
    deployment_catalog_digest: str
    resource_policy_epoch: int
    binding_digest: str

@dataclass(frozen=True, slots=True)
class ProjectorBinding:
    projector_id: str
    projector_version: str
    source_kind: Literal["RESEARCH_LEDGER", "RUNTIME_JOURNAL", "CANONICAL_OWNER"]
    source_ref: str
    source_digest: str
    projection_schema_ref: str
    declared_loss_profile_ref: str
    binding_digest: str

@dataclass(frozen=True, slots=True)
class MaterializerBinding:
    materializer_id: str
    materializer_version: str
    predecessor_plan_digest: str
    source_value_digest: str
    target_domain_contract_snapshot_digest: str
    binding_digest: str

@dataclass(frozen=True, slots=True)
class RecoveryBinding:
    recovery_handler_id: str
    recovery_handler_version: str
    interpreter_profile_digest: str | None
    authoritative_readback_profile_ref: str
    binding_digest: str

HandlerBinding = CompilerBinding | QualificationBinding | InterpreterBinding | ProjectorBinding | MaterializerBinding | RecoveryBinding

class RuntimeAssignment(BaseModel):
    schema_version: Literal["mrw.runtime.assignment.v1"]
    runtime_protocol_version: str
    work_item_id: str
    assignment_kind: Literal[
        "COMPILE",
        "QUALIFY",
        "INTERPRET",
        "VERIFY_ADMIT",
        "PROJECT",
        "RECONCILE",
        "MATERIALIZE_SUCCESSOR",
    ]
    project_key: str
    run_id: str
    step_id: str | None
    capability_id: str
    operation_contract_ref: OperationContractRef | None
    operation_contract_digest: str | None
    handler_binding_kind: Literal["COMPILER", "QUALIFICATION", "INTERPRETER", "PROJECTOR", "MATERIALIZER", "RECOVERY"]
    handler_binding_ref: str
    handler_binding_digest: str
    program_digest: str
    plan_digest: str | None
    deployment_catalog_digest: str
    execution_epoch: int
    incarnation: str
    input_refs: tuple[str, ...]
    input_closure_digest: str | None
    payload_ref: str | None
    payload_digest: str | None
    queue_eligibility_digest: str
    resource_policy_epoch: int
    claim_authority_epoch: int
    claim_policy_digest: str
    expected_step_revision: int | None
    deadline_at: datetime | None
    trace_id: str

@dataclass(frozen=True, slots=True)
class ClaimBinding:
    work_item_id: str
    assignment_digest: str
    handler_binding_digest: str
    attempt_id: str
    lease_token: str
    lease_expires_at: datetime
    node_id: str
    node_profile_digest: str
    interpreter_profile_digest: str | None
    authority_digest: str
    execution_reservation_ref: str | None
    execution_reservation_digest: str | None
    claim_authority_epoch: int
    binding_digest: str
```

`RuntimeAssignment` 描述待处理的同质工作；`ClaimBinding` 描述某个节点在当前时刻获得的执行资格。每个 assignment kind 都必须绑定 exact `HandlerBinding`。`INTERPRET/VERIFY_ADMIT` 使用 exact `InterpreterBinding`；`RECONCILE` 使用 `RecoveryBinding` 并闭包原 interpreter/readback profile；节点不得在 claim 后从 mutable registry 选择“任一可用 handler”。节点只能执行 `RuntimeAssignment + exact HandlerBinding + current ClaimBinding`，不能直接解释裸 work-item row。

数据库 state-dependent constraints：

- `INTERPRET/VERIFY_ADMIT` 的 `operation_contract_digest/InterpreterBinding/expected_step_revision` 非空；
- `RECONCILE` 的 `operation_contract_digest/RecoveryBinding/attempt identity/expected_step_revision` 非空；
- `COMPILE` 的 `program_digest/CompilerBinding/deployment_catalog_digest` 非空；
- `QUALIFY` 的 `plan_digest/QualificationBinding/resource_policy_epoch` 非空；
- `PROJECT` 的 `ProjectorBinding/source ref/source digest/declared loss` 非空；
- `MATERIALIZE_SUCCESSOR` 的 `MaterializerBinding/predecessor plan/source value/target contract snapshot` 非空；
- assignment 的任一 contract/profile/epoch 改变必须创建 successor work item，不得原地更新 digest。

所有 `RuntimeNode` 运行同一 claim/interpret/commit 循环：

1. 从 PostgreSQL claim due `runtime_work_items`；
2. 读取 exact Program/Plan/step、OperationContract、deployment catalog 与当前 authority/resource binding；
3. 在 claim transaction 中匹配 node/interpreter profile、创建 attempt/lease/reservation 与 `ClaimBinding`；
4. 按 `assignment_kind` 调用纯 transition、compiler 或具名 capability interpreter；
5. 在 UnitOfWork 中提交 event/snapshot/value/receipt/successor work item；
6. effect 处于未知状态时只提交 `OUTCOME_UNKNOWN` 与 `RECONCILE` work item，不重做 effect。

节点相同只表示代码接口同形。节点可按部署授予不同 capability/resource grant；缺少 grant 的节点跳过该 work item，而不是把差异固化成新的进程类。

work item 不携带可独立修改的完整业务事实作为权威输入。节点必须从 PostgreSQL 读取 canonical binding，验证 work-item/assignment/contract/deployment/node/interpreter digest、state、attempt/idempotency、plan/step/input/authority/reservation/incarnation；任何差异产生 `ASSIGNMENT_BINDING_MISMATCH`，不得执行。

`attempt_id` 由 `(project_key, run_id, step_id, execution_epoch, incarnation, assignment_digest, handler_binding_digest, input_closure_digest, authorization_digest, capability_id, claim_authority_epoch, claim_policy_digest)` 确定性生成。同一 attempt 的 lease 续期或 transport redelivery 不创建新的 effect attempt；assignment、handler/interpreter、deployment binding 任一变化必须推进 execution epoch 并创建新 attempt identity。

可选 Celery/Redis adapter 只能运输 `work_item_id + assignment_digest`。接收端仍回到上述 PostgreSQL claim；broker acknowledge、Celery result、Redis lock 或 task state 都不构成 effect success、completion、cancel 或 admission 事实。legacy transport 的 task retry/acks/time-limit 配置继续由 migration adapter 冻结，不进入 greenfield core contract。

第零阶段默认值：

| 参数 | 默认值 |
| --- | --- |
| node poll batch | `32`，按 due/derived effective priority 有界 claim |
| node idle backoff | `100ms` 至 `5s`，带 jitter |
| step heartbeat interval | `10s` |
| step lease | `45s`，heartbeat CAS 续租 |
| lease-loss grace | `15s`，仅用于 cleanup，不延长写 authority |
| resource reservation lease | `60s`，随有效 heartbeat 续租 |
| default operation soft limit | `240s` |
| default operation hard limit | `300s` |
| maximum operation hard limit | `1800s`，超出需单独 capability contract |

任何 capability 覆盖值必须进入 operation/plan digest。外部 provider/crawler 的任务时限还必须小于其 authoritative readback/recovery 上限。

## 13. Scheduler、并发与资源合同

### 13.1 ready-set

纯函数 `ready_steps(snapshot)` 只返回满足以下条件的 step；任何 `RuntimeNode` 都可计算同一结果，实际 claim 仍由数据库 CAS 决定：

- 所有硬依赖达到其允许的 terminal/return disposition；
- 没有未解决 approval；
- run 未取消/终止/supersede；
- retry backoff 已到；
- resource requirement 已通过 qualification；实际容量在 claim transaction 决定；
- concurrency key 不冲突；
- 当前 epoch/incarnation 有效。

同一 ready set 的 deterministic order：

```text
declared_priority
-> stable_topological_index
-> step_id
```

该顺序只适用于一个 run 内的语义 ready set；跨 project/capability 的 work-item claim 必须另行满足 13.4 公平性，不得把本顺序当作全局 queue order。

### 13.2 并行授权

并行需要显式 `ParallelPolicy`：

- dependency-disjoint；
- effect class 允许并行；
- project-scope resource budget 允许；
- concurrency key 不冲突；
- failure aggregation 已声明；
- output merge order 已声明；
- cancellation propagation 已声明；
- external side effects 不共享不可协调资源。

缺少上述任何一项即保持有序串行。并行安全不等于可交换。

### 13.3 resource/backpressure

最少资源类：`CPU_LIGHT`、`CPU_HEAVY`、`NETWORK_IO`、`DB_WRITE`、`LLM_CALL`、`CRAWLER_JOB`、`EXTERNAL_PROCESS`。

每个 `ProjectScopeRef` 维护：

- 全局 active step 上限；
- 各 resource class 上限；
- provider-specific 上限；
- queue backlog 阈值；
- retry budget；
- cost/token/request budget。

backpressure 必须产生 `WAITING/RESOURCE_LIMIT`，不能通过无界线程池或无限 Celery dispatch 绕过。

防超卖算法：RuntimeNode claim `INTERPRET/VERIFY_ADMIT` work item 时，在同一 Postgres transaction 中锁定 work item 与 `runtime_resource_policies` row，汇总同 policy epoch 的 active reservations，验证 units/concurrency/provider budget，然后原子创建 `ExecutionReservation + attempt + StepClaimed event + node lease`。Delivery 是具名 `INTERPRET` operation，不建立独立 claim protocol。多节点并发必须在该 row lock/serializable check 下串行 reserve；`QUALIFY` 阶段不得提前 reserve。

以下路径必须原子或幂等 release/reap reservation：work item 永久失败、deadline 在 claim 前过期、用户 cancel、节点 terminal outcome、lease expiry、authority revocation、reconciliation 判定终态。stale assignment 在 reservation 失效后必须拒绝。

### 13.4 公平性与容量边界

`SKIP LOCKED` 只是 claim mechanism，不提供跨 project/capability 公平性。greenfield core 必须定义：

- `fairness_key` 默认是 project key，可由冻结 policy 细分 capability/resource class；
- project active limit、capability active limit 与 resource class limit；
- `effective_priority = declared_priority + bounded aging`，aging 只防饥饿，不越过 authority/deadline/resource guard；
- 对持续 eligible 且资源可用的 work item，`max_starvation_seconds` 必须在 `CapacityEnvelope.v1` 中给出并以测试/压测验证；
- 同一 project 的大量高优先级任务不得占满所有 node/DB connections；
- long crawler/LLM/process interpreter 使用专门 resource/security `RuntimeNodeProfile`，但仍共享同一 assignment/claim/transition protocol。

实现可以使用 project queue-state row、weighted fair share 或等价算法；不得只按全局 `priority,due_at` 排序后声称公平。

冻结 canary 前必须生成实测 `CapacityEnvelope.v1`，至少绑定：PostgreSQL 版本与配置、node/profile 数、project 数、eligible/terminal row 数、claim batch、work-item rate、concurrency、p50/p95/p99 claim/commit latency、lock wait、DB connections、backlog age、starvation bound、vacuum/partition/archive policy。未测范围只能标为 `UNSUPPORTED_CAPACITY`，不能从架构推导。

在 `CapacityEnvelope.v1` 产生前，P0 只授权两个 RuntimeNode、单 PostgreSQL、单 first-specimen fixture 的功能与恢复验证；不构成生产吞吐、可用性或多租户容量声明。

### 13.5 recurrence、rolling deploy 与节点生命周期

recurrence 由 versioned `RecurrenceSpec.v1` 与 `RecurrenceOccurrence.v1` 表达，并持久化到 `runtime_schedules/runtime_schedule_occurrences`：

```python
@dataclass(frozen=True, slots=True)
class RecurrenceSpec:
    schedule_id: str
    project_key: str
    schedule_epoch: int
    timezone: str
    schedule_spec: str
    misfire_policy: Literal["SKIP", "COALESCE", "CATCH_UP_BOUNDED"]
    max_catch_up: int
    max_concurrent: int
    program_ref: str
    authority_digest: str
    spec_digest: str

@dataclass(frozen=True, slots=True)
class RecurrenceOccurrence:
    occurrence_id: str
    schedule_id: str
    schedule_epoch: int
    scheduled_for: datetime
    program_ref: str
    occurrence_digest: str
```

- occurrence 唯一键 `(project_key, schedule_id, schedule_epoch, scheduled_for)`；
- misfire policy 只能是 `SKIP|COALESCE|CATCH_UP_BOUNDED`；
- catch-up 必须有最大 occurrence 数和截止时间；
- schedule 更新创建新 epoch，不原地重新解释旧 occurrence；
- occurrence 创建与对应 work item 在同一 UoW，重复 timer 不产生重复 run。

任一具有 schedule-materialization profile 的 RuntimeNode 都可通过 `SELECT ... FOR UPDATE SKIP LOCKED` claim due schedule row；同一事务必须创建 deterministic occurrence、对应 Program/work item 并 CAS 推进 `next_due_at`。节点在事务前后崩溃由 occurrence unique key 与 schedule revision 收敛，不需要 leader；失败只能重试同一 scheduled occurrence，不能跳过或重复推进 next due。

rolling deploy 使用 `runtime_nodes` registry：`node_id/node_profile_digest/deployment_catalog_digest/state=ACTIVE|DRAINING|DEAD/heartbeat/started_at`。claim 必须满足 exact operation contract、interpreter profile、node profile 与 deployment catalog compatibility。

- `DRAINING` 节点停止新 claim，继续 heartbeat、cleanup、readback 和已持有 attempt；
- 旧节点不得 claim 只由新 interpreter version 支持的 assignment；
- deployment catalog 更新产生新 digest，旧 work item 只有在其 frozen compatibility range 允许时才可由新节点执行；
- terminal work item/event 必须按冻结 retention 归档或分区，避免 hot claim index 被历史行拖垮。

## 14. Lease、heartbeat、取消与 stale node

claim 必须通过 Postgres 条件更新或 `SELECT ... FOR UPDATE SKIP LOCKED`：

- 生成不可复用 `lease_token`；
- 绑定 `run_id/step_id/execution_epoch/incarnation`；
- 设置 `lease_owner/lease_expires_at`；
- 每次 heartbeat 使用 lease token + expected revision；
- lease 丢失后节点不得写可采纳结果；
- 可选 transport revoke 是 best-effort 动作，不是取消事实；
- canonical cancellation 由 `cancellation_requested` 事件与 reducer 决定；
- handler 在 effect 前、长循环边界、外部 readback 前检查 cancellation。

cleanup receipt 只证明清理动作，不证明原 effect 成功或失败。

## 15. Effect interpreter 合同

每个 interpreter 必须注册：

- `interpreter_id/version`；
- 支持的 operation kind/version；
- input/output/failure codec；
- effect class/resource class；
- idempotency strategy；
- retryable failure set；
- authoritative readback 能力；
- cancellation/cleanup 支持；
- receipt schema；
- canonical-write capability，默认 false。

`execute` 只返回：

- `SUCCEEDED(value_ref, receipt)`；
- `FAILED(typed_failure, receipt?)`；
- `OUTCOME_UNKNOWN(attempt_ref, reconciliation_hint)`。

不得把 fallback/degraded payload 伪装为普通 success。若旧模块必须返回 fallback，adapter 应产出 `SUCCEEDED` 加显式 `DEGRADED` qualifier，run completion 规则必须决定该 qualifier 是否可接受。

Shadow 运行不得让 legacy 与 successor 各自重复一次真实网络/LLM/DB write effect。允许的方式：

1. legacy 执行一次真实 effect，successor 只解释同一 receipt；
2. 两边都使用 fixture/readback；
3. successor dry-run/simulation，显式标注非 live evidence；
4. 只对纯转换进行双执行。

## 16. Authority、verification 与 admission

### 16.1 `AuthorityContext`

必须包含：actor identity、`ProjectScopeRef`、`AuthoritySourceBinding[]`、grants、grant epoch、expiry、operation scope、resource ceiling、canonical base revision/incarnation，以及 approval refs。context digest 必须闭包所有 source ref/digest/epoch，不能只哈希聚合后的 grants 文本。

编译不授予权限。以下时点重新验证 authority：

- create run；
- step 从 READY 进入 CLAIMED；
- RuntimeNode claim；
- effect 执行前；
- staged result admission；
- canonical commit。

`AuthorityProvider` 只是聚合读取 Port，不是新的 authority owner。它只允许读取以下 canonical sources：

- `project_scope_registry`：project registry revision、resolved schema、scope digest 与不可复用 incarnation；
- `runtime_authority_grants`：actor/capability/operation/project scope、grant epoch、expiry、resource ceiling 与 revocation；
- `runtime_approvals`：exact payload/step/delivery intent digest、decision、actor、expiry 与 approval epoch；
- `runtime_capability_authority`：legacy/successor 单一 claim/write owner 与 cutover epoch；
- credential registry 的 opaque ref/epoch，secret bytes 不进入 authority store。

这些表的 mutation 只能通过 audited `AuthorityAdminPort`，记录 actor、reason、before/after digest、approval ref 与 event。环境变量只允许首次 bootstrap，不得在运行中成为并列 authority。既有 `agent_approvals` 在迁移前只能作为 `IMMUTABLE_EXTERNAL_APPROVAL_REF`，由 adapter readback；同一个 operation 不得同时接受 legacy approval 和 `runtime_approvals` 两套可写决定。

重新验证必须通过 `AuthorityProvider` 聚合上述当前 sources，不得只反复读取 create-run 时保存的旧 binding。revocation 或 epoch 前进使未开始 step fail closed；已在执行的 effect 转入 cancel/reconcile，并禁止旧 node admission。

### 16.2 `VerificationBinding`

绑定：

- program/plan/step/attempt identity；
- exact input/output/content digest；
- ordered event payload closure digest；
- schema/compiler/interpreter/verifier ID/version；
- actor/project-scope/authority digest；
- project registry revision/scope digest/resolved-schema binding；
- canonical base identity/revision/incarnation；
- evidence/receipt/provenance digest；
- declared loss 与 qualifier。

任何 payload byte、event order、authority、base revision 或 incarnation 改变都使旧 binding 无效。

### 16.3 canonical owner

- runtime journal 拥有运行事实；
- source-library、Document、typed knowledge、report、graph 等业务事实继续由各自现有 repository 拥有，直至逐 capability cutover；
- admission port 是 runtime 与 capability-owned canonical store 之间唯一写入口；
- interpreter 不能直接同时写 runtime completed 与业务 canonical fact；
- projection 不能执行 admission。

### 16.4 idempotent canonical commit/readback

每次 admission 先创建 `CommitIntent`：

- `commit_intent_id`；
- capability canonical owner；
- project/object identity；
- project registry revision/scope digest；
- expected base revision/incarnation；
- exact content/event/verification/authority digest；
- idempotency key；
- state `PREPARED|COMMITTED|REJECTED|OUTCOME_UNKNOWN`。

capability repository 必须支持按 `commit_intent_id/idempotency_key` readback。若 canonical commit 已发生但 runtime receipt 写入前崩溃，reconciler 调用 `AdmissionPort.readback_commit`，取得 exact canonical revision/content digest 后写 commit receipt；不得重复 commit。若 capability store 不支持 authoritative readback，该能力不得切换 write authority。

### 16.5 不可逆 Delivery 合同

artifact admission 不授权 delivery。Delivery 通过普通 Program Atom 与同质 RuntimeAssignment 执行，但必须具有独立语义对象和 owner：

1. Research Ledger 保存 `DeliveryIntent`，绑定 exact artifact revision/content digest、audience、channel、format、approval refs、authority epoch、idempotency key 与 irreversibility profile；
2. Execution Journal 保存 `DeliveryAttempt` 与 effect disposition；
3. interpreter 调用 external/internal delivery effect，并返回 provider locator/receipt 或 `OUTCOME_UNKNOWN`；
4. project-scoped receipt store 保存 immutable `DeliveryReceipt`；Research Ledger 只在 authoritative readback 后追加 `delivered_as` relation；
5. runtime crash 后优先按 idempotency key/provider locator readback，禁止直接重发；无法 readback 的不可逆 channel 必须进入人工裁决，不能自动 retry；
6. revoke 只能阻止未开始 attempt；已发生的外部 delivery 通过 supersede/retraction 新对象处理，不能删除历史 receipt。

## 17. Recovery、replay 与 reconciliation

必须实现并测试以下 crash windows：

| Crash point | 恢复决定 |
| --- | --- |
| Program 持久化前 | 无 run；客户端以 idempotency key 重试 |
| run/events 已提交、work item 未提交 | 不允许；必须同事务 |
| work item 已提交、尚未被 claim | 任一有 grant 的 RuntimeNode 可 claim；不重建 run |
| 可选 broker 已投递、节点尚未 claim | 回到 PostgreSQL work-item CAS；transport 去重不替代 claim |
| 节点 claim 前重复 delivery/poll | CAS claim，仅一个 lease 生效 |
| effect 前节点 crash | lease expiry 后新 epoch/attempt，需证明 NOT_STARTED |
| effect 已发生、receipt 前 crash | `OUTCOME_UNKNOWN`，禁止 redispatch，走 authoritative readback |
| staged result 已写、verify 前 crash | 从 staged digest 继续 verify，不重做 effect |
| canonical commit 前 crash | 重新检查 exact binding/base/incarnation |
| canonical commit 后、runtime event 前 crash | canonical readback 生成 commit receipt，不重复 commit |
| projector crash | 从 projection offset 继续或 full rebuild |
| canonical delete/recreate | incarnation 不同，旧 prefix/receipt 全部 stale |

reconciler 只能做：

- 读取 PostgreSQL journal/work-item/attempt；
- 调用 interpreter 的 authoritative `readback`；
- 记录 reconciliation event；
- 将 `OUTCOME_UNKNOWN` 收敛为 `SUCCEEDED/FAILED`，或继续 `WAITING`；
- 创建显式 successor attempt/epoch。

它不得凭缺少 receipt 推断 `NOT_STARTED`，不得重新执行 Agent、network、process、filesystem 或 DB mutation。

`NonStartProof` 必须绑定 attempt ID、interpreter/provider ID/version、external idempotency/readback locator、authoritative observation、observed_at 和 proof digest。只有 interpreter 的 authoritative `prove_not_started` 返回有效 proof 时才可创建新 attempt；lease expiry、node loss、缺少 receipt、Redis/Celery 无结果永远不是 `NOT_STARTED` 证明。

## 18. Projection 与查询模型

read model 包括：

- runtime run/step/attempt query；
- AgentSession/AgentTask projection；
- Process/Celery/DB readback projection；
- API `status/data/error/meta` envelope；
- frontend current run、events、failures、approvals、artifacts；
- Elasticsearch/graph/index handoff projection。

规则：

- observed event、derived event、inferred status 必须有不同类型；
- terminal status 不能补造一整条未观察事件序列；
- SSE/query 使用 `after_seq` 增量读取；
- projection offset 绑定 projector version 与 source digest；
- 删除 projection 后可从 journal/canonical facts 重建；
- frontend localStorage project selection 只是客户端偏好，不是 canonical project identity；
- UI/dashboard 不得写 scheduler、approval 或 completion state。

## 19. 部署拓扑

后继不再增加 `runtime-relay`、`effect-worker`、`admission-worker` 等固定状态机角色。所有后台执行主体共享同一 `RuntimeNode` core、entrypoint、assignment/claim/transition protocol；不同 resource/security profile 可以使用附加依赖不同的镜像变体，但不得复制 runtime semantics 或形成第二控制面：

```text
frontend-modern
  -> backend /api
       -> PostgreSQL Research Space + runtime journal + runtime_work_items
       -> command/query/SSE

RuntimeNode 1..N
  -> claim due runtime_work_items with SKIP LOCKED
  -> handle COMPILE/QUALIFY/INTERPRET/VERIFY_ADMIT
  -> handle PROJECT/RECONCILE/MATERIALIZE_SUCCESSOR
  -> commit event/snapshot/value/receipt/successor item in UoW

Elasticsearch / pgvector / Scrapyd / providers
  <- capability-specific interpreters

Redis / Celery
  <- optional legacy or migration transport adapter only
```

职责：

- `backend`：接收 command/approval，提供 query/SSE；长 effect 只形成 work item；
- `RuntimeNode`：相同循环和相同接口；处理能力由 exact assignment、installed node/interpreter profile 与当前 authority grant 共同决定，不由进程类决定；
- `db`：public control plane 拥有 runtime durable facts；project data plane/现有 capability stores 按 owner matrix 拥有研究事实；
- `redis/celery`：可选 legacy/migration transport，不是 core dependency；
- `runtime_artifacts`：project-scoped content-addressed blob store，由获得相应 project grant 的 backend/RuntimeNode 共享，只通过 `ValueStorePort` 访问；
- `frontend-modern`：read-only projection consumer。

每个 assignment handler 只产生 typed transition result；统一 reducer/UnitOfWork 追加事件并推进 snapshot。`INTERPRET` success 可生成 `VERIFY_ADMIT` work item，canonical readback 可生成 `RECONCILE` result；handler 不得绕过 reducer 直接宣称 run、research adoption 或 delivery 完成。

逻辑 owner 是纯 `runtime.transitions + reducer` 与 `RuntimeUnitOfWork`，不是一个必须单独部署的 central service。API、RuntimeNode、approval、timer 和 recovery 都提交同一 `RuntimeCommand/TransitionResult`；所有进程复用同一事务实现，不复制 DAG 或 research semantics。

第零阶段可单节点运行；扩容只增加同构 `RuntimeNode`。PostgreSQL claim、resource row lock、authority epoch 和 idempotency 保证多节点安全，不引入 global leader。若容量证据要求独立 broker，只替换 assignment transport port，不改变节点、Program 或 completion contract。

## 20. C1–C9 具体接线合同

本节 C1–C9 只作为 legacy code locator 与 parity inventory，不构成后继领域模块。每项必须先生成独立 atomic binding，写明旧路径、对应的 `frame/seek/observe/qualify/relate/compose/deliver/reopen` 领域 operator、对象类型、capability algebra、Atom operation kind、允许的组合构造、interpreter、canonical owner、fixture、legacy replay、shadow observation、迁移目标和 rollback。

迁移不是把旧函数简单包进 callback。每个能力必须按以下次序进入新架构：

```text
恢复 legacy 语义对象与调用链
  -> 映射到综合信息研究领域对象、关系与 operator
  -> 定义 ObjectType 与 capability algebra
  -> 把 legacy 操作表示为 Atom/Then/MapOutput/ZipOrdered/TraverseOrdered/Decide
  -> 用 LegacyInterpreter 解释同一 Program AST
  -> 用 SuccessorInterpreter 解释同一 Program AST
  -> 验证 Compile 的恒等/有序复合保持
  -> 验证具名 observation 下的 legacy/successor compatibility
  -> 接入 durable runtime
  -> canary/cutover
```

只有 legacy 与 successor 真正消费同一个 typed Program/ExecutionPlan，才能把该能力算作迁入函子化架构。

### 20.1 原子能力抽取清单

以下是必须逐项完成 eligibility、algebra、legacy replay 和 migration 的原子单元；family 不能以一个总测试替代其子单元：

| Cell | 语义边界 | 初始状态 |
| --- | --- | --- |
| `C1.1` | graph parse/validate/compile | `ELIGIBILITY_PENDING` |
| `C1.2` | graph runtime/executor/failure | `ELIGIBILITY_PENDING` |
| `C1.3` | graph store/replay | `ELIGIBILITY_PENDING` |
| `C2.1` | source normalize/taxonomy/mode selection | `ELIGIBILITY_PENDING` |
| `C2.2` | four source-mode orchestration | `ELIGIBILITY_PENDING` |
| `C2.3` | provider/credential/handler effects | `ELIGIBILITY_PENDING` |
| `C2.4` | terminal/compat projection | `ELIGIBILITY_PENDING` |
| `C3.1` | collect batch plan/traverse | `ELIGIBILITY_PENDING` |
| `C3.2` | collect result fold/receipts | `ELIGIBILITY_PENDING` |
| `C4.1` | batch plan/supplementation/branching | `ELIGIBILITY_PENDING` |
| `C4.2` | retry action/ordered reducer | `ELIGIBILITY_PENDING` |
| `C4.3` | submit/idempotency/API | `ELIGIBILITY_PENDING` |
| `C5.1` | session/task state machine | `ELIGIBILITY_PENDING` |
| `C5.2` | effect attempt/reconciliation | `ELIGIBILITY_PENDING` |
| `C5.3` | event fold/snapshot | `ELIGIBILITY_PENDING` |
| `C5.4` | Celery/DB/process readback projection | `ELIGIBILITY_PENDING` |
| `C6.1` | AgentCore program/tool loop | `ELIGIBILITY_PENDING` |
| `C6.2` | provider interpretation | `ELIGIBILITY_PENDING` |
| `C6.3` | redaction/evidence | `ELIGIBILITY_PENDING` |
| `C7.1` | ingest submission/staging | `ELIGIBILITY_PENDING` |
| `C7.2` | persistence/verification/admission | `ELIGIBILITY_PENDING` |
| `C7.3` | index/graph handoff | `ELIGIBILITY_PENDING` |
| `C7.4` | retry/recovery/rollback | `ELIGIBILITY_PENDING` |
| `C8.1` | typed knowledge/read handles | `ELIGIBILITY_PENDING` |
| `C8.2` | writing composition/artifacts | `ELIGIBILITY_PENDING` |
| `C8.3` | report/export/admission | `ELIGIBILITY_PENDING` |
| `C8.4` | graph consumer/provenance/loss | `ELIGIBILITY_PENDING` |
| `C9.1` | API command/query envelope | `ELIGIBILITY_PENDING` |
| `C9.2` | frontend projections/interactions | `ELIGIBILITY_PENDING` |
| `C9.3` | projection rebuild/offset | `ELIGIBILITY_PENDING` |

每个 cell 的冻结附件必须含：旧函数/route/store/test 精确路径，ObjectType，Atom kind/payload schema，允许的 Program combinator，failure/return union，canonical owner，effect/authority/resource contract，legacy interpreter ID，successor interpreter ID，observation profile，fixture ID，rollback observation 和 eligibility disposition。

### C1 Workflow Graph

- 旧路径：`main/backend/app/services/workflow_graph/{contracts,compiler,runtime,store,executors}`；
- legacy compiler/interpreter adapter：`main/backend/app/successor_migration/legacy_workflow_graph.py`；
- operation kinds：`workflow.vector_search.v1`、`workflow.llm_call.v1`、`workflow.join.v1`；
- runtime：原 API 内同步执行仅作 legacy interpreter；successor 走 durable run/step；
- canonical owner：runtime journal 仅拥有 run/step；graph business artifact 仍由 graph repository 拥有；
- 必测：node type/config 改变 plan digest、invalid graph effect 前失败、cycle、node failure/degraded、reload/replay、memory/SQL observation；
- rollback：feature flag 回 legacy runtime，不删除 successor journal。

### C2 Source Library

- 旧路径：`services/source_library/{item_resolver,resolver,runner,handler_registry}`；
- operation kinds：四个 `source_library.*.v1`；
- legacy sibling adapter 可调用 `ItemResolver` 和四个 orchestrator；successor-native algebra/interpreter 必须等待 eligibility disposition 后在新包独立实现，最终 handler selection 仍属 source-library capability owner；
- canonical owner：source item/config/project schema；runtime 只记录 execution；
- 必测：taxonomy idempotence、四模式、generic-web internal-only、credential failure、terminal output、collection 不等于 Document adoption；
- rollback：逐 item/capability allowlist 回 legacy。

### C3 Collect Runtime

- 旧路径：`services/collect_runtime/{contracts,runtime,adapters}`；
- 新 IR：`CollectProgram` 编译为多个有序 `CompiledStep`；
- 现有 `CollectAdapter` 只能由 `successor_migration/legacy_collect_runtime.py` 作为 legacy interpreter 调用；successor-native batch/traverse/fold interpreter 在新包独立实现；
- 必测：batch plan、singleton identity、ordered fold、error/receipt 不丢、serial/parallel observation、resource/backpressure；
- rollback：`SUCCESSOR_RUNTIME_COLLECT=off`。

### C4 Agent Batch

- 旧路径：`services/agent_batch/*`、`api/agent_batch.py`；
- 必须先迁移进程内 batch/idempotency registry 到 Postgres；
- `RetryAction` 是 capability IR，不是通用 runtime operation；
- source mode 仍由 C2 决定；
- 必测：重启恢复、duplicate request、budget monotonic、ordered rewrite、approval、Celery receipt、API compatibility；
- rollback：旧 API 读写 adapter 映射 successor run，但禁止双 claim。

### C5 Agent Session/Task/Event/Readback

- 旧路径：`services/agent_sessions/{service,store}`、`services/task_readback_metadata.py`、`api/process.py`；
- 迁移目标：runtime journal 成为 run/step canonical；AgentSession/Process 成为 projection；
- 必须消除 terminal success 补造中间事件；
- 必测：claim/lease/heartbeat/retry/reopen、event sequence 并发、DB outage fail-closed、projection rebuild、OUTCOME_UNKNOWN；
- rollback：projection 可回旧视图，run authority 不双写。

### C6 AgentCore

- 旧路径：`services/agent_core/*`、`services/agent_runtime/*`；
- AgentCore 继续负责 model/tool loop；successor runtime 负责 durable effect step；
- tool schema 注册映射为 versioned operation kind；
- 必测：permission pause/resume、tool order、read-only parallel policy、provider evidence class、redaction、cancel、receipt；
- provider 替换只声明 named observational compatibility。

### C7 Ingest/Persistence/Index/Graph Handoff

- 旧路径：`services/ingest/*`、`services/tasks.py`、indexer/graph handoff；
- 分成 collect/stage、verify、canonical commit、index/graph projection；
- exact content/event binding 在 admission port；
- 必测：idempotency、transaction rollback、work-item replay、partial failure、commit-after-crash、index rebuild、no duplicate effect。

### C8 Typed Knowledge/Writing/Report/Graph

- 旧路径：`services/typed_knowledge`、`services/writing`、LLM report、graph consumers；
- demand-read、source handle、provenance 与 declared loss 进入 capability payload；
- semantic/source quality 不由 runtime 自动评分；
- 必测：read handle round-trip、loss declaration、source/adoption fact 不被 projection 制造、export authority。

### C9 API/Frontend Projection

- 旧路径：`app/api/*`、`contracts/responses.py`、`frontend-modern/src/lib/api/*` 与 pages；
- API 只调用 runtime facade；
- frontend 先迁 query/read model，后迁 commands；
- 必测：envelope、trace/project identity、unavailable/blocked/waiting、SSE after_seq、no control feedback、projection rebuild；
- rollback：旧页面/API adapter 保持，不能回退 runtime canonical state。

## 21. Feature flag 与 cutover

环境变量只提供启动默认值：

```text
SUCCESSOR_RUNTIME_MODE=off|shadow|canary|on
SUCCESSOR_RUNTIME_CAPABILITIES=comma-separated allowlist
SUCCESSOR_RUNTIME_SHADOW_EFFECTS=fixture|receipt-only|disabled
SUCCESSOR_RUNTIME_NODE_ENABLED=true|false
SUCCESSOR_RUNTIME_NODE_GRANTS=comma-separated capability/resource grants
```

进程启动后，真实 claim authority 来自 `runtime_capability_authority` 表及其 `authority_epoch`，不是各容器独立读取的环境变量。backend 与 RuntimeNode 的 assignment/claim 必须携带并重验同一 epoch。数据库约束和 claim transaction 保证 legacy/successor 不能同时 claim。

compiled step、step authorization、work item、RuntimeAssignment、EffectAttempt 与 receipt 全部绑定 `capability_id/claim_owner/claim_authority_epoch/claim_policy_digest`。RuntimeNode 将 scheduled epoch 与当前 registry epoch 比较；不一致时产生 `CLAIM_AUTHORITY_STALE`，不得执行。已 `IN_FLIGHT/OUTCOME_UNKNOWN` effect 进入 reconcile，未开始 effect 取消旧 assignment；routing policy 必须显式决定 future run 的新 owner，不允许旧 work item 在 `off/on` 循环后重新生效。

- `off`：只运行 legacy；
- `shadow`：successor 只消费 fixture/receipt/readback，不重复真实 effect；
- `canary`：allowlist capability/project 由 successor claim；
- `on`：已批准 capability 由 successor claim，legacy 仅兼容读取/adapter。

同一 logical run 任何时刻只能有一个 claim authority。rollback 只切换未来 dispatch/read routing；不得删除已写 successor events 或把旧 receipt 重新解释为未执行。

## 22. 实施阶段与硬门禁

### 前置门禁 F-0：只读语义与 owner inventory

在任何 production package、schema 或 runtime 实现前，只读冻结：

- 第一 specimen 使用的现有 Document/source/writing/approval 路径与 exact canonical owner；
- legacy cell 到 `ObjectContract/OperationContract/interpreter/projection` 的映射；
- 每个对象的 `CANONICAL_OWNED|IMMUTABLE_EXTERNAL_REF|DECLARED_LOSS_PROJECTION`；
- current source/target identity、revision/incarnation、readback、failure 与 rollback evidence；
- 已知不能被元语言统一的真实权限、资源、外部 effect 和失败差异。

F-0 只产生 inventory/fixture/owner matrix，不 import 或改写 legacy service，不转移 authority。

### 前置门禁 F-1：架构冻结

产物：本文冻结合同、`DomainContractSnapshot`、元语言闭包、第一 specimen contract 与 exact capability/owner bindings、最小 schemas、diagrams、C1–C9 locator/pending inventory、crash fixtures、依赖图、freeze manifest。C1–C9 正式 eligibility disposition/binding 在 P1 后逐 cell 冻结，不是 F-1 前置条件。

门禁：不改生产代码；open P0 为零；所有 hash 指向 Git blob 或冻结文件，不把 mutable working file 当 baseline。

F-1 不是开发阶段，只是进入第零阶段的授权门禁。

### 第零阶段 P0-A：Greenfield 函子化程序内核

建立第一 specimen 实际需要的综合信息研究对象与程序元语言：`ResearchIntent/Inquiry/ResearchPlan/SourceRef/MaterialRef/EvidenceQualification/Claim/Gap/ResearchArtifact/DeliveryIntent`、typed provenance relations、`ObjectContract/OperationContract`、`Identity/Atom/Then/MapOutput/ZipOrdered/Decide`、canonical codec、immutable catalog snapshot、compiler fold、typed `ExecutionPlan/RuntimeAssignment`、Port、reducer、dependency lint。P0-A 必须能编译第一真实 specimen；`SourceRef` 只指向 existing Document/source locator，P0 不执行外部 acquisition。`TraverseOrdered`、recurrence、真实 acquisition 和 C1–C9 其余 operation kind 即使已在设计合同中定义，也不得在缺少对应 specimen/law/recovery evidence 时声明 production-supported。

门禁：

- research/language/capabilities 无 FastAPI/SQLAlchemy/Celery/settings import；
- `MaterialRef != EvidenceQualification`、`effect success != research admission != delivery receipt` 有明确 type/guard；
- gap、counterevidence、review failure 可形成具名 successor inquiry/program；
- AST 保存完整子程序，不只保存 digest；
- transform/merge/discriminator 全部具名、版本化、可序列化；
- Identity/Then/ZipOrdered/Decide 的适用规律有真实结构反例；
- Compile 保持恒等与有序复合；
- 不存在 callback-only parity 声明。

### 第零阶段 P0-B：Greenfield durable substrate

只实现第一 specimen 所需的 project data plane 与 public control plane：project `research_objects/research_relations/research_owner_bindings/research_program_specs/research_execution_plans/successor_values`，public runtime refs、run/step/event/work-item/attempt、lease、idempotency、approval、authority、claim-time resource reservation、commit intent 与最小 projection offset。现有 Document 内容不复制到 Research Ledger；submission 必须把本次读取的 exact bytes 复制到 project `successor_values`，形成 immutable `CapturedMaterialSnapshot` runtime input。暂不实现通用 source acquisition、全量 projector、recurrence 或外部 broker。

门禁：事务、CAS、duplicate claim、DB restart、event concurrency、work-item replay、Research Ledger/Runtime Journal 权威分离测试。

### 第零阶段 P0-C：Greenfield runtime realization

用 successor-native、安全可逆 interpreter 运行真实 first specimen：从同一 project schema 读取两个 existing Document，并在 submission transaction 固化为两个 `CapturedMaterialSnapshot`/`MaterialRef`，再形成 evidence qualifications、claim 或 gap、Markdown artifact、人工 approval 和内部 content-addressed export receipt。`successor_runtime/**` 只依赖 `DocumentCanonicalReadPort`；读取现有 Document 的实现位于 sibling `successor_migration`，只允许 authoritative readback，不导入 legacy workflow/agent/control flow，也不获得写 authority。使用两个同构 RuntimeNode、exact InterpreterBinding、Postgres work-item claim、heartbeat、cancel、纯 transition/reducer、claim-time resource reservation、admission 与 reconciliation。synthetic fixtures 只用于 law/crash 反例，不能替代真实 specimen。

门禁：两节点 single-valid-lease、Document/Ledger 无内容双写、approval/authority/base drift fail closed、`OUTCOME_UNKNOWN`、不重复 effect/admission/delivery receipt、stale node、work-item backlog/restart；不得要求 Redis/Celery 才能闭环。

### 第零阶段 P0-D：新架构自举闭环

新内核必须独立完成：

```text
ResearchIntent + Inquiry + SourceRef(existing Document locator)
-> capture immutable Document input snapshots
-> typed Program
-> Compile
-> Qualify
-> persist run/event/work item
-> RuntimeNode claim
-> interpret successor-native first-slice capability
-> stage EvidenceQualification/Claim-or-Gap/Artifact ValueRef
-> verify/admit Research Ledger objects and relations
-> create DeliveryIntent and internal export DeliveryReceipt
-> reopen one gap into successor inquiry
-> project/delete/rebuild
-> crash/reconcile/replay
```

门禁：successor package 在不 import legacy service、Redis 或 Celery 的情况下完成真实 PostgreSQL 集成闭环；注入 artifact staged 后 crash、canonical commit 后 event 前 crash、delivery effect 后 receipt 前 crash，并验证 readback/rebuild。记录 `CapacityEnvelope.v1` 的两节点基线。只有 F-0/F-1 与 P0-A 至 P0-D 全部通过，第零阶段才完成。

### 第一阶段 P1：设施与能力迁移资格审计

对旧工作树、服务和能力生成 `FunctorizationEligibility`。可复用设施接入 infrastructure adapter；能力按 `ADAPT/EXTRACT_AND_REWRITE/REIMPLEMENT/REJECT` 分类。此阶段不迁移业务 authority。

### 第二阶段 P2：第一个外部 acquisition / legacy capability 迁移

在 P0 的真实 Document-ref specimen 通过后，从 P1 eligibility 中选择一个 `seek/observe` 或现有 workflow capability cell，完成 legacy replay、successor interpreter、shadow parity、canary 与 rollback。不得默认 Workflow Graph 必然先行，选择必须由 owner/readback/风险证据决定。

### 第三阶段 P3：C2–C6

按 atomic capability binding 逐项迁移；低耦合准备可并行，adoption/cutover 串行。

### 第四阶段 P4：C7–C9

在 durable/admission/projection 路径稳定后迁移写入、知识、报告、API 与前端。

### 第五阶段 P5：Assembly/canary/cutover

整体验证、逐能力 canary、rollback rehearsal、exact-candidate independent review。

## 23. 验证矩阵

必须同时包含：

- comprehensive information-research domain object/relation codec tests；
- `MaterialRef -> EvidenceQualification -> Claim/Gap/CounterEvidence`、gap reopen 与 artifact citation-closure tests；
- effect success / research admission / delivery receipt 三状态分离 tests；
- ObjectContract/DomainContractSnapshot/OperationContract/profile/catalog digest tests；
- extension-locality gate：增加 fixture capability 时共享 AST/compiler/reducer/work-item root schema 零修改；
- exact OperationContract/InterpreterBinding/DeploymentCatalog/AuthoritySourceBinding claim tests；
- Research Ledger owner matrix、external-ref incarnation drift、无 canonical 双写 tests；
- public control schema 无 Program/Plan/payload/value bytes tests；
- Program AST normalization/golden/reload 测试；
- `Identity/Then/MapOutput/ZipOrdered/TraverseOrdered/Decide` 构造测试；
- Compile identity 与 ordered-composition preservation；
- typed IR schema/codec golden tests；
- invalid program/effect-before-validation negative tests；
- reducer/state transition tests；
- StepState enum、transition table、DB CHECK 和 reducer 可达边完全一致性 tests；
- property tests：identity、ordered composition、associativity、normalization idempotence、failure/authority preservation；
- Postgres transaction/CAS/event sequence/work-item/lease tests；
- multi-`RuntimeNode` duplicate claim、node crash、backlog、retry tests；
- claim-time resource reservation、防超卖、无排队占槽 tests；
- per-project/capability fairness、aging、starvation-bound property/capacity tests；
- recurrence occurrence uniqueness/misfire/catch-up tests；
- rolling deploy compatibility、drain、旧 profile backlog tests；
- DeliveryIntent/Attempt/Receipt、effect-after-crash authoritative readback tests；
- 可选 Celery adapter 只在 migration/transport scope 做 duplicate delivery/queue outage tests；
- crash-window/recovery/reconciliation tests；
- per-capability legacy replay 与 shadow observation；
- projection delete/rebuild；
- API contract 与 frontend interaction；
- dependency lint；
- current candidate commit/tree/evidence binding。

基础命令至少包括：

```text
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q -p no:cacheprovider <focused tests>
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q -p no:cacheprovider <integration tests>
cd main/frontend-modern && npm run lint && npm run build
git diff --check -- <owned paths>
```

涉及 PostgreSQL/RuntimeNode 的声明必须在 Docker test profile 或明确的临时数据库/节点环境验证；no-server mock 不能替代 durable/runtime closure。Celery/Redis 只在声明 legacy/migration transport compatibility 时进入对应测试，不是第零阶段完成前提。

## 24. Manifest、baseline 与 candidate 身份

修正后的 manifest 分离三类身份：

1. `baseline_inputs`：绑定指定 commit 的 Git blob/tree identity；
2. `frozen_contract_family`：绑定冻结文件、schema、fixture、diagram 的当前 SHA-256；
3. `candidate_evidence`：绑定候选 commit/tree、测试报告和生成证据。

不得把将被修改的 production working file 作为永久 freeze hash 直接校验；否则任何正常实现都会让合同 validator 失败。

## 25. 重新启动开发 Goal 的前提

原 Goal 不得直接恢复。目标任务必须先：

1. 通过产品支持的 Goal 状态确认旧 Goal 已由用户停止；不得伪标 `complete` 或因一次暂停伪标 `blocked`；
2. 把旧 worktree 的 F0/C1–C9 代码、production diff、cache 与测试输出全部标为 `INVALIDATED/UNADOPTED_DRAFT`，只保留只读 evidence locator；
3. 在新的 clean worktree 或明确 quarantine 后的工作树启动，`git status` 必须只包含本次冻结文档，不能继承未审查 production diff；
4. 逐字读取本文绝对路径；
5. 独立审查并生成冻结 architecture correction；
6. 生成并冻结 first-specimen typed schemas/runtime diagrams/exact bindings、C1–C9 locator/pending inventory matrix 与 crash fixtures；不得在 P1 前伪造 C1–C9 eligibility disposition；
7. 更新总 freeze manifest，使旧合同与本文形成 additive contract family；
8. 修复 progress 中过时的 `HASH_VALID` 与 dirty-state 声明；
9. 验证 correction manifest；
10. 确认 F-0 owner inventory 与 F-1 元语言/first-specimen freeze 已完成，再创建新的 durable Goal；目标从第零阶段 P0-A 开始，不继承旧 F0 的 `MIGRATED` 状态；
11. 严格按 P0-A→P0-B→P0-C→P0-D→P1→P2 顺序推进；第零阶段只允许以 immutable adapter 读取 first-specimen existing Document refs，不得让 legacy service 塑造 successor core；首个外部 acquisition/legacy capability 完成真实纵向闭环前不得并行实现其余 C2–C9。

新的 Goal 完成条件是：综合信息研究领域内核、真实 production runtime、durable substrate、work-item/RuntimeNode/recovery、至少一个完整 inquiry-to-delivery 纵向 specimen 及随后 legacy cells 迁移全部通过合同；不能以实验目录、字段齐全、若干 spike 测试或 callback shadow 作为替代。

## 26. 当前裁决

当前开发状态应保持：

```text
ARCHITECTURE_FROZEN
F0_F1_CONTRACT_FAMILY_FROZEN
GOAL_STOPPED_OR_INACTIVE
NOT_CODE_COMPLETE
NOT_LIVE
NO_CANDIDATE
NEXT_AUTHORIZED_STAGE_P0_A
```

本文件只在 `02_functorial-successor-migration-development-contract.freeze.json` 验证通过时构成冻结合同。新的开发请求从第零阶段 P0-A greenfield 函子化程序内核开始，不继承旧 F0 的完成状态，也不把 legacy wrapper 当作新架构 foundation。
