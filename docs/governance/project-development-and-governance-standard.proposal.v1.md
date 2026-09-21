# MRW 项目级开发与治理规范（Proposal v1.1）

Status: `PROPOSAL_ONLY · NOT_NORMATIVE · DOES_NOT_AMEND_EXISTING_FREEZE`

Date: `2026-09-04`

Revision:

- `v1.1` incorporates the latest functorial development rules supplied for this
  workspace: recognize-before-realize, one canonical representation per domain
  object, closed owned unions, interface quartet, equation witnesses, derived
  read-only values, single writer, extension/refinement/loss classification,
  shared template parameterization, and architecture-test enforcement.
- Normative migration basis remains the frozen v2.3 contract family:
  `01_functorial-successor-migration-development-contract.md`,
  `02_functorial-successor-migration-development-contract.freeze.json`,
  `18_functorial-successor-effect-failed-state-machine-amendment.*`, and
  `20/21_functorial-successor-semantic-movement-completeness-amendment.*`.

Project root: `/Users/wangyiliang/market-research-workflow`

## 1. Proposal purpose

本文件提出一个覆盖 MRW 全项目的开发与治理规范。它不是函子化迁移合同的替代品，也不是新的架构层；其目标是在现有 backend、frontend、automation、documentation、research workflow 和 successor runtime 之上建立统一的开发入口、变更分级、验证边界、证据格式和治理节奏。

通过后，本规范适用范围是：

- `main/backend/**`
- `main/frontend-modern/**`
- `scripts/**`
- `tests/**`
- `docs/**`
- `development/latest-dev-docs/**`
- deployment、automation、database migration、API contract、research workflow 和 successor migration 的跨面变更。

本规范明确不修改既有冻结合同、schema、authority grant 或 production runbook。若与项目局部合同冲突，按第 2 节优先级裁决。

## 2. Authority and precedence

项目治理按以下顺序裁决：

1. 用户显式授权和 production authority。
2. 已冻结的合同、schema、authority grant、migration freeze 和 release gate。
3. 项目局部架构合同，包括 functorial successor v2.3 freeze family。
4. `docs/governance/semantic-movement-completeness-standard.md`。
5. 本 proposal。
6. 项目 README、局部 checklist、historical evidence 和 draft 文档。

Historical evidence 只说明当时观察，不自动构成当前状态。当前状态必须来自本轮 direct evidence。

## 3. Project constitution

MRW 的产品语义是：在项目作用域和人类授权边界内，把开放世界材料持续转化为可追溯、可质疑、可恢复、可交付的综合信息研究成果。

开发时的稳定对象链是：

```text
ResearchIntent / Inquiry / ResearchPlan
  -> SourceRef -> MaterialRef -> EvidenceQualification
  -> Claim / Gap -> ResearchArtifact
  -> DeliveryIntent / DeliveryAttempt / DeliveryReceipt
  -> successor Inquiry / Plan / Program
```

市场、政策、社交、商品、报告等是来源域；backend、frontend、agent、workflow、graph、search、report、automation 是投影、adapter、interpreter 或运营界面，不是互相独立的真相源。

所有项目级设计必须分别回答：

1. 语义对象和运动是什么；
2. canonical identity 归谁所有；
3. 哪些视图只是 projection；
4. effect、authority、resource、failure、recovery 如何表达；
5. 项目 scope、credential、budget、human approval 在哪里裁决；
6. 观测、证据、验收与 production claim 如何分离。

### 3.1 Functorial methodology baseline

MRW 的函子编程方法论不是要求每个模块使用范畴论术语，而是要求在存在组合、替换、解释或执行边界时，先用结构保持的方式描述开发对象。

项目级读法如下：

