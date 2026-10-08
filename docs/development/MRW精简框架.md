# MRW 精简框架

> 2026-10-08 · 当前主线为原生规则贯通生产消费者并同批整族退役，基线为已提交的 `c3adced5946a52b66be4494aba3dbb707ee879b5`。上一轮完成的是迁移保持与本地验证，生产仅净减29行，不构成全局退役或显著瘦身完成。本批安全整族退役及Runtime、workflow有界首例已实施；app净减2114行，其中Runtime仅净减14行、workflow首例净增50行，尚不支持总体减量或提速结论。实际收支、验证及attempt集中见[平台结构精简与删减阶段](MRW平台结构精简与删减阶段.md)。

## 1. 从必要能力确定退役对象

MRW服务项目中的来源获取、材料组织、检索、信息拓扑、分析和引用写作。保留范围由用户需要的能力、权威事实与不可替代的效果决定。目录、API mount、测试、checker或旧兼容入口的引用只是消费者定位线索，不能使整族实现永久保留；还必须判断消费者能否并入已选入口或已有kernel。

本轮将必要能力及其实现分别处理。项目、材料、查询、知识关系和写作对象具有自己的身份；操作连接这些对象，领域writer拥有业务事实，既选耐久Runtime拥有运行事实，provider、DB和host继续拥有各自效果与授权边界。API、界面和读回投影指向这些事实，不取得新的写权。方法组织问题与判断，信息结构组织证据，执行过程承担状态变化，三者不因原目录耦合而合并成另一套通用系统。

退役包含两种明确变化：停止已经不再需要的冗余功能，连同其入口和专属验证撤出；保留必要能力时，以现有入口和最小原生核替换旧实现，然后切断原消费者，删除整个旧实现闭包。前者记录能力范围收缩，后者证明身份、权限、失败和效果保持。保留能力不等于保留整文件或整个服务族。

`services`作为旧整体组织承载是退役对象。领域类型、特殊算法核和真实effect须逐项重证并压缩后接入已有原生贡献位置；不能把130558行整包搬到`successor_runtime`或改名为domain层。目标也不是为了目录归零而搬家：暂留的必要最小核须有具体能力、权威、符号与退出/稳定承载说明，不能获得整目录豁免。successor中的样板、重复装配和派生外壳同样接受退役审查；唯一耐久Runtime保持既选内核，不新建runtime、DSL、安装、注册或审批层。

## 2. 必要能力与事实地图

### 2.1 能力地图

下表记录已知消费者族及其权威位置。一个能力可以由互相关联的原生定义组成：实体schema、操作签名、权限和特定UI表达承担不同事实。无需新增万能`CapabilitySpec`或主配置把这些定义重新抄录。表中路径相对仓库；`A=main/backend/app`，`F=main/frontend-modern/src`。

