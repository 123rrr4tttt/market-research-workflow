本文件为中文翻译稿；冻结与实施权限仍以英文源草稿及后续冻结合同为准。

# MRW 函子式后继迁移开发合同

Status: `REVIEW_DRAFT · NOT_FROZEN · DOES_NOT_AUTHORIZE_IMPLEMENTATION`

Version: `0.1.0-draft`

Date: `2026-08-30`

Repository: `market-research-workflow`

Topic root: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration`

Proposed laboratory root: `experiments/functorial-kernel`

## 1. 目的

本合同为 MRW 定义一次结构保持的后继迁移。迁移应先把现有能力恢复并复现出来，再把它们移入一个小的组合式程序内核。迁移不得以全仓库重写、对所有工作树进行盲目合并、新建控制面，或把现有模块仅作术语上的范畴论改名来开局。

目标是一个后继架构，其中：

- 在需要检查、重放、审批或审计之处，领域程序在执行前可检查；
- 效果在显式运行时边界处解释；
- provider、store、scheduler 与 execution 实现只有在命名观察合同之下才可替换；
- 规范身份、来源、权限、失败、恢复与有序组合在迁移后存续；
- 每个遗留能力先通过一个有界样本复现，再重放、影子比较、迁移，且只在之后退役；
- 实验区通过经核验的能力采纳成长为后继架构，而不是通过一次终局性大爆炸式重写。

本草稿不是实施授权。在源迁移开始前，必须有一个独立任务审查并冻结一份完全一致的合同副本及一份内容寻址的冻结清单。

## 2. 权限与文档拓扑

### 2.1 文档角色

该主题使用以下文档角色：

| 路径 | 角色 | 可变性 |
| --- | --- | --- |
| `00_functorial-successor-migration-development-contract.draft.md` | 由监督任务撰写的源提案 | 冻结输入选定后不可变 |
| `01_functorial-successor-migration-development-contract.md` | 经独立审查的冻结合同 | 冻结 |
| `02_functorial-successor-migration-development-contract.freeze.json` | 内容寻址的合同/输入清单 | 冻结 |
| `03_functorial-successor-migration-development-progress.md` | 唯一的当前开发与生命周期记录 | 可变，在阶段边界追加/更新 |
| `04_functorial-successor-capability-ledger.json` | 机器可读的能力/对齐/迁移注册表 | 通过经验证的转换可变 |
| `05_functorial-successor-final-review.md` | 精确候选独立审查 | 不可变的审查产物 |

进度文档是本开发唯一可变的人类可读当前状态源。README 文件、仪表盘、测试输出、分支名、工作树名、实验区 fixture 与运行时回执是投影或证据；它们不得独立声明完成。

### 2.2 权限排除项

本合同不授权：

- 未经事先清点与分类即合并每个工作树；
- 删除、重置、清理、变基或覆盖用户拥有的工作树改动；
- 启用实时网络、生产 provider、外部发布、破坏性清理或不可逆迁移；
- 将规范写入权移交实验区；
- 把运行时成功、测试成功、模式有效性或干净工作树视为语义或迁移完成；
- 新建通用管理器、真相存储、仪表盘控制器或强制工作流层；
- 在没有相应对象、变换、观察与测试的情况下宣称严格函子性、自然性、可交换性或代数效果。

## 3. 须保留的前身约束

除非明确的冻结修正宣告语义破坏，后继架构必须保留以下现有约束：

1. `agent_batch` 拥有补充、条目选择、`query_terms` 与目标数量。
2. `agent_batch` 分派不强制最终 `source_mode`。
3. `source_library.ItemResolver` 选择最终源模式；源库运行时选择 handler/provider。
4. 除非另有单独合同改变该边界，`generic_web.*` 仍仅限内部适配器使用。
5. 源收集成功不意味着 Document 持久化、索引、图采纳、报告完成或研究完成。
6. API、UI、dashboard、report、readback 与自动化证据仍是有界投影，而非独立真相源。
7. Provider 配置、凭据、权限、实时可用性与结果质量仍是相互区分的观察。
8. 取消、超时、重试、资源清理、网络、文件系统、数据库、进程、外部 Agent 与模型调用仍是具有具名所有者的显式效果。
9. 项目/租户隔离、已认证行为者身份、审批与不可逆操作权限不由程序组合本身提供。
10. 现有 adapter、caller、envelope、错误族、恢复路径与兼容性行为在其 ledger 条目达到 `LEGACY_RETIRED` 之前保持可用。

## 4. 迁移修正：先清点后收敛

### 4.1 工作树普查门禁

在产出工作树普查之前，不得开始任何合并或能力迁移；普查须对每个可达工作树或相关分支包含：

- 工作树绝对路径；
- 分支、`HEAD`、基础提交与树身份；
- 脏状态摘要与所有权警告；
- 按能力分组的已变更文件；
- 实现、测试、文档、fixture、自动化与证据分类；
- 当前验证状态及已知时的确切命令；
- 与其他工作树的重叠/冲突集合；
- 处置：`CURRENT_CANDIDATE`、`CAPABILITY_DONOR`、`PARITY_ORACLE`、`EXPERIMENTAL`、`SUPERSEDED`、`USER_OWNED_UNRESOLVED` 或 `OUT_OF_SCOPE`。

统一的 mtime、检出创建时间、分支命名或收尾性文字的在场不构成实质变更的证据。

### 4.2 能力包

收敛按能力包进行，而不是不加区分地整树合并。一个包包含：

- 源工作树/提交引用；
- 所拥有的文件；
- 语义责任；
- 保留的观察；
- 声明的损失或不兼容；
- 依赖与冲突列表；
- 聚焦测试命令；
- 回滚/回退边界；
- 审查者处置。

包按依赖顺序集成。仅当文件所有权、效果、权限、资源使用与观察互不干扰时，独立包才可并行准备。集成、规范状态更新、最终清单与完成声明保持串行。

### 4.3 脏工作树规则

不得仅为准备后继架构而暂存、提交、移动、合并、改写或删除未提交的用户改动。如果某项必需能力只存在于未解决的脏改动中，能力 ledger 记录 `USER_OWNED_UNRESOLVED`，依赖该能力的迁移保持开放，同时独立工作继续。

## 5. 最小生成架构

### 5.1 原语族

实验区从以下最小有用族开始：

- `Program[A]`：在需要检查时，对有界领域计算的可检查描述；
- `ValidatedProgram[A]`：结构性与不依赖权限的不变量均已通过验证的程序；
- `Interpreter[F]`：一个能力/效果族的实现边界；
- `EffectOutcome[A]`：带类型执行处置及结果或失败信息；
- `StructuralObservation`：用于对齐与替换检查的命名观察；
- `AuthorityContext`：显式权限、项目/租户范围、授权、到期/纪元与行为者身份；
- `CanonicalRef`：稳定身份、内容摘要、修订，以及可在可重建情况下不可复用的化身/世代；
- `Projection[A, B]`：从规范事实到 API/UI/报告/回读形式的有界派生；
- `CapabilitySpec`：一个能力的语义合同、效果、解释器、观察、律、fixture 与迁移状态。

这些名称是内部设计句柄。除非抽象改善理解，公共 API 保留领域语言。

### 5.2 核心操作

内核只能提供由具体用途证明其必要性的操作：

- `map_value`：在保持上下文身份与失败的同时，在稳定上下文内变换结果；
- `then_ordered`：有序组合，其中第二个程序依赖或跟随第一个程序；
- `combine_independent`：静态组合已知程序，而不暗示运行时并行安全；
- `traverse_ordered`：以显式访问顺序与错误语义，对稳定形状应用有效果操作；
- `validate`：产出 `ValidatedProgram` 或带类型的不兼容；
- `interpret`：通过所选解释器实现一个已验证程序；
- `observe`：将执行/规范结果投影为命名结构观察；
- `project`：从规范事实派生有界读模型；
- `fold_events`：当某能力采纳事件折叠时，从已接纳的有序事件派生状态；
- `reconcile`：在不自动重新分派的情况下，解决 `OUTCOME_UNKNOWN` 或过期锚点。

没有操作被假定为可交换。并行执行需要另外证明效果独立、资源安全、权限兼容、失败隔离与观察顺序容忍。

## 6. 架构视图

### 6.1 语义运动

```text
ResearchIntent
  --plans--> DomainProgram
  --interprets--> StagedOutcome
  --qualifies/verifies--> AdoptionCandidate
  --admits--> CanonicalArtifact