- **Objects** 是版本化的研究领域对象、关系、program AST、plan、assignment、receipt、projection 和 typed failure，不是任意 dict、ORM row 或 API 字段。
- **Morphisms** 是具名语义转换，例如 `seek`、`observe`、`qualify`、`relate`、`compose`、`deliver`、`reopen`、compile、admit、project、reconcile 和 recover。
- **Identity** 是每个对象和转换的 canonical identity，以及组合运算的 left/right identity。
- **Ordered composition** 是 `Then`、有限遍历、依赖图和 plan occurrence 的显式次序。后一步依赖前一步结果时使用 monadic sequencing；图在观察中间结果前固定时才可使用 applicative-style independent combination；两者都不授权任意重排。
- **Interpreters** 是 pure、test、simulation、PostgreSQL、provider、crawler、delivery 等执行解释器。Program description 不等于 execution effect，effect success 不等于 semantic completion。
- **Observations** 是 parity、readback、failure trace、recovery trace 和 projection result 的具名观察边界。backend substitution 只在声明该边界后比较，不默认称为 naturality。

只有当组件确实给出对象映射和有序态射映射，并绑定 identity 与 composition preservation 证据时，才可声称 functorial structure。缺少完整组件族或已验证 naturality square 时，两个 adapter 的关系只能称为具名 `observational compatibility`，不得称为 naturality。

### 3.1.1 Latest functorial development hard rules

以下规则优先于命名、目录形态和示意图相似性，适用于 C2 及以上变更；C1 变更若触及其中任一对象也必须遵守。

1. **Recognize before realize.** 为领域对象新增表示前先查共享基底是否已有该对象的值。已有则复用或通过显式 adapter 投影；确属不同领域对象时，先命名差异再新增表示。
2. **One domain object, one canonical representation.** 同一领域对象不得有两个可独立写入的 canonical 表示。前两次受控复制必须标注 `KNOWN_COPY` 及收敛 owner；第三次出现前必须抽共享 core，并登记判别串和替换路线。
3. **Closed union ownership.** 被两个以上消费者 case 分析的值必须是闭合 discriminated union，由一个模块拥有。消费者导入词表，不复制分支集合。失败类型、risk class、lifecycle state 和 disposition 均适用。
4. **Interface quartet.** 可替换接口必须同时声明 operations、types、laws、failure family。缺任一项不得称为 lawful、substitutable 或 backend-compatible。
5. **Equation witnesses.** 每条被依赖等式必须有类型证明、测试 ID 或显声明的 deviation。标为 testable 而无测试 ID 的主张自动降级为 heuristic。
6. **Derived values have no write authority.** view、cache、preflight、dry-run、simulation、dashboard 和外部声明在类型与文档上是 projection。事实源只有一个 writer；projection 不反向写入事实源。
7. **Change classification.** 修改接口、codec、law 或 interpreter 时必须分类为 extension、refinement 或 loss。loss 必须声明损失、迁移路线和新判别串，防止旧数据被静默读成新语义。
8. **Parameterize shared families.** 新增同类 subject 只提交 mapping data、port、profile 和差异测试；不得复制 runtime、program、fixture、law suite 整栈。
9. **Architecture tests are the structural gate.** 项目已有 architecture test 时，import 方向、判别串登记、失败类型白名单、一对象一表示和共享模板约束由测试执行；不得以人工复核或文档说明替代或绕过。
10. **No layer without authority.** 新增 Layer、Agent、Gate、Manager、Schema 或专用协议前，必须说明不可合并职责、独特输入输出、authority、failure owner、rollback owner，以及为什么共享基底、role、adapter 或确定性程序不能承担。

### 3.2 Weakest-abstraction rule

C2 及以上变更先按问题形状选择最弱结构，不因术语升级而增加层：

1. 直接函数：无稳定上下文、无替换需求、无复杂依赖时使用。
2. Stable-context mapping：只变换稳定上下文中的值时使用，并验证 identity 与有序复合保持。
3. Independent combination：computation graph 在中间结果观察前固定时使用；它只表示 value independence，不表示 effects commute。
4. Dependent sequencing：后一步依赖前一步结果或观察值时使用，并保持可观察次序。
5. Effectful traversal：有限结构需要按声明次序访问、重建并执行 effect 时使用，必须保留 shape、ordering 和 partial-failure 语义。
6. Program / interpreter split：只有当 live、test、simulation、backend substitution 或 recovery 边界真实存在时使用。

若某个接口、schema、manager 或 workflow layer 不能改善组合能力、局部推理、可测试性、替换能力或 effect 控制，则不得进入项目。