| 用户能力 | 权威定义与领域写入责任 | 已知消费者族 | 当前承载与扩展方向 |
| --- | --- | --- | --- |
| 建立项目、选择领域与约束 | `A/models/entities.py`项目实体、项目服务；可信身份及原grant/approval定义；customization与extraction各自协议 | projects/admin API、项目选择、工具context、检索绑定、采集与写作 | `A/project_customization`、`A/subprojects`及项目配置；共享身份装配，领域协议分别扩展 |
| 组织来源、资源与候选 | resource/site-entry等实体、`services/resource_pool/site_entries.py`；source/channel与候选typed contracts | resource_pool/source_library/discovery API、资源界面、搜索与采集工具 | 来源发现、URL资源、项目/共享资源有不同身份和可见性；适配器承担外部协议 |
| 导入、取得和管理材料 | `models/entities.py::Material`及领域writer族；`Document`为同一映射的兼容别名；原导入/抽取核 | ingest/crawler API与任务、document queries/views、搜索、拓扑、写作引用、原生工具 | `services/ingest`与领域数据接口；provider和项目抽取adapter可替换，正文权威不转移到图节点 |
| 检索、索引和迭代调查 | `services/search`候选/查询合同、现行index服务与ES协议、`services/project_retrieval`方法/预算/结果 | search/indexer/project_retrieval API、检索工具、图谱和资源搜索、写作suggest | 搜索索引是派生表示；研究方法决定问题/后续判断，执行层承担需要持久化的生命周期 |
| 表达知识、关系与信息结构 | `services/information_topology/{contracts,structural_schema,repository,service}.py`、typed知识原贡献与writer、图节点/边实体 | information_topology/typed_knowledge API、Graph、检索IO、写作context | 信息结构包含对象/关系/出现位置；方法结构和运行状态分别关联，不压成一张无类型图 |
| 分析、报告与引用写作 | `models/writing_entities.py`的WritingDocument/Draft/Citation；`services/writing`文档/引用/模板等事务；报告和LLM动作各自合同 | writing/reports/llm_report API、WritingWorkbench、拓扑写作context、工具 | 材料引用保留来源身份；正文版本/ETag、草稿、引用更新各有生命周期；LLM/provider是效果边界 |
| 调用工具、构造和观察工作 | `agent_core/contracts.py::CoreToolSpec`、原native贡献、工作流模板/版本、原组合语言；运行事实owner | 原生Core、functorial/workflow_graph/agent_batch API、session/process、WorkflowDesigner | direct/sync/durable按合同选择；宿主推理和MRW领域/运行权限分属各自owner |
| 访问、管理和部署平台 | API显式mount与权限依赖；`F/app/kernel/moduleManifest.ts`及页面表达；部署脚本/依赖清单 | HTTP客户端、业务前端、CodexAgentPage、WebUI、CLI/CI和开发者 | frontend已有manifest派生routes/registry；WebUI为上游vendor＋MRW边界适配；运行模式和验证工具属于交付责任 |

API挂载见`A/api/__init__.py`，包括上述领域、配置/治理、skills、agent_cell、clue_chains等。挂载证明入口存在；provider是否可用、各分析/报告链是否完成真实读回，仍由对应能力owner验证。历史[能力清单](../architecture/MRW项目能力清单_替代方案评估.md)用于识别覆盖面，其历史实施描述不代替当前源码证据。


这张地图定义需要判断的能力，不给现有实现发放保留凭证。每个退役包先指出仍需哪项用户操作、哪一事实owner和哪种独立效果，再定位最小实现；如果只是旧表示或包装继续引用另一层，应切掉包装和其专属接线。真实的草稿/发布、材料/索引、项目出现位置、provider协议和运行生命周期差异继续保留。

## 3. 同源接线与整族退役

主线是原生typed能力语义与真实特殊kernel → 已有native rule同源派生 → 实际production声明查找、handler安装与reader消费 → 同批切断并删除重复声明、装配、注册、旧adapter、执行owner及其专属tests/checkers。能力定义固定输入/输出类型、身份、权限与效果关系；规则保持这些关联，构造既选Runtime所需对象，投影仅供工具检查。生产消费者必须使用同一typed native对象，不能凭相同kind另维护一份factory表。注册存在、委托成功或删一个循环都不构成整族退出。

能力族以原生typed定义及对象身份`i`为索引：`D_i`包含明确的输入/输出、effects、failures和authority关系，`P_i`是纯检查投影，`C_i(d)`是与定义相容的当前资源/授权上下文，`B_i(d)`是保留该定义类型关联的实际绑定。两种有向解释共用语义源，生产实例只绑定上下文，不重抄定义：

$$
d_i\in D_i,\qquad \pi_i:D_i\to P_i,\qquad a_i:\prod_{d:D_i}\bigl(C_i(d)\to B_i(d)\bigr).
$$

