# MRW 平台结构精简与删减阶段

> 2026-10-07 · 整体实现的首个大阶段，已获用户授权实施，当前进入删除边界确认与先行收缩；尚未完成阶段验收。本文是本阶段工作包、串并行安排、执行合同与验收条件的唯一维护位置。

全平台目的、能力地图、事实归属、保持见证和成本基线见[MRW 精简框架](MRW精简框架.md)。本文沿用[流程缩减规则](../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/19_direct-testing-batch-freeze-amendment.v1.md)，不复制其规则。

本文路径相对仓库根：`A=main/backend/app`，`F=main/frontend-modern/src`；测试及运行模块缩写在§5定义。

## 1. 目标与结束后的唯一逻辑结构

整体实现首先完成“平台结构精简与删减”。本阶段的主要产物是**删减后的实际平台结构**：既有消费者使用更少的权威定义、执行机制、运行写权和装配位置，旧职责及其代码在同一完整替换族内退出。[总体框架](MRW精简框架.md)规定全局语义，本文仅分发本阶段所需的删减工作；后续建设不作为本阶段前置。

阶段结束后的唯一逻辑结构如下。职责可以共处现有模块，不按表新建目录或服务。

| 结构面 | 阶段结束后的承载与实际减少 |
| --- | --- |
| 领域事实与操作 | Material、知识、写作、项目/权限等各由原权威定义与领域writer拥有；保留真正不同的事实，删除同事实重复定义、解析及独立可写投影。业务实现、身份和原生注册不会在同步/耐久端各复制一份 |
| 入口与组合解释 | API、工具、页面只在各自支持域表达同一领域操作；直接调用沿原handler，请求内有序组合与耐久组合保留两种必要解释边界，共用领域定义和组合含义。退出各service自有通用runner、第二套业务解释及安装表 |
| 持久运行与效果 | 需要MRW跨请求生命周期的工作只由收缩后的现有耐久承载推进与写运行事实；session/process/batch/Graph运行页面读同一事实。provider协议内重试、领域事务与宿主推理保留各自责任；旧runtime的通用推进、状态writer、可执行fallback及启用接线整族退出 |
| 装配、表示与交付 | 工具贡献、页面manifest、领域原生定义分别是其事实源；沿已有规则派生确定的装配，删除平行词表/转发/样板依赖和已失效交付副本。必要的布局、协议版本、运行模式和独立验证见证继续存在 |

`services`和`successor_runtime`都必须收缩：前者退出旧通用控制和运行副本，必要领域核/协议adapter/事务writer继续由最小现有模块承载；后者退出重复profile/Program/codec/安装、强制样板依赖及无用外壳，保留被实际消费者依赖的最小语言、运行、权限和存储机制。不能因一个services目录仍含领域核便豁免其旧控制职责，也不能因某能力只在旧runtime中存在便保留整套旧runtime。独有且仍必要的语义只迁到已选现有承载中的最小位置，失去消费者/需求的语义直接退出。

## 2. 范围与后置内容

| 本阶段必须完成 | 后置内容及进入边界 |
| --- | --- |
| 确认重复/退役族；复用现有承载；完成删除必需的类型、权限、消费者、效果适配和原验证修改；切换、停旧写权、同批删除；核算结构及生产源码净减 | 全面类型强化、普遍拆巨文件、全仓命名整理，留待后续具体需求；本阶段只修影响当前删除族的必要边界 |
| 用普通材料到引用写作、demo非默认项目及既有运行入口证明删减保持 | UI重设计、性能优化、新扩展自动化/新贡献设施、产品或依赖选型后置；两条非runtime首例不要求建设新能力 |
| 使未调查的大族获得保留/合并/删除的明确处置；对已选删除族完成原消费者及必要历史依赖交接 | 平台功能扩充、普遍适配任意新形状、替换宿主/DB/索引/部署方式后置；现有支持域以本阶段必要验证保持 |

判断为保留且有真实职责/依赖依据的族可以零源码改动。这里的保留不适用于已明确退役的旧runner/writer/执行fallback；那些族的消费者未切换意味着未完成。历史decoder可以独立只读保留，不能重新装配旧执行器。原七gate与现有交付要求继续有效；本阶段不新增审批阶段或验证平台。

## 3. 当前实现族、保留承载与删除块

下表确定删除方向和保留责任；完整文件交接沿§5及附录A.6。实施作者先把已知候选收紧为具体符号/文件及真实消费者，再动手。旧方案已删除的模块保持其历史结果，不重建以便再次退役；当前未知是否仍有入口的残留在本阶段核清。

| 当前重复或退役实现族 | 保留的最小承载／消费者切换 | 同批删除块与边界 |
| --- | --- | --- |
| 旧Agent决策/控制runtime及残留触发器 | 原生host拥有推理；控制命令指向真实运行owner，摘要只读投影，宿主授权保持 | 旧决策循环、推理memory更新、伪完成/自动任务派发、执行fallback及其注册/配置。已退役部分不重做；剩余progress/task_bus/watchers逐一按真实职责判断，不因目录名整包保留 |
| WorkflowGraph、functorial、项目定制工作流的通用循环 | 模板/版本/表达式与特殊节点保留；同步入口解释原同步合同，耐久Graph消费收缩后的现有runtime | 服务驱动循环、HTTP第二runner、通用handler装配、SqlRunStore新run/events写入及session双写。旧表独立只读历史不要求旧执行器 |
| project_retrieval查询/followup推进及运行状态 | 方法、预算判据、候选/正式化/proposal领域核保留；原POST/task及读回切到已选生命周期承载 | service claim/heartbeat/通用终态、新ProjectRetrievalRun运行writer、第二调度循环；不可把整个旧loop包成一个Atom |
| URL/source/collect并发计划、重复Program和fold | 原单项kernel、channel/provider协议、Material writer保留；直接单项和耐久批次分别沿原正式入口消费 | ThreadPool/dispatch选择、第二plan/timeout/fold、专用重复装配、在线旧模式及迁移桥；协议Retry-After与领域partial/order保持 |
| batch/session/process运行副本与根tasks/skill胶水 | 消息/批准/显式plan/artifact保留；真实运行身份、控制和业务readback成为唯一来源 | claim/reclaim/retry第二引擎、通用task/event双写、死submitter、GET补写状态、重复transport/lifecycle接线 |
| successor重复native/profile/codec/Program/安装与研究样板强制依赖 | 原typed声明、已确认共同规则、真实handler/admission/readback；实际运行装配与必要离线验证各沿现存入口 | 同事实builders/安装switch/转发、无消费者外壳、无关fixture强制装配、重复样板。保持必要验证语义；只迁到tests不计全仓删减 |
| 材料/查询/拓扑/写作中的同事实表示 | 已统一Material和document queries/views、原写作事务；原搜索/Graph/引用消费者保持身份 | 只删确认同义的字段翻译、解析/正文副本。草稿、发布、引用、出现位置及live/sample区别不列冗余 |
| 项目身份和重复装配、页面身份词表 | 两项目协议保留，参数化确认相同的配方；manifest继续驱动现有routes/registry；checker读取同一页面事实 | 重复项目配方/身份注册和确证机械页面清单、无消费者转发；前缀语义、实例scope、布局差异和独立i18n表达保持 |
| 交付/验证/当前文档及历史承载副本 | 原启动模式、CI/local runner、七gate、当前入口及仍必要恢复依赖 | 同合同重复selector/配置/失效指引及已解除依赖的历史副本；不能以删见证凑减量，vendor/生成来源另账 |
| resource_pool/unified_search、graph、LLM报告/governance及宿主边界 | 有界核对各族权威、consumer和effect；必须形成保留/合并/删除判断 | 确认重复才给精确删除块；有依据保留可零改动。未知不能直接算保留或阶段通过，也不阻断独立族 |

旧runtime整族退出以**旧执行职责不再可执行且其实现/安装已删除**为判断，不以目录名称为判断。把services改名、搬到successor、通过adapter委托整套旧引擎或仅让新入口调用旧loop均不通过。successor中的必要现行承载也不能成为批量添加外壳的出口。

## 4. 防膨胀约束与净收益结算