Failure / Counterevidence / Changed Requirement
  --reopens--> DomainProgram or ResearchIntent
```

箭头描述的是不同关系。规划不是执行；执行不是资格确认；资格确认不是规范接纳；反向回返不是逆映射或自动取消。

### 6.2 规范状态与投影

```text
Canonical Facts
  --projects--> API
  --projects--> UI
  --projects--> Report
  --projects--> Readback
  --rebuilds--> Derived Index / Dashboard

Runtime Receipt / Journal
  --supports reconciliation--> Canonical Admission Boundary
```

运行时回执、日志、缓存、仪表盘与进度文件不会成为第二个规范源。可以在不删除底层领域对象的情况下重建或删除投影。

### 6.3 运行时实现

```text
ValidatedProgram
  --interpret by Memory--> EffectOutcome
  --interpret by Legacy--> EffectOutcome
  --interpret by Shadow--> EffectOutcome
  --interpret by Production Adapter--> EffectOutcome
```

不同解释器可能在追踪、延迟、资源消耗、后端本地标识与时机上不同。替换主张限于命名观察与失败/权限语义。

### 6.4 权限与资格确认

```text
Program description
  --does not authorize--> effect execution

AuthorityContext + ValidatedProgram
  --permits bounded dispatch--> Effect Interpreter