### 3.3 Claim levels

每条结构性主张必须标为以下三类之一：

- **Strict structure**：由类型、canonical codec 和 law 检查直接支持，例如 identity preservation 与 ordered composition preservation。
- **Testable engineering regularity**：在具名 observation boundary 上用 parity、failure preservation、replay 或 backend agreement 支持。
- **Heuristic analogy**：只用于设计直觉，不得作为实现、验收或 authority 依据。

禁止把 heuristic analogy 宣称为 functor、natural transformation、free construction 或 algebraic effect。禁止从“两个实现都能跑”推出任意交换图成立。

### 3.4 Non-commutativity default

除非变更明确声明并证明相关路径等价，否则以下均不默认可交换：

- 两个 semantic movements；
- 两个 effect attempts；
- retry 与 cancellation；
- projection rebuild 与 canonical write；
- authorization check 与 external call；
- resource reservation 与 work claim；
- delivery attempt 与 receipt admission；
- provider call 和 database commit。

并行执行还必须另行确认资源、权限、失败归属、时序、外部可见 trace 和恢复路径互不干扰。没有值依赖只是并行的必要条件，不是充分条件。

## 4. Repository development topology

### 4.1 Backend

Backend 分为：

- API transport layer；
- application service layer；
- domain object / capability layer；
- successor language、runtime 和 substrate；
- legacy service 与 `successor_migration` compatibility / parity boundary；
- database model、migration 和 repository adapter；
- provider、crawler、LLM、search、delivery 等 effect adapter。

新增代码不得让 API 反向决定 domain semantics，也不得让 projection 或 dashboard 成为第二控制面。Backend 内部的结构顺序是：

```text
semantic object / operation contract
  -> program composition
  -> compiled plan
  -> interpreter port and assignment
  -> runtime effect / receipt / recovery
  -> bounded projection
```

API、frontend、scheduler 和 dashboard 只能消费或提交这个链路的两端，不得在中间复制第二个 workflow 语义。

Backend representation rules:

1. The typed successor language/runtime is the semantic authority for C2+ program, plan, effect and recovery contracts unless a bounded compatibility projection is explicitly declared.
2. `services/agent_core/functorial/**` is a development projection surface. It may catalog and expose existing surfaces, but it may not claim canonical write, promotion, cutover, production authority or semantic completeness on its own.
3. A projection must not become a second schema authority. If `CoreToolSpec` already owns an operator schema, a functorial projection derives that schema or records an explicit deviation; it does not silently replace it with a static fallback.
4. A program has one executable interpreter contract. A lightweight projection may not validate one embedded program representation while runtime independently reparses a second representation unless the divergence is a declared C3 observation boundary.
5. Module import must not mutate project state. Catalog seeding, filesystem creation and persistence require an explicit lifecycle entry point owned by one writer.

### 4.2 Frontend

Frontend 是 typed API consumer 和 bounded read-model projection。页面可以提交 command、渲染状态和暴露诊断，但不得自行推导 canonical business fact。

前端变更必须同时关心：

- API typed contract；
- loading / empty / error / partial state；
- i18n；
- responsive layout；
- accessibility；
- runtime smoke 或 component/e2e coverage；
- no hidden control-plane inference。

### 4.3 Automation and scripts

每个 automation lane 必须有稳定入口、dry-run 默认、machine-readable artifact、checker 和失败分类。不得只留下一次性执行记录。

Nightly / recurring task 的默认顺序是：

```text
spec dry-run -> runner -> artifact checker -> human-visible status
```

无 spec 时 fail closed；下游 artifact 状态是 unavailable，不是 failed。

### 4.4 Documentation and evidence

文档分为：

- normative contract；
- current-state index；
- implementation plan；
- process record；
- immutable evidence；
- historical archive；
- draft / proposal。

每份文档必须显式标明 status。冻结文件不可为了 checker 绿而改写；当前状态只能用 additive supersession 表达。

## 5. Change classification

每个 issue、branch 或 task 在实现前必须获得一个 classification。分类决定审查、测试和授权上限。

