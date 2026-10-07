# MRW 精简框架

> 2026-10-07 · 当前工作按整族退役重新组织，基线为已提交的 `c3adced5946a52b66be4494aba3dbb707ee879b5`。上一轮完成的是迁移保持与本地验证，生产仅净减29行，不构成全局退役或显著瘦身完成。当前为退役设计与定界，尚未执行本轮删除。具体包、预算和验证入口见[平台结构精简与删减阶段](MRW平台结构精简与删减阶段.md)。

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

## 3. 整族退役的组织方式

工作沿一条完整链展开：保留必要能力 → 明确整族退役对象 → 取得最小保留核 → 切断真实消费者 → 连同注册、adapter、配置、专属测试和当前文档同批删除 → 独立收支与保持验证。整族的终点是旧职责已不可执行且实现已删除；新入口能调用、服务委托给新runtime、删掉一个循环或只减少导入数量均不足以完成。

优先处理已被替代、没有现役能力要求的零新增整族删除。必要替代只为具体退役包的真实缝隙实现最小首例，已有原语能表达的部分直接复用。新代码、共核、接缝、派生生产物和转出目录成本全部归入实际受益的删除族；没有一个可无限扩建的“共享建设预算”。若替代方案膨胀或仍依赖旧runtime，退回该删除族重新缩小承载，不能把旧实现留下并宣布迁移完成。

上一轮workflow净增999、retrieval净增3763、shared净增1594，是原跨目录替换族的独立复审责任。单个services子目录的增减不能替换这三个口径，source净减5991也不能抹去其增长。`projection_contracts.py`及`retrieval_material_native.py`有真实消费者，应按具体类型与效果重新定界，不是假定零引用的删除对象。已经退掉的staged/effect文件和旧URL ThreadPool区间不得再次计入可删量。

## 4. 全项目规模预算与收支约束

本节统一维护全项目计量与可执行预算。撤回上轮未经最小充分保留核和真实收缩包支持的全局硬帽、各责任分帽及净减承诺；原探索值保存在`f9926bac`提交历史，不驱动当前发包或验收，也不另设一组未经验证的较宽数字。冗余职责切断、旧执行owner退出、唯一路径及必要行为保持仍为硬验收；规模承诺由实际删除闭包与替代成本证明。

生产基线为`c3adced`；文档提交`139d0561`的现场源码盘点与其app一致。tracked regular源码按`.py/.ts/.tsx/.js/.jsx/.css/.scss/.mjs/.cjs/.sh`逐文件`splitlines()`计，含注释空行；全库3521文件862028行。可复算定位数据为`/tmp/mrw-whole-project-budget-20261007/whole-source-baseline.json`，不是另一个审批或事实平台。

| 自有实现责任面 | 当前行数 | 计量边界与预算责任 |
| --- | ---: | --- |
| 后端app | 307472 | 全部758文件；运行结构、领域、API与其它平台各有owner，按真实闭包取得预算 |
| 业务前端src | 69822 | 234文件，test/spec另入测试账；按必要交互与重复表达定界 |
| 全部自有kit/native贡献与开发、迁移、运维工具 | 137848 | kit3875、contributions36、backend migrations4845、backend scripts55543、root scripts52275、frontend tools4903、owned ops3296、search-lab11648、local入口1427；外移native实现同样计入 |
| 自有主体小计 | 515142 | 不含尚未完整分离的vendor内MRW定制增量 |
| vendor内MRW定制改动 | 待分离 | 以具名上游基线分离MRW维护的实现增量；定制测试入测试账，不以vendor标签豁免 |
| 自有运行实现与工具总计 | 515142＋未分离增量 | 未知量不记零，整体规模承诺由具名保留核及互斥删除包校准后确定 |

app当前路径基线互斥覆盖：services398文件130558行、successor_runtime233文件135154行、api39文件26297行、其它88文件15463行。路径清单负责不漏文件，语义归属负责不藏成本。领域按来源采集、检索资源、材料知识、写作报告、宿主工具与业务工作流、项目治理及业务根胶水组织，全部必要类型、kernel、effect与adapter入账；不自动授权删除provider、报告或其它用户必要能力。

**运行结构计量与保持。** `successor_runtime/{language,runtime,substrate,assembly}`及根`__init__.py`共130文件79503行，分别为7856、16099、49162、6385、1行；这是含部分领域handler的物理调查面，不能冒充纯泛用Runtime语义统计，也不再附加未经证明的族净减量。各实际退役包抽出的领域核、跨目录保留原字节、新增替代与共同接缝全部计回原族`A_actual`，搬家净收益为零；族与app及全项目总账同一代码只计一次。旧services执行owner与控制循环另行整族退出，不重复计收益，不因现核收缩难度而永久保留。