StagedOutcome + Verification + Exact Content Binding
  --permits bounded adoption--> Canonical Store
```

内核不授予权限。过期执行器、过期租约、错误项目/租户、缺失授权、内容摘要已变更、规范化身已变更或基础修订不兼容时，必须失败即关闭（fail closed）。

## 7. 实验区布局

首个实现目标是仅限开发的实验区：

```text
experiments/functorial-kernel/
  README.md
  pyproject.toml or package-local test configuration
  core/
    program.py
    validation.py
    outcome.py
    observation.py
    authority.py
    canonical.py
    projection.py
    laws.py
  interpreters/
    memory.py
    legacy.py
    shadow.py
  capabilities/
    workflow_graph/
    source_library/
    collect_runtime/
    agent_batch/
    agent_session/
    agent_core/
    ingest_index/
    writing_report_graph/
    api_frontend_projection/
  fixtures/
  parity/
  migration/
  tests/
```

实验区不得在模块导入时导入生产设置、默认连接网络或生产存储，也不得成为生产调度器。稳定组件只有在能力级采纳之后才能移入现有生产模块或经单独审查的生产内核。

## 8. 能力单元协议

每个能力接收一个 `CapabilitySpec`/ledger 单元，包含：

- `capability_id` 与所有者；
- 遗留源路径与捐赠工作树；
- 语义输入/输出；
- 已接纳的变换与有序组合；
- 效果与失败所有者；
- 权限与项目/租户范围；
- 规范身份与投影规则；
- 所选结构观察；
- 刻意丢失或后端本地信息；
- 微样本；
- 遗留重放 fixture；
- 影子对齐场景；
- 律/性质测试；
- 迁移适配器与回滚路径；
- 当前状态与证据引用。

### 8.1 能力状态

允许的状态为：

```text
INVENTORIED
SPECIMEN_REPRODUCED
LEGACY_REPLAY_GREEN
DUAL_INTERPRETER_GREEN
SHADOW_PARITY
MIGRATED
LEGACY_RETIRED
BLOCKED_BOUNDED
INVALIDATED
```

状态变更必须指明其证据与确切代码/树身份。`BLOCKED_BOUNDED` 记录一个已知有限缺口，且不阻塞独立单元。`INVALIDATED` 在反例或漂移发现之后重新打开一个此前通过的单元。

### 8.2 三个强制复现层级

#### Level A：微样本

最小的现实示例确立领域对象、变换、失败与观察。省略能力之定义性权限、效果或失败边界的玩具不足以通过。

#### Level B：遗留追踪重放

一个确定性遗留场景由新程序表示，但通过遗留能力解释。它必须保留所选身份、参数、事件顺序、失败族、权限、来源与外部 envelope。

#### Level C：影子对齐

遗留与后继解释对同一有界输入运行。通过命名 `StructuralObservation` 比较；仅在合同声明精确字节保留处才要求字节相等。

三层全部通过后，迁移才开始。生产面向调用方、恢复、回滚与可观测性都迁移之后，退役才开始。

## 9. 能力迁移顺序

### 基础 F0：普查、ledger、内核与律测试台

交付：

- 工作树普查；
- 能力 ledger 模式与初始单元；
- 实验区脚手架；
- 核心 program/outcome/observation/authority/canonical 类型；
- 用于性质测试的确定性种子/重放支持；
- 无实时/无规范写入守卫。

门禁：

- 无生产行为变更；
- 所有捐赠方与用户拥有的未解决状态可见；
- 内核测试无需网络、DB、Redis、Elasticsearch、Celery 或 Docker 即可运行。

### 能力 C1：Workflow Graph

问题形态：执行前可检查的程序加经验证的编译。

必须复现：

- DSL 解析/验证/编译；
- 节点类型/配置与有序依赖身份；
- 执行器选择；
- 节点失败与运行终止；
- 安全时的内存与 SQL 存储观察；
- 已编译程序的重载/重放。

必需修正：

- 编译身份绑定规范化的节点类型/配置及所有执行语义字段；
- 运行时消费 `ValidatedProgram` 或返回带类型验证失败；
- 无效原始图不得绕过验证进入编译/执行。

### 能力 C2：Source Library

问题形态：带四个有界解释器的 provider 中立程序。

必须复现：

- 条目/频道合并与分类法规范化；
- `ExecutionRequest` 构造；
- `protocol_search`、`provider_harvest`、`site_search` 与 `url_execution`；
- 终端输出与遗留兼容性投影；
- 仅内部 generic-web 边界；
- 项目范围凭据与 handler 行为。

必需修正：

- 单一规范化/分类法源；
- `source_mode -> interpreter` 注册表；
- 保留 `agent_batch` 所有权边界；
- 收集结果仍与下游持久化/采纳相区分。

### 能力 C3：Collect Runtime

问题形态：稳定请求形状、有效果遍历与纯结果折叠。

必须复现：

- `CollectRequest`、adapter 注册表与 `CollectResult`；
- 遗留/工作流路由选择；
- 自动批处理 split/map/fold；
- 链接、计数、错误、provider 回执与展示元数据。

必需修正：

- 纯 `BatchPlan` 创建；
- 带单位元身份与所选观察结合的纯 `ResultFold`；
- 不假定效果可交换的串行/并行兼容测试。

### 能力 C4：Agent Batch

问题形态：可检查任务加数据相关的有界重试。

必须复现：

- 计划规范化；
- 源补充；
- 有界分支；
- 分派回执；
- critic 与重试决策；
- 幂等性与轮次身份；
- 现有 API 响应形状。

必需修正：

- 带标签的 `RetryAction` 与纯归约器；
- 重试预算单调性；
- 显式有序改写组合；
- 有效果提交与纯转换分离；
- 最终 `source_mode` 仍归 source-library 所有。

### 能力 C5：Agent Session、Task、Event 与 Readback

问题形态：显式状态机、持久事件、恢复与有界投影。

必须复现：

- claim/heartbeat/release；
- 依赖与审批行为；
- 重试/重开身份；
- 失败包来源；
- workflow/agent-batch 状态映射；
- Celery/DB 回读投影。

必需修正：

- 纯转换归约器；
- 非法转换失败即关闭；
- 最终状态吸收普通命令，除非带类型的重试/重开创建新纪元；
- 观察事件、派生事件与规范完成事实可区分；
- `OUTCOME_UNKNOWN` 与对账禁止不安全重新分派；
- 事件折叠与快照所选观察一致。

### 能力 C6：AgentCore 与 provider/tool 解释

问题形态：带多个 provider 实现的能力接口。

必须复现：

- 请求/项目/行为者身份；
- 权限与路由决策；
- tool 模式、调用、结果与有序事件追踪；
- 脱敏投影；
- fake/repo-local/selected-live 证据类别且不混淆。

必需修正：

- 除非建立更强的律，provider 替换主张仍只是观察兼容性；
- 凭据/网络/超时/取消/脱敏仍是解释器效果；
- 历史实时回执不得视为当前 provider 就绪状态。

### 能力 C7：Ingest、持久化、索引与图交接

问题形态：带不同采纳边界的有序效果。

必须复现：

- 提交/幂等性；
- fetch/normalize/candidate 创建；
- 持久化事务；
- 索引/图交接；
- 部分失败、重试与回滚观察。

必需修正：

- 分阶段收集不意味着下游采纳；
- 精确内容摘要与有序事件/负载身份绑定接纳；
- 重放重建状态而不重复非幂等效果。

### 能力 C8：类型化知识、写作、报告与图消费者

问题形态：有界投影与可组合消费者。

必须复现：

- 稳定读句柄与来源；
- 在需要处合成前按需读取；
- 写作/报告产物与导出边界；
- 图上下文 adapter 行为；
- 声明的有损压缩/脱敏。

必需修正：

- 投影不能制造源/采纳事实；
- 语义质量仍是被论证的用户/领域判断，而不是通用律分数；
- 即使内容有损，压缩仍保留规范身份与读句柄。

### 能力 C9：API 与前端投影

问题形态：对规范状态的多个有界视图。

必须复现：

- `status/data/error/meta` envelope；
- 项目/追踪身份；
- task/run/source/report/workflow 读模型；
- 失败与不可用状态；
- 迁移期间的前端兼容性。

必需修正：

- 投影从规范或显式标记的运行时观察派生；
- UI/回读不得把推断出的完成回馈进控制；
- 缺失或歧义绑定要如实呈现。

### 集成 I1：后继组装

在 C1-C9 至少达到 `SHADOW_PARITY` 后，通过适配器集成后继路径，同时遗留保持可用。不得仅因其样本通过就退役遗留能力。

### 收尾 I2：权限移交与遗留退役

权限移交需要单独的精确候选审查。只有满足以下条件，收尾才可将能力移入 `LEGACY_RETIRED`：

- 所有调用方已迁移，或拥有经审查的兼容性适配器；
- 恢复与回滚已经演练；
- 规范身份与投影重建通过；
- 无未解决的 `USER_OWNED_UNRESOLVED`、P0 或依赖性的 P1 残留；
- 能力 ledger、进度记录、Git 提交/树与证据摘要一致。

## 10. 律与性质测试矩阵

每条律按语义主张选择启用。内核不得强加无关律。

| 律/检查 | 适用条件 | 最小反例 |
| --- | --- | --- |
| Identity（恒等） | 定义了中性程序/变换 | 中性映射改变所选观察 |
| Ordered composition（有序组合） | 定义了顺序组合 | 编译/解释后的复合与有序组件组合不同 |
| Associativity（结合性） | 定义了三个兼容组合 | 括号化改变所选观察 |
| Normalization idempotence（规范化幂等性） | 规范化器声明为规范 | 第二次规范化改变规范形式 |
| Failure preservation（失败保留） | 声称 adapter/解释器替换 | 失败族/所有者消失或变成成功 |
| Authority preservation（权限保留） | 映射执行/接纳 | 更弱授权获得更强效果或主张上限 |
| Projection rebuild（投影重建） | 声称增量与全量重建路径等价 | 规范重放与当前投影观察不同 |
| Recovery equivalence（恢复等价） | 支持重启续作 | 已提交前缀重复，或过期前缀被采纳 |
| No duplicate effect（无重复效果） | 支持外部效果重试/重放 | 效果计数增加而无安全幂等性证明 |
| Content binding（内容绑定） | 支持验证/接纳/提交 | 负载/内容变更在身份不变下被接纳 |
| Backend compatibility（后端兼容性） | 两个解释器声称替换 | 命名结构观察发散而无声明损失 |
| Traversal/fold shape（遍历/折叠形状） | 重建稳定批处理形状 | 条目重排/消失或错误违背合同消失 |
| Monotonic budget（单调预算） | 定义重试/资格预算 | 转换不适当地增加已用/剩余预算 |

性质测试必须记录可复现种子，并使最小失败用例可检查。示例测试对领域语义与面向用户行为仍是必要的。

## 11. 效果与恢复合同

每个有效果的解释器返回以下之一：

```text
NOT_STARTED
IN_FLIGHT
SUCCEEDED
FAILED
OUTCOME_UNKNOWN
```

规则：

1. 缺失回执不意味着 `NOT_STARTED`。
2. `OUTCOME_UNKNOWN` 要求对账或权威外部回读。
3. 自动重试要求幂等身份，或证明效果未开始。
4. 重放/投影器重建不得重新执行网络、provider、进程、文件系统、DB 变更、Agent、发布或其他非幂等效果。
5. 取消、超时、清理与租约丢失有显式所有者，且不抹除效果结果。
6. 过期执行器不能发布可接纳结果。
7. 规范重建使用不可复用化身/世代，使旧前缀不能通过 ABA 等价修订/摘要/栅栏映像进入新项目。

## 12. 兼容性与迁移适配器

适配器必须声明：

- 源与目标表示；
- 保留的身份与观察；
- 刻意变更或丢失的信息；
- 全量、部分或有效果行为；
- 失败与权限映射；
- 版本化与移除条件。

兼容性适配器不得包含隐藏业务路由、静默提升权限，或把遗留读模型当作规范事实。如果现有语义无法保留，适配器标记为 `LOSSY` 或 `SEMANTIC_BREAK`，且迁移需要显式审查。

## 13. 开发工作流与进度纪律

### 13.1 目标

实施任务必须为完整冻结合同族创建一个持久 Goal。不得仅因当前能力或最终编辑文件变绿就标记 Goal 完成。

### 13.2 进度记录

进度文件必须包含一个顶部 `Current claim identity` 块，其中包含：

- Goal/任务身份与状态；
- 仓库分支/提交/树与脏状态边界；
- 冻结合同与清单摘要；
- 当前阶段与能力单元计数；
- 已接受候选/收尾身份或显式 `null`；
- 最近一次独立审查处置；
- 实时/规范权限状态；
- 当前阻塞项与下一步行动。

历史章节可保留早期主张，但不得与顶部块冲突。每次失效先更新顶部块，再加历史。

### 13.3 阶段边界更新

在以下时机更新进度：

- 合同冻结；
- 工作树普查完成；
- 基础 F0 完成；
- 每个能力进入 `LEGACY_REPLAY_GREEN`、`SHADOW_PARITY`、`MIGRATED` 或 `INVALIDATED`；
- 集成候选创建；
- 独立审查；
- 收尾或再次修正。

不要每次小编辑都改写进度。

## 14. 验证层级

### Level 0：文档与清单

- 成对围栏与链接检查；
- JSON 解析/模式检查；
- SHA-256 冻结输入匹配；
- 对所拥有文件执行 `git diff --check`。

### Level 1：实验区

- 纯内核单元测试；
- 带种子的律/性质测试；
- 无网络/无生产存储守卫；
- 微样本测试。

### Level 2：遗留重放

- 聚焦遗留测试；
- 精确 fixture/回读来源；
- 除非显式授权，无实时服务要求；
- 比较旧/新所选观察。

### Level 3：影子集成

- 对有界输入的双解释；
- 失败、取消、超时与恢复注入；
- 无重复外部效果；
- 投影重建与内容变更反例。

### Level 4：仓库集成

- 模块聚焦套件；
- 合同/集成套件；
- 适用的 lint/typecheck/build；
- 架构边界与导入检查；
- 当前树/报告绑定；
- 干净或显式有界脏状态审查。

### Level 5：独立精确候选审查

审查者重新打开精确候选树、冻结清单、能力 ledger、进度记录与生成的证据。它必须重放命名的 P0/P1 反例，而不是接受聚合绿色输出。

## 15. 必需验收场景

冻结合同必须至少保留以下场景：

1. 添加一个新的同形态 source/provider，而不编辑所有旧 provider。
2. 更改工作流节点类型/配置，并观察编译程序身份随之改变。
3. 尝试执行无效原始程序，并在任何效果之前收到带类型失败。
4. 以全部四种模式运行一个 source-library 条目，并保留终端身份/失败观察。
5. 比较串行与并行 collect 实现，且不重排或抹除失败。
6. 应用有序重试改写，并证明重试预算不能增加。
7. 外部分派后、回执发布前崩溃，得到 `OUTCOME_UNKNOWN` 且不重新分派。
8. 删除并重建具有相同可见修订/摘要/栅栏的规范状态，并通过化身不匹配拒绝旧前缀。
9. 变更任何已接纳内容/事件负载字节，并在旧验证绑定下拒绝提交。
10. 删除读模型/仪表盘，并从规范事实重建它，且不超出声明的投影损失产生语义损失。
11. 替换 memory/legacy/shadow 解释器，并比较所选观察、失败、权限与来源。
12. 移除 manager/dashboard 投影，并证明领域对象与可执行能力仍然存在。

## 16. 反模式否决门禁

出现以下情形时否决或修正实现：

- 所有工作树在无能力普查下被合并；
- 实验区成为第二个应用或真相源；
- 引入 `FunctorManager`、通用上下文或中央语义路由；
- 每个模块都包装进一个通用 Program，尽管问题形态不同；
- 仅仅因两个 adapter 共享一个方法名就称映射为自然；
- 把并行资格当作可交换性；
- 运行时回执、进度行、fixture 或仪表盘状态成为规范完成；
- 后继静默移除遗留行为、失败模式或恢复路径；
- 用一个微样本授权迁移，而无遗留重放与影子对齐；
- 性质测试被削弱以制造绿色证据，而不是保留反例；
- 语义质量或源质量被替换为模式完整性、嵌入相似性或模型共识；
- 从聚合测试推断完成，而无精确树/证据绑定。

## 17. 冻结协议

冻结任务必须：

1. 阅读本草稿与当前仓库证据；
2. 在不修改无关文件的情况下验证当前 branch/HEAD/worktree 边界；
3. 对身份、权限、效果、恢复与能力保留进行独立架构审查；
4. 仅修正有界合同缺陷，并记录相对本草稿的变更；
5. 写入 `01_functorial-successor-migration-development-contract.md`，状态为 `Status: FROZEN`；
6. 写入 `02_functorial-successor-migration-development-contract.freeze.json`，其中包含：
   - schema/version；
   - 仓库与主题身份；
   - 源草稿路径/摘要；
   - 冻结合同路径/摘要；
   - 规范输入路径/摘要；
   - 基线 branch/commit/tree；
   - 权限排除项；
   - 能力顺序与必需场景；
   - 审查任务身份与处置；
7. 验证所有清单哈希；
8. 创建进度与能力 ledger 文件；
9. 只有在此之后才创建/启动实施 Goal。

如果审查因必需脏改动无主或冲突而无法建立安全基线，它记录一个有界阻塞项，且仅在该工作不依赖被阻塞改动时仍可准备实验区脚手架。

## 18. 完成合同

只有满足以下条件，实施任务才能关闭其 Goal：

- 冻结合同与清单仍哈希有效；
- 工作树普查完成，且没有未解决捐赠能力被静默丢弃；
- F0 与 C1-C9 满足其必需状态，或显式冻结的范围缩减另有规定；
- 每个已迁移能力都通过微样本、遗留重放与影子对齐；
- 当前调用方、恢复、回滚与投影均已覆盖；
- 能力 ledger ID 与证据引用唯一且可解析；
- 进度、ledger、Git 提交/树与报告身份一致；
- 命名的内容变更、恢复、ABA、验证绕过、失败保留与无重复效果反例通过；
- 一次新的独立精确候选审查报告无开放 P0 或依赖性 P1；
- 未激活冻结范围之外的实时/规范权限；
- 实施任务向监督任务发送完成报告，包含结果、变更文件、验证状态、风险、精确候选身份与审查请求。

收尾仍是代码/迁移声明。除非另行证明并授权，它不意味着市场研究质量、源真相、生产就绪、provider 可用性、人类验收或实时切换授权。

## 19. 监督审查与修正循环

实施 Goal 完成后，监督任务必须独立审计：

- 合同与冻结完整性；
- 工作树普查与能力捐赠方覆盖；
- 当前源，而不只是进度文字；
- 程序身份与验证边界；
- 效果所有权与 `OUTCOME_UNKNOWN` 处理；
- 规范单一真相与投影重建；
- 能力级对齐与保留的失败；
- 精确候选/证据归属；
- 完成措辞与权限上限。

如存在发现：

- P0 或语义身份/恢复/权限失败使完成失效；
- 依赖性 P1 阻塞受影响的迁移/退役，同时独立单元可保持已接受；
- P2 文档/投影漂移需要修正，但不抹除无关的已验证代码；
- 新的修正任务收到精确发现、冻结输入、所有权、测试与完成标准；
- 历史失败候选与反例作为负面开发证据保留。

## 20. 草稿交接

下一个授权动作是独立冻结任务。在其冻结清单创建并验证之前，本文档不授权任何实施、工作树收敛、源迁移、权限移交或遗留退役。