### C0: Observation / audit

只读收集事实，不改产品行为。

Required output:

- checkout identity：cwd、branch、HEAD、dirty state；
- direct evidence path；
- observed / inferred / blocked 分类；
- non-claim；
- proposed next action。

### C1: Local implementation

单模块内的明确缺陷修复、小功能、UI correction、test repair、documentation correction。

Required gate:

- focused tests；
- typecheck / lint；
- affected contract check；
- no authority or schema expansion。

### C2: Cross-surface implementation

跨 API、service、runtime、DB、frontend、automation 或 docs 的变更。

Required gate:

- interface contract update；
- functorial applicability note：说明是否引入或改变组合、依赖次序、解释器替换或 observation boundary；
- backward-compatibility decision；
- migration / rollback decision；
- focused tests on every touched surface；
- one integration or smoke trace；
- documentation index update。

### C3: Architecture / semantic change

改变对象、关系、movement、authority、failure model、runtime protocol、canonical ownership 或 data truth source。

Required gate:

- object / morphism inventory；
- weakest-abstraction decision；
- identity、ordered composition、interpreter boundary 和 observation profile；
- law applicability matrix，每项标记为 `APPLICABLE` 或 `NOT_APPLICABLE + reason`；
- semantic movement matrix；
- predecessor completeness review；
- declared-scope correctness review；
- selected law / negative / recovery tests：只测试该 API 实际暴露的结构主张；
- explicit non-goals；
- user authority for any promotion claim。

### C4: Production / external effect

涉及 live provider、external delivery、credential、production DB write、scheduler execution、public network、tenant data 或不可逆操作。

Required gate:

- explicit user authorization；
- scoped credential boundary；
- production runbook；
- rollback and recovery rehearsal；
- telemetry and alert ownership；
- live readback evidence；
- no inferred production completeness。

### C5: Retirement / destructive operation

删除、归档、reset、clean、retire、rebind、remote mutation、schema drop、data cleanup。

Required gate:

- explicit path-level authority；
- replacement or recovery route；
- immutable evidence retention；
- rollback owner；
- post-operation readback。

## 6. Development workflow

项目级工作流固定为：

```text
intake -> scope classification -> evidence baseline
       -> contract-first design -> implementation
       -> focused validation -> review -> promotion/release
       -> current-state record
```

### 6.1 Intake

任务描述必须包含目标、边界、非目标、验收和授权上限。缺失时由执行者补齐并记录假设，不得自行扩大。

### 6.2 Evidence baseline

实质性实现前必须记录：

```text
cwd
branch
HEAD
dirty-state summary
affected contract / checker
current blocker
```

大规模 dirty worktree 不是阻塞只读审计的理由，但任何未归属改动不得被 absorb、reset、delete 或 rebind。

### 6.3 Contract-first design

C2-C4 变更先写或更新契约：

- API request / response / error；
- domain object and relation；
- operation profile；
- dependency shape and ordered composition；
- interpreter boundary and substitution scope；
- persistence boundary；
- authority boundary；
- failure and recovery；
- projection / readback；
- test matrix。

已冻结合同只允许 additive amendment，不允许局部“顺手修正”。

C3 契约还必须按第 `3.1.1` 节记录：

- canonical representation 与既有 `KNOWN_COPY` 状态；
- closed union owner 和消费者词表；
- interface quartet 完整性；
- equation witness / declared deviation；
- derived projection 与事实源 writer；
- extension / refinement / loss 分类和判别串；
- shared-family template 与 mapping 表；
- architecture test 覆盖项。

### 6.3.1 Morphism and effect contract

每个新增或改变的 semantic morphism 必须记录：

- source object 与 target object；
- ordered dependencies；
- authority scope；
- failure modes 与 typed failure owner；
- recovery、readback 和 rollback route；
- observation profile；
- declared loss 或 zero-loss claim；
- applicable interpreter family。

Pure domain 不得直接依赖 DB、network、filesystem、provider、scheduler 或 process。这些能力通过 named port 和 interpreter 实现。Interpreter 边界必须保留 receipt、authoritative readback、cancel、`OUTCOME_UNKNOWN`、duplicate-effect prevention 和 recovery 语义。