这是待实现和见证的设计义务，不是已验证定理；只主张已声明端点及有序复合保持，不自动推出交换、自然性或不同形状同构，不据此新增代码schema。operation输入/输出、codec、kernel签名及reader结果关系须由同一原生定义维持；本批重复接线产生的Any/宽dict随壳消除，不能先擦成object/cast再称同源。JSON/provider不可信值只在解析边界开放，经原具体模型或判别失败收窄后进入领域/Runtime；现有无关类型债不纳入全库清零。

已有局部链路证明此方向可复用，但尚未全域贯通。`successor_runtime/capabilities/knowledge_graph_projection_contribution.py`的`KnowledgeGraphProjectionAuthorSource`经`lower_knowledge_graph_projection_author_source`派生contract/profile/dataclass codec/Program atom，`knowledge_graph_projection_native_rule`及`KNOWLEDGE_GRAPH_PROJECTION_NATIVE_RULE`组织规则；`assembly/knowledge_assembly.py`实际调用`native.assemble`和`binding.install`。图的`substrate/postgres/c8_graph_projector.py::project_graph_generation/read_active_graph`仍承担不能由模板猜出的业务/持久化语义。这是静态链路证据，不是本轮运行证明。

workflow局部首例已使`composition/production.py::_installed_operation_facts`和`_installed_operation_handler`从同一选定`WorkflowRuntimeDefinition`查找完整operation ref，并由`workflow_assembly.py::assemble_workflow_runtime_handler`构造原handler、检查完整类型/codec/authority关联。原`build_workflow_runtime_definition`支持既有三类节点内的kind映射，真实PG见证覆盖default与alternate。此处只统一operation安装接缝，未使`WORKFLOW_NATIVE_CONTRIBUTION_RULE`或全能力目录全面贯通；提取原handler及新增检查的成本计入首例，详见阶段§2.1。复用`PersistentOperationHandler`及`services/workflow_graph/__init__.py`的`submit_installed_program`与reader；`runtime.py::invoke_workflow_runtime_node`的输入关系与`execute_node`效果继续由领域核承担。`contributions/project_catalog.py`当前主要给CLI/check投影，`retrieval_native_catalog.py`也区分native与projection，均不能单凭catalog声称worker已安装。

Runtime自身同样沿“原生typed状态/值/事件/命令语义 → 已有关系规则 → 当前Node/PG消费者与只读readback”收敛。同一运行事实的codec、row映射、装配、投影与验证接入可以有向派生，减少重复模型和检查维护；结构收益不自动等于总代码减少，新增规则与派生生产量均计成本。现有局部调查与首例分为四面：

- 状态与事件：复用`runtime/transitions.py`的`RunState/StepState/EffectDisposition`、`RunEvent/StepEvent`、`RUN_TRANSITIONS/STEP_TRANSITIONS`及`transition_run_result/transition_step_result`共同查表解释；可派生的是这些既定关系的表示和校验，Run/Step/Effect身份与语义不同，不另抄TransitionSpec、词表或万能状态机。
- 值与row：`substrate/postgres/runtime_values.py::RuntimeValueBinding.values()`已从原dataclass字段派生浅层映射，`put_exact`合法state集合已从原`RuntimeValueState`派生，仍由`RuntimeValueRepository.put_exact/load_exact`消费。pure与实际PG原消费者见证及观察边界见阶段§2.1；这一小样本净减14行，不证明更大Runtime收缩，不延伸为字段微修或新生成框架。
- 命令与journal：`substrate/postgres/runtime_journal.py::JournalCommandSet/RuntimeJournalRepository`的开放snapshot/events/work_items及`append_transition`是typed命令与row/event projection候选；`FOR UPDATE`、revision CAS、seq分配、同Connection原子写入及失败仍由现repository承担，repository自身不commit/rollback，不能把所有SQL都归为模板。
- 权限与恢复：`runtime/ports.py::RuntimeScope/ProjectScopeRef/ControlPlaneScope`可支持既定shape的同源检查，但trusted resolver和执行前current grant读取才拥有授权判断；`runtime/recovery.py::NonStartProof/authorize_successor_attempt`保留UNKNOWN与真实未开始证明。转换可派生，claim/commit、幂等、事务、真实reconcile读回、cancel、版本identity与领域writer权限不转移到投影。