沿既选Runtime保留typed AST/codec、组合与版本身份、claim/commit、幂等、PG journal与UoW、staged-value及原子终态记录、effect/commit边界的current grant重读、真实审批引用、UNKNOWN按attempt读回、取消和必要恢复。领域canonical writer保持原owner，外部effect与DB不冒称天然原子；已发生或未知effect不能记作未发生，读回投影不取得第二状态写权。现核按真实消费者压缩重复实现，不要求推倒重写或另造kernel。

泛用validation、codec、claim/commit、install/admission、assembly、reconcile/recovery、运行状态及readback无论目录均归Runtime责任。领域handler保留自身schema、业务前置条件和特殊effect，不能包住旧loop藏成本。first-specimen/sample、重复状态与codec、安装外壳和冻结审批生产化按实际义务删除或合并，不能因唯一Runtime已选而豁免整个现实现。

**测试、文档与库存另账。** 自有测试当前773文件235198行含`scripts/tests`，不含vendor内测试；后续分离出的MRW定制测试仍入自有测试账。全库1444个Markdown文件172971行是当前与历史合计，正式现役入口须单独定界。vendor库存77588行已含generated8154行；历史脚本11785与evidence/fixture22315合计34100行另列。该机械路径口径的自有代码含测试与库存共784440行（515142＋235198＋34100），vendor单列；历史初分不授权退役现役依赖。历史脚本或fixture若仍被当前运行或验证工具执行，其必要实现成本回纳对应预算。库存不抵扣实现退役收益，冻结原字节不改写，不能以转archive或标历史逃账。测试和文档随真实职责退役、重复承载合并而收缩，不设未经证明的行数帽，不按LOC删除必要独立见证；现役七gate与真实消费者保持验证继续严格。

每个实现包发放前，从精确删除闭包取得最低删除量`D`、新增上限`A_max`和最低净减`N_min`，实际另报`D_actual/A_actual/N_actual`。新增包括公共接缝、派生生产物及跨目录提取；不得以难为由保留完整services或已被替代的旧runtime。当前已证明首批`D=2155/A_max=6/N_min=2149`保持硬约束，仅覆盖三个小闭包，不构成整体目标；已定安全删除包不等待所有预算校准。上一轮新增18141、删除18170、净减29仍只是历史迁移结果。

以一个有真实消费者的代表性收缩包校准最小充分保留核、实际删除与替代成本；已有证据充分就复用，不增流程门禁。具名保留核与互斥删除包预算形成后，由root裁定可执行总体区间与累计净减，继续扩展同形删除，不无限定界，也不以首批或总净减大于零结项。实际缺口回到对应包修正，不为行数弱化类型、权限、UNKNOWN、恢复或消费者见证。

## 5. 推进与验证

当前先核清现核保持、真实消费者与旧执行owner边界，并行推进已确认的零新增或最小替代整族包；再以真实收缩包校准成本，扩展同形删除；最后按有证据的总体区间与累计净减收口。依赖共同接口的替代由一个owner打通最小首例，已有证据直接复用；独立领域、前端和工具包不等全域定界。消费者与共享写面按实际依赖交接，不触发另一轮全面构造或大kernel建设。全局最多6名活跃Agent（含root分发与Astra编排各1名），其余最多4个作者/调查席和4个独立写面；共享贡献源、registry/checker、启动入口和测试资源按实际冲突交接。

复用原贡献权威源与`sync/check`，派生registry、sketch和witness不手工改表。停用功能的专属测试/脚本/selector随功能退役；仍存在的相邻能力、身份和权限见证继续执行，现役七gate不降低。原测试命令、公共类型检查、PG、coverage、build及其独占资源见[工作包文档](MRW平台结构精简与删减阶段.md)。本轮文档改写不运行这些验证，不构成退役执行或发布证据；后续删除沿用户已授权范围和预算就绪派发，普通定界不新增审批。

## 6. 历史迁移结果与当前状态

提交`c3adced`保留上一轮迁移实现和证据：原CI分步结果及未变依赖kept、PG39的21项、七gate291项、Search尾包15项、合并coverage core100%/other69.41%、4skip、原ci-pr/native coverage的exit1和成本分别记录。原`LOCAL_COMPLETE_NOT_RELEASE_AUTHORITY`仅指当时迁移合同的本地闭合，本轮撤回其作为整体精简完成的解释；不撤回真实测试结果。

精确历史可从`git show c3adced:docs/development/MRW平台结构精简与删减阶段.md`读取；原aggregate为`/tmp/mrw-structure-20261007-w4uct7gr/integration/ci-group-resumption-2.json`。这些是旧候选证据，新退役改动只能按未变依赖复用。全文件类型债、浏览器mocks、direct HOST写作工具证明范围和不完整调用/token成本仍保留，不新增为本次后置治理工程。

当前状态：未经证明的硬行数帽已撤回，结构退役方向、全项目计量和已证首批预算保持；总体规模承诺待真实收缩包校准，退役实施未完成。本轮只修改原文档，无生产/测试代码更改、未实际退役、未运行代码验证；文档随本次交付统一提交；未push或deploy。旧生产部署Stage4–6任务继续STOPPED，不恢复历史任务。