Provider/backend replacement 默认只声明具名 observational compatibility。将比较升格为 naturality 是独立 C3 变更，必须定义两个结构、完整组件族和每个观察边界上的交换路径。

### 6.4 Implementation

实现必须：

- 优先复用共享 substrate；
- 新增同类 subject 只提交 mapping、port、profile 和差异测试；
- 不复制完整 runtime / fixture / test stack；
- 不把 effect 污染进 pure domain；
- 不因独立值而重排 effect，不因接口相似而宣称 backend naturality；
- 在共享核心实现一次 law、serialization、failure 和 recovery；场层只做 mapping 检查；
- 不引入新的 manager/schema layer 来规避语义问题；
- 保持 API envelope 和项目风格。
- 修改接口、codec、law 或 interpreter 时在任务记录中输出
  `EXTENSION | REFINEMENT | LOSS`；`LOSS` 不得合并，必须另走 C3/C5 变更；
- 不绕过 architecture test、失败白名单、判别串登记或共享模板约束。

同类 subject 扩展的验收还必须证明：

1. 新增 subject 不需要修改所有旧 subject；
2. 至少一个旧同构 subject 的具名观察行为不漂移；
3. 删除新增 projection 后 canonical/domain object 仍存在；
4. 共享族 drift 已归零或完成 exact rebind。

### 6.5 Review

C3-C5 变更必须双审：

1. Declared-scope correctness：实现是否满足声明的契约和验收。
2. Predecessor completeness：旧语义、失败、恢复、authority、projection loss 和 rollback 是否被完整处理。

Review 是 exact-byte evidence。后续相关字节变化会 invalidate 旧 review binding，直到新 review 绑定新字节。

## 7. Verification standard

### 7.1 Evidence levels

所有结论使用以下状态，禁止把历史或推断包装成 observed：

- `OBSERVED`：本轮直接读到的当前事实。
- `VERIFIED`：本轮命令、测试或 readback 通过。
- `UNEXECUTED`：尚未运行。
- `BLOCKED`：存在明确 blocker。
- `HISTORICAL`：来自旧记录，可能漂移。
- `INFERRED`：由事实推出，需标注依据。
- `NON_CLAIM`：明确不主张的范围。

### 7.2 Minimum gates by area

| Area | Minimum focused gate |
| --- | --- |
| Backend service | unit / contract tests plus affected API test |
| Combinator / mapping abstraction | selected identity and ordered-composition law tests, one counterexample if a claimed law fails |
| Program / interpreter boundary | same program through relevant test and live/simulation interpreters, plus failure, cancellation and recovery path |
| API schema | schema contract test and backward-compatibility check |
| DB migration | migration graph, upgrade/downgrade where applicable, disposable DB readback |
| Runtime / successor | dependency lint, focused family tests, generator `--check` where bound, declared law matrix, relevant negative/recovery replay and interpreter substitution evidence |
| Frontend | typecheck / lint, focused component or E2E smoke, i18n/layout check |
| Automation | dry-run, artifact checker, fail-closed missing-spec test |
| Security / credential | no-secret test, scoped permission review, redaction check |
| Release | runbook, rollback, telemetry, deployment readback |

全量 suite 只在 milestone、integration、release 或 fail-fast 后需要补跑的边界执行；小修复不得默认触发全仓验证。

Algebraic property tests are not a universal gate. They are required only when the patch claims identity, associativity, ordered-composition preservation, interchange, traversal ordering, round-trip, idempotence, monotonicity, failure preservation or backend agreement. The law applicability matrix must map each claim to `APPLICABLE` or `NOT_APPLICABLE + reason`; blank `where applicable` is not accepted. An applicable test must state the valid input domain, observable equality, seed/replay strategy, and counterexample retention policy.

### 7.3 Required statuses

完成报告必须包含：

1. Changed scope；
2. Verification command and exact result；
3. Unexecuted checks；
4. Current blockers；
5. Authority ceiling；
6. Rollback route；
7. Follow-up only if it is a real required action.

## 8. API and data governance