除已完成的值映射首例外，这些仍只是现役符号与候选的静态依据，不是可删量或运行证明。已有原生状态表/普通函数足够时直接复用，不为每个函数加贡献壳；不预定新IR、数据库生成框架、通用schema、注册器或恢复平台。若确需补共同规则，由一个owner用一个真实消费者打通后释放依赖的同形包；与workflow规则机制能复用就复用，不各建框架或重复计成本。无现役需求的功能直接退役，无需为生成保留。

标准化范围包括source/material/knowledge/writing/host/项目API、同步工具与reader、前端manifest和WebUI边界，均沿各自权威源到原消费者；durable operation只承担首公共案例。已贯通的前端manifest等形状直接复用，真实protocol/lifecycle差异不抹平。能力按真实形状处理：已有规则支持的同形定义直接复用；新语义形状只补当前所需的一条规则；特殊kernel与权限判断由作者明确；无现役需求的功能整体退役。不强制所有API/CRUD变成durable，也不以`Any`或unchecked cast抹平输入输出差异。领域作者只提供语义、类型、特殊核及独立见证；公共规则owner补lower/derive缺口；集成owner唯一维护共享production消费者、有效native目录及其投影与sync/check。三者是责任分工，可以由同一作者承担，不增加管理层。

公共首例由一个owner贯通原声明、真实消费者及删除闭包；依赖该接缝的同形批量迁移随后展开，已有形状、独立kernel和安全删除不等待。一次权威事实修改应驱动所有已确定装配字段；非默认同形定义也必须到真实消费者，可用现有第二实例或受控测试实例。交叉输入输出类型、重复/缺失identity、错误authority须明确失败，声明和sync/check不得执行effect。框架机制用原kit独立见证验证，项目迁移用真实消费者验证行为、顺序、失败与权限，二者不能互相替代；首例不是新审批关卡，不另建万能CapabilitySpec、Runtime、DSL、scheduler或注册审批平台。

新规则、公共首例、派生生产物、提取和集成成本均计回受益删除族；没有无限共享建设预算。旧services整体承载、旧runtime及旧执行owner全部退役，既选Runtime通过同源结构收敛消除重复模型、映射与装配，保留必要核，不推倒重写。上一轮workflow＋999、retrieval＋3763、shared＋1594继续分别复审，source−5991不抵消；有消费者的`projection_contracts.py`、`retrieval_material_native.py`按类型与效果定界，已退staged/effect和旧URL ThreadPool不得重复算删除。

## 4. 全项目规模预算与收支约束

本节统一维护全项目计量与可执行预算。撤回上轮未经最小充分保留核和真实收缩包支持的全局硬帽、各责任分帽及净减承诺；原探索值保存在`f9926bac`提交历史，不驱动当前发包或验收，也不另设一组未经验证的较宽数字。冗余职责切断、旧执行owner退出、唯一路径及必要行为保持仍为硬验收；规模承诺由实际删除闭包与替代成本证明。

生产基线为`c3adced`；文档提交`139d0561`的现场源码盘点与其app一致。tracked regular源码按`.py/.ts/.tsx/.js/.jsx/.css/.scss/.mjs/.cjs/.sh`逐文件`splitlines()`计，含注释空行；全库3521文件862028行。可复算定位数据为`/tmp/mrw-whole-project-budget-20261007/whole-source-baseline.json`，不是另一个审批或事实平台。

