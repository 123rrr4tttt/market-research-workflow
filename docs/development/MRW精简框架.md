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

## 4. 当前基线与收支约束

唯一当前生产基线为`c3adced`的tracked regular app源码，扩展名`.py/.ts/.tsx/.js/.jsx/.css/.scss`，逐文件`splitlines()`含注释与空行；758文件、307472行。下列四面互斥且覆盖全部文件，不等于四面被保留。

| 责任域 | 文件 | 当前行数 | 当前义务 |
| --- | ---: | ---: | --- |
| services | 398 | 130558 | 旧整体承载退役；必要类型/kernel/effect逐项重证 |
| successor_runtime | 233 | 135154 | 既选内核以外装配、样板及重复类型整族审查；内核自身也核最小承载 |
| api | 39 | 26297 | 清理停用功能入口与旧链胶水；必要API聚合到现有owner |
| 其它app源码 | 88 | 15463 | composition、模型、合同、启动、观测、项目配方等全部具名定界 |
| 合计 | 758 | 307472 | 无未归属残差 |

上一提交生产新增18141行、删除18170行，仅净减29行。旧`23468a40`和dirty-start数值只用于历史追溯，不能用撤回未提交膨胀充当本轮正式版本瘦身。

每个实现包发放前固定生产删除预算`D`、新增上限`A_max`和最低净减承诺`N_min`；实际结果另记`D_actual`、`A_actual`及`N_actual=D_actual−A_actual`。`N_min`不能在实施后改成任意已取得的正数。预算从精确删除闭包和保留kernel估算，新增含空行/注释、公共接缝、跨目录提取及仍运行的派生代码。脚本、工具、前端、native贡献等转出成本另列并计入整体新增，不能藏在app统计之外；移动代码收益为零。测试、文档、vendor和生成库存独立计量，不抵扣生产成本。

已定首批三个包合计`D=2155`、`A_max=6`、`N_min=2149`，只是有限首批承诺。其余具名定界包必须产出互斥文件集与实现预算，全部实现包的最低净减合成全局承诺后才能判全局净量验收。现在没有可信的全局削减总目标，不臆造百分比；也不允许再以“总净减大于零”或首批2149行代替全局退役。结构本体未退完、预算未定或净量不足都不得记整体完成。

## 5. 推进与验证

当前顺序为并行只读定界与零新增删除 → 必要替代的最小首例 → 对应消费者切断与整族删除 → 集中保持验收和净量结算。只有真实缝隙依赖串行，已具备预算和原接口的删除不等全域定界。全局最多6名活跃Agent（含root分发与Astra编排各1名），其余最多4个作者/调查席和4个独立写面；共享贡献源、registry/checker、启动入口和测试资源按实际冲突交接。

复用原贡献权威源与`sync/check`，派生registry、sketch和witness不手工改表。停用功能的专属测试/脚本/selector随功能退役；仍存在的相邻能力、身份和权限见证继续执行，现役七gate不降低。原测试命令、公共类型检查、PG、coverage、build及其独占资源见[工作包文档](MRW平台结构精简与删减阶段.md)。本轮文档改写不运行这些验证，不构成退役执行或发布证据；后续删除沿用户已授权范围和预算就绪派发，普通定界不新增审批。

## 6. 历史迁移结果与当前状态

提交`c3adced`保留上一轮迁移实现和证据：原CI分步结果及未变依赖kept、PG39的21项、七gate291项、Search尾包15项、合并coverage core100%/other69.41%、4skip、原ci-pr/native coverage的exit1和成本分别记录。原`LOCAL_COMPLETE_NOT_RELEASE_AUTHORITY`仅指当时迁移合同的本地闭合，本轮撤回其作为整体精简完成的解释；不撤回真实测试结果。

精确历史可从`git show c3adced:docs/development/MRW平台结构精简与删减阶段.md`读取；原aggregate为`/tmp/mrw-structure-20261007-w4uct7gr/integration/ci-group-resumption-2.json`。这些是旧候选证据，新退役改动只能按未变依赖复用。全文件类型债、浏览器mocks、direct HOST写作工具证明范围和不完整调用/token成本仍保留，不新增为本次后置治理工程。

当前状态：退役框架已重组，首批预算已定，全局定界与退役实施未完成。本轮只修改原文档，无生产/测试代码更改、未实际退役、未运行代码验证；本地文档提交随此次交付收口，未push或deploy。旧生产部署Stage4–6任务继续STOPPED，不恢复历史任务。