### 8.1 API

- Preserve the project response envelope and error taxonomy.
- Version breaking transport changes.
- Do not expose internal DB objects directly.
- Every mutation states idempotency, authorization, failure and readback.
- API projections must identify observed, derived and inferred values.
- Public compositional APIs expose only the structure callers need. Stable-context mapping, independent combination, dependent sequencing and effectful traversal are separate commitments; changing one requires a transport contract review.
- A compositional API must not collapse execution outcomes to a boolean. Transport and workflow wrappers preserve the underlying typed status, failure code, retry/readback disposition and authority ceiling.
- Error mapping is owned by one contract layer. String matching against exception messages is not a stable failure family.

### 8.2 Database

- One canonical owner per object/relation.
- Projections are rebuildable and never independently authoritative.
- Migrations are additive by default.
- Destructive migration requires C5 authority and a rehearsed rollback path.
- Tenant/project scope and ABA protection are part of data correctness.
- A record store advertised as a canonical catalog must have one domain writer per record family, an explicit upsert/version policy, cross-process conflict handling, fail-closed loading, and durable readback semantics.
- Append-only history with last-line-wins loading is not by itself idempotent canonical storage. If a write changes current state by overwriting an id, it is a version transition and requires a version/revision policy.

### 8.3 Provider and external effect

Provider call, receipt, admission and business completion are separate facts.

External adapters must record:

- provider identity and version；
- request identity；
- credential scope；
- timeout / cancel / retry；
- `OUTCOME_UNKNOWN` route；
- authoritative readback；
- cost / quota；
- redaction；
- failure taxonomy。

## 9. Security and operations governance

Minimum project rules:

1. No secret in source, log, artifact or public payload.
2. Credential scope follows least privilege and is project/tenant bound.
3. External writes and irreversible delivery require explicit human authority.
4. Admin and runtime control surfaces enforce permission, project scope and audit identity.
5. Every production capability has a runbook, rollback owner, alert threshold and recovery route.
6. Dashboards report health, but do not infer completion or mutate authority.

## 10. Documentation governance

Every substantive change updates:

- current-state index；
- API / architecture contract where affected；
- runbook or checklist where operationally visible；
- evidence record with exact path and status.

Documentation rules:

- No completion language beyond direct evidence.
- Historical pass must cite byte binding.
- Supersession is additive.
- Draft cannot authorize implementation.
- Frozen files cannot be edited for stylistic cleanup.

## 11. Simplification as a special change class

瘦身是 C2/C3 的特殊情形，不是独立于治理的清理活动。函子化之后的瘦身首先指结构性去重：把重复的 mechanics 收敛到共享对象、组合子、解释器和测试核心，同时保持 identity、有序复合、failure、authority 和 recovery 语义。任何“简化”必须声明保持什么、改变什么、丢失什么、由谁回滚。

### 11.1 Simplification principles

1. Reduce duplicated mechanics, not semantic depth.
2. Preserve object identity, morphism direction, left/right identity, associativity and ordered composition where those claims are exposed.
3. Shared core owns laws, serialization, failure and recovery once.
4. Same-form subjects contribute mappings, profiles, ports and differences only.
5. Legacy oracle and compatibility paths are frozen before retirement.
6. Evidence is immutable; navigation can be simplified.
7. A smaller diagram is not improvement if it hides authority, failure, evidence or recovery.
8. Do not merge representations merely because they use similar vocabulary; the lightweight JSON projection and typed successor language remain separate unless an explicit adapter and observation boundary is justified.
9. A simplification may remove mechanics, but not typed order, failure ownership, authority, recovery visibility, or counterexamples.

### 11.2 Current project simplification surface

Current direct audit identifies these candidates:

- Ignored `__pycache__` / `.pyc` artifacts can be cleaned only after explicit path-level authorization.
- Three exact copies of `_atoms` in successor PostgreSQL handlers are a shared traversal consolidation candidate.
- C6 interpreter validation skeletons are a parameterized validator candidate, preserving error order and family-specific predicates.
- Shared-family generator happy-path tests contain duplicate coverage; fail-closed and drift tests remain mandatory.
- Legacy family generators can become frozen parity oracles after exact shared-generator equivalence and rebind.
- `successor_migration/**` is protected compatibility / parity surface until member-by-member classification.
- `services/agent_core/functorial/**` is a lightweight projection surface, not production authority and not ready for semantic expansion without focused tests.
- All-lines evidence and freeze artifacts are immutable; only current-state navigation can be simplified.