| 自有实现责任面 | c3基线行数 | 计量边界与预算责任 |
| --- | ---: | --- |
| 后端app | 307472 | 全部758文件；运行结构、领域、API与其它平台各有owner，按真实闭包取得预算 |
| 业务前端src | 69822 | 234文件，test/spec另入测试账；按必要交互与重复表达定界 |
| 全部自有kit/native贡献与开发、迁移、运维工具 | 137848 | kit3875、contributions36、backend migrations4845、backend scripts55543、root scripts52275、frontend tools4903、owned ops3296、search-lab11648、local入口1427；外移native实现同样计入 |
| 自有主体小计 | 515142 | 不含尚未完整分离的vendor内MRW定制增量 |
| vendor内MRW定制改动 | 待分离 | 以具名上游基线分离MRW维护的实现增量；定制测试入测试账，不以vendor标签豁免 |
| 自有运行实现与工具总计 | 515142＋未分离增量 | 未知量不记零，整体规模承诺由具名保留核及互斥删除包校准后确定 |

app的c3路径基线互斥覆盖：services398文件130558行、successor_runtime233文件135154行、api39文件26297行、其它88文件15463行。路径清单负责不漏文件，语义归属负责不藏成本。领域按来源采集、检索资源、材料知识、写作报告、宿主工具与业务工作流、项目治理及业务根胶水组织，全部必要类型、kernel、effect与adapter入账；不自动授权删除provider、报告或其它用户必要能力。

**运行结构计量与保持。** `successor_runtime/{language,runtime,substrate,assembly}`及根`__init__.py`共130文件79503行，分别为7856、16099、49162、6385、1行；这是含部分领域handler的物理调查面，不能冒充纯泛用Runtime语义统计，也不再附加未经证明的族净减量。各实际退役包抽出的领域核、跨目录保留原字节、新增替代与共同接缝全部计回原族`A_actual`，搬家净收益为零；族与app及全项目总账同一代码只计一次。旧services执行owner与控制循环另行整族退出，不重复计收益，不因现核收缩难度而永久保留。

沿既选Runtime保留typed AST/codec、组合与版本身份、claim/commit、幂等、PG journal与UoW、staged-value及原子终态记录、effect/commit边界的current grant重读、真实审批引用、UNKNOWN按attempt读回、取消和必要恢复。领域canonical writer保持原owner，外部effect与DB不冒称天然原子；已发生或未知effect不能记作未发生，读回投影不取得第二状态写权。现核按上述同源结构链收敛重复实现；一个内核的多种表示均有向派生，不建立第二事实owner或Runtime，也不要求推倒重写。

泛用validation、codec、claim/commit、install/admission、assembly、reconcile/recovery、运行状态及readback无论目录均归Runtime责任。领域handler保留自身schema、业务前置条件和特殊effect，不能包住旧loop藏成本。first-specimen/sample、重复状态与codec、安装外壳和冻结审批生产化按实际义务删除或合并，不能因唯一Runtime已选而豁免整个现实现。

**测试、文档与库存另账。** 基线自有测试773文件235198行含`scripts/tests`，不含vendor内测试；后续分离出的MRW定制测试仍入自有测试账。全库1444个Markdown文件172971行是当前与历史合计，正式现役入口须单独定界。vendor库存77588行已含generated8154行；历史脚本11785与evidence/fixture22315合计34100行另列。该机械路径口径的自有代码含测试与库存共784440行（515142＋235198＋34100），vendor单列；历史初分不授权退役现役依赖。历史脚本或fixture若仍被当前运行或验证工具执行，其必要实现成本回纳对应预算。库存不抵扣实现退役收益，冻结原字节不改写，不能以转archive或标历史逃账。测试和文档随真实职责退役、重复承载合并而收缩，不设未经证明的行数帽，不按LOC删除必要独立见证；现役七gate与真实消费者保持验证继续严格。

