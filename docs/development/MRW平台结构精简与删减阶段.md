# MRW 平台结构精简与删减阶段

> 2026-10-08 · **当前：第二批旧generator、I1装配外壳及workflow静态资格链已退役，所需局部验证完成；整体精简未完成。** 本批基线`0dc9b3c34d3084d219df5ae41038d0b73943aa3d`，初始计量基线`c3adced5946a52b66be4494aba3dbb707ee879b5`；上一轮迁移保持结果列为§8历史，不再等同整体精简完成。平台必要能力和事实归属沿[MRW精简框架](MRW精简框架.md)，流程沿[19号规则](../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/19_direct-testing-batch-freeze-amendment.v1.md)；[06号入口](../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/06_production-deployment-stage-progress.v1.md)的旧部署任务保持停止。

## 1. 退役终点与边界

本轮按“typed语义/特殊kernel → native rule派生 → production声明查找、handler安装与reader → 同批切断旧路径并整族删除”组织。终点是必要能力由最小现有核承担，重复声明、装配、注册、旧adapter/执行owner及专属tests/checkers整批消失，并达到发包前净减承诺。保留用户能力、对象身份、权限、真实effect和失败观察，不默认保留目录、API、测试或checker。每包明确是停止冗余功能，还是保留能力的实现替换；前者记录撤回范围，后者证明原必要观察保持。

services旧整体组织承载与successor重复承载都在退役范围，API/胶水和其它app源码不漏账。必要领域类型、特殊kernel、provider/DB效果逐项证明后接已有原生贡献位置，不把services全量搬家或包装进新runtime/domain/DSL。唯一耐久Runtime沿既选内核，领域writer、DB/provider和host权威不转给API或投影。真实必要核可以暂在原文件承载，但必须具名、压缩且没有整文件/整目录保留豁免。

## 2. 基线、预算与完成判断