### 11.3 Simplification ledger

Before implementation, project must create:

```text
docs/governance/simplification-ledger.v1.json
```

Each row must contain:

- path / surface；
- observed duplication or complexity；
- proposed action；
- semantic invariant preserved；
- object / morphism / composition claims affected；
- interpreter or observation boundary affected；
- declared loss；
- authority level；
- owner；
- focused acceptance；
- rollback；
- current status。

### 11.4 Drift gate

A simplification cannot merge while exact donor bindings or generator checks report drift unless one route is chosen:

1. adopt dirty source after ownership confirmation and additive exact rebind；
2. preserve frozen candidate and explicitly exclude dirty bytes；
3. reject the simplification.

Current observed blocker: shared-family all test reported `12 failed, 13 passed`; shared output agrees with legacy construction, but disk fragments do not bind current dirty donor bytes. This must be resolved before treating it as evidence for or against shared-core simplification.

## 12. Parallel work and delegation governance

Parallelism is allowed only with clear IO boundaries. Each delegated package states:

```text
goal / input / output / allowed read-write scope / acceptance / return format
```

Routing:

- architecture, semantic matrix, authority, risk acceptance, promotion and final review remain mainline responsibility；
- fixed-IO implementation, mechanical refactor, test generation, formatting and evidence normalization can be delegated；
- delegated output is implementation evidence only and must be independently integrated and verified.

Parallel tasks must not:

- modify frozen semantics；
- decide authority/cutover；
- rebind evidence；
- absorb unrelated dirty files；
- expand write scope；
- hide partial failure behind an aggregate success.

Parallel scheduling additionally requires resource, permission, failure-owner, timing, external-trace and recovery compatibility. Absence of value dependency does not authorize effect reordering or parallel execution.

## 13. Release governance

Release requires:

1. scope and non-goals；
2. semantic movement status；
3. focused and integration validation；
4. disposable runtime / DB evidence where applicable；
5. live evidence only for explicitly claimed live scope；
6. migration and rollback rehearsal；
7. security and privacy review；
8. telemetry and alert ownership；
9. runbook；
10. named approver。

Passing CI is release evidence, not release authority.

## 14. Current-state reporting

Project-level reports use four separated views:

```text
semantic movement
runtime / execution evidence
authority / qualification
release / operations readiness
```

A report may not collapse these views into one green/red value. Exact blocker classes remain visible even when aggregate state is healthy.

## 15. Non-goals of this proposal

This proposal does not:

- amend the functorial successor v2.3 freeze；
- authorize deletion of legacy code；
- authorize candidate, live provider, canonical write or cutover；
- merge lightweight functorial API with typed successor language；
- introduce a second governance runtime or manager；
- override user-owned dirty worktree authority；
- turn historical evidence into current completion.

## 16. Acceptance criteria for adopting this proposal

This proposal becomes an active project standard only after:

1. user accepts its authority boundary；
2. it is checked against the frozen v2.3 contract family；
3. the C2/C3 task template includes object/morphism inventory, weakest-abstraction decision, interpreter boundary and observation profile；
4. the C3 task template includes canonical representation, closed-union owner, interface quartet, equation witness, single writer, extension/refinement/loss classification, and architecture-test mapping；
5. a representation census marks existing duplicate surfaces as `CANONICAL`, `KNOWN_COPY`, `PROJECTION`, or `COMPATIBILITY_SURFACE`；
6. the simplification ledger is created；
7. current donor drift is classified；
8. task templates reflect C0-C5 classification；
9. focused verification commands are named for each major area；
10. architecture tests or an explicit bounded architecture-test adoption plan cover import direction, discriminant registry, failure whitelist, one-object-one-representation, and shared-template constraints；
11. no frozen file is modified.