1. 每包开始先在本文原记录中列退出职责、实际删除文件/符号、当前消费者、保留承载及对应原验证入口；只调查未决族时输出明确处置判断。未定位删除对象，不能先造新通用设施。
2. 必要新增只服务该包的当前consumer，并与同一个完整删除族绑定，执行同包删减后才结算。共同提取至少有已确认的重复输入与两个真实使用位置，不为可能的未来能力预建；已有规则足够就直接复用。
3. 迁移桥只服务具名consumer，由同一删除族owner负责；同包切换时删除桥、旧writer、旧装配及fallback。临时并存只能发生在该完整族尚未切换且有精确退出块时，包保持未完成，桥债不转嫁给未来包。
4. 不新建通用runtime、Schema体系、注册平台、验证或审批平台。同步解释/动态续接仅作为已选删除族的必要最小接缝；若只能靠大范围新构造才能迁移，登记为该族的具名设计缺口，收紧/重选已有承载，由主线处理，不预授权扩建。其依赖包不能结算完成，无依赖删除继续。
5. 每个实际替换包结算时，所拥有的完整删除族生产源码与维护结构净下降；纯核对后有据保留的包可零改动。公共接缝的新增和测试/集成修复计入依赖它的完整删除族，不作为“公共建设成本”漏算。临时正增只记在途。
6. 阶段整体须在相同口径下生产源码净下降，且独立事实副本、通用执行/运行writer和手写装配位置实际减少；不设无依据固定比例。同时报告[总体框架源码基线](MRW精简框架.md#52-已测源码基线)的HEAD→阶段候选及当前dirty起点→阶段候选；现有app净增6425行仍属本轮待收缩承载，换阶段起点不清零历史增长。领域、前端、运行等分账；有效删减抵消同族新增，包含共同规则、桥及生成后仍运行的生产代码。测试、文档、vendor、生成物和外移另账，不能抵扣生产增长；迁目录节省为0。

这些约束是本文分派和收口条件，使用现有记录与工具检查，不另建表单、审批流或证据系统。

## 5. 责任包、独占写面与串并行

以下为已授权实施的“平台结构精简与删减”分派合同。每包先确认§3的退出块，随后只作同批删除需要的最小修改；纯建设事项按§2后置。统一cwd为`/Users/wangyiliang/market-research-workflow`；Python入口为`main/backend/.venv311/bin/python`，Python路径为根、`src`、`main/backend`；前端Node/npm沿现有环境。每包输出在本文记录：结果、改动文件、原消费者、退出块、验证范围/退出码、成本和剩余风险，不新增成套开发文档。

`B=main/backend/tests`，`C=A/successor_runtime/capabilities`，`S=A/successor_runtime/substrate/postgres`。下表的花括号是明确文件集合；未列文件只读。开始前核对已有dirty和占用，现有改动保留。需要新增/扩展写面时由root在本文交接精确文件，不得以“相关目录”获得任意改写权。领域作者不重写其他包的规则/解析器/安装表。

| 责任包：目标／权威输入 | 独占写面／输出 | 前置／验证／资源／完成条件 |
| --- | --- | --- |
| **删减集成与接缝收口**：本文事实归属、§3删除族及原贡献规则；核对接缝和未分配残留 | 本文、`docs/development/MRW精简框架.md`、`docs/development/README.md`；共享`A/api/__init__.py`、`A/composition/{production,production_runtime}.py`、`A/services/{tasks,skill_runtime}.py`、`A/main.py`、`contributions/project_catalog.py`与派生registries/sketches | 单writer窗口；V-kit/V-type及必要联合验证。共享接线同批删除，原旧runtime入口/配置无遗漏，公共修复成本计入相应删除族，完成阶段净收支及消费者读回 |
| **领域数据与表示去重**：[材料到引用写作保持见证](MRW精简框架.md#31-普通材料到引用写作的保持见证)及原Material/查询/拓扑/写作owner；仅确认的同事实副本 | `A/services/document_queries/{contracts,identity,writing_documents,writing_material_queries,search_endpoint}.py`、`A/services/document_views/{__init__,writing_view,writing_card_view,consumer_boundary}.py`、`A/services/information_topology/{document_materials,repository,service}.py`、`A/services/writing/{document_service,citation_service,search_suggest_service}.py`；`B/unit/{test_document_queries_contracts_unittest,test_document_views_unittest,test_information_topology_document_materials_unittest,test_writing_document_service_unittest}.py`、`B/integration/{test_topology_document_unification,test_writing_api_unittest}.py` | 可立即独立；原模型/导入/API只读，删除必需改动才精确交接。V-data及隔离DB原集成测试；删除确认重复后原身份/正文/草稿/引用保持。现有正确统一不重做；有据保留可零改动 |
| **项目身份与装配去重**：[非默认领域扩展保持见证](MRW精简框架.md#32-非默认领域扩展的保持见证)中的两个真实项目及原双协议；确认相同配方/发现装配 | `A/project_customization/{registry,service,interfaces,defaults}.py`、`A/subprojects/{registry,base}.py`；`A/subprojects/demo_proj/{__init__,customization,extraction_adapter}.py`、其`mappings/{fields,llm,menu,workflow}.py`；`A/project_customization/projects/demo_proj/__init__.py`、`A/project_customization/projects/{hk_water_investigation,hk_water_macro_registration_trial_20260928}/{__init__,customization}.py`；`B/unit/test_project_customization_service_factory_unittest.py`、`B/core_business/test_project_customization_core_contract.py` | 可立即独立；只复用/极小修复身份装配，不建扩展自动化。V-extension；重复配方/注册实际退出，trial键漂移与冲突处理有结论，默认/非默认/前缀/历史alias及scope保持 |
| **页面身份副本删减**：原manifest及现有派生规则、baseline checker、页面布局合同 | `F/app/kernel/{types,contracts,moduleManifest,moduleContributionRule}.ts`、`F/app/topology/{pagePlacementMatrix,baselineInventory,contracts,navigationSwitching}.ts`、`main/frontend-modern/scripts/check_topology_platform_contract.mjs`；i18n及具体domain client仅按首例选定现有文件交接，不获整个前端写权 | 可立即删减页面身份副本；仅删除涉及wire变化时依赖数据包。V-ui；checker改读同一权威后删除旧库存/平行机械词表，routes/registry现有派生复用；不重设计布局/页面 |
| **宿主边界去重核对**：CoreToolSpec与既有host接入合同；仅MRW边界适配副本 | 首轮只读`A/services/agent_core/{contracts,registry}.py`、CodexAgentPage和WebUI README/协议适配；发现真实冗余后由集成固定具体adapter文件再发实施，不改vendor全树 | 不依赖runtime；先确定保留/合并/删除，V-host在具体适配删除前固定。必要权限/context/结果保持，vendor与generated分账；有据保留可零改动，不实施宿主替换或新adapter体系 |
| **执行退役的最小接缝**：附录A的原机制及已选旧执行删除族；共享修复仅为其consumer切换 | 原`A/successor_runtime/language`与`runtime`中首例涉及文件、`S/{first_specimen_activation,first_specimen_terminal,first_specimen_reconciliation_handler,first_specimen_successor,composition_root,node_adapter,work_items,runtime_lifecycle,models,batch_task_submission_handler}.py`；首例精确文件见下一段，schema迁移由集成单窗交接 | 对应族按需启动；同步真实consumer和动态片段分别证明必要接缝，可复用时直接迁移。V-core/V-sync/V-durable、PG独占。接缝不能独立算阶段产物；连同所依赖旧族删除才结算，需广泛新构造时记该族设计缺口 |
| **旧运行体系整族退出**：工作流、来源、检索、控制的原领域定义与§3旧runner/writer/装配 | 按四个子窗口交接：workflow_graph及functorial原入口；source/URL/collect原入口；project_retrieval原入口；batch/session/process原入口。每个窗口必须从附录A.6固定文件集合领取，公共composition/tasks仅集成写 | 只依赖本族所需已存在接口或必要修复，不等无关形状；V-workflow/source/retrieval/control，各子窗1writer。正式consumer切换、停止旧写权、同批删旧runner/状态副本/安装/fallback/桥；独有必要领域语义落最小现有承载，未删整族不完成 |
| **successor样板与装配删减**：原typed定义及运行/验证真实consumer；重复builders与强制fixture依赖 | `C/{profiles,catalog,codecs,__init__,first_specimen_submission,first_specimen_program,first_specimen_payloads,fixture,first_specimen_delivery_gate}.py`；`S/{first_specimen_handlers,first_specimen_assembly,first_specimen_delivery_gate,delivery_runtime,capacity,staged_recovery}.py`；`A/successor_runtime/assembly/{base,successor_assembly,app_assembly,s1_horizontal_port_assembly,s2c_ops_domain_surface_assembly,__init__}.py` | 不依赖所有执行接缝；只按重叠文件交接或实际consumer依赖等待。V-core/V-kit及原历史selector；停止强制样板装配，删重复外壳/转发/安装，保留必要验证并结算全仓净减；不建设通用生成平台 |
| **交付与验证副本删减**：现行launchd/Compose、依赖pin、CI/local selector与七gate | `.github/workflows/backend-tests.yml`、`scripts/{test-standardize.sh,dev.py,platform-macos.sh}`、`pyproject.toml`、`main/ops/README.md`；模式脚本/Compose实际需改文件由其现存入口精确补入后才写 | 可立即独立；V-delivery/V-suite/V-kit按实际删除选择，具体模式selector在实施前固定。删除同合同副本/失效配置与指引；必要差异及100/20 coverage保持，不改部署产品/模式、不建调度器 |
| **资源、分析与治理处置**：尚未完整追踪的resource_pool/unified_search、graph、LLM报告/governance族 | 只读`A/services/resource_pool`、`A/models/entities.py`图模型、`A/api/{llm_report,reports,governance}.py`及它们直接调用的原服务；输出每族定义/消费者/写权/替代候选和精确后续写面到本文 | 独立有界取证，必须逐族形成保留/合并/删除判断。保留可零改动；选删除则先精确交接现有文件及原验证命令，并在本阶段完成删减。未知/not_run不通过，不阻断独立包 |
| **文档与历史副本处置**：当前入口及checker/恢复引用；确认重复或已失效承载 | 首轮只读README/docs/development和checkers；当前失效链接修复限原文档精确文件交接。快照删除须先列具体路径、依赖迁移与原验证入口再发包，不自动获得development全树写权 | 可立即独立；V-doc及受影响原checker。当前重复事实/失效入口收敛；历史逐族保留/合并/删除有依赖依据，删除所需迁移同包完成。不扩写文档体系，不无差别清理快照 |

执行删除族需要接缝修复时，两个既有保持见证仍固定：同步`A/api/functorial.py`→`services/agent_core/functorial/{run,native}.py::run_workflow`；动态`A/api/project_retrieval.py`→`services/project_retrieval/{service,execution,submission}.py`→原task，调用`search/candidate_search.py::discover_candidates`与`ingest/url_pool.py::execute_single_url_kernel`。这些文件在必要接缝窗口归消费者作者，随后连同证据交同族删除作者，不并写或复制入口。公共写者是“执行退役的最小接缝”owner，简称接缝owner；公共文件只按当前删除族实际缺口收紧，未用文件只读。该窗口本身不计完成包，须并入其支持的完整删除族结算。

```mermaid
flowchart LR
  subgraph FIRST[首阶段：平台结构精简与删减]
    G[有界确认删除族 / 权威 / 接缝] --> D[领域数据与表示去重]
    G --> E[项目身份与装配去重]
    G --> U[页面身份副本删减]
    G --> H[宿主边界去重核对]
    G --> R[执行退役的最小接缝]
    G --> O[交付与验证副本删减]
    G --> K[文档与历史副本处置]
    G --> Q[资源、分析与治理处置]
    G --> S[successor样板与装配删减]
    G -->|原接口已足够| M[旧运行体系整族退出]
    R -->|只释放依赖该接缝的族| M
    D -->|仅必要wire变动| U
    D --> C[切消费者 / 停旧写权 / 同批删除]
    E --> C
    U --> C
    M --> C
    S --> C
    H -->|选删除则收口 / 保留有依据| C
    O --> C
    K --> C
    Q -->|处置已定 / 所选删除已完成| C
    C --> I[联合验收：能力保持 / 结构与源码净降]
  end
  I -.本阶段结束后按需要另行安排.-> L[后续：类型深化 / UI与性能 / 新扩展及选型]
```

每个删除族按“有界确认→复用或极小共同修复→切消费者/停旧写权→同批删除→联合验收”收口；图中的共同收口节点是各包都要满足的条件，不要求所有包同时切换。独立数据、项目、页面、样板和交付删除无需等待全部runtime；必要接缝也不成为全局建设前置。资源/治理等族须有明确处置，所选删除未完成不能宣称阶段完成；其未知只阻断对应族。后续建设不进入本阶段退出条件。

此前全局调查窗口为root＋框架作者＋3名只读调查，最多5名活跃Agent；当前实施由root分发/最终审查、集成owner和最多4名包作者组成。**后续实施全局上限为1名集成owner＋最多4名独立写作者＋1名轮转只读审查，合计6名活跃Agent。** 各包内部上限如下，不可累加突破全局写者和活跃人数上限；只读调查同样占全局活跃名额。

| 包 | 包内上限 |
| --- | --- |
| 领域数据与表示去重 | 1名写作者 |
| 项目身份与装配去重 | 1名写作者 |
| 页面身份副本删减 | 1名写作者 |
| 宿主边界去重核对 | 1名只读调查；进入实施后为1名adapter owner |
| 执行退役的最小接缝 | 最多2名：1名公共写者＋1名消费者作者；消费者按同步→动态窗口交接 |
| 旧运行体系整族退出 | 最多4名，各子窗口1名写作者；仍受全局4个独立写席限制 |
| successor样板与装配删减 | 1名写作者＋轮转只读审查；审查占用全局同一名额 |
| 交付与验证副本删减 | 1名作者 |
| 资源、分析与治理处置 | 1名只读调查；后续实施按精确写面重新分派 |
| 文档与历史副本处置 | 1名作者 |

共享文件始终只有1名写者：`S`中的公共文件及models/lifecycle由接缝owner负责；composition、tasks、skill_runtime、project catalog及派生registries/sync由集成owner负责。明确交出样板文件的窗口中，原owner停止写入该文件。一包腾出写席即可安排其他依赖已满足且资源兼容的包，复用现有分派方式。

PG窗口为1；同checkout前端build/E2E窗口为1；纯pytest最多2进程，各自使用不同tmp、Hypothesis、cache和日志路径，不写共享coverage。可变fixture根及其他缓存写入同样按冲突资源串行；不同文件、测试名或Agent不证明隔离。已知失败只阻断依赖它的包。

推进按以下有名执行窗口组织，引用本节包表及人数上限，不新增审批或阶段文档，也不要求窗口内全部完成后才释放下一包。

- **删除边界确认**：集成owner限定各族删除块、消费者、接缝和独占写面；未决族的只读处置可以并行，已有依据的包直接进入先行收缩。
- **先行收缩**：现成接口足够的旧块、死链，以及独立项目、页面、数据和交付副本先退出；必要接缝仅在对应删除族有实际缺口时启动，最多2人。一个可用前沿为集成1＋接缝2＋项目1＋页面1＋轮转只读1＝6；槽位可换成其他无依赖包。
- **依赖释放后整族退出**：四类执行消费者最多4名写作者，各自只等待所需接缝；完成即让位样板、文档或其他就绪包。共享文件按现有owner单窗交接，不等所有执行族一起完成。
- **联合验收**：稳定输入下集中执行原七gate、适用typecheck及原消费者验证，PG与同checkout build/E2E各单窗；局部失败只阻断其传递依赖，无依赖包继续收口。

## 6. 原验证入口与资源

下列命令为本阶段原验证入口，实际执行结果集中记§8；入口存在不代表通过。原venv已由集成确认；默认Docker项目沿原Docker入口，纯单元用已核本地入口，不反复安装依赖。纯测试函数使用不可连的外部端口，使未声明服务访问失败；需要DB的测试另走隔离资源，不能用该函数冒充集成验收。

```bash
cd /Users/wangyiliang/market-research-workflow
focused() (
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$PWD/src:$PWD/main/backend" \
  DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:1/postgres \
  REDIS_URL=redis://127.0.0.1:1/0 ES_URL=http://127.0.0.1:1 \
  main/backend/.venv311/bin/python -m pytest -p no:cacheprovider -q -rs "$@"
)
```

| ID | 可直接执行的原入口（根cwd；覆盖按变更补原用例） |
| --- | --- |
| V-data | `focused main/backend/tests/unit/test_document_queries_contracts_unittest.py main/backend/tests/unit/test_document_views_unittest.py main/backend/tests/unit/test_information_topology_document_materials_unittest.py main/backend/tests/unit/test_writing_document_service_unittest.py`；原`integration/test_topology_document_unification.py`与`test_writing_api_unittest.py`按其fixture资源在隔离DB执行 |
| V-extension | `focused main/backend/tests/unit/test_project_customization_service_factory_unittest.py main/backend/tests/core_business/test_project_customization_core_contract.py`；补demo精确/前缀匹配和trial身份见证 |
| V-ui | `npm --prefix main/frontend-modern run check:topology-platform`；`npm --prefix main/frontend-modern run check:writing-workbench-typed-fetch`；`npm --prefix main/frontend-modern run build`；行为变化用原E2E对应selector与真实API读回 |
| V-core | `focused main/backend/tests/successor_runtime/test_program_ast.py main/backend/tests/successor_runtime/test_compiler.py main/backend/tests/successor_runtime/test_p3_traversal_foundation.py main/backend/tests/successor_runtime/test_p0d_event_replay.py` |
| V-sync | `focused main/backend/tests/unit/test_agent_core_functorial_projection_unittest.py main/backend/tests/core_business/test_project_customization_core_contract.py` |
| V-workflow | `focused main/backend/tests/unit/test_workflow_graph_runtime_unittest.py main/backend/tests/unit/test_workflow_graph_compiler_unittest.py main/backend/tests/unit/test_workflow_graph_handoff_store_unittest.py main/backend/tests/integration/test_workflow_graph_api_unittest.py` |
| V-source | `focused main/backend/tests/unit/test_collect_runtime_composition_unittest.py main/backend/tests/unit/test_collect_runtime_auto_batch_unittest.py main/backend/tests/unit/test_source_library_resolver_unittest.py main/backend/tests/unit/test_source_library_runner_gray_rollout_unittest.py main/backend/tests/unit/test_collect_runtime_url_pool_adapter_unittest.py` |
| V-retrieval | `focused main/backend/tests/unit/test_project_retrieval_execution.py main/backend/tests/unit/test_project_retrieval_formalization.py main/backend/tests/unit/test_project_retrieval_proposals.py main/backend/tests/unit/test_project_retrieval_mode.py` |
| V-control | `focused main/backend/tests/unit/test_agent_sessions_service_unittest.py main/backend/tests/unit/test_agent_batch_api_unittest.py main/backend/tests/unit/test_agent_control_tools_unittest.py main/backend/tests/successor_runtime/test_batch_business_readback.py` |
| V-type | `MRW_TYPECHECK_PYTHON=.venv/bin/python main/backend/.venv311/bin/python scripts/dev.py typecheck --public-boundaries`；受影响文件使用原ruff入口 |
| V-kit | `main/backend/.venv311/bin/python scripts/dev.py sync`（声明改变时单owner）后同入口`check`、`test`、`gates`；`tests/test_architecture.py`及七gate义务保留 |
| V-suite | `bash scripts/test-standardize.sh ci-pr -q`，按原执行计划核对selector覆盖、资源与CI `not flaky`等差异；原coverage检查100/20阈值两入口保持 |
| V-doc | `focused tests/checkers/test_documentation_navigation_unittest.py`；特定快照迁移必须运行其当前引用checker，导航通过不证明历史资格可删 |
| V-delivery / V-host | 前者复用V-suite/V-kit和现有对应模式入口；后者按已选适配文件确定原合同用例。两项目前没有完整可执行验收selector，owner须在进入实施前固定；不将缺项算通过或让其阻断其他包 |

V-durable固定沿原隔离PG测试：`test_agent_batch_api_pg.py`、`test_request_cancel.py`、`test_mixed_operation_worker.py`、`test_traversal_persistent_activation.py`（均在`B/successor_runtime`）。历史专属资源`mrw-simplification-pg-20261006`/57659仅是待重新确认的资源身份；启用前核对owner及无业务卷，单窗执行原pytest命令并设置`SUCCESSOR_TEST_DATABASE_URL`。原动态用例需补根budget/currentgrant、WAIT、prefix不重放、活动父续接及取消见证，文件存在不代表已有覆盖。本轮未触碰或清理该资源。

## 7. 阶段退出与具名设计缺口

首阶段以真实结构下降结束，不以新入口能调用、共核新增功能或局部测试通过结束。每个包按完整删除族或有据保留的处置结算；全部以下条件满足才可声明“平台结构精简与删减”完成：

1. §3旧执行族中的通用runner、运行writer、自动fallback、专用安装与过渡桥实际退出，不能包裹原loop继续执行；必要历史读取独立于旧执行器。services旧控制职责与successor重复承载都有实际删除结果。
2. 每个事实仍只有自己的owner；原消费者的能力、项目/出现/材料身份、当前权限、失败/partial/UNKNOWN、必要类型与direct/sync/durable合同保持。材料到引用写作及demo非默认项目是保持见证，运行族按附录A核验真实结果/生命周期。
3. 生产源码按§4口径净下降；事实定义副本、独立通用执行/运行写权、装配维护位置分别有前后实数及对应退出证据。测试/生成/外移另账，临时正增和未清桥债不计完成。
4. 未调查族已逐族形成删除、合并或保留判断；保留要有职责/消费者/独立生命周期依据，可零改动。所选删除尚缺消费者、最小接缝或必要验证时仍未完成，未知、blocked和not_run不能记通过。
5. 原必要验证、适用typecheck/lint、七gate及实际交付合同通过；旧结果仅按未变依赖注明kept。验证只覆盖本阶段真实变化，不把后置类型治理、UI重设计、性能或新扩展建设偷偷加为退出条件。

| 未决面 | 责任与退出证据 |
| --- | --- |
| 数据表示待删块的原查询/索引/typed知识消费者 | 数据去重owner；沿原注入/查询核验身份和必要读回，保留live/sample区别；普遍扩展方式后置 |
| resource_pool/unified_search、graph模型、LLM报告与governance完整族 | 资源、分析与治理处置owner；逐族核对权威/消费者/效果/替代候选，明确保留/合并/删除；选删除则在本阶段按精确文件收口，保留可零改动 |
| demo扩展跨界面/工具的真实维护面、菜单外部consumer | 项目去重与页面删减owner；仅核验拟删配方/注册/菜单的默认与非默认consumer；外部未知不伪记无用，新扩展自动化后置 |
| WebUI本地patch与上游/生成协议的精确成本、host完整往返 | 宿主/交付owner；保留来源、协议版本和真实线程/项目身份读回 |
| 当前dynamic父续接、root budget/cancel聚合与in-flight方案 | 接缝owner及对应删除族owner；只补该族退出所必需部分，不接纳伪父完成。若须广泛新构造，记为该族设计缺口，不扩大本阶段、不放过该族完成条件 |
| CI/local选择器精确同异、全部测试归属和历史快照依赖 | 验证/文档owner；复用原runner/checker，七gate与独立见证不降格 |
| 全仓vendor/generated/config/docs细分及最终净收支 | 交付与全局集成owner；按[总体框架的成本口径](MRW精简框架.md#5-全仓维护成本与净收益)，未知成本不记0 |

各包交付真实新增/删除/外移及派生量、维护半径变化、手写机械接线、局部通过/kept/未执行和失败归属。模型调用/token、共同验收耗时、首次失败和主线规则修复成本从已有日志汇总，缺失明确标注；不同任务/范围不混作提速比例。必要typecheck/lint、原七gate及适用集成要求通过后停止扩测。不新增通用审批、schema、receipt或统计平台；必要的具体序列化契约仍由原事实owner维护。

## 附录A：执行工作线保留的严格合同

以下承接已有运行时调查，规定删除迁移必须保持的语义。它们不是本阶段预建完整共核的清单；只落实已选删除族当前需要的最小接缝，并在同族切换时删除旧承载。无依赖材料、UI、项目和交付包继续独立推进。

### A.1 直接调用、同步组合与耐久执行

分流依据是调用合同；不按“tool”“provider”“服务”名称，不做运行中自动猜测。

1. **直接调用**：一次同步读取、领域事务、provider特殊核，或者由原生Core管理的单次工具调用。沿原handler与权限执行，返回原typed结果；不创建持久run/profile套件。不因为含一次HTTP/LLM/DB效果就提升为平台任务。
2. **请求内有序组合**：调用方要求同步返回、无跨请求恢复/租约/独立取消生命周期的多个operator。原组合声明通过同一权威规则解释为typed有序组合，保留每步输出、失败短路及approval/deferred响应。删除service自有generic runner和状态判定；不改成submitted、不增第二RunStore。共同解释逻辑位于原language/组合实现，只有请求内局部值和出现身份，没有调度器、broker、持久run或恢复账本。
3. **耐久任务**：合同明确包含后台跨请求/worker的多步执行、持久WAIT/恢复、全程预算或独立取消。以原Program/Plan提交一个根运行，原RuntimeNode调度，原数据库承担claim/lease/idempotency/journal。已存在外部单任务可由原任务owner继续承载；只有MRW确有跨任务组合义务时才建立MRW根运行。

WorkflowGraph有持久run/events和恢复观察，进入第3类；检索轮次及后台多项采集进入第3类。functorial HTTP同步多operator与同步定制workflow进入第2类，其未来后台模式须是显式合同而非按步骤数自动改变响应。单URL同步入口属于第1类；相同单URL kernel被耐久批次调用时作为已声明叶效果。三者共用领域kernel和组合含义，不要求三套业务实现。

### A.2 现有内核的候选复用与类型边界

执行工作线优先检验复用原`ObjectType`、typed operation、`Then/MapOutput/ZipOrdered/Decide/TraverseOrdered`及已有编译/activation语义的候选；收敛共同控制解释，复用原RuntimeNode、Postgres UoW、run/step/work/journal、grant、resource和ValueRepository。业务能力与provider保持可扩展，运行状态和协议版本保持封闭、可穷尽检查。同步端需要的typed组合不附加耐久设施；耐久端才派生精确合同、codec引用和安装绑定。

定义、效果分类与权限含义只在原领域声明中写一次。贡献规则将已有typed定义降低到必要实现：同步可调用对象、耐久contract/profile、codec/ref、安装条目及验证引用。七类profile是当前持久协议的一种表示；旧已存digest必须保持，新增同形操作由规则派生其已确定字段。语义差异由作者明确输入，规则不能从函数名猜权限。原`OperationProfiles`、`build_operation_catalog`、`dataclass_codec`、`NativeContributionRule`可作起点，但当前散落的每域Program builder、安装switch和registry副本都要合并。

具体扩展例：第二个来源channel已拥有`Request → Result|Failure`的kernel及原权限声明。作者只提供channel参数、kernel引用和该channel不可推导的协议/结果见证。若需后台批量，实例化同一个有序采集组合；不再新增activation wrapper、submitter、profile文件和worker kind分支。同形执行叶的目标是公共runtime/production文件修改数为0，目录级新增通用执行器为0；实际领域声明、配置、UI和见证的必要改动分别计数，不能据此承诺完整项目扩展只改两个文件。 确需注册新family时只改现有catalog一处；这是新形状而非每实例成本。只有已确认重复且当前删除族确需的新结构缺口，才由接缝owner作一次最小修复；两个真实使用位置的原消费者见证后展开同形删除，普遍扩展能力后置。

`Then`传递实际前序typed输出；`ZipOrdered`规定访问次序与结果合并，兄弟分支不因此获得前一个分支输出。同一对象或同一根身份不推出效果可交换；顺序、数据依赖与失败短路分别验证。

公开数据边界保留具体类型：source请求、候选bundle、材料/知识引用、工具结果状态、dispatch ACK、业务结果、权限与失败族。工具`arguments`、用户自定义metadata及外部JSON协议可以使用经schema校验的CanonicalJson；不能把已知身份/状态/codec/budget擦成`dict[str, Any]`让下游重新解析。普通内部函数无需再加序列化Schema。

### A.3 动态续接、WAIT、取消与重试

| 需要保持的语义 | 统一实现决定 |
| --- | --- |
| 数据决定后续N、条件分支、followup | 原组合生成下一段Program/Plan；序列来源绑定精确ValueRef/字节/element顺序，出现身份含位置；不把旧整个循环塞成一个Atom。 |
| 不可变Program与运行续接 | 保持一个对外根运行。可用原materializer持久化不可变子Program/子run；父保持RUNNING/WAITING，根聚合未终结子项。禁止为了满足claim条件把未完成suffix的父伪标COMPLETED。 |
| 当前在途epoch设计 | `work_items.py:992`的MATERIALIZE_SUCCESSOR要求前驱已COMPLETED，原本服务终态gap后继。动态续接应在原materializer的明确绑定/资格分支表达“活动运行的续接”，保留原终态后继含义；**不采纳用TraversalEpochCompleted把局部前缀冒充整run完成的方案。** |
| lineage | 根、parent、来源step、原Program/输入值关系必须可验证且同scope；重建不能重做已完成effect。优先复用原事务/关系承载；当前新增`parent_run_id`仅在首例证明确需运行层直接查询且现有关系不够时保留，不能与另一套parent映射双写。 |
| 总budget/资源 | 根拥有全程预算消耗；子运行使用同一预算身份及已消费量，不能重置。现有resource policy负责容量/公平/lease；领域query/token/material预算保留原意义，两者不互相代替。 |
| WAIT与外部任务 | ACK后观察同一真实task；PENDING/UNKNOWN不等于NOT_STARTED。独立业务readback把结果/错误发布为typed值；有原生可等待接口时直接利用其readback，规则按边界派生WAIT段，不为每种业务复制等待Atom模板。 |
| 审批 | 同步遇needs_approval/deferred按原API返回并停止后继；耐久WAIT持久化批准关联，恢复时读取真实批准和currentgrant。worker不得伪造此前宿主ContextVar。 |
| 取消 | 根取消传播到待执行/在途子项；效果前阻断，效果后按原provider/readback确认，全部settled才终态。外部任务soft revoke不证明已停止；租约释放与attempt状态同事务。 |
| 重试 | currentgrant、expiry、失败分类、budget均重验。已知失败或证明NOT_STARTED方可重试；OUTCOME_UNKNOWN先reconcile。已终态run保持不变，新重试通过明确后继关系保留根业务身份，不能FAILED→RUNNING抹历史。 |
| 完成 | 根全部必要效果、动态后继、WAIT与业务结果达到合同终态才完成。固定顺序、部分成功/失败聚合按领域合同；dispatch COMMITTED/ACK/单epoch terminal均不充分。 |

首个动态见证选择真实“候选搜索得到N个结果→逐项取得→结果合并→有预算的后续判断”片段，并复用现有检索/采集入口。覆盖空N、N>1、前缀已有效果、suffix、重启、预算耗尽与取消。动态控制只由原runtime推进，任何测试替身仅替代叶provider，不代替控制owner。

### A.4 已有在途实现的归属

本表是后续实施决定，不在本轮执行撤回。

| 新增或扩大块（当前行数） | 保留/合并/改写/待撤回 |
| --- | --- |
| `agent_batch/dispatch.py`274；`business_readback.py`202；`capabilities/batch_business.py`306 | 保留真实提交/只读业务结果核与已验证幂等边界；合并重复合同/等待装配到共同规则，API必须消费业务结果。 |
| `agent_core/functorial/native.py`498及run.py单算子提交分支 | 原tool DTO/合法状态可复用；撤回“所有单tool都持久提交”的设计，恢复同步契约；耐久叶才按共同规则派生，不保留整套专用profile/program/wrapper。 |
| `project_retrieval/submission.py`88；`retrieval_effect_native.py`783 | 当前无正式提交消费者。候选提交与三种read/save/formalize声明重新按direct/durable边界归属；重复program/catalog/profile构造合并，纯direct操作不保留这些runtime外壳。 |
| `agent_core/source_library_dispatch.py`120 | 当前仅测试调用。领域lowering若可由共同有序规则派生则待撤回；保留不可推导item/权限语义，最终必须从原工具入口使用。 |
| `capabilities/acquisition_url.py`220及production URL分支 | installer存在，尚无该kind的正式Program提交链；原kernel有真实直接消费者。优先直接kernel，后台叶所需合同由共同规则派生，撤回无用途activation wrapper。 |
| profiles/catalog共核、`PersistentOperationHandler` | 有真实复用，保留可缩减重复的部分；规则不能继续要求每域500行接线。common handler不解释模糊status、更不能把deferred当成功。 |
| `production.py`扩大安装switch、tasks续投 | 改为从既有单一贡献catalog精确装配，kind/version/digest全匹配；transport读canonical frontier。删除按领域命名的专用wrapper与默认candidate安装分支；任务取消继续按§A.3传播、确认settlement及释放租约。 |
| dynamic successor builder、parent字段/migration、epoch/enqueue在途代码 | 按§A.3重写；父伪完成路径待撤回，prefix不得重放effect。schema变更只在首例所需唯一关系上保留；保留现有dirty字节供后续owner审阅，不视为已采纳完成。 |
| 新增测试约3038行、全部backend测试净增4219行 | 复用真实API、权限、取消、恢复见证；参数化重复fixture，删仅证明新增外壳存在的镜像测试。mixed PG未执行；局部PASS不代替总设计验证。 |

### A.5 执行工作线的接口责任

此表固定删除迁移需保持的语义、IO和原接口。存在当前删除族必须跨越的缺口时，接缝owner只在原模块作必要修复；已可复用者直接调用。表内缺口不自动授权全面实现，更不授权各包新建descriptor、runtime或安装switch；大范围构造需求按§4归属该删除族。

| 交接 | 权威输入 | 必须产出的typed结果/保持条件 | 现成symbols与当前删除族必要缺口 / owner |
| --- | --- | --- | --- |
| 声明→同步组合解释 | 原CoreToolSpec/领域typed函数、合法顺序与typed数据连线、调用者可信上下文；开放arguments仅在原schema边界校验 | 请求内组合的实际typed结果或原Failure/needs_approval/deferred；原同步HTTP envelope；顺序、数据依赖、失败短路；没有持久run、broker ACK或第二状态库 | 原`services/agent_core/contracts.py::CoreToolSpec`、`CoreToolRegistry.execute_tool`、`run_workflow`、`Then/MapOutput/ZipOrdered`与`NativeContributionRule`可复用；工作流退出第二runner若确需共同同步解释/端点适配，由接缝owner在原模块最小修复；consumer只给实际声明和响应适配。 |
| 声明/组合→耐久lowering与提交 | 同一领域声明、实际Program节点、精确payload值、RuntimeScope、可信actor、幂等键、当前授权与明确审批 | `ProgramSpec`、派生contract/catalog、精确`ValueRef+bytes`、原`ExecutionPlan`与事务提交返回的`run_id`；committed work身份/due从原仓储读取；不把提交当业务结果 | `build_operation_profiles`、`build_operation_catalog`、`dataclass_codec`、`compile_program`、`submit_compiled_program(...) -> str`、`PersistentOperationHandler`、`build_program_activation`。当前删除族确需的handler/codec/profile机械安装由接缝owner复用原规则作最小修复，不为普遍非默认实例建设完整新规则；领域包不新建submit wrapper。重复提交也必须重验currentgrant。 |
| 运行观察→continuation | 原根/parent/source step和Program身份、原`TraversalMaterialization`、精确序列ValueRef与元素顺序、completed prefix输出、未执行suffix、当前grant、根预算身份及已消费量 | 同scope且可追溯的子Program/Plan/leaf关系与原work；父仍RUNNING/WAITING；消费根预算、不重放prefix效果；取消/终态读回能穷尽所属children | 原`activate_plan_result`/`TraversalMaterialization`、`first_specimen_successor`、`RuntimeLifecycleRepository`和已有UoW；`resolve_business_root_run_id`为dirty未完成实现。活动父materializer资格、唯一lineage存储、根预算关联与聚合是检索/采集退出旧控制的具名缺口，由接缝owner只补当前实际需要；领域仅提交下一段合法组合/预算判据。 |
| 效果观察→业务readback | provider或broker原task/receipt身份及其实际输出、错误和外部状态；运行assignment的精确scope/ref | 已类型化SUCCESS/FAILURE/REVOKED/WAIT/UNKNOWN及真实输出/错误，区分ACK；读取无事实写入，持久发布只经原runtime终态UoW | `BrokerBusinessReadback.read_task`、`BatchBusinessWaitHandler`、`PostgresBatchTaskBusinessReadbackHandler`、原`ValueRepository`；当前删除族确需的根children等待/取消聚合缺口由接缝owner最小修复。控制投影只映射原API envelope，domain提供其合法终态判据。 |
| 控制命令→运行状态/只读投影 | 可信actor与当前grant、根/step/attempt身份、命令幂等键、真实失败/NOT_STARTED证明或reconcile结果 | cancel请求/settlement或明确拒绝；retry当前运行的合法attempt或终态后继引用；GET返回同一根业务状态与结果，永不制造运行事件 | `RuntimeLifecycleRepository.request_cancel`、原grant/idempotency/attempt仓储与journal projection；live retry及终态后继统一规则仍需首例/控制投影联验。公共owner持有控制状态机，控制投影持有HTTP/会话适配，domain不自行改FAILED→RUNNING。 |

这些接口共同保证单一权威声明、一个组合语义源、一个耐久运行事实源；持久序列化与开放JSON边界仍按§A.2执行。权限、领域预算和资源容量的不同语义不因共用IO表而合并。

### A.6 执行消费者的文件交接

以下集合分属不同窗口，domain native声明与原消费者同owner；公共catalog、composition、tasks、skill_runtime及派生同步由集成owner写；`S`公共文件及models/lifecycle由接缝owner写。具体tests先采用§6明确selector，只在原文件增加必要行为；额外文件须精确交接。

| 子窗口 | 文件集合与整体退出责任 |
| --- | --- |
| 工作流 | `A/services/workflow_graph/{__init__,runtime,store,compiler}.py`、`A/api/workflow_graph.py`、`A/services/agent_core/functorial/{run,native}.py`、`A/api/functorial.py`、`A/services/projects/workflow.py`、`A/api/project_customization.py`；`C/{workflow_common,workflow_legacy_dsl,workflow_native_contribution,workflow_slice_acceptance}.py`、`A/successor_runtime/assembly/workflow_assembly.py`、`src/mrw_functorial_kit/contributions/workflow.py`。退出服务驱动、SqlRunStore新写、定制handler循环与HTTP第二runner；模板/特殊节点/同步响应/历史读回保留 |
| 来源采集 | `A/services/ingest/url_pool.py`、`A/services/source_library/{resolver,runner}.py`、`A/services/agent_core/{project_tools,source_library_dispatch}.py`、`A/services/search/candidate_search.py`、`A/services/collect_runtime/{runtime,contracts}.py`、`A/composition/collect_runtime.py`；acquisition/source能力family与assembly先由owner列当前具体文件交集成再领写。退出URL/source线程池、第二plan/fold与C3专用重复装配；保留单项kernel/provider协议、Material writer及partial/order |
| 项目检索 | `A/services/project_retrieval/{service,execution,submission,formalization,proposals}.py`、`A/api/project_retrieval.py`；`C/{retrieval_candidate_native,retrieval_effect_native,retrieval_flow_native,search_retrieval_panel}.py`、`src/mrw_functorial_kit/contributions/retrieval.py`。退出query/followup通用推进和ProjectRetrievalRun新运行状态写权；保留方法/预算判断、proposal和no_claim/partial |
| 控制投影 | `A/api/{agent_batch,agent_sessions,process}.py`、`A/services/agent_batch/{dispatch,business_readback}.py`、`A/services/agent_sessions/{service,store}.py`；`C/{batch_task,batch_task_program,batch_task_interpreters,batch_task_native_contribution,batch_business}.py`、`A/successor_runtime/assembly/{batch_task_assembly,task_observation_assembly,projection_assembly}.py`、`A/successor_runtime/substrate/projections/agent_session.py`、`src/mrw_functorial_kit/contributions/{batch,task,projection}.py`。退出session任务引擎、通用task/event双写及死submitter；保留消息/批准/显式plan/host thread关联和真实readback |

同一个符号族的未列文件不默认授权；以真实consumer trace补齐明确列表后实施，不能只删表内几行便宣称整族退出。历史decoder只读接受明确旧身份，不允许失败后回退执行旧链。AST import仅作引用线索，TYPE_CHECKING/fixture/脚本调用要区分实际用途。

## 附录B：历史进度与证据

[原结构整理方案](MRW结构整理方案与分发包.md)保留旧64项、29/35和后续局部复核的历史记录；这些计数不再作为当前进度或分包依据。此前process、collect alias、JSON/HTML共核、replay取消、finiteN及HTTP batch隔离PG有局部证据；business readback在最后修改后未复验，mixed-operation PG仅收集未执行。需复用时沿原日志和未变依赖标注kept，不能记成本轮passed。

本文独立维护首阶段的分派与验收合同；已进入授权实施，进度见§8。原dirty代码按完整删除族收口，历史记录及无删除依据的测试资源保留，后续按真实依赖继续发放。

## 8. 当前执行状态（2026-10-07）

**首阶段状态：`LOCAL_COMPLETE_NOT_RELEASE_AUTHORITY`。** §7五项退出条件已按实际执行与未变依赖复用闭合，无本阶段未解决的具名blocker。最终结算为`integration/ci-group-resumption-2.json`（SHA256 `878665a345cd21b3ab5002595b7f0835354c2ad3e5322b70aea6fbc8edbf848c`），不是一次新的整套命令执行。原ci-pr-4与native coverage-2的exit1永久保留，后续分步与tail结果按真实归属替换受影响证据。共享工作树基线为`main@23468a40f4b2ad0b6055cdf089601668d58d6d52`；保留既有dirty，本地统一提交随本批次收口；未push或deploy。证据根为`/tmp/mrw-structure-20261007-w4uct7gr`，本节相对日志均以此为根。

最终`required-selector-summary-8.json`为1444 collected／ci-pr1013／coverage934／补集431。Search两文件首次纳入required共15节点，其中9为原节点、6为新增；无节点删除、共同marker/selector漂移或新补集。`capacity-resource-partition-2.json`核全量4736与native4731之差精确为原capacity5，无交、无额外移除，全部required节点在原全量中。core-business原runner还限定`tests/core_business`目录，不能把宽marker表达式计数当作其实际通过数。

| §7退出条件 | 最终结算 |
| --- | --- |
| 旧执行族与重复承载实际退出 | 旧loop3→0、运行writer组3→0、双写2→0；历史reader独立于旧执行器，source/workflow/control与共享重复承载的退出证据见本节已接受各包 |
| owner、能力、身份、权限与失败保持 | 原PG39全21项通过并以61输入零漂记kept；中文query/body、child→父settlement、九字段预算、真实topology_write、UNKNOWN/cancel及各原consumer见证已闭合。原direct HOST、frontend/browser与typed Runtime证据严格分域 |
| 源码净降与职责成本可核 | progress18 app307472（HEAD−29／dirty-start−6454），services130558（＋256／−1308）单列；tests186416（＋3007／−1212）。替换族161520（−550／−6688）；workflow＋999、retrieval＋3763、shared＋1594保留各自责任，source−5991不抹去这些增长。submission身份维护5→1，装配按真实声明与消费者位置核算，不按函数数推断 |
| 各族处置及未知面收口 | 所选删除族及尾包完成；resource/search、graph、LLM报告、reports/governance已按职责与消费者保留，非生产库存、历史与上游来源另账。无未调查族被伪记删除，无未执行项被计通过 |
| 原必要验证与交付合同 | unit/integration沿ci-pr-4保留未变部分，Search完整15项新执行替换原9项；core-business-5原exit0、backend-e2e-2原16项/exit0按未变依赖kept。七gate-6原291项、public types 0 errors、kit clean、前端与PG证据按未变依赖复用。combined-coverage-2原checker exit0：core409/409（100%）、other83146/119795（69.41%），阈值100/20不变 |

coverage当前去重执行归属为2657−9＋15＋capacity5＝2668 passed，4 skipped与186 subtests另账；这不是一次2668项新运行。原431补集仍为426原passed＋3 PG39 kept＋1 W04修后passed＋1 PG40补运行，不宣称一次431全新通过。root已逐SHA读回PG39的61、七gate的1057、capacity43的761输入零漂；CI变化精确为core2/e2e1/Search2及单行coverage探针，native2变化仅Search2。脚本反向恢复探针后SHA等原输入，已完成CI函数依赖不变。

全文件内部类型债和Ruff债保留，public-boundaries通过不等于全文件strict green。4个skip是live crawler、live host及两项由静态负向签名验证承接的用例，仍记skip；原HOST的1 passed只证明注册写作工具、approval/turn与canonical API/SQL读回。frontend14包含route mocks和Codex iframe mock shell，不构成新的typed Runtime/model/provider往返；service health/bootstrap仅证明进程与入口。调用/token及首次整组验收成本不完整，不报提速。内部类型治理、UI重设计、性能和新扩展仍属后置工作，本状态不建立发布权限。

下文保存各批次修复、失败及中间快照的原执行历史；其中“待执行／未完成”属于相应尝试当时状态，当前结论以本节顶部及最终aggregate为准。

PG36的20/1、PG37预算后topology失败及PG38的`TOPOLOGY_SEED_INVALID: source_registry rows are absent`保留为历史诊断。共同来源为Pure冻结表示丢失object/array身份，已由同一codec包在声明、持久Program decode、激活及source/workflow消费者完整修复；旧PG20项因公共输入变化未记kept，已由PG39全21项新执行取代。

### 整体结构与执行顺序

本阶段以“权威声明＋全部consumer＋旧职责删除＋保持见证”为完整工作包。原Program、领域typed对象、ValueRepository、RuntimeLifecycle及各领域writer分别拥有结构、对象合法性、精确值、运行事实和业务事实；派生安装、投影与读回沿原有贡献入口复用。

四个已确认的构造原则决定整批修复范围：控制顺序与值来源是同一Program的不同投影；相同ObjectType不推出相同语义角色，static occurrence及budget保留事实锚点，明确的template槽可以运输语义值；对象合法性由原typed constructor拥有，transition只检查identity、receipt及trust保持关系，并对合法复合闭合；结构哈希与typed payload codec是不同语义，ValueRef的bytes与内容身份只由其声明codec确定，跨表示必须显式运输，不独立重编码。currentgrant在effect前拒绝，claim与effect是两个实际边界；新测试把claim误等同effect的假设已裁定修正，不增加零attempt分配的调度政策。

先由共同规则owner打通当前真实案例，再同步全部同形consumer；局部见证通过后关闭同一批缺口。PG失败按共同声明、投影、关系或执行边界归因，一次修复该来源及受影响消费者，停止逐报错增加适配器、重复schema或新状态层。公共规则和全部消费者稳定后，由root集中执行相关PG，判定共同规则的替换保持；真实净减与职责收缩确认后，再执行最终未覆盖的必需selector及完整suite/coverage。PG诊断通过本身不构成阶段结项，失败只阻断真实依赖面。输入不变的旧结果只标记`kept`，已完成必要验证且没有新变化后停止扩测。

### 唯一当前状态矩阵

| 工作面 / 唯一owner | 最新实际结构与证据 | 有界缺口与下一完成条件 |
| --- | --- | --- |
| 共享控制与精确值 / astra_simplification_framework | `runtime.activation`统一控制树语义来源，S删除独立递归；Then运输前值，Zip的顺序与数据分别解释，Identity零step。typed publisher复用原同bytes/type/codec的Ref、provenance及write-intent，effect/child共同消费；只读observation替代重复settlement读取。原9file `control-projection-6.log` **144 passed、8 PG deselected**；追加codec组6passed与其重叠，不相加 | PG36已通过N2中文query/body与child→父settlement，原bytes drift已修复；PG38公共Pure形状丢失已同包修复，PG39全21项通过。裸Identity Decide及无根输入Map(Identity)继续明确拒绝 |
| static事实与semantic输入 / 集成 | handler所有原static refs始终走原exact reader。workflow原occurrence及candidate followup模板保持static；CandidateWork/Control与URL明确选择semantic payload视图，其他budget refs保持原样。原candidate validator保留route/round/budget/provider及结果上限约束 | 新通用handler见证覆盖异workflow_id、异cursor拒绝及真实join消费者的合法cursor1→2；`payload-roles-3.log` **6 passed**。相关5file原消费者`payload-roles-group-2.log` **86 passed / 1.46s**，公共类型0error；PG35实际消费者通过 |
| 检索复合保持 / retrieval_runtime_retirement | API/skill/Rapid进入原Program/Runtime，review→URL→body→formalize→revalidate由原领域leaf执行。PG36已通过candidate→revalidated→父settlement，PG37已完成两次candidate/search/URL/formalize及完整九字段预算 | 同一validator已修复合法复合的identity/receipt/trust保持，shape只由原constructor拥有；37passed及strict0（`/tmp/mrw-retrieval-pure2-pg34-law-20261007-62911.log`）。B1/B2已同步共享单口且pure48/strict0通过；PG39最终topology_write completed原期待已通过，Ret领域判据保持，Runtime与领域结果分别读回 |
| pre-effect与claim / runtime_contraction_seams；PG文件集成 | 原Node拒绝不再误入IN_FLIGHT-only commit。PG35已真实claim1、effect前AUTHORITY_GRANT_INVALID，executed/committed均false；完成prefix不重放 | 修正新增PG断言：唯一NOT_STARTED attempt、work/step CLAIMED count1、无receipt/EffectStarted、原lease及RECONCILE assignment保留，预算按实际EffectStarted仍0。PG35新增完整断言已PASS，不声称零attempt allocation |
| Traverse失败、UNKNOWN与取消 / 集成＋原控制owner | 原journal绑定位置/source/materialization/root budget，COMPLETED连续前缀才释放suffix；真实FAILED用原active_child.v2因果事件，无假step/attempt；UNKNOWN保持WAIT，suffix取消沿原owner。领域结果只接受COMPLETED，真实typed gap仍为COMPLETED输出 | PG35双worker、真实FAILED、UNKNOWN及取消见证已PASS。原v1相邻EffectFailed因果检查保留。共享输入变化后的受影响重验已纳入PG39全21项通过 |
| 安装与读回 / 集成 | 原领域catalog拥有定义全集，`build_program_activation`按实际child Program派生deployment，worker保exact binding。Graph/retrieval/batch进入`submit_installed_program`；API读原run/steps/events/typed output | 检索正式单口已同步，5处submission身份构造归一到原入口；装配职责按真实维护输入核算，不按函数数量推定成本。无新增读回store或事实writer |
| workflow / workflow_runtime_retirement | 旧SqlRunStore与独立loop退出，facade使用原Program/Runtime及exact输出；PG35真实Graph两节点与mixed均PASS | static occurrence补修由集成统一维护；节点kind及builder验证重复仅按真实权威与消费者判断，不删除非法topology拒绝 |
| source / source_runtime_retirement＋source_retirement_finish | C3重复装配、旧URL任务及artifact/event双写退出；保留原同步CollectResult，4个service消费者复用原run_collect，app/celery安装adapter。原尾包25＋17＋36及后续6项局部通过，strict0 | 最新291 gate已覆盖声明尾项；局部source删除与retrieval/shared增长独立计账，不能相互抵销责任 |
| control/batch / control_runtime_retirement＋集成 | session task.retry与batch retry/lease旧生产入口退出；provider/process retry保留。batch为dispatch→business_wait，按Plan顺序读真实业务结果，PG35整组通过。C2三项test-only生产builder已删除，fixture组合原atom/ACK merges，`c2-contraction-2.log`25passed/8PG deselected | 原route15、S依赖17、cancel局部7为已执行局部证据；本轮不增加第二业务完成owner |
| HOST / host_delivery_owner | 本机正式入口approval consumed、turn completed、doc1及canonical API/SQL读回，**1 passed / 21.98s**，`/tmp/mrw-local-actor-live-20261007-073117.log`。clean浏览器bootstrap200、错key/forwarded401、payload actor422；87passed/9subtests及authorization24passed，既有build/E2E/TS fixture/tsc仅留成功工具输出，缺日志/input manifest，不能记最终kept | 原静态/build＋五fixture41/tsc补验、服务重启及frontend14已完成，证据范围分别保留；显式local-single-user、loopback/private server key及RequestActorContext边界保留 |
| 页面／项目／数据 | 页面baselineInventory退出，manifest拥有placement；项目身份exact/prefix配方原25及typecheck0；数据去重复身份/引用转发，原unit27、API9、topology PG6及V-doc9/8subtests通过 | 既有局部结果未重复执行。页面生产−74/checker−39，项目−4，数据−18与集成Session注解+2分列；静态通过不冒充浏览器，全文件strict诊断仍保留 |
| 规则验证 / 集成 | `payload-roles-gates-1.log` **291 passed / exit0**；`payload-roles-public-boundaries-2.log` **0 errors**；Ruff F通过。原sync/check已PASS，原16pilot134passed | 当前公共规则门禁已统一复验。public-boundaries通过不代表全文件strict通过；此前S＋activation定向strict仍有64项诊断 |
| 必需覆盖与交付 / root＋platform_delivery_scope | 原27项job/name/needs及not-flaky差异保留，最终inventory8为1444／1013／934／431；全量4736＝native4731＋原capacity5，原selector无漂移 | aggregate2按Search15替换旧9、其他未变kept闭合CI；core5/e2e2真实exit0，combined2原100/20 checker exit0。补集431原分账与4skip/186subtests分列，原ci4/native2 exit1不反写；首阶段LOCAL_COMPLETE_NOT_RELEASE_AUTHORITY |

### 原suite暴露的审计checker退役同步

`integration/logs/final-ci-pr-1.log`与`integration/final-ci-pr-1-result.json`保留原collection失败，exit2、1752输入无漂移、qualification表0→0，suite原两表不变。失败属于`check_graph_editing_audit_durability.py`继续引用旧`InMemoryRunStore`及persist/append合同；不能把尚未运行的unit/integration/core/e2e记为失败或通过。

root分派`retired_graph_audit_checker`（GLM5.3/high），独占原checker与`unit/test_graph_editing_audit_durability_unittest.py`，pure1；Astra仅只读审核和维护本节。当前生产合同为`WorkflowGraphHandoffStore.build`返回request-local、`durable=False`，`HistoricalWorkflowRunReader`只读已有历史，list/replay无追加且API要求`source=historical`和project scope。同步范围包括本地build无写、固定历史events只读及事件/scope保持见证，并保留curated audit、conflict rollback及live evidence failclosed。历史fixture不构成新的持久写入或live DB durability；不恢复旧store或新增兼容writer。原PG39和已闭合必需补集保持其原执行归属，只有实际受checker/test变化影响的collection和suite由root恢复。

checker首次READY两文件hash经Astra核对一致，原`/tmp/mrw-graph-audit-retired-consumer-20261007-attempt-2.log`为8 passed／0.69s／exit0。nested live证据字段改为`historical_handoff_readback_from_persistent_storage`，当前代码消费者仅checker与其原unit，均已同步；旧字段未保留兼容。只读审核发现一项保持见证缺口：event_types和两个audit断言仍读fixture输入，而非reader实际输出，故首次8项PASS未被当作该语义读回的完成证据。原owner已返工到`replayed.events/result`与`listed.items`实际输出，events/result全量对固定输入，并保留snapshot前后不变；新增丢replay事件、丢persisted audit两项负向见证。第二READY的两个hash与实际文件一致，`/tmp/mrw-graph-audit-retired-consumer-20261007-pure2-attempt-1.log`为10 passed／0.71s／exit0，Astra仅收口该差分，checker具名缺口已关闭，pure2释放；未扩审生产或原PG。

无依赖原`final-core-business-1`已实际exit1，971输入无漂移，四项失败；证据`integration/final-core-business-1-result.json`及`integration/logs/final-core-business-1.log`。其中两项stats失败映射共因是Celery/DB读回helper吞异常为`[]`，使后端失败成为200空统计，绕过原500 INTERNAL_ERROR；另两项涉及旧ORM fake和list/stats/history三次DB读回与两次SessionLocal fixture不符。root另分原process包处理共享失败语义与现行fixture，保留原observation投影、项目过滤和身份去重，不能恢复旧writer或按单个报错造fallback。qualification表仍0→0，suite库此次实际新增13个public表，root持有其精确恢复窗口；这不是PG39输入或证据失效。此处未核得该日志完整pass汇总，不推算passed数量，四项失败未闭合前不声明core-business通过。root已分派GLM5.3/high原process包，独占`app/api/process.py`与三份core测试，pure1；checker实际读回见证返工已结束并释放pure2。`integration/suite-db-restore-1.json`记录root已确认13个新增public表全空、其它连接0、FK0后仅DROP指定表且无CASCADE，保留原topology两空表，qualification仍空。

### 阶段退出的具名缺口结算

process权威dispatch已核为`api/resource_pool.py:670-677`通过kwargs传`project_key`；原位置args测试fixture随该正式调用同步，不新建task registry，不放宽unknown项目拒绝或身份去重。该包已交WRITE_READY并静止；Astra核四文件SHA与回传一致，Celery/DB共享loader移除吞异常返回空集，正常inspect None与DB空继续合法，四公共入口的失败/合法空见证及原项目/身份断言保留。root实际回传原四node4 pass、新失败/空consumer10 pass／2 deselected、直接readback12 pass；对应tmp日志仅应用logging，测试计数沿原执行工具回传，不虚构其自含pytest summary。owned Ruff F/diff0；全process strict166诊断、完整Ruff56规则债保留，最后返回注解修正未重跑，不宣称全文件静态green。

checker/process、formal/source及core/e2e/search尾包、前端编译补验、服务重启与原E2E均已收口；最终inventory8、capacity分区2、aggregate2和progress18已核一致，本阶段具名缺口为空。Search15新结果替换其旧9节点，其余未变CI证据保原归属；原ci-pr-4/native2 exit1不反写。七gate/public-boundaries、PG39及capacity按各自未变输入复用，不触发额外PG、模型或全量重跑。详细执行身份、skip和未完成的后置事项见本节顶部及最终aggregate。

HOST原owner已完成有界证据查找：本轮frontend build/E2E及WebUI五fixture Vitest/tsc仅留原工具成功输出，未形成可核日志和输入manifest，旧失败日志不能记kept。root据此分派`frontend_final_validation`（GLM Flash/low），只补原静态/build、五fixture41及tsc，并记录前后输入hash；E2E在root完成集成、服务最小重启并释放PG窗口后执行，不发起外部模型调用。此为已确认的证据缺口收口，不新加验证产品或研究。已交COMPILE_READY：`frontend-final/validation-summary.txt`及三attempt状态/原日志保留首次cwd错误与pnpm隐式install/catalog失败；改用已安装native runner，未安装或改源码。最终topology34／manifest34／placement18，typed-fetch6／handoff1，build2978 modules，WebUI五文件41 tests，tsc exit0。1242文件before/after路径差0、hash漂0，Astra另对当前1242文件逐项SHA核验0 mismatch；仅编译/静态/fixture通过，未E2E。typed-fetch原报告继续`live_closure_claimed=false`及三个typed-knowledge live缺项，不据静态通过伪关，也不新增为本阶段provider门禁。delivery的`pytest-focused-2.log`为37 passed／1.93s，`selector-readback.log`保留原五入口marker表达式，`dev-check.log`为clean；后端checker/process修复不自行使这些脚本行为证据失效，完整suite执行义务另列。

宿主真实执行selector固定为`B/integration/test_live_host_material_chain.py::test_codex_oauth_model_registered_tool_persists_and_reads_back_material`，只有`MRW_LIVE_HOST_MATERIAL_CHAIN=1`才执行。其原1 pass／21.98s证明注册工具到写作事务及canonical API/SQL读回，不含新Program或process API，未变依赖下保留原结果；最终suite中的默认skip不能当新live通过，也不撤销原实际运行。root已接受该原归属，后续只做服务最小重启与bootstrap/静态当前输入核查，不重复模型调用，不将其称为typed Runtime实际往返；HOST原owner只读提供UI证据及launchd labels。`test_topology_document_unification.py`六项与demo factory六项在collection3未被ci-pr/coverage选中，沿已闭合必需补集结算；`test_writing_api_unittest.py`九项走integration/coverage，API mock与实际DB见证继续分别记录。不增加未要求的provider验证。

最新覆盖引用`integration/required-selector-summary-4.json`：1296 collected／ci-pr865／coverage841，431补集不变，added22、removed0、marks/selector变化0、新补集0、external0、输入无漂移。新增是process consistency12与checker10两个先前未dirty文件首次纳入当前清单；不把新增清单数称为新补集执行，也不重复已闭合431。ci-pr-2终态exit1，仅unit执行，14项失败按下表收口；后续integration/core/e2e未运行。

### ci-pr-2原unit失败的最小完整包

`integration/logs/final-ci-pr-2.log`保留真实14项失败；1752输入无漂移，只有unit执行，未把runner未进入的integration/core/e2e记通过或失败。root分派formal四测试文件与source两测试文件两个独立包，各守pure1/2；没有证据支持前不修改运行producer。

| 失败组 | 归因与允许收口边界 |
| --- | --- |
| I1 rollback 1项 | 现行cells已27→25；同步当前计数与`ALL_I1_CELLS`精确集合，保留binding/route/gap断言及30份冻结spec历史验证 |
| C3 fragment generator 5项 | 原专属文件实际有6例：5个依赖已删除generator的重建测试失败，另1个只检查root副本不存在/topic存在。Astra核当前family集合仅C9，C3已列retired history；允许整文件退役、collection精确removed6，不将5失败记PASS。冻结C3.json、shared history固定SHA/2cells/authority/content_digest检查及aggregate的topic权威路径保留；不恢复generator或影子fixture平台 |
| Traversal typed guard 2项 | 同一坏codec和byte_size已由更早的typed value guard拒绝，分别为`typed value codec identity drift`与`typed value exact bytes binding drift`；原坏输入、ActivationError及精确拒绝身份保持，只同步过时错误字符串 |
| macro environment 1项 | 原测试自建registry漏传`read_run`必填invocation_context；沿正式RequestActorContext与actor_id修测试桥和service mock，验证trusted project/run/actor运输，不放宽scope或恢复无context读口 |
| source handler cluster 5项 | 旧ThreadPoolExecutor/start_job patch引用已退役loop/writer；现行一次unified_search接完整query_terms，旧fake只取首term。同步完整q fake与原run_item_payload consumer，保留first-seen去重、全部terms、预算和状态传播；不靠降低call_count/候选断言或恢复旧executor/job writer通过 |

两尾包已交READY并静止。Astra核formal三现存文件与source两测试文件共五SHA均与回传一致，C3专属文件已删除；`/tmp/mrw-formal-retired-consumer-20261007.ZRjAYz/attempt-1.log`为35 passed／2.68s，`c3-history-attempt-2.log`为2 passed／0.08s；C3 removed6不记passes。`/tmp/mrw-source-handler-consumer-tail-pure2-20261007/logs/attempt-1.log`为13 passed／1.49s。formal保持当前25项顺序与identity、typed坏输入精确拒绝、verified host actor运输；source保持完整terms/预算/first-seen、失败不进入路由及adapter结果状态，无生产改动。两具名包已局部闭合；专属测试退役与现役消费者验证分别记账。源码未变的PG39、前端1242输入结果和原直接writing live结果不因这批测试同步而全体失效，最终cost及collection仍跟踪实际文件变化。

### 当前服务与浏览器保持证据

`integration/service-current-input-restart-1.json`记录root按原launchd labels重启backend/WebUI/frontend，8000/8172/5173监听PID均替换，原health/bootstrap/首页各HTTP200；仅证明当前服务进程与公开入口，不证明provider turn或typed Runtime业务完成。fresh public-boundaries5为0 errors／exit0，kit-check1 clean／exit0；原全文件strict/Ruff债不因此消失。

`frontend-e2e/e2e-validation-summary.txt`及原log记录native Playwright、单worker、原三个spec共14 passed／33.4s／exit0：codex-entry-retirement9、codex-writing-crossflow2、business-line-browser-actions3。frontend297/backend app764两组before/after hash逐行一致，8000:25653、8172:25678、5173:25738前后PID一致，窗口已释放。entry及business rail包含route mocks；writing crossflow实际创建/读回writing API并在工作台显示，但Codex iframe为mock shell。因此本证据是浏览器及写作API保持，不能写成新模型执行或typed Runtime实际往返。原1 pass live registered writing结果与PG39分列，不重复provider调用。

### ci-pr-3 integration局部收口与capacity资源分区

`integration/logs/final-ci-pr-3.log`及`integration/final-ci-pr-3-result.json`为原runner终态exit1：unit已通过，integration4 failed＋3 setup errors，core/e2e未执行；1751输入无漂移，qualification表0→0，suite实际新增原同13个public表。source两失败与batch两项403随后分别由原两包同步现役consumer，均只改指定integration测试。source最终日志`/tmp/mrw-source-int-provider-recovery-final-122252-41612/logs/final.log`为2 passed／0.64s；batch为root执行回传39 passed／Ruff F0，未虚构其日志路径。Astra核四文件hash及差分：source保留原item/channels/project/override参数、legacy结果、terminal合同及provider metadata；batch经真实auth middleware取得verified actor并保持run/project/item身份，未授权请求独立403，授权缺project仍400。原历史reader实际承接list/replay，URL明确`source=historical`并断言`read_only`与结果身份；该文件未重复snapshot前后断言，沿未变生产reader复用原checker10的实际events/result/list全内容、snapshot不变及两个负向见证。两个具名integration包已闭合，无旧loop/writer恢复。局部PASS不代替完整ci-pr-4，已通过unit保留原执行归属。

capacity三个setup errors均发生于`p0d_capacity_fixture._require_local_test_url`拒绝当前Docker TCP URL，未执行领域断言。三项保留为现行必要验证：`test_postgres_guard_proves_non_superuser_unix_socket_and_exact_nodes`验证真实非superuser/Unix socket与精确双node；`test_two_node_capacity_baseline_is_measured_without_mutating_work_items`沿原due_claim测量公平份额、时延并核work_items前后完全一致；`test_generator_writes_only_after_live_guard_and_digest_readback`沿现役`generate_successor_capacity_envelope`只在live guard后写出并读回digest。它们消费仍在的runtime capacity与Postgres observer，不属于已退役C3 generator，不能随历史清理删除。

root负责有界恢复真实Linux Python＋PostgreSQL Unix socket环境，执行原三selector；不改guard、不伪socket、不skip。fixture拒绝现有public表和冲突role/schema；observer还要求current/session role精确、非superuser、server/client inet地址均None、仅fixture scope及exact双node。原suite的topology schema也不满足observer专属范围，须用独立fresh test DB。此前三项setup errors是明确环境不匹配，不记domain失败。root已用现有`ops-backend` Linux image直连同PG容器真实`/proc/1/root/run/postgresql` Unix socket，原guard/fixture不变；复制已有pytest9.0.3及纯Python依赖只读挂载，无安装新依赖、无TCP代理。capacity41因缺原py shim在pytest前失败，保原日志；加原shim后的`capacity-linux/capacity42-result.json`及`capacity42-attempt-1.log`记录完整原file5 passed／1.31s／exit0（3真实PG＋2pure），7输入无漂移，专属`mrw_capacity_test_20261007_r42`事后tables0/measurement role0；原test实际断言inet两端None与非super。容量环境缺口已关闭，不新增性能研究路线。PG39和未变局部结果不因它全体重跑。

容量资源分区由原runner参数完成：native公共TCP运行仅追加`--ignore=tests/successor_runtime/test_p0d_capacity_postgres.py`，原5节点沿独立Unix socket原runner结算；逐node核原必需集合等于native所选与capacity5的无交并集，不视为skip、不降门禁，ci四组照常运行。Astra只读裁定此分区保留义务，不新建调度器。`integration/capacity-resource-partition-1.json`已核原完整4730与native4725之差精确为capacity5，集合无交且无其他移除，各marker/selector保持。coverage采集另由`capacity-linux/capacity43-result.json`及`capacity43-attempt-1.log`实际完成：同5node为5 passed／2.25s／exit0，761输入无漂移，`--source=app` line coverage，专属DB事后tables0/measurement roles0。此为原容量测试与原始coverage采集通过，整体100/20尚未通过。保留native/Linux原数据，仅将Linux路径有向映射到当前同字节源码后combine，保持原source/core路径与line模式并核无重复或未映射app路径，再跑原checker。native runner先调用checker的原退出码保留，合并checker结果另列。

source/batch integration恢复原已派两包遇GLM5.3与Flash实际429，root已改路由至当前可用DeepSeek；范围仍限指定integration测试，未获生产写面，也不虚报沿用原GLM路线。

collection5历史账目以`integration/required-selector-summary-5.json`为准：1333／902／878／431；最新`integration/required-selector-summary-6.json`为1374／943／919／431，新纳入四份integration文件共41节点，marks/selector变化0、新/移除补集0、external0；C3六项退役在此前required inventory之外另记，Traversal两项param-id替换明确记录，不能由总数反推测试执行。

### ci-pr-4的core fixture尾项与原分步续跑

`integration/final-ci-pr-4-result.json`及原log记录exit1、1751输入无漂移：unit/integration已通过；core两项`test_process_stats_success_returns_envelope`与`test_process_stats_success_contract`为500而非200，e2e尚未执行。两项正常mocked合同只提供Celery inspect，遗漏合法空DB的`SessionLocal` fixture；生产process原loader已正确传播`etl_job_runs`缺表，不能为测试恢复吞异常或改变生产。root分派`process_core_fixture_tail`（GLM Flash），仅写`test_admin_dashboard_process_core_contract.py`、`test_api_group_b_core_contract.py`，复用原DB-readback fixture语义；最终READY的两文件SHA与回传一致，`/tmp/mrw-process-core-tail-20261007/pytest.log`为51 passed／2.72s；Astra只读差分确认新增局部`SessionLocal` fake经`execute().scalars().all()`给出合法空DB，正常inspect仍200、异常inspect仍500，两组原断言保留，无生产或共享fixture改动。该具名局部缺口已闭合，root已发起原`final-core-business-5`，不能以局部51项替代它。

Astra只读核`integration/all-selector-coverage-native1.json`：两份owned文件共51节点，unit/integration/e2e/coverage选择均0，core_business/ci_pr选择各51；两失败均`contract`＋`mocked`。原`test-standardize.sh core-business`及`e2e`与ci-pr内部对应命令一致。按19号文档既有“重试从受影响步骤继续”，本次实际修改仅两份局部fixture，生产/共享fixture/selector不变，因此ci-pr-4 unit/integration保原执行归属kept，修后从原core/e2e分步入口继续。ci-pr-4原exit1和失败日志保留，后续aggregate仅汇总真实组级结果，不能写成一条新ci-pr整命令exit0。coverage沿原完整入口另跑，仅保留已核精确capacity资源分区；没有新增runner、审批或全量重跑义务。

`integration/final-dev-gates-5-result.json`及`integration/logs/final-dev-gates-5.log`记录原七gate本轮新执行291 passed／8.65s／exit0，1057输入无漂移，无PG/provider。两个core文件不在其app/gate inputs内，本次纯fixture变化不要求重跑该gate；原全文件strict/Ruff债与尚未完成的core/e2e/coverage分别保留。生产progress16仍净−29，tests186201尚未包含本尾包新增46行，最终progress由root集中刷新。

### core/e2e分步终态与coverage入口修复

`integration/final-core-business-5-result.json`实际exit0、1751输入无漂移。原backend-e2e-1为1 failed／15 passed，同样是process正常mock缺合法空DB fixture；独立owner只修改`test_runtime_observability_smoke_e2e.py`，Astra核最终SHA与回传一致，差分仅局部`SessionLocal`空结果fake及patch，原HTTP200、request/project context断言不变，无生产改动。`integration/final-backend-e2e-2-result.json`及原log为16 passed／5.27s／exit0，1751输入无漂移。此为backend e2e，和先前frontend Playwright14及HOST真实模型1项分列。ci-pr-4原整命令exit1保留，组级收口沿unit/integration原归属及后续core/e2e实际结果汇总。

`integration/required-selector-summary-7.json`为1429 collected／ci-pr998／coverage919／补集431；新增core51与e2e4首次进入当前清单，removed0、selector变化0、external0、新/移除补集0，当前required节点与原完整collection相符。`integration/production-count-progress-17.json`为app307472（HEAD−29／dirty−6454）、tests186270（＋2861／−1358）；progress16是core/e2e补修前历史数。

`integration/final-coverage-1-result.json`保留exit2、1751输入无漂移；日志显示插件探针报missing，未执行测试及coverage checker。root实际确认已安装pytest_cov7.1.0／coverage7.16.2，pytest help exit0含`--cov`，当前具名候选为`set -o pipefail`下`grep -q`提前结束导致上游SIGPIPE。独立owner仅修`run_pytest_coverage`内部探针，原pytest命令、selector、coverage source及100/20保持；当前尚待修复READY和真实coverage执行。ci-pr调用的prepare_env、run_pytest_marker、resolve_python_exec及core/e2e分支不调用该函数，因此严格限该探针的修复不使已完成CI组失效；依实际函数依赖复用，不以整个脚本hash改变重跑全部CI。此处不把SIGPIPE候选写成已验证终因，不新增框架或验证义务。

### coverage-2真实结果与search边界尾项

探针修复仅将`grep -q -- "--cov"`改为完整消费输出的`grep -- "--cov" >/dev/null`；`/tmp/mrw-coverage-probe-tail-20261007/probe.log`记录旧PIPESTATUS为1/0、新为0/0，并保留无cov拒绝和producer真实非零失败。`integration/coverage-probe-dependency-readback-1.json`核单行反向还原后SHA精确等ci-pr-4输入，原CI调用函数未变。原`ci-group-resumption-1.json`因此据实结算当时四组义务，PG39的61输入现场零漂并保原21项kept。该aggregate是search尾包前快照，不能在新改unit/integration文件后直接照搬“无changed inputs”。原七gate-6由root回传291 passed／7.97s、1057输入无漂移。

`integration/final-coverage-2-result.json`与原log为exit1、1751输入无漂移：实际2657 passed／4 skipped／186 subtests passed（197.24s）；native checker core393/409（96.09%）、other69.19%。`integration/combined-coverage-1-result.json`保留native2与capacity43原始data，758个app输入同字节，Linux路径仅映射到原canonical app根，749唯一路径、无未映射或重复路径，逐line union已核；combined checker仍exit1，core393/409（96.09%）、other69.41%。不能把测试通过或数据合并写成coverage门禁通过。

未覆盖16行均为`app/api/search.py`：102、109、126、139、143、145、153、162、163、181、230、290、291、293、367、428。独立owner仅拥有原`integration/test_search_api_unittest.py`与`unit/test_search_endpoint_document_query_contract_unittest.py`，先复用现有case，再补公开API的空/typed有效输入、run-id错误、fallback/source/readback及去重等真实合同见证；不改app、threshold、marker或原断言，不靠伪造执行行数。两个owned完整文件须实际重跑并采app line coverage；局部全文件fixture如变化由该完整文件验证覆盖。其余未变用例保持native2原执行身份，不重跑2657整组。

root最终inventory8明确新增node差集及原unit/integration/coverage选择归属；若选择范围意外外溢，仅补实际新增义务。最终aggregate以tail新运行替换这两文件的旧结果，其余保持原kept，ci-pr-4与native2的整命令exit1不反写。native2＋capacity43＋tail沿同字节源码合并原line data后，再由原100/20 checker实际新退出决定是否通过；当前tail和最终门禁未完成，不mark complete或提交。

### search尾包接受与合并coverage门禁通过

最终两文件SHA与owner回传一致；Astra只读接受五个公开API新方法、原overlong错误用例扩展和一个聚合防御unit。公开用例沿原typed builder、writer validator、真实JSONL reader及GET返回的envelope，覆盖诊断backend补全、同合法hit重复时source_refs唯一、fallback来源及freshness/count回退；没有新增生产、marker或fixture框架。四个正常合法公开链不可达的空默认单独标明为防御unit，不能冒充public场景；其中text-list不可达由known_limitations唯一producer恒list保证，其余由typed集合/identity/source要求保证。

`/tmp/mrw-search-coverage-tail-20261007/final-pytest.log`为完整两文件15 passed／19.00s；`final-readback.json`记录764个app输入零漂。最终`search-tail.coverage`与`final-search-tail.coverage`SHA相同，并与combined2使用的tail raw SHA一致，旧24项初稿日志不代表接受后的最终测试集合。

`integration/combined-coverage-2-result.json`及`integration/logs/combined-coverage-thresholds-2.log`为原checker exit0：core409/409（100.00%），other83146/119795（69.41%），阈值仍100/20。native2、capacity43及tail原data保留；758个同字节app输入、749唯一canonical paths，Linux映射仅原app根，无未映射/重复路径，line union已核，原native2 exit1保留。此门禁已通过；后续inventory8、全node差集/容量分区2、替换Search旧file归属的aggregate2及cost18均已完成，只读核对与§7五项退出条件相符。当前状态已在本节顶部结算，本地统一提交随本批次收口；未push或deploy。

### 资源、分析与治理的有界处置

原调查因429未交付，现由`remaining_resource_governance_audit`（GLM Flash/low）补完只读调查，Astra核原挂载及核心writer/reader后裁定四族保留，生产0改动。本处是§3最后一族与§7对应未决面的处置结果；不重新迁移已完成source族，不把静态存在当作live运行通过。

| 完整族 | 权威、正式consumer与效果 | 本阶段处置 |
| --- | --- | --- |
| resource_pool / unified_search | `models/entities.py`的project/shared URL与site-entry实体；`resource_pool.extract.append_url`和site-entry upsert拥有资源写入；API `/resource_pool`、source_library resolver与ingest真实消费；unified_search选择写pool并复用原`run_collect` | 保留资源身份、可见性及候选发现；不以材料/搜索相邻概念判同事实重复，无新增删除写面 |
| graph模型 | `GraphNodeRecord/GraphNodeAliasRecord/GraphEdgeRecord`为材料派生图查询投影；`GraphNodeWriter.persist_graph_nodes`与`GraphNodeReader.load_graph`在`document_admin.py:1362/1390`消费，report source enrichment亦读取 | 保留现行投影及其查询/更新职责，不认领typed knowledge/topology事实；未发现本批可直接删除的同义承载 |
| LLM报告 | `/llm-report/generate`调用原generator，export artifact、one-time token claim、audit与quality trends有独立合同；原同步请求的`EtlJobRun`记录存在于API，前端generate/export/quality入口真实消费 | 保留报告生成与交付事实，不并入普通policy HTML/CSV报告，不增加第二运行owner |
| reports / governance | `/reports`只读Document policy并生成HTML/CSV，缺summary时可调用原provider；`/governance/cleanup`沿retention显式删除旧Document/metric/price/job，aggregator sync写聚合表及cursor | 保留显式报告/运维效果；governance跨owner删除是既有合同边界，本批未授权替代其语义，不无据删除 |

四组API分别在`api/__init__.py:55/71/74/77`正式挂载。调查仅rg/sed和直接符号追踪，未执行pytest、DB、provider或gate；reports更广的外部consumer未核实，但正式挂载已明确，不以未知外部使用为无用。必要验证随本阶段受影响输入执行；本只读保留处置不新建测试任务。

### 两条非runtime保持见证与宿主证据边界

现有日志保留：`slot2/logs/data-contraction-v3.log`为27 passed，`slot2/logs/writing-doc-1.log`为18 passed／8 subtests（写作服务与API两组），`slot1/logs/v-extension-final-5.log`为25 passed，`pg/logs/data-topology-1.log`为6 passed。拓扑原PG确认Material is Document、同一doc_id、跨project拒绝、原Document writer更新后拓扑读取新字段以及历史/provenance保持；写作unit验证citation alias、版本/ETag，API的mock service结果不能提升为完整数据库写作旅程。demo原factory见证覆盖default/exact、embodied前缀、最长前缀、trial独立身份及adapter，不宣称完成未支持的全新扩展自动化。

`test_live_host_material_chain.py`及`/tmp/mrw-local-actor-live-20261007-073117.log`验证真实模型沿注册`writing.document.create/read`、唯一完成事件、批准consumed、session/thread映射、canonical API与SQL正文/provenance一致；其handler直接调用原写作事务，未穿过本次Program/Pure/source codec。此证据属于原输入的完整宿主往返，不由health200替代，也不扩大成新Program行为通过。上述日志未附足够完整输入manifest，故本轮不据PASS尾行认证新候选或自动记kept；root最终required/suite按实际受影响输入覆盖必要缺口。

### 非生产库存与来源分账

`nonproduction_cost_audit`（GLM Flash/low）已交唯一tmp统计`integration/nonproduction-cost-breakdown-1.json`，SHA256 `ca3dcef6080298e3521f5253d52a78ed9915c745b6a45a49e3ffcf690866cf1f`，实际9,177,716 bytes；Astra只读核14,836个唯一file_records及各bucket文件/字节/LOC加总一致。位置独占分类为vendor1,205／101,551行，非vendor生成物6／3,533，config44／8,745，docs位置712／127,811，historical位置10,433／7,944,469。生成物union759／20,281及exact-byte snapshots7,574／4,005,962均属重叠视图，不与位置分类相加；全部口径与路径见[框架§5.1](MRW精简框架.md#51-分类账而非目录排行榜)。

本次将当前体积与来源缺口分开收口：docs位置含541个ARCHIVE路径，current/history语义分类仍PARTIAL；pinned upstream `44ad73a9…`本地blob MISSING，故上游patch增删行仍unknown，README的16＋8文件不当作LOC。当前dirty vendor相对本地HEAD为15触及文件／全文件6,754行／增451删103，与导入patch口径不同。原生成来源和现sync/check入口已记录，统计不运行生成或测试，也不重开历史清理。本有限调查已收束，具名未知保留；本阶段实际生产净收支仍归root最终快照。

### 公共编码边界裁定（本地实施完成，PG39通过）

PG35暴露的共同来源是同一声明codec被两个encoder解释。`language.checksum`沿`research.codec`保留Unicode并按UTF-16键序编码；`capabilities.checksum.canonical_json`使用ASCII转义与普通键序。ASCII例子不能证明二者保持。实际支持域还须覆盖中文query/body/gap、非BMP键与字符、有限数值、布尔值和空序列；domain `_scrub`允许的bytes/键转换与language拒绝的值域差异亦不能当作无损运输。

| 生产→保存→消费边界 | 当前唯一声明及真实行为 | 同一完整包的裁定 |
| --- | --- | --- |
| Program/Plan、shape、element identity | `language.program/plan`及`research.codec`拥有AST、plan、`traversal_element_digests`与shape摘要 | 结构摘要不等于领域payload的bytes摘要；形状缺口后采用下述AST v2，其他摘要规则保留 |
| 领域payload→Effect→typed result | 原`PayloadCodec`负责DTO↔JSON值；candidate/work/control、URL、workflow、batch的原生产者及`PersistentOperationHandler`使用capabilities编码 | 沿原领域声明选择同一编码；静态occurrence/budget仍exact验证，不能以另一canonical重新认领同codec |
| Pure/Map/Zip新值→ValueMaterialization | `_derive_value`目前统一用language编码，却给结果填写`step.output_type.codec_id`，领域输出因此可能不合法 | 新值按完整ObjectType及声明codec调用安装的现有encoder；编码同时决定exact bytes、size和content digest。结构provenance/依赖摘要仍由原language规则计算 |
| Id／preserves-value Map／Then／Decide运输 | 原Ref可保留，但BoundStepValue/ProgramInput只有semantic value，exact bytes未连续运输 | 保存已验证的原Ref与exact bytes；校验值与声明codec的编码关系，Id及控制传递不出版新值。preserves-value Map仍须证明值不变，不改旧digest |
| Traverse输入→child occurrence | sequence v1/v2由`sequence_object_type`声明，v2绑定完整element type；sequence/element/shape原用language规则 | 语言sequence envelope使用语言encoder；元素成为child payload时显式以领域codec编码，结构element_digest独立校验。不得把domain content_digest当element结构摘要 |
| child结果→settlement→父Program | `build_retrieval_work_active_child_bytes`现在用domain编码整个language sequence，并用domain摘要核对结构element_digest；`_completed_values`又以language重编码比Ref | 原领域函数保有receipt/trust/顺序检查；aggregate改由声明sequence codec编码，element identity用原plan规则。settlement携带reader验证的exact bytes，纯激活核Ref/type/codec/size/hash、语义关系、cardinality及原materialization谱系 |
| project/public写入→读回 | ValueRepository拥有exact bytes、CAS、incarnation、provenance/write-intent；public binding仅opaque投影。`load_bound_runtime_output`返回exact bytes，但调用settlement时丢弃 | 已持久bytes不归存储层重编码；writer前、semantic消费前各按声明验证。reader运输原bytes，不能以content_json或另一encoder重新生成领域身份；历史原样读回与可继续激活分开 |

最小充分候选只扩展现有activation安装解释边界：给`FirstSpecimenActivationCatalog`及其纯activation调用传入当前所需的`encode_value(ObjectType, semantic_value) -> bytes`关联。关联由原native DTO/codec声明、原transform/merge endpoint及Program里真实sequence/tuple构造派生，引用现有encoder；不建新的registry服务、Schema、持久状态或手抄codec词表。匹配使用完整ObjectType及精确codec身份；未知、重复或冲突关联直接拒绝，不能按前缀、项目名或值中是否含Unicode选择。原research/C8 consumer明确安装原language规则，迁移的Graph/retrieval/batch按其原领域声明安装规则；不保留会悄悄替未知domain codec选择language的生产默认。

该解释关联同时进入全部纯新值生产、Traverse输入/输出校验、generic handler的声明验证及settlement编码；`BoundStepValue/ProgramInput`只增运输本次已读exact bytes所需的字段，不能单靠这一字段绕过同codec双producer冲突。已验证bytes与semantic value的对应关系由同一声明encoder检查；preserves-value Map以原Ref声明codec比较候选值编码与原exact bytes，保留Claim/Gap既有union兼容关系；结构checksum只用于结构身份与结构相等，不再假扮payload编码。所有原project/public exact hash、codec/type、版本、size、provenance、materialization和ordered lineage拒绝均保留。

版本边界：现有domain codec与language sequence codec各自的合法字节规则保持，修正的是错误realization；其后PG38另暴露frozen形状信息丢失，Program AST的显式v2替换按下文裁定，Plan/shape其余公式不变。若执行绑定需要区别修复前后，使用原DeploymentCatalog的realization版本/digest，不另造版本表。旧同codec下不符合声明的bytes继续按原Ref供历史证据读回；它们不能静默换digest、重新出版或冒充已兼容的新激活输入。恢复这类run须另有明确迁移/新run决定，本包不默许自动迁移；若候选最终需要改变合法codec字节规则，则必须采用新codec身份并同步ObjectType/消费者，不能当作本次修错。

一次完整变化包固定为：原encoder关联及其安装派生、所有Pure/Map/Zip生产点、Id/Then/Decide值运输、project/public保存与权威reader、Traverse materializer/settlement/父激活、原消费者与保持见证共同收口。先用一个真实含中文query/body且带非默认值的检索Program证明同规则的生产→保存→读回→组合→结算闭合，再复用该规则覆盖Graph/batch及原research消费者；局部codec矩阵应同时覆盖合法非ASCII/数值/空序列和wrong codec/type/hash/size/semantic mismatch，随后一次集中21PG。不得按下一个失败再新建一个补丁包；最终未覆盖selector/fullsuite/coverage仍以真实职责收缩与净减为前提。

该批三个包的完成范围及证据如下；已决族输入不变时复用原证据，同源失败回原包，不新增包或流程。

| 实施包 | 当前owner与依赖 | 同一包完成边界 |
| --- | --- | --- |
| ①完整codec与值运输 | `codec_transport_executor`（GLM high）执行，已交`READY_LOCAL_ONLY`并静止写席；Astra只读核对8文件hash一致。新日志`evidence/integration/logs/typed-codec-*-2.log`中pure60、C8 27、traversal pure3、公共类型0、规则门禁291通过，sync/check clean | 全部生产、保存、读回、组合、settlement共享声明规则及原保持见证；PG36已证N2精确运输与结算，PG37已证followup两轮及九字段预算；PG38暴露Pure object/array表示丢失，现由同一owner修完整freeze→Program持久roundtrip→activation及直接consumer，PG39新61输入全21项已通过 |
| ②检索事实投影B1/B2 | root已确认Ret新READY：正式单口import/call、service五标量及原身份见证均同步，pure48、strict0、Ruff/diff通过，Ret写面已释放 | ceilings读原静态预算，消费读EffectStarted/settled Work，query身份读真实启动assignment的exact语义Invocation；不重新claim，不依赖新grant，不按ordinal猜测；PG36/37已验证真实query/预算投影，末端公共Pure形状已由原codec包修复，Ret领域源不变，PG39最终topology读回已通过 |
| ③同族职责与成本收缩 | `batch_unused_trigger_contraction`（GLM Flash）已删除batch未消费trigger，局部净−4；身份构造5→1已交PG相关`LOCAL_READY`，本包生产40 added/85 deleted净−45，含tests净−39，Ret第五caller另账；原6file纯98pass/2subtests、公有type0、sync/check clean、gates291，12输入hash经Astra只读核对一致 | 旧C2.1无消费者handler/transition/service已退役，623→49行净−574，原authority_digest及唯一PG rehydration消费者保留；staged经正式consumer/需求零引用核查，原writer已删除432行模块与515行专属测试，属于明确有损退役，写席静止；现役admission/staged/C8及W07三码保留，精确残留0、模块不可解析、owned diff通过，无pytest/PG。证据`integration/c2-canary-retirement/staged-recovery-retirement/evidence.md`。root写席稳定progress14全app307473，HEAD−28／dirty−6453，生产净降但不等于stage结项；五caller去重不单独代表成本闭合，最后公共扫描按真实依赖统一执行 |

共享单口固定为`composition.production.read_installed_program_input_bindings(..., static_input_type)`，返回原Program的exact静态绑定及按EffectStarted序列的`(step_id, attempt_id, ValueRef, bytes)`；共享执行者唯一维护该读口，领域owner消费，不复制SQL或重新claim。该符号已落地可导入，原attempt→assignment_digest→唯一work→validated assignment→exact语义输入链及缺失/重复/旧epoch拒绝已实现；N2原PG正反例已在PG36执行通过。完整命令、修复尝试和8文件输入hash见`evidence/integration/logs/typed-codec-inputs-and-results-2.manifest`，修后本地结果通过且writer quiescent；gate首轮no-throw及中间异常参数遗漏均保留失败日志，沿原failure_policy修复，无基线豁免。Astra不再修改生产/测试或运行验证。Ret正式单口及service五标量已交READY。PG36为20/21，PG37通过完整预算后暴露最终topology_write failed；PG38定位公共Pure形状，Ret静止、原codec包修复，不放宽原期待。共享frozen表示修复后原20项同受影响，PG39已按新61输入全21项重验通过。结构职责与app对HEAD净降确认后执行最终覆盖和原suite/coverage；整体成本与交付仍未结项。

### 同包内的 frozen JSON 形状修复与版本边界

PG38的`TOPOLOGY_SEED_INVALID: source_registry rows are absent`定位到原控制literal中`source_registry=[]`经freeze与thaw成为object。`algebra._freeze_json_value`与`program._json_value`重复把mapping/list归为普通tuple，`activation._thaw`再按pair形状判断，空tuple满足空全称条件；非空pair数组亦可能被误解为object。该缺口属于同一codec完整包的声明运输丢失，不能在Ret种子上将错误object容忍成array，也不按每个PG失败另造补丁树。

root裁定由原`codec_transport_executor`独占实施：复用已有`_FrozenJsonObjectMarker`，单一freeze递归保持mapping marker与array tuple，marker幂等判断先于Sequence；Program构造、metadata、encode/decode复用该权威；单一thaw按明确marker，activation及具名直接consumer `source_resolution_interpreters`、`workflow_legacy_dsl`不再按pair猜形状。验证覆盖Pure构造→持久Program decode→activation，空array、空object、pair数组、nested及既有scalar/set合同；Ret仅提供领域首例，不复制规则。

原empty tuple与新合法空array可能具有相同旧AST字节而解释不同，仅新mapping内容digest不足以隔离全部情况。因此`PROGRAM_AST_CODEC_ID`由v1显式升v2，作为同一解释器的有损版本替换；原object与`$array`语法继续复用，未变化的外层program_spec wrapper schema可仍为v1，DB schema不变。新Program、Plan及exact安装绑定随新身份重建；v1在原codec边界明确拒绝，不猜恢复、不保留第二runtime/fallback、不硬改历史冻结hash。原存储bytes、事件、ValueRef不改；原始历史可读不等于旧Program可decode或可继续运行，不能宣称无损resume。

非Program的source冻结字段也受同一规则影响：`SourceItemDefinition.to_plain/digest`原仅还原params顶层，`source_resolution._plain/_rebuild_value`把嵌套object当pair数组。root已限定同包扩写`source_contracts.py/source_resolution.py`及原直接声明/消费者测试：SourceItemDefinition与ChannelCatalog当前schema v2→v3；source_resolution当前payload codec_version 1→2，相应schema/ObjectType/codec身份沿权威常量派生，真实item/catalog/payload/contract/profile摘要重算。旧current schema/codec在原入口明确拒绝，现有historical常量与decoder须由原字节见证保持，不能重写历史fixture hash或猜恢复旧nested对象；若历史只读兼容无法证明必须明确报告。此项不构成新的schema系统或自动迁移。 历史兼容必须用修改前真实baseline/HEAD的freeze、digest、encode生成固定旧合法bytes，并固定schema、item/catalog/payload摘要与字节SHA；不得用新实现helper重造expected。当前source-v3全文件21 pass与historical单项1 pass仅保留尝试：只读审查发现其重构的历史item/catalog摘要公式与原代码不一致，且遗漏旧historical顶层搭配旧current v2子对象的原见证，兼容PASS已撤回，原owner已改用真实HEAD旧字节并于`source-v3-final-4.log`完成21 passed，见下列最终包证据。

最终包已交`READY_LOCAL_ONLY`：`evidence/integration/logs/json-shape-codec-final-manifest-1.manifest`，SHA256 `54cdbde34608609b0caf65d306d1038f2e7e9d44d7b2ae752d6e0e2452e2b943`。Astra只读核35个源码、测试、结果、失败与旧baseline文件hash全部一致。language/program49、activation60、traversal真实检索首例及原纯selector4、source21、source-family36、workflow37、C8 27均通过；公有type0、Ruff F0、sync/check clean、gates291均exit0。最终源码包含原marker的单一freeze/thaw、持久Program v2往返、两个直接consumer及source current版本替换；provider identity未变。typed/source-family首轮失败保留身份，source-family曾覆盖的35/1失败日志明确缺失，不伪造恢复；后续独立final-2为36 passed。

固定旧wire来自HEAD原algebra/source_contracts/source_resolution，canonical SHA为`f94d9ac5a092b761baafc5871be3ea589c2652e89e4b0d083234d26a61a5df4b`，payload digest为`82a82badd7f4f4df4295a71fbff376e9051f7f276fbd1943612fe46e0507e4d8`；测试内嵌原bytes，不依赖tmp。其top payload为C2-1 v1，item/catalog为旧current v2；原strict extra/missing字段检查与明确子schema拒绝通过。没有真实bytes支持的C2-1 v1子schema明确拒绝；支持范围不外推为任意历史版本可读/可resume。最终当前resolution为payload schema/codec id v3、codec_version2、ObjectType v2；SourceItem/Channel schema v3，Program AST v2。真实检索用原`_retrieval_followup_plan`经_control_literal_node→normalize/compile→持久encode/decode→PURE activation，验证空registry、六数组词表、source routes数组与ref object保持。

所有实现writer已静止，pure1释放；root已执行PG39全21项通过，现刷新必需覆盖及原suite/coverage。原PG36的20项和3个mixed旧kept计划均因公共输入变化撤销。progress12净下降仅为修复前中间快照；稳定写席成本已更新至下文progress15。

### 同族职责与成本裁定

明确列举的三个旧循环由3→0：`WorkflowGraphPlatformInterpreter.run`、`execute_retrieval_run`、`resolver._run_tasks_with_concurrency_plan`；三个旧写权组由3→0：`SqlRunStore`、`ProjectRetrievalService.update_run`、`SqlAgentSessionStore.transition_task`；两个run双写投影由2→0，提交identity的digest/Binding构造由5→1。原`integration/structure-symbol-inventory-1.json`是具名符号清单，不能把三个新函数计成三个独立手写装配维护点；此前2→3数字按函数计数，撤回该维护成本结论。原collect注册及`build_candidate_activation`退出保持其实际删除事实。

当前装配维护责任按真实输入拆解：`_installed_operation_facts`从原native builder读取contract/profiles，resource/effect及非dispatch的interpreter/authority均是有向投影，dispatch的特殊摘要仍由原声明拥有；六类family选择在facts与handler各有一次，但handler中项目scope、codec、ordered review预算、UNKNOWN/失败和broker生命周期不可由contract端点推导。`build_program_activation`的refs排序、deployment digest/entries和codec端点派生是通用算法；batch merge及retrieval callable registry安装是仍显式声明的family接线。现有workflow llm/join与retrieval WORK_LEAF均经原kind集合和native定义派生，新增同形实例不需改公共production文件；Graph原PG与N2领域leaf链提供真实非默认consumer见证。不能据函数数宣称装配增长或下降，也不为归并真实effect差异增建factory协议；后续成本结论按实际需同步的声明与消费者保持，不按重命名计数。

成本沿HEAD与dirty-start双基线，含空行/注释，tracked/untracked去重，tests单列。最终为`integration/production-count-progress-18.json`及`runtime-family-cost-progress-10.json`：app307472（HEAD−29／dirty−6454）、successor135154（−559／−5675）、services130558（＋256／−1308）、tests186416（＋3007／−1212）；替换族161520（HEAD−550／dirty−6688），workflow＋999、source−5991、retrieval＋3763、control−915、shared＋1594。各增长责任分别保留，不用source删除抵销解释义务；源码净减结合§7全部保持与验证才构成本次本地结项。以下progress17及更早均为历史快照，不覆盖最终成本。

写席稳定后`integration/production-count-progress-14.json`／`runtime-family-cost-progress-8.json`：app307473（HEAD−28／dirty−6453）、successor135154（−559／−5675）、services130558（+256／−1308）、tests186033（+2624／−1595）；替换族161521（HEAD−549／dirty−6687），workflow+999、source−5991、retrieval+3763、control−914、shared+1594。PG39后collection3与必需补集缺口已关闭，原ci-pr-1已在collection暴露审计checker退役同步缺口，修后重入suite及coverage，未结项。此快照早于仅改测试的W04修复，生产数不受其影响，tests数不冒充W04修后的重新统计。

以下13/12/10只保留历史。原中间快照`integration/production-count-progress-13.json`／`runtime-family-cost-progress-7.json`：app307436（HEAD−65／dirty−6490）、successor135117（−596／−5712）、services130558（+256／−1308）、tests186019（+2610／−1609）；替换族161484（HEAD−586／dirty−6724），workflow+999、source−6027、retrieval+3763、control−914、shared+1593。该快照已由稳定写席的progress14取代。以下progress12/10仅历史。root在C2/staged后实际快照`integration/production-count-progress-12.json`：app307315（HEAD −186／dirty −6611）、successor134996（−717／−5833）、services130558（+256／−1308）；完整替换族unique_total161363（HEAD −707／dirty −6845），分族workflow+1019、retrieval+3763、shared+1616继续单列。该快照记录当时整体生产净降；其时followup与最终suite尚未通过，不构成阶段结项。以下progress10为历史输入。09:07快照`integration/production-count-progress-10.json`：app307993（HEAD **+492**／dirty **−5933**）、services130473（+171／−1393）、successor135938（+225／−4891）、frontend69822（−224／−101）、src3875（−393／−393）；backend tests185502（+2093／−2126）。`runtime-family-cost-progress-5.json`完整替换族HEAD−57／dirty−6195，分族workflow+1028、source−6191、retrieval+3629、control_batch−888、shared+2365；当时仍未满足app对HEAD净减；上述旧快照不覆盖当前progress15，后续修整成本继续计入。

同族审查单位是definition→Program→deployment→handler→readback，不以删除436行作为设计目标。检索typed候选、预算、真实review、Material正式化、拓扑及共享顺序/失败保持具有真实消费者；重复submission身份构造、安装facts、预算fallback及重复读取则归回各原owner。handler各域kernel、scope、codec及UNKNOWN/cancel/readback职责不同，不能按相似壳形合并；对象shape不在transition重录。旧来源删除不能替检索/shared增长结账，不扩大到无关退休面抵销增长。batch未消费trigger已由独立执行者删除：`dispatch.py`由190→186行，4 added/8 deleted，builder的无效参数及第七返回项退出，唯一caller同步；正式提交仍传原now/trace_id。证据`batch-unused-trigger-contraction.evidence.md`明确以任务输入副本为基线（文件untracked），不算作HEAD净删除；syntax/Ruff F/diff已通过，pytest未运行。原`submit_installed_program`统一五consumer身份构造已实施并经98项原consumer验证，本包生产净−45，Retservice另账。安装facts公共profiles投影保持原实现；dispatch特殊interpreter/authority摘要继续由原声明拥有，不新增wrapper或kind词表，未实施的粗估收益不记作删除。调用/token及首次整组验收成本仍不完整，不报告提速幅度。

submission身份的只读审查已确认：`workflow`当前`operation_kind`取全部registry的首项，实际Program首atom未必为同一kind；`IdempotencyRepository`将该字段纳入exact绑定。因此不能以Program执行顺序替代caller的身份选择。root已确认最小签名并发实施：原`submit_installed_program`移除`idempotency: IdempotencyBinding`参数，改收必填`idempotency_id / identity_capability_id / logical_request_id / identity_operation_kind / run_id`，在原入口解析scope后按原公式构造Binding，原下游重算及exact冲突校验保留；caller原字段值不变，不新增DTO、wrapper或双入口兼容。五个真实consumer为batch dispatch、API ingest、retrieval service、workflow facade及agent authoring；Ret的logical id仍为原idempotency_key。

本轮身份收缩独占写面：`batch_unused_trigger_contraction`拥有`A/composition/production.py`、`A/services/agent_batch/dispatch.py`、`A/api/ingest.py`、`A/services/workflow_graph/__init__.py`、`A/services/agent_core/authoring_tools.py`；原六测试为`B/unit/{test_agent_batch_api_unittest,test_workflow_graph_runtime_unittest,test_agent_core_unittest}.py`、`B/contract/test_ingest_response_contract_unittest.py`、`B/integration/test_frontend_ingest_flow_smoke_unittest.py`、`B/core_business/test_ingest_core_contract.py`。Ret继续唯一写`service.py/execution.py`及原检索unit，由root正式传递固定接口；Astra只审查协调。成本writer已完成原消费者、公有type及sync/check/gates，Ret已完成48项pure及strict0，双方已交新READY并静止；PG37领域topology尾项经同一codec包修复共享frozen表示后，由PG39新61文件输入全21项通过闭合；C2/staged也已静止，pure1已释放。原45文件PG36与共享旧manifest仅保留当时输入身份；最终codec包的公共扫描及35项manifest核验已经完成，不再等待第二轮同输入扫描。

资源由root统一持有：专属PG容器`mrw-simplification-pg-20261006`（127.0.0.1:57659，无Mounts），隔离suite库`mrw_test_structure_20261007`及`mrw_structure_topology_20261007`原两表。PG输入稳定后整批冻结；pure slot1归集成、slot2归检索，tmp/Hypothesis/cache独立，无第三pure pytest。fullsuite/coverage由root在共享资源窗口串行执行；该资源安排及本机HOST验证不改变发布权限。