每个实现包发放前，从精确删除闭包取得最低删除量`D`、新增上限`A_max`和最低净减`N_min`，实际另报`D_actual/A_actual/N_actual`。新增包括公共接缝、派生生产物及跨目录提取；不得以难为由保留完整services或已被替代的旧runtime。安全首批发包预算`D=2155/A_max=6/N_min=2149`已达到，仅覆盖三个小闭包；本批各面实际收支统一见阶段§2.1，不构成整体目标。上一轮新增18141、删除18170、净减29仍只是历史迁移结果。

以workflow公共首例及同形迁移的真实消费者校准最小充分保留核、实际删除与替代成本；已有证据充分就复用，不增流程门禁。具名保留核与互斥删除包预算形成后，由root裁定可执行总体区间与累计净减，继续扩展同形删除，不无限定界，也不以首批或总净减大于零结项。实际缺口回到对应包修正，不为行数弱化类型、权限、UNKNOWN、恢复或消费者见证。

## 5. 推进与验证

安全整族退役与两个有界首例已有本批结果；下一前沿是寻找既有同形的整族重复装配或旧执行owner闭包，证明计入规则和集成成本后仍有正净收益，再发包。其它能力形状与D/A/N仍待定，不由首例通过直接宣布可批量迁移。首例一名owner贯通共享规则与production后，释放依赖它的同形作者；公共消费者和目录始终由集成owner串行收敛，消费者切换与整族删除同包验收。具体合同、依赖、写面及命令见阶段文档；完整路径覆盖账只防漏项，不决定架构切片。

全局最多6名活跃Agent，root分发与Astra编排各1名，最多4名作者/调查者；集成owner占其中1席。领域作者不各写adapter补共同缺口；共同规则失败回到唯一owner，独立包继续。PG、coverage、前端build/E2E独占，pure最多2个资源隔离进程。原进度记录汇总现成分派、首次共同验收、失败、手写机械接线、调用/token及共同修复成本；缺失不记零，不能由局部通过推断整体提速。

复用原贡献权威源与`sync/check`，派生registry、sketch和witness不手工改表。停用功能的专属测试/脚本/selector随功能退役；仍存在的相邻能力、身份和权限见证继续执行，现役七gate不降低。原测试命令、公共类型检查、PG、coverage、build及其独占资源见[工作包文档](MRW平台结构精简与删减阶段.md)。本批执行、kept、失败attempt及未运行范围集中见阶段§2.1；当前文档同步只做文档检查，不重复运行源码验证。后续删除沿用户已授权范围和预算就绪派发，普通定界不新增审批。

## 6. 历史迁移结果与当前状态

提交`c3adced`保留上一轮迁移实现和证据：原CI分步结果及未变依赖kept、PG39的21项、七gate291项、Search尾包15项、合并coverage core100%/other69.41%、4skip、原ci-pr/native coverage的exit1和成本分别记录。原`LOCAL_COMPLETE_NOT_RELEASE_AUTHORITY`仅指当时迁移合同的本地闭合，本轮撤回其作为整体精简完成的解释；不撤回真实测试结果。

精确历史可从`git show c3adced:docs/development/MRW平台结构精简与删减阶段.md`读取；原aggregate为`/tmp/mrw-structure-20261007-w4uct7gr/integration/ci-group-resumption-2.json`。这些是旧候选证据，新退役改动只能按未变依赖复用。全文件类型债、浏览器mocks、direct HOST写作工具证明范围和不完整调用/token成本仍保留，不新增为本次后置治理工程。

当前状态：局部试跑已完成安全整族退役、Runtime值映射派生与workflow安装接缝贯通；实际收支、验证范围及成本缺失统一见[阶段§2.1](MRW平台结构精简与删减阶段.md#21-本批局部试跑结果与证据)。全能力规则贯通和整体精简仍未完成。未经证明的硬行数帽继续撤回，“6–10万”保留为未校准历史情景，不是可信预期；不外推总体删减或提速。文档交回集成统一提交，未push或deploy；旧生产部署Stage4–6继续STOPPED。