全项目计量范围、当前基线和预算规则以[框架§4](MRW精简框架.md#4-全项目规模预算与收支约束)为唯一权威。上轮未经充分保留核与真实收缩包支持的规模硬帽、分帽和族净减承诺已撤回，历史探索值不驱动当前发包或验收。app基线为`c3adced`的758文件307472行；首批提交`0dc9b3c3`为743文件305358行；第二批稳定工作树为737文件299234行，分别见§2.1与§2.2。上一轮迁移净减29行不计入本批退役收益。现场全项目定位数据为`/tmp/mrw-whole-project-budget-20261007/whole-source-baseline.json`，可按原口径复算。

`A=main/backend/app`，`B=main/backend/tests`。每包发放前取得精确可删闭包、必要保留核与`D/A_max/N_min`；抽出领域核、跨目录保留原字节、替代及共同接缝计回原族，搬家净收益为零，原族与全局同一代码只计一次。未定该包预算时先做有界定界，不扩建实现；已证明的首批预算保持，安全删除不等待全项目预算校准。

冗余职责切断、旧执行owner全量退出、唯一路径和必要typed/authority/effect/UNKNOWN/恢复保持仍是硬方向；现既选核收缩冗余，不要求重写。后续总体区间与累计净减由root据代表包和具名保留核裁定，不另猜一组温和数字。测试、现役文档与历史库存分账；首批2149或净减大于零不能代替整体退役，也不能靠移入archive逃账。

### 2.1 首批局部试跑结果与证据

本节保留已提交为`0dc9b3c3`的首批结果，以下“本批”均指该首批，不覆盖§2.2。首批以`c3adced`为生产基线完成五个互斥的有界闭包（安全退役3、Runtime1、workflow1），聚合为三类app试跑。安全退役取得实质净减；Runtime同源映射只带来14行净减；workflow统一了operation安装接缝，但首例净增50行。后二者证明的结构范围与规模收益须分别判断，不能由局部贯通推断全局精简完成。

| 计量面／已实施闭包 | D实际 | A实际 | N实际 | 预算与结论 |
| --- | ---: | ---: | ---: | --- |
| 安全整族退役：ops_domain、local_index、streamplus | 2156 | 6 | 2150 | 原预算D2155/A≤6/N≥2149；额外删除item_writer旧import，三个闭包已退出 |
| Runtime原typed字段及state集合到原值仓库 | 18 | 4 | 14 | 达到D18/A≤4/N≥14，仅此小样本，不外推Runtime总体删减 |
| workflow同源operation查找与实际handler安装 | 42 | 92 | −50 | 达到最终预算D≥38/A≤92/N≥−54；早期A68/N−31估算遗漏正常imports、可读格式及完整类型/权威检查，已修正，不能沿用旧上限 |
| **app合计** | **2216** | **102** | **2114** | **758文件307472行 → 743文件305358行** |
| 自有工具，17文件 | 9094 | 0 | 9094 | 13个ops/search-lab local_index实验脚本8334、专属checker527、drift gate230、selectors2、classifier1；与app分账 |
| 自有测试，20文件 | 2117 | 142 | 1975 | 只计测试收缩，不抵扣实现新增 |
| 配置JSON | 1 | 0 | 1 | 单列，不计实现收益 |

自有实现与工具合计净减11208行（app2114＋工具9094）。工具退役不能抵消workflow的app新增，测试、文档与配置也不进入实现收益。退役工具族已无当前正式CI、root scripts或非archive可执行调用者；历史raw JSON、reader与archive保留。独立sqlite `local_index_backend_evaluation`承担不同职责，继续保留。

Runtime首例以`dataclasses.fields(RuntimeValueBinding)`派生浅层键值映射，以原`RuntimeValueState`的Literal派生合法值集合，未新增class、IR、schema或registry，也未修改journal/CAS。保持观察限定为键值内容、named SQL/params、identity/content binding和单字段失败；字典插入顺序已改为声明顺序，不主张保留多字段漂移时首个诊断的顺序。原pure消费者使用fake `_StoreConnection`，实际PostgreSQL消费者另有独立结果。

workflow首例在既有`WorkflowRuntimeDefinition`上补`operation_for_ref`，按完整ref解析，原builder支持封闭三种既有节点的kind映射，并拒绝缺失、额外、空值和重复kind；原production事实查找和handler安装读取同一选定definition。新增最小装配函数`assemble_workflow_runtime_handler`直接构造原`PersistentOperationHandler`，保留原scope/schema/capability、项目绑定、kernel、settled failure和bound input validator，并检查完整input/output ObjectType、codec payload_type_id/contract_ref、authority profile与canonical owner。跨类型负向见证重建contract和codec ref而保留codec ID，验证完整端点失配确被拒绝；错payload、owner/profile及同kind错版本/digest也拒绝，构造时UoW/kernel不执行。未新增kernel_ref、wrapper dataclass、文件或catalog。把原handler代码提取到assembly本身仍是提取成本，不能算消除重复代码。

真实PostgreSQL见证覆盖default及alternate：后者只替换`llm_call`的operation kind，经唯一module builder使原service program、production、worker及reader/replay读取同一定义。这证明有界同形身份变化可以到达原消费者，不证明新增节点语义或可部署配置机制。`project_catalog`与`NativeContributionRule`尚未跨全部能力贯通，当前统一范围只有workflow operation安装接缝。

| 集中实际验证 | 本次结果／退出码 | 现成证据与范围 |
| --- | --- | --- |
| public typecheck | 0 errors／0 | §6原命令内联输出，无独立日志 |
| sync/check | clean，changed_paths为空／均0 | §6原命令内联输出，无独立日志 |
| dev test | 136 passed／0 | `scripts/dev.py test`内联输出 |
| 现役完整七gate架构套件 | 290 passed／0 | `scripts/dev.py gates`→`tests/test_architecture.py`→`functorial_kit.architecture_gate_tests(ROOT)`；内联输出。较历史291减少1为退役专属贡献后的派生数量变化，不是丢弃selector |
| workflow pure | 4文件，77 passed，28 subtests／0 | `/tmp/mrw-pure-workflow-20261008/pytest2.log` |
| workflow真实PostgreSQL default＋alternate | 2 passed／0 | `/tmp/mrw-pg-workflow-20261008/pytest.log` |
| safe V-ops/V-index | 73 passed／0 | `/tmp/mrw-pure-v-ops-index-20261008/pytest.log` |
| W01 | 2文件，11 passed／0 | `/tmp/mrw-pure-safe-shared-20261008/pytest3.log` |

以下结果在输入依赖未变范围内记为**kept**，不冒充集中收口时重新运行：V-source 23 passed／15 subtests（`/tmp/mrw-pure-v-source-20261008/pytest.log`），Runtime pure原消费者1 passed（`/tmp/mrw-pure-runtime-values-20261008/pytest.log`），Runtime真实PostgreSQL原消费者1 passed（`/tmp/mrw-pg-runtime-values-20261008/pytest.log`）；原退出码均为0。

失败attempt保留：source-helper首次4 failed（`/tmp/mrw-pure-safe-shared-20261008/pytest.log`），第二次3 failed（同目录`pytest2.log`），清理当前selector/helper后最终11 passed。workflow pure首次1 failed（`/tmp/mrw-pure-workflow-20261008/pytest.log`）：package级`runtime`解析成instance而非module，用`importlib`准确定位module后最终77 passed；该失败属于导入定位，不是领域行为失败，未删除断言。历史迁移失败及原退出码继续沿§8保留。

本批所需的上述已选验证lane最终没有failed、skip或not_run；该结论不覆盖全仓验证。full repository suite、browser、deployment本轮均未运行。Ruff可执行文件缺失，原退出码127，未成功执行，未安装或替代。当前结果不构成完整生产发布资格；旧部署Stage4–6继续STOPPED，未push或deploy。

成本记录边界：五个有界闭包聚合为三类app试跑并形成收支闭合；工具和测试按独立计量面列示。实际Agent派发总数、各owner调用/token、首次共同验收完整耗时及共同等待成本不可得，不记为零，不宣称提速。workflow首例的手写安装接缝和完整检查成本已计入A92；其他尚未核定形状与D/A/N继续未知。

下一前沿是在现有实现中寻找真正同形的整族重复装配或旧执行owner闭包，连同共同规则及集成成本仍有正净收益后再发包；不累积字段微修，也不为延伸首例启动新共享框架。Runtime15000、app80000、总130000及原分帽、64503/390142目标继续撤回；“6–10万”只是未校准历史情景，不是可信预期删减量。

### 2.2 第二批整族退役结果与证据

本批从干净`main`的`0dc9b3c3`推进，沿已有生产operation接缝删除旧generator、I1/C8/C9局部装配外壳和workflow静态资格链。三个独占包与共享接线分账，首批app净减2114、工具净减9094不重复计入。

| 计量面 | D实际 | A实际 | N实际 | 边界 |
| --- | ---: | ---: | ---: | --- |
| app | 6287 | 163 | 6124 | 743文件305358行 → 737文件299234行 |
| 工具 | 2063 | 0 | 2063 | 已退generator及专属执行工具；不抵扣app新增 |
| `src`原生贡献及根`contributions/project_catalog.py` | 163 | 17 | 146 | 独立于app与工具；原failure metadata保留声明净成本16行已计入 |
| 全部测试，含frontend | 6848 | 257 | 6591 | 专属测试退役、混合测试保留与新增见证另账 |
| config/derived | 39 | 31 | 8 | `.functorial`、registries、sketches及既有governance可变map；不算实现收益 |

本批实现与工具合计净减8333行（app6124＋工具2063＋原生贡献146）；测试、配置及文档不抵扣实现新增。app相较初始`c3adced`累计净减8238行。app互斥归属为safe1712、I1独占2108、workflow独占1796、shared508；shared由assembly导出退12、workflow壳净减501、knowledge refs净新增5组成。workflow独占源码新增上限120行满足；首批workflow净增50行仍留在首批历史，不回写成当时已净减。

safe包退出`specification/{c4_p3,c5_p3,c9_p4,shared_family_generator}.py`及专属generator链；`CapabilityCellSpec`、compiler、RuntimeKernelABI及其原消费者继续保留。I1包退出旧`SuccessorAssembly`总装、knowledge assembly和projection专属装配/离线fixture；保留真实C8 kernel、native binding、workflow handler及app mount需要的closed projection ports。startup/API原actor、scope与真实PG query保持，command仍不写入，未借退役打开生产submit权限。名字含`first_specimen`的现役worker/terminal/qualification及仍被agent_core/session使用的`agent_runtime`核不按目录标签删除；PG事务、current authority、UNKNOWN和领域writer归属保持。

workflow退出旧静态compile/observe/restore资格cell、重复lowering、旧catalog及专属验收生成。新compiled record沿原合同增加单一`binding_version`，复用已有DSL `content_digest`；运行前核对graph identity、版本、DSL digest及完整domain projection（version/options/checksum/topo/双向edges/nodes），之后才连接Runtime数据库、构造真实Program并提交。public topo/checksum与真实运行的program/plan metadata保持，不新建DSL、Runtime、wrapper、catalog或签名/baseline设施。

这是**有显式兼容性损失的迁移**：旧compiled record的`platform`与嵌套历史payload仍可list/get读取，但缺少当前binding的旧记录不能继续运行，必须重新编译；未知binding version也拒绝。新compile响应不再提供旧静态program/plan/catalog digest。完整性保证限定在可信store下拒绝内部不一致或过期绑定，不声称检测整条record连同digest的一致替换。compile/acceptance历史reader仍按原schema解释、校验hash并返回原字节，历史observability/handoff读回保留。

共享收口只在既有位置处理：catalog引用原`WORKFLOW_DEFINITION_FAILURES`和官方`contribution_failures`保留必要failure登记，不新建failure族、对象或factory；4处witness（app_assembly、batch_task_assembly、knowledge_graph_projection及workflow_legacy_dsl reader）改指仍存真实覆盖，函数body不变。C8四项声明指向真实保留kernel。W08B继续验证compiler，混合C6/C7历史读取、typed macro和真实app mount/native见证保留。`ACTIVE_MUTABLE` authority-map仅将退役generator的状态/kind历史化，raw路径、IDs、rows及hash保留；其独立7项map测试继续验证。所有历史冻结及旧债务starting-baseline、packets、resolutions保持原字节，贡献sync不意味着重写这些旧快照。

| 实际验证范围 | 结果／原runner退出码 | 现成证据与执行归属 |
| --- | --- | --- |
| public typecheck；sync/check | 0 errors；clean／均0 | 本批最终实际输出 |
| dev test | 115 passed／0 | `/tmp/mrw-final-devtest-20261008.log` |
| 完整现役七gate架构套件 | 284 passed／0 | `/tmp/mrw-final-gates-20261008.log` |
| 最终focused | 8 passed／0 | `/tmp/mrw-final-focused-20261008.log` |
| 真实PostgreSQL C8/HTTP＋workflow worker default/alternate | 31＋2 passed／均0 | `/tmp/mrw-pg-final-20261008/c8-http.log`、同目录`workflow-worker.log`；合计33 |
| workflow/shared pure | 53 passed／0 | `/tmp/mrw-w-shared-final.log` |
| C7/safe四文件focused | 28 passed／0 | `/tmp/mrw-w-c7-safe-final.log` |
| typed macro | 5 passed／0 | `/tmp/mrw-macro-native-20261008.log` |
| 历史authority-map | 7 passed／0 | `/tmp/mrw-governance-maps-20261008.log` |

作者较早实际验证另有workflow 85 passed／41 subtests（真实内联输出，未落独立日志）、C8 pure2项及mount3项；末轮未重新执行的局部结果只在未变依赖范围复用，不伪装为新执行，也不与上表相加为独立测试总数。本批作者Ruff F检查实际通过，范围仅为该检查；§2.1的Ruff exit127仍是首批未执行成功的历史。前端eslint、strict tsc与Playwright-list通过，list不等于浏览器执行。实际live E2E、full repository suite及deploy本批未跑；这些结果不建立完整发布资格。

失败和返工未抹去：workflow/shared pure初轮52 passed／1 failed，原rollback路径预期修复后53 passed；root分包漏列C7 native对已删rollback fixture的消费，补派workflow owner用已有`MaterialIngestAssemblyOptions`与submission保留scope/handler digest断言，再取得四文件28 passed。完整性测试曾把DSL、nodes和重算digest的一致替换误写为必然失败；现改为digest未更新，或重算DSL digest但stored nodes仍不同的真实不一致案例。最终gate首轮出现no-throw5、registry2及derived-marked5：前两类源于旧fake workflow contribution退出后原两组failure登记遗漏，后一类为初轮3处witness仍指已删测试；末轮另同步1处workflow reader旧name，共4处修正，按原权威位置收口后284 passed。dev test初轮114 passed／1 failed的report rollback旧预期修复后115 passed。gate失败时一度错误读取管道末端exit0，已纠正；该0不构成PASS，最终结果使用原runner退出码。

本批三个独占实施包及共享收口均完成所需局部验证；失败attempt状态已列，原始失败日志的持久保留范围尚未核实。派发恢复、主线补修及集成等待计入过程：集成任务数次在实施中途只回剩余清单，root收缩其turn为PG验证后完成，并接管/重新分派遗漏的共享修复。调用/token、完整首次共同验收耗时及等待量不可得，不记零，不宣称提速。下一前沿仍按真实消费者寻找可整族退出的重复实现，未调查形状与净量继续未知；全平台精简和全能力native贯通未完成，旧部署Stage4–6继续STOPPED，未push或deploy。

## 3. 已定首批退役包

共同执行合同：cwd为仓库根，Python为`main/backend/.venv311/bin/python`，`PYTHONPATH=.:src:main/backend`；只使用现有依赖。表内保留发包时预算与合同，三个安全包均已实施；实际收支、验证与attempt见§2.1。验证入口沿§6。每包输出原文档中的实际删除/新增、消费者切断、原验证结果及风险，不新建报告或平台。

| 包／目标与权威输入 | 精确源范围、消费者与最小核 | 输出与预算 | 独占写面／仍存验证／完成条件 |
| --- | --- | --- | --- |
| **运维镜像层退役**：停止已无app调用的重复ops surface；原API与生产观测继续承担健康、配置和运行查询 | `A/successor_runtime/ops_domain/{__init__,base,dashboard_admin_surface,health_matrix_surface,ops_misc_surface,projects_config_surface,runtime_ops_surface}.py`，7文件1345行；`ops_surface_failure`等仅被两专属测试消费，旧s2c装配器已不存在；无需保留kernel | 整目录及专属`main/backend/tests/functorial_debt/test_w07_ops_surface.py`、`main/backend/tests/successor_runtime/test_s2c_ops_domain_surfaces.py`退出；生产`D=1345/A_max=0/N_min=1345`，不得新增生产壳或见证来维持旧surface | 该7文件与两测试；`scripts/build_functorial_debt_packet_registry.py`路径项由集成owner串行处理。贡献权威源、派生registry/sketch/witness的实际影响沿原sync/check收口，不能手删派生条目或豁免gate。现有`src/mrw_functorial_kit/core/w07_semantics.py::ops_surface_failures`与`registries/failures.json`的`successor.ops_surface.failure`由根W07测试独立消费，保留该失败声明/历史识别，不因此保留ops模块或新增生产壳。验证V-ops及引用清零；原健康/配置/权限保持，整族消失才完成 |
| **旧本地索引功能退役**：停止无现役app能力要求的LanceDB local-index路径；保留当前search/indexer入口 | `A/services/local_index/{__init__,embedding_provider,schema,service}.py`及`adapters/{__init__,lancedb_adapter}.py`，6文件695行；初始定界含`main/backend/scripts/check_wave14_vectorization_provider_capability.py`与专属test；试跑发现的shared及13实验脚本/10tests消费者闭包已按§2.1同退；无保留核 | 目录、专属checker与`main/backend/tests/unit/test_local_index_service_unittest.py`同退；生产`D=695/A_max=0/N_min=695`。不新增另一个索引adapter | 该目录/checker/test；`main/backend/scripts/pre_release_gate.sh`对应已退selector由集成owner改。验证V-index及精确引用清零，原search/indexer能力保持；不是为了green而删现役gate |
| **来源常量壳退役**：保留source item默认capability，退出streamplus旧合同族 | `A/services/streamplus/{__init__,contracts}.py`共115行；唯一现役consumer是`A/services/source_library/item_writer.py`对`SOURCE_ITEM_CAPABILITY_DEFAULT`的读取。其余dedupe/idempotency符号无外部consumer；最小核为原5行常量 | 常量落现有item_writer，连注释空行新增最多6行；生产`D≥115/A_max=6/N_min=109`。不建新常量模块；目录与专属`main/backend/tests/unit/test_streamplus_contracts_unittest.py`同退 | 两源文件、item_writer中该常量和import；其余来源改动不授权。pre_release_gate同一owner清其专属selector。验证V-source及默认字段保持、引用清零；之后item_writer交回来源owner |
| 首批合计 | 三个生产删除集合互斥，共15文件2155行 | `D=2155/A_max=6/N_min=2149`，不是全局目标 | 非app源码、脚本/测试改动单列；不得以外移新增绕过上述上限 |

零新增包只能清理既有义务并复用仍存见证。如果当前贡献源/注册闭包要求新代码，先返回该包重新定界和预算，不能在A=0名义下偷偷新增。历史快照保持原字节；仅取消已退功能的当前生成/验证入口，仍需读取的历史失败标识继续通过原只读路径解释。

## 4. 原生规则贯通与删除工作包

共同合同沿§3的cwd、解释器与依赖，验证入口见§6。首批workflow与Runtime有界首例见§2.1，第二批整族退役见§2.2；其它族仍需各自定界。发包前把下表符号范围落实为精确文件/符号闭包和D/A_max/N_min，公共规则与集成成本计回受益族；当前未定预算的迁移仅可做有界定界，不能写成实施ready。规则已支持的形状直接使用，真实新形状交唯一规则owner补当前缺口，领域作者不各造解析/装配协议。框架机制和项目消费者分别验收，沿原kit和七gate，不新建门禁系统。

| 实际工作包／目标 | 权威输入与现成接口／输出 | 独占写面、依赖与包内并发 | 可执行验证／完成条件 |
| --- | --- | --- | --- |
| **workflow公共首例／规则与集成同一owner**：同一typed定义驱动生产声明查找与handler安装，替换同kind两处手写分支 | 现役`capabilities/workflow_native_contribution.py::{build_workflow_runtime_definition,build_workflow_runtime_program}`与`workflow_assembly.py::assemble_workflow_runtime_handler`；旧资格用`assemble_workflow_native_definition/WORKFLOW_NATIVE_CONTRIBUTION_RULE`已在第二批退役；`PersistentOperationHandler`、原提交/reader；参考知识图投影的lower/assemble/install。输出最小规则扩展、原production消费者接入及被替代分支/装配删除；不另造factory清单 | 1作者贯通`workflow_native_contribution.py`、`assembly/workflow_assembly.py`及`composition/production.py`的workflow接缝，必要有效native目录及原测试；集成owner同人，禁止其它包同时写production/catalog。领域`services/workflow_graph/runtime.py::invoke_workflow_runtime_node/execute_node`只按必要接口改，不生成其输入/effect语义。首例实际D42/A92/N−50，最终预算与成本修正见§2.1 | V-wiring＋V-workflow、V-type/V-kit及受影响V-durable。非默认同形定义进入真实production入口；本批已在原真实PG测试覆盖default/alternate；仅证明既有三种节点内的kind身份变化，不扩张为全能力目录贯通；事实改动自动带动装配，crossed input/output、重复/缺失identity、错authority均拒绝；声明/sync无effect，原权限/事务/UNKNOWN/cancel/恢复保持；旧分支删除才完成 |
| **Runtime同源结构收敛与旧执行owner退出／耐久内核owner**：原生typed状态/值/事件/命令经已有关系规则到Node/PG及只读readback，同批消除重复表示与旧执行owner | 复用`runtime/transitions.py`原状态/事件表与解释、`runtime/ports.py`scope和`runtime/recovery.py`真实未开始证明；首候选核查`substrate/postgres/runtime_values.py::RuntimeValueBinding.values`能否由原typed字段派生必要映射并被`RuntimeValueRepository.put_exact/load_exact`消费，连同`RuntimeValueState`合法集合比较选一个完整闭包；也可复用已有充分证据的更有价值同形闭包，不能用更大包装换十余行映射。journal typed命令与row/event projection是另一候选，不模板化全部SQL；保留Program/compiler/ports/ValueRepository、PG claim/commit/锁/CAS/seq/事务、current grant、UNKNOWN/cancel/真实恢复与领域writer权限 | 1owner、最多1个独立写面；若需补规则，由该owner一真实例贯通后才释放依赖的同形包；独立形状无需等所有领域迁移。workflow共享assembly/production/catalog仍由唯一集成owner维护；两首例机制复用，不各建框架或重计成本。值映射首例实际D18/A4/N14，其它闭包D/A/N未定；物理79503不作净减，迁出与派生生产成本计回原族 | V-core/V-durable/V-type/V-kit及下述Runtime原见证；一处原生事实变更驱动受支持codec/row/readback与校验，不复制词表；原consumer读写、identity/grant/失败保持，跨型非法状态、错binding、过期grant、UNKNOWN误判及rollback负向保持，纯派生无effect。本批值映射与state合法集合已有pure及真实PG原consumer见证，观察边界见§2.1；journal等其它候选未实施；完整旧闭包已删、旧owner不可执行且D_actual/A_actual/N_actual达到原包预算才完成 |
| **同形能力迁移／领域作者**：复用已贯通规则并给出族内完整删除闭包 | 已知族：workflow剩余节点/读回；retrieval的`retrieval_{candidate,material,flow}_native`与`retrieval_native_catalog`；source的原source contracts/resolution/acquisition贡献；material/knowledge/writing原类型与writer贡献；host/项目API及同步工具/reader原权限与服务合同；前端manifest/WebUI原适配边界。每族先判已支持/新形状/特殊核/无需求；输出语义、typed定义、特殊kernel与独立见证，不逐能力手写contract/profile/codec/装配 | 每族1作者；有效native目录/production由集成席合入。最多3领域作者＋1集成席，互不改同一贡献源或consumer；依赖新接缝的形状等首例，既有形状与独立kernel可先做。workflow与首例共享文件须交接；source的item_writer等常量包释放；各族D/A/N未定，不假报可批量执行 | workflow用V-wiring/V-workflow；retrieval用V-retrieval及`focused main/backend/tests/successor_runtime/test_retrieval_native_catalog.py main/backend/tests/unit/test_retrieval_flow_native.py`；source用V-source；knowledge/material/writing用V-wiring中的知识图原见证及V-data；host/项目API用V-host/V-project；同步reader用对应原消费者测试，frontend/WebUI用V-ui。真实消费者保持且机械接线由规则派生；输入/输出、codec、kernel签名及reader结果关联保持，重复接线Any/宽dict随壳消除，不先擦为object/cast；不支持形状回规则owner |
| **生产消费者收敛／唯一集成owner**：同一有效native组合供实际安装与投影消费 | 接收已验证typed native对象，使用`_installed_operation_facts/_installed_operation_handler`原入口及原reader；`contributions/project_catalog.py`当前CLI/check投影不能冒充worker目录，retrieval native/projection保持类型差异。输出原入口对同源对象的消费及重复列表、refs、手工装配删除，不建新注册层 | 1作者独占`composition/production.py`、共享assembly、有效native目录、project projection、贡献sync/check及受影响共享consumer；按族串行合并。可与不触及这些写面的最多3作者并行，首次workflow合并属于首例，不重复发包/计成本 | V-type/V-kit、V-durable及各族原API/reader测试；同一事实修改沿依赖到达真实消费者，当前grant仍执行前重读，派生投影无写权，安装失败不回退旧factory。无共享输入一致性不运行集成验证 |
| **整族删除与净量结算／对应族owner**：切断旧执行与重复承载 | 原consumer已切换的证据、权威贡献源与该包D/A/N；输出旧声明/adapter/执行owner、专属tests/checkers/config及当前文档同批删除；现选Runtime沿同源结构链删除重复模型、映射、装配及检查 | 每族1作者，最多2个互斥删除写面，同时仍受4席总限；consumer/catalog/checker交集归集成席串行。切换和删除是同一包完成条件，不拆成接入已完成/删除无限后置。无现役需求包直接沿§3，不依赖首例 | 各族focused selector、引用清零及V-kit，真实受影响集成沿V-durable/V-suite。保留必要独立见证和历史字节，原失败/恢复观察保持；达到原定D/A/N且旧路径不可执行才完成 |

workflow首例已让原production声明查找与handler安装消费同一选定definition，并保留typed codec/authority关联，实际范围见§2.1；这不表示全平台其它形状或预算已经确定，其余族继续按本表分类和定界，不预建覆盖所有未来能力的协议。知识图投影已有装配路径可复用机制，不能据此认定retrieval动态步骤、source外部效果及所有CRUD都是同一语义形状。同步工具/reader、前端manifest和WebUI继续各自protocol/lifecycle，不因本首例添耐久层；真正外部JSON/provider输入在原解析边界收窄，不扩大为全库类型债治理。

### 全路径预算与删除覆盖账

下表只防漏文件，不作为主要架构切片或目录保留凭证。按上述能力链圈定互斥闭包，再向本账归集删除、保留核与新增；先扣§3已分配文件，跨目录成本只计一次。路径相对`A`，各面D/A/N随实际包形成。

| 覆盖责任面 | c3路径范围 | 文件／行数 |
| --- | --- | ---: |
| 来源采集 | `services/{source_library,collect_runtime,ingest,crawlers,crawlers_mgmt,ingest_config,http}` | 126／38587 |
| 检索资源 | `services/{search,project_retrieval,resource_pool,discovery,indexer}` | 56／19896 |
| 材料知识写作 | `services/{document_queries,document_views,information_topology,typed_knowledge,graph,clue_chains,writing,extraction}` | 93／19534 |
| 宿主工作流 | `services/{agent_core,agent_runtime,agent_batch,agent_sessions,workflow_graph,llm}` | 85／37575 |
| 项目治理 | `services/{projects,aggregator,governance,local_index,stats,streamplus}` | 19／3307 |
| 服务根胶水 | `services/*.py`的19个tracked文件 | 19／11659 |
| 原生能力与样板 | `successor_runtime/{capabilities,specification,research,ops_domain}` | 103／55651 |
| 运行结构与装配 | `successor_runtime/{language,runtime,substrate,assembly}`及根`__init__.py`，含领域handler | 130／79503 |
| API | `api/**` | 39／26297 |
| 其它平台 | app其余全部tracked源码，包括composition、models/contracts、启动、观测及项目定义 | 88／15463 |

前六面398文件130558行、successor两面233文件135154行，加API与其它覆盖758文件307472行。前端、kit/native贡献、脚本/迁移/ops/search-lab/local入口、vendor内MRW定制及测试/现役文档继续按框架全项目账定界；独立用途删除可先行，不能以archive标签逃账。workflow＋999/retrieval＋3763/shared＋1594沿旧跨目录family口径复审，不与本表重计。当前url_pool2112行中的旧ThreadPool已退；staged/effect旧文件不得重计；stats与time-density checker同义尚未证，真实consumer引用只用于定位，不能全保或假报零新增。

## 5. 执行前沿、职责与资源

§3安全包及首例结果保留于§2.1；第二批旧generator、I1外壳及workflow静态资格链退役已完成本批所需验证，结果见§2.2。当前前沿是寻找已有同形整族重复装配或旧执行owner闭包，确认计入共享及集成成本后的正净收益，再释放对应包；其它形状与预算继续定界。首例1作者贯通后，依赖该规则的同形包才释放；已经充分证明的规则路径直接复用，不增审批关卡。root按具名保留核、互斥包和实测公共成本裁定后续可执行总体区间与累计净减，不无限定界、不恢复已撤硬帽，也不以首批2149或净减大于零结项。

| 可执行前沿 | 依赖、并发与收敛边界 |
| --- | --- |
| 已完成首批与下一闭包定界 | 首批与第二批已完成的有界闭包分别见§2.1/§2.2；后续先取得整族互斥闭包及包含共同成本的正净收益。1名规则兼集成owner与≤3名不争写作者，总作者≤4；独立已有形状不受无关接缝阻塞。新规则只由1owner以真实consumer贯通，未定只阻塞依赖包 |
| 首例贯通后的同形迁移 | 只释放依赖已证明规则的形状，≤3名领域作者＋1名集成；新形状及未定预算继续由对应owner定界，不据此阻塞无依赖包 |
| 每族消费者与删除闭合 | 共享消费者串行合入 → 原消费者验证 → 同包删旧 → 实际收支结算；这些是一个包的完成依赖，手写减少不等于总量净减，不能接入即结项或把删除无限后置 |
| 一致输入上的集成验证 | 集成owner集中运行受影响gate及真实PG等原验证；验证期间禁止改所测输入面，其它无依赖写面可继续。源码并发不等于测试并发，资源限制沿下文执行 |
| 总体覆盖与净量收口 | 汇总全项目具名保留核、互斥删除包与全部替代成本，由root据实际闭包裁定总体区间和累计净减；未知形状/预算保留身份与owner，不以局部通过或首批净减代替整体完成 |

全局最多6名活跃Agent：root分发/裁定1名、Astra编排/只读审查/文档1名、作者或调查者最多4名，集成owner占其中1席。领域作者给语义/类型/特殊核/独立见证；规则owner补lower/derive缺口；集成owner唯一改共享production消费者和有效目录/投影。首例期间规则与集成由同人承担，另3席可做独立包；批量期最多3领域作者＋1集成。共同错误归唯一owner修复，无依赖包继续；不能让每个迁移作者重建同一parser/adapter。每包回传结果/文件/验证/风险及净量，成本沿原进度记录汇总，不新建平台。

源码并行不等于测试并行：PG、coverage、frontend build/E2E各独占；pure最多2进程，使用独立tmp/cache/Hypothesis目录和明确不可达DB/服务端口，不写共享coverage。同一权威源、registry、shared checker及装配只能由集成owner在一致输入上sync/check。§3的local-index与streamplus可分作者删除，但`pre_release_gate.sh`由同一集成席串行清selector；item_writer先常量包后source包。ops贡献源/派生registry同样集中交接；已有七gate和相邻能力验证不因专属测试退出而降低。

## 6. 原验证入口

统一根cwd和原venv；下列是按影响面选择的原验证入口，不是本轮全量运行清单。各批实际执行及复用分别以§2.1/§2.2为准。不安装依赖，不恢复已停止历史部署任务，不新增测试调度/证据平台。

```bash
cd /Users/wangyiliang/market-research-workflow
focused() (
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD:$PWD/src:$PWD/main/backend" \
  DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:1/postgres \
  REDIS_URL=redis://127.0.0.1:1/0 ES_URL=http://127.0.0.1:1 \
  main/backend/.venv311/bin/python -m pytest -p no:cacheprovider -q -rs "$@"
)
```

| ID | 仍存在的原命令／约束 |
| --- | --- |
| V-ops | `focused tests/test_w07_failure_semantics.py main/backend/tests/core_business/test_api_group_b_core_contract.py main/backend/tests/core_business/test_admin_dashboard_process_core_contract.py`；符号引用清零及原V-kit，registry PG见证在独占PG窗运行，不把它伪当pure |
| V-index | `focused main/backend/tests/unit/test_policy_indexer_vector_contract_unittest.py main/backend/tests/integration/test_search_api_unittest.py` |
| V-source | `focused main/backend/tests/unit/test_source_library_item_resolver_unittest.py main/backend/tests/unit/test_source_library_runner_gray_rollout_unittest.py main/backend/tests/unit/test_collect_runtime_url_pool_adapter_unittest.py main/backend/tests/integration/test_t22_source_library_scrapy_collect_runtime_integration_unittest.py` |
| V-retrieval | `focused main/backend/tests/unit/test_project_retrieval_execution.py main/backend/tests/unit/test_project_retrieval_formalization.py`；原动态PG归V-durable |
| V-data | `focused main/backend/tests/unit/test_document_queries_contracts_unittest.py main/backend/tests/unit/test_document_views_unittest.py main/backend/tests/unit/test_information_topology_document_materials_unittest.py main/backend/tests/unit/test_writing_document_service_unittest.py` |
| V-control／V-workflow | `focused main/backend/tests/unit/test_agent_sessions_service_unittest.py main/backend/tests/unit/test_agent_batch_api_unittest.py main/backend/tests/unit/test_workflow_graph_runtime_unittest.py main/backend/tests/integration/test_workflow_graph_api_unittest.py` |
| V-project | `focused main/backend/tests/unit/test_project_customization_service_factory_unittest.py main/backend/tests/core_business/test_project_customization_core_contract.py` |
| V-wiring | `focused main/backend/tests/successor_runtime/test_c1_native_catalog.py main/backend/tests/successor_runtime/test_c8_graph_projection_contribution.py main/backend/tests/unit/test_workflow_graph_executor_kernel_unittest.py`；知识图已有catalog纯性、非默认registry、重复identity和真实装配见证作参考；在原workflow测试与V-durable补同源变化、非默认production、类型/identity/authority负向与无effect见证；本批workflow首例覆盖见§2.1，不外推其它能力 |
| V-core | `focused main/backend/tests/successor_runtime/test_program_ast.py main/backend/tests/successor_runtime/test_compiler.py main/backend/tests/successor_runtime/test_p3_traversal_foundation.py main/backend/tests/successor_runtime/test_p0d_event_replay.py` |
| V-durable | workflow首例复用下列精确命令及`test_p0c_postgres_activation.py`相关原见证；原`main/backend/tests/successor_runtime/{test_agent_batch_api_pg,test_request_cancel,test_mixed_operation_worker,test_traversal_persistent_activation,test_successor_production_wiring}.py`，设置实际专属`SUCCESSOR_TEST_DATABASE_URL`，fixture资源先核再运行，PG独占 |
| V-type／V-kit | `MRW_TYPECHECK_PYTHON=.venv/bin/python main/backend/.venv311/bin/python scripts/dev.py typecheck --public-boundaries`；原venv `scripts/dev.py sync`（有声明变更时）再`check`、`test`、`gates`；受影响原ruff保持，不手改派生表 |
| V-suite | `bash scripts/test-standardize.sh ci-pr -q`及原`coverage`入口，100/20不降；沿现有selector清单核精确新增/退役/资源分区，capacity原Unix-socket条件保持。只按实际交付与依赖跑，不由文档编辑触发 |
| V-host／V-ui | 沿实际改动选择原auth/typed-fetch/manifest/浏览器与写作API见证；真实provider调用需其原授权资源。无宿主适配改动不新加模型测试；vendor/generated分账 |

Runtime原见证沿`main/backend/tests/successor_runtime/`中的`test_p0d_event_replay.py`、`test_p0c_node_adapter.py`、`test_p0c_admission_recovery.py`、`test_p0c_delivery_recovery_postgres.py`与`test_p3_c2_3_recovery.py`选择受影响观察，分别进入V-core/V-durable及原fixture资源窗口。需要PG的见证必须使用已知专属数据库及原fixture，不能放进`focused`不可达DB环境；值与事务原消费者入口为同目录`test_p0c_postgres_lifecycle.py`的`test_runtime_value_index_and_staged_artifact_store_only_opaque_refs`、`test_terminal_outcome_updates_full_semantic_packet_atomically`及`test_authority_provider_rehashes_current_scope_grant_and_capability`，沿原scope fixture进入V-durable。row候选的同源变化若缺覆盖，只在原测试补最小读写/identity/失败见证，不伪称上述测试已覆盖新增义务。

workflow真实worker回放使用原`live_database`fixture，先核隔离并独占PG窗口；复用已配置专属地址，不能通过`focused`的不可达DB环境执行，保留原退出码。以下原测试已在本批实际执行default/alternate两实例，结果见§2.1；非默认production见证进入同一原测试文件，不靠增加生产业务功能证明扩展性。

```bash
PYTHONPATH="$PWD:$PWD/src:$PWD/main/backend" \
SUCCESSOR_TEST_DATABASE_URL="${SUCCESSOR_TEST_DATABASE_URL:?use the existing isolated PostgreSQL test database}" \
main/backend/.venv311/bin/python -m pytest -q -rs \
  main/backend/tests/successor_runtime/test_mixed_operation_worker.py::test_graph_facade_real_tasks_replay_exact_upstream_outputs
```

所有测试路径相对根cwd；不把已删local-index/streamplus/ops专属测试写作退役后的验收命令。引用清零使用现有`rg`并明确源码/脚本/贡献源观察边界；历史快照允许残留原文本，不要求改写历史。若原声明/门禁仍绑定该专属义务，先修权威源并sync，不跳过现役七gate。

## 7. 整体完成条件

- 必要能力、事实owner、真实effect、身份/当前权限和失败语义保持；明确停用能力已撤去公开与内部执行入口。
- services旧整体承载、successor冗余族、API/胶水及其它承载均完成具体处置；必要核逐项有依据，不能把全目录改名、委托或保留互相引用当退役。
- 每个实施包同源规则到达实际production/worker/reader消费者，旧接线与实现整族退出并达到发包前D/A_max/N_min；全项目必要核及互斥包覆盖明确，达到root据真实闭包裁定的总体区间与累计净减，不以注册或接入通过代替整体退役。
- 原注册/配置/派生见证/专属测试/文档同批一致；非默认同形定义到真实消费者且类型/identity/authority错误拒绝，声明/sync无effect；框架机制与项目迁移分别具备必要行为、公共类型、现役七gate及实际交付证据，operation/codec/kernel/reader保持具体类型关系，kept、skip、not_run与失败按原归属记录。
- 成本包含共同修复和跨目录新增；生产/测试/工具/前端/vendor/历史分列，不以删文档、搬家或旧dirty回撤抵扣。缺失调用/token和完整验收成本不记零，不报无证据提速。

内部全面类型治理、UI重设计、性能和新扩展建设不自动加入退出条件。它们也不能被拿来掩盖当前结构退役未完成。未经证明的硬规模承诺已撤回，其它包定界、代表性整族收缩与总体承诺校准仍未完成；这不授权永久保留完整services或旧runtime。

## 8. 上一轮迁移历史及本轮状态

上一轮结果已提交为`c3adced`：完成既选Runtime迁移与保持验证，但生产净减仅29行。原`LOCAL_COMPLETE_NOT_RELEASE_AUTHORITY`是当时迁移合同的本地闭合记录，不能继续作为用户全局退役/显著瘦身目标的完成声明。原文与逐attempt记录可用`git show c3adced:docs/development/MRW平台结构精简与删减阶段.md`读取，不在新当前章节重复重写。

原证据根`/tmp/mrw-structure-20261007-w4uct7gr`，最终`integration/ci-group-resumption-2.json`的SHA256为`878665a345cd21b3ab5002595b7f0835354c2ad3e5322b70aea6fbc8edbf848c`。原ci-pr-4和native coverage-2 exit1保留；Search15替换旧9后归属2668 passed/4 skipped，186subtests另账；原431补集为426原passed＋3 PG39 kept＋W04修后1＋PG40补运行1。PG39原21、七gate291、core/e2e原分步以及合并coverage core409/409100%/other69.41%保留原依赖边界，不因本次改写撤回，也不冒充新退役执行证据。

原frontend14含route mocks及Codex iframe mock shell，direct HOST1只证明注册写作工具/approval/turn及canonical API/SQL读回；内部类型/Ruff债、4skip和缺失调用/token成本继续保留。上一轮workflow＋999/retrieval＋3763/shared＋1594的独立增长责任进入本轮定界，source下降不抵消。

首批实际完成与attempt保留于§2.1；第二批旧generator、I1外壳及workflow静态资格链退役与返工集中记于§2.2；三份当前文档随批次交回集成owner统一提交。整体精简及全能力native规则贯通仍未完成，下一闭包按§5寻找与定界；未push或deploy，旧Stage4–6部署任务继续STOPPED。
