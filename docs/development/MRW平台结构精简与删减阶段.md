# MRW 平台结构精简与删减阶段

> 2026-10-09 · **文档规划的有限精简面已完成本地验收。** 本波从`cc1ea6c1`使app Python由641文件231238行降至632文件227991行，净减3247行；从`a17930da`的299234行累计净减71243行（23.81%）。九面处置、必要保留核、完整成本与分步验证见§5，整体退出判断见§7；不将分类、注册或单项门禁当作完成证明。§2.1/§2.2保留历史字节。平台必要能力和事实归属沿[MRW精简框架](MRW精简框架.md)，流程沿[19号规则](../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/19_direct-testing-batch-freeze-amendment.v1.md)；未push/deploy，[06号入口](../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/06_production-deployment-stage-progress.v1.md)的旧Stage4–6部署任务仍STOPPED。

## 1. 退役终点与边界

本轮按“typed语义/特殊kernel → native rule派生 → production声明查找、handler安装与reader → 同批切断旧路径并整族删除”组织。终点是必要能力由最小现有核承担，重复声明、装配、注册、旧adapter/执行owner及专属tests/checkers整批消失，并按事前预算与最终明确校准的实际成本验收。未达原预算的偏差保留，不以其它包收益冲销。保留用户能力、对象身份、权限、真实effect和失败观察，不默认保留目录、API、测试或checker。每包明确是停止冗余功能，还是保留能力的实现替换；前者记录撤回范围，后者证明原必要观察保持。

services旧整体组织承载与successor重复承载都在退役范围，API/胶水和其它app源码不漏账。必要领域类型、特殊kernel、provider/DB效果逐项证明后接已有原生贡献位置，不把services全量搬家或包装进新runtime/domain/DSL。唯一耐久Runtime沿既选内核，领域writer、DB/provider和host权威不转给API或投影。真实必要核在原文件承载，每项均具名说明职责与消费者，没有整文件/整目录保留豁免。

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

## 4. 有限删除波次与待重构组合

本节保留此前各批输入时点、预算、调查与集中结果；其中“当前”“待齐”和“下一切口”均归当时记录。2026-10-09最终状态以§5及§7为准，不重新打开历史工作包。

用户要求继续完成整体精简。本轮从`a17930da7a542f4d2cc5a6eb572baaa5004032b0`实施九项能力覆盖下的有限删除波次；它不是全部剩余架构工作的穷尽清单。§2.1、§2.2及§3保留已提交历史，不重做、不重计收益。下表包含十路径账与app以外的前端、kit、工具和ops，后文分别记录已实施闭包、当前集中验证与仍待重构的真实语义组合。

每项调查必须在一次有界读源与消费者追踪后形成四类处置之一：**可删除**（无必要现役职责，退出精确闭包）、**同形收敛**（原消费者转向已有权威接口并同批删旧）、**特殊核保留**（具名符号、不可派生职责、唯一owner及必要观察）、**真实阻塞**（精确缺口、owner、blocked_by与解除条件）。引用存在只证明需要追踪，不给整个services或Runtime目录保留资格；未知项不能当已保留或已完成。混合族按符号分别处置，不以一个必要kernel保住外围整族。

每个实施包均沿本表回填精确源/consumer/test/tool路径及`D/A_max/N_min`后执行；抽取、派生、公共接缝和跨目录替代全部入A。九项不另凑全目录行数帽，按下表已批准的真实闭包分别核预算，未变必要核按具名原consumer验收；尚未定界的具体切口明确列出，不将物理行数当可删量。调查输出直接回填本表或现有阶段结果，不新增包文档；不能连续只回“待调查”而不交具体删除闭包、保留核或真实阻塞。已证规则直接复用；真实新接缝由唯一owner用一个原消费者贯通后再释放依赖它的同形包，无依赖工作照常执行。

| ID／目标与权威输入 | 输出及必须具名的保留边界 | 独占写面／共享依赖 | 当前闭包、原验证及退出判据（包预算见下表） |
| --- | --- | --- | --- |
| **R1 来源与采集**：原source contracts/resolution/acquisition贡献、`services/source_library`的item writer及现行collect/crawler桥接 | 删除重复候选/调度/结果包装；source item身份、provider协议、材料writer及不可推导的采集kernel分别具名；从原来源API到实际worker、provider边界、持久化读回确认唯一执行owner | 来源作者独占source/collect/crawlers相应符号；与R2交接候选、与R3交接材料；production和原生目录由集成改，同一item_writer不并写 | C2、sourceContract两次裁剪及LongCycle闭包见下表，最终原consumer验证待齐；§6 V-source及原source/crawler durable见证。API动作到实际运行与readback一致，旧loop/adapter不再可执行，默认字段、权限、失败和UNKNOWN保持，完整闭包达预算才关闭 |
| **R2 检索与资源**：`retrieval_{candidate,material,flow}_native`、`retrieval_native_catalog`及`services/{project_retrieval,search,resource_pool,discovery,indexer}`原合同 | 同源输入/结果与原Program组合消除重复派发、递归/批次控制及codec装配；搜索provider、索引派生、方法/预算、动态child语义逐个保留或收敛，不将native投影当worker安装 | 检索作者独占retrieval族；R1来源候选和R3材料kernel接口只引用；production/activation/journal shared由集成单写 | 默认candidate/leaf必要核已定；semantics声明层与fixed-flow/method_flow孤岛已收缩，局部pure已证；V-retrieval＋保留native catalog/AgentMacro及V-durable traversal PG。真实候选派发、子项commit、结果读回及失败恢复到同一owner；引用循环或纯测试不算执行闭合 |
| **R3 材料导入与数据读写**：原`Material`/Document别名、ingest/crawlers effects、material native贡献、document queries/views | 合并旧写入壳、重复事务装配及读投影；正文与材料identity、导入幂等、抽取特殊核、canonical writer和投影loss分别具名 | 材料作者独占ingest/document/material相关符号；R1 provider与R4知识/写作consumer按明确接口衔接；原材料writer与跨域共享消费者由集成协调；C7专属admission/terminal已随原型退出 | M1历史局部attempt与C7/C9最大岛退役同文件不重计；RawSnapshot/3errors迁回产品，最终验证待齐；V-data材料部分＋现役material_input/submission_registry/ingest API与实际材料PG读回；已退C7专属native/admission测试随族退出。真实导入到材料持久化/读回保持，投影不取得写权；旧writer/adapter闭包退出且预算达成 |
| **R4 知识、信息结构与写作**：information_topology/typed_knowledge/graph原合同、WritingDocument/Draft/Citation及原writer；C8专属native binding已退 | 删除同义DTO/装配/读取包装；知识关系identity、图投影、引用来源、草稿/发布版本与ETag、LLM/report特殊effect有具名保留核；已退I1 knowledge壳不重建 | 知识写作作者独占领域/贡献符号；消费R3材料，原production及跨族API由集成协调；C8专属terminal/projector已退 | K1–K4历史局部与C8最大岛退役不重计；真实TypedSQL/Graph/writing核保，最终PG/HTTP待齐；V-data写作/拓扑＋现役TypedKnowledge SQL、Graph、writing/LLM API的实际PG/HTTP；已退C8专属测试不再作为退出义务。材料到知识/引用/报告真实消费者保持，当前授权、版本冲突及canonical owner保持，重复承载同批消失 |
| **R5 宿主、Agent与业务工作流**：CoreToolSpec、agent_core工具、agent_batch/session原合同、已证workflow runtime definition与handler | 删除第二执行循环、静态资格/观察壳与重复工具安装；保留宿主推理、工具effect、task业务事实、session派生视图、workflow node kernel和历史reader；首二批已退cell/catalog不恢复 | 宿主作者独占agent/workflow领域符号；batch路由与R1/R2实际dispatch对齐；共享production与app入口集成单写，frontend交R8 | Host与batch/task observation闭包见下表，纯局部已证；业务readback/UNKNOWN实际PG待齐；V-control/V-workflow＋V-host及原batch/session PG。工具/API→真实dispatch→worker→canonical读回闭合，单一运行owner，no-effect构造及旧compiled运行需recompile语义保持 |
| **R6 项目治理、API与根胶水**：项目实体、原grant/auth、customization/subprojects协议、governance/stats/aggregator及API envelope | 沿必要用户操作合并透传层和重复组装；租户/项目隔离、管理权限、retention效果和领域统计含义各有具名核；API只适配输入/输出，不复写领域事实 | 项目/API作者独占对应入口与根services胶水；域API随R1–R5各自consumer切换，跨域公共auth/main由集成单写 | 具名原项目/同步workflow/治理/统计核保；旧reports端点闭包已批，shared路由与API验证待齐；V-project、V-ops与实际改动API/权限原见证。保留必要操作与授权，已退功能无公开/内部入口；不得因为有API import就整目录保留，也不得删route假装重复已消除 |
| **R7 选定Runtime与生产安装**：Program/AST/compiler、原状态表、ports/current grant、claim/commit/journal/UoW/recovery及`composition/production.py` | 同源构造替换重复model/codec/装配/校验；保留身份、版本、事务/CAS/seq、UNKNOWN、cancel、真实未开始证明及外部effect边界。优先核余下source/batch/material/task_observation family assembly是否仅服务旧native装配，再切精确闭包 | Runtime作者独占已定kernel符号；root裁跨族公共接缝，集成独占production、assembly基础/导出、有效目录与贡献sync；不与领域作者重复实现adapter | 既选durable运行owner与SingleDispatch ABI静态核已证；大原型岛退出及最终Runtime PG待齐；V-core/V-durable/V-type/V-kit。一个运行事实owner，原真实worker/PG/readback及错误绑定/过期grant/rollback保持；保留核具名且无新通用Runtime、manager、schema或安装层 |
| **R8 前端、WebUI与宿主适配**：`moduleManifest.ts`、现行typed API客户端、Graph/写作/Agent页面及WebUI边界 | 原manifest/类型直接驱动重复routes/注册/客户端投影；保留真实交互状态、授权与宿主生命周期，区分vendor原件和MRW定制；服务端退役后的死入口同步移除 | 前端作者独占frontend与MRW宿主适配；依赖R1–R6已确定API，不反向猜域语义；auth/host公共入口集成协调 | F1/K3/C9前端源码已收口，最终Node构建与7项shell browser已过；fresh backend与direct-host实际E2E已按本节集中结果分时点收口；V-ui对应eslint/strict tsc/build及真实浏览器原见证。用户操作到canonical API读回成立，列表收集/mock不替代实际E2E；不附加UI重设计或性能工程 |
| **R9 kit、工具、ops与验证消费者**：原贡献权威源、registries/sketches、dev.py、现役runner/selector、生成器与部署工具 | 随真实职责退役专属脚本/校验器/test；重复机械注册由已有规则派生；保留通用kit机制、历史只读reader与原冻结字节。owned ops、search-lab、local入口、迁移脚本及vendor内MRW定制均分类，不以archive标签逃账 | 工具作者独占无共享脚本；project_catalog、shared checker/selector、sync及派生表由集成单写；各R包提供消费者切口，工具收益不抵app新增 | 本波工具机械覆盖未判定面已清零，不代表全源码语义审计；最后4个search-lab资格工具退役及完整suite/planner/类型/七gate结果待齐；V-type/V-kit，原mixed metadata/history tests及真实受影响runner。退役代码无当前执行caller，必要mixed见证保留，七gate保持；历史baseline不被当作随sync已重写 |

原四个family assembly观察面共2663行（source395、batch355、material1131、task_observation782）现已随各自闭包退出，不能再作为未开展调查或重复删除收益。shared base保留真正工作流所需部分，由Runtime作者统一收缩后交集成验证；初始base569行从未是整体删除授权。下表记录本次已定互斥删除包的实施过程；其局部“待验证”状态由本节集中结果覆盖。剩余架构工作还包括下列具名业务组合，不能缩成仅补suite、类型/七gate、PG与用户读回。

### 本轮局部包、预算与当前状态

下表记录从`a17930da`继续的实施合同与局部实绩，不是整体完成结果。局部包不关闭所属R项；源码仍在变动时不把中途diff写成最终实际，实际D/A/N在稳定后按同一基线复算。测试、工具和app分别计量。M1/K1/K2的先前局部实绩保留为attempt；后续C7/C8整岛删除与其覆盖同文件，最终只能按`a17930da`到当前NUL numstat计一次，不将先局部、后整删收益相加。

| 所属项／实施闭包 | 预算／实际计量 | 必要保留与当前状态 |
| --- | --- | --- |
| R1／C2旧资格、安装与canary闭包 | 调查预算app D11287/A0/N11287；实际18 app文件D11269/A0/N11269，root已接受按统一git口径校准；原脚本每文件尾行多计1行，范围仍为18文件；15专属tests D5018另账，共享接线另计 | 作者闭包已删除source assembly/native、resolution/planning/provider程序与interpreters、single_source_guard_port、C2.1/C2.23 handler/canary及旧terminal projection。保留`source_contracts.py`内现役provider读回/取消类型、真实item_writer、service single_source_guard、terminal_output与crawler base/bridge/adapter。实际production封闭operation安装不含C2；源码引用只读检查未见hidden dispatch。作者7个保留kernel的py_compile通过仅证明语法；共享source贡献、W06/W08D/W08E、S1/S2与C2-runtime-failure混合消费者仍由集成修复，未记pytest或总体通过 |
| R1／source_contracts孤C2类型/codec/operation尾段 | source D≥635/A=0/N≥635；当前实际D663/A0/N663 | root批准保守移除无消费者planning/codec/operation片段，真实provider readback/cancel/source类型保留；不是source_contracts整文件豁免 |
| R1/R3／LongCycle probe岛 | app D≥3250/A≤60/N≥3190；7专属checker tools D≥728/A≤60/N≥668，分账；当前app实际D3257/A0/N3257，time-gate tools D8/A2另计，专属checker最终账待回填 | 退digestion scaffold、同进程live-runtime探针及专属model/checkers，冻结migration原字节保留且不drop表；`build_time_semantics`仅gate消费，复用原time-density fallback，必要移出成本计回本族，不新增facility |
| R1／sourceContract第二裁剪与LongCycle旧合同 | sourceContracts Stage2 D≥903/A0，保Collection union；与Stage1合并后当前同基线实际A37/D1707/N1670；`contracts/ingest_digestion` D≥733，实际待统一账 | root已批准孤planning/parser等残留及旧探针合同退役；原Collection outcome联合与真实采集类型保留，不能按静态计量误删union成员 |
| R2／retrieval semantics声明层收缩 | source D≥148/A≤30/N≥118；局部actual未单列，实际改动已纳总体机械账 | 退Source/Definition/NativeRule/无effectassemble镜像，原catalog直接引用既有ProjectedContributionSpec；独立只读对照已确认原id/owner、topology_failures、project_retrieval_failures及topology_state_codec三个原权威对象保持，当时registry与消费者验证待集中，当前结果见本节集中表 |
| R2／fixed-v1与method-flow孤投影 | source事前flow D91＋method D265＋shared约D30，tests D219另账；实际两专属source D356/A0，shared作者报约D26待统一账 | fixed-v1 native定义与无执行caller的method-flow projector/profile/validator已同族退出；`retrieval_common` Flow primitives相对基线无diff，AgentMacro真实路径保持。旧flow/default/method名称在app/src/contributions引用清零；AgentMacro＋native catalog 8 passed、candidate runtime/consumers 18 passed，exit0，无独立日志，仅工具记录。真实动态PG与整体验证另计 |
| R6／旧report单端点 | source D≥212/A≤15；实际待回填 | root已批准撤回`POST /api/v1/reports`旧接口，无生产frontend调用；同步API mount、business-line metadata与mixed tests，当前LLM/writing入口保持。这是有限兼容损失，旧payload不自动兼容当前接口 |
| R3／M1 material旧LOCAL_OFFLINE rollback镜像 | 作者source D≥429/A≤25/N≥404；shared base D≥11/A≤3；合计source D≥440/A≤28/N≥412，tests另账 | 源码局部完成，联合实际D451/A24/N427，其中作者D445/A22、shared base D6/A2，tests D43/A0另账。保留原C7.1 Program、native compile/project/assemble、C7 admission及canonical writer/projector/registry handler。实读确认`staged_candidate`、`commit_readback`、`projection_diff`三个原profile ID都被真实路径需要，均保持；仅退四个旧interpret函数、outcome壳、reconciliation ID及旧fixture路线。base由集成单写；4个pure selectors实际22 passed／exit0，日志`/tmp/mrw-all-material-pure-20261008.log`；当时真实C7 PG尚待集成，后续原型闭包退役及当前验证见本节集中结果。Ruff因venv无模块未执行成功，不算通过 |
| R4／K3写作假LLM端点与primary loop | joint backend＋frontend D≥900/A≤10/N≥890；backend D≥750/A≤10/N≥740，frontend另账且不与F1重叠；实际joint D928/A1/N927（backend D765/A1、frontend D163/A0）；tests D460/A16、stories D145、tool D26独立计量 | 原900行误标为backend预算，实为joint，已校准而不加删凑数。root已批准退役假LLM入口与相应primary loop；保留真实Core AI、agent_updates与ETag路径，不能撤回实际写作权限/版本语义 |
| R4／K4死Jsonl typed knowledge存储 | backend source D≥130/A≤5/N≥125；实际D141/A0/N141，tool D93、tests D58另账 | root已批准无现役消费者的Jsonl承载退役；typed PostgreSQL writer及其实际读回保留 |
| R8／F1未挂载双ReactFlow设计器 | frontend＋config D≥5000/A≤100/N≥4900；实际source D5350/A5/N5345，config D329/A3/N326，joint D5679/A8/N5671；tools D123/A2、stories D199另账 | root已批准退出两个未挂载设计器；保留实际WorkflowManager、module ID、routes/hash与AppShell，必要浏览器验证不以文件删除或tsc替代 |
| R5／Host Core工具目录同源 | source修订D≥395/A≤145/N≥240（原330/90/240漏计准确schema/权限/状态投影）；实际D397/A136/N261，tests D6/A40另账 | 已进入实现。工具发现复用原CoreToolSpec与已注册handler，退出两个复制ID集合、标准工具清单和被同ID覆盖的read/control投影。root已授权发现全部现有105个Core工具；权限、feature flags、stream及MCP状态仍需保持。已修复SSE HTTP能力误标为未实现的回归，implemented仍由原capability声明提供；真实read-only调用复用已有service，默认fallback仍可构造DB store，故不作全局no-effect结论。作者最后4文件pure 34 passed／exit0，原输出仅在任务工具记录，无独立日志；Ruff无模块未成功执行 |
| R5/R7／A：batch旧plan/retry/submission安装族 | source D≥2500/A≤80/N≥2420，含共享成本；当前闭包实际D2984/A24/N2960（含本族共享与orphan store退役） | root已批准旧assembly/native/store、canary/quality、旧handler尾段及program/interpreter闭包退役。保留真实single dispatch API→Program→BatchTaskSingleDispatchHandler→ACK/business readback，PersistentOperationHandler、UNKNOWN、CAS和恢复保持；batch DTO第二个依赖切口须另给精确scope与预算，不能混入此包 |
| R5/R7／A的第二依赖切口：batch旧DTO/contract bundle | **事前数值预算缺失**，root已接受其独立实际；orphan acceptance类型再退后D2532/A145/N2387；不并入outer A的A≤80 | `batch_task.py`旧DTO与bundle收缩，保留AgentBatchSubmissionItem、DISPATCH_SINGLE payload/ACK/profiles/contracts/codecs/catalog/registry、dispatch身份、failure ABI；后续实读确认submission store无消费者，连同其唯一BatchTaskAcceptanceState退出。root已授权该语义范围但要求先报精确scope/budget；最终本族shared收口后纳入83项pure通过，当时真实PG尚待集成，当前验证见本节集中结果 |
| R5/R7／B：task observation旧装配与line-event镜像 | source D≥2423/A≤35/N≥2388，含共享成本；当前闭包实际D2561/A14/N2547，含本族shared收口 | root已批准旧assembly/native、line-event port、legacy projection及明确历史bridge/tail/base options退役。保留API/process当前normalize/join、真实agent-session与Runtime projector/reconciliation；旧historical bytes reader、identity与line-event桥仅由本退役族自环消费，随族退出且无replacement；保留的是当前观察normalize/join与真实PG projector，不声称保留全部历史读取API。本族shared导出/base已由root交回Runtime作者一次收口，最终纳入83项pure通过；当时真实PG尚待集成，当前验证见本节集中结果 |
| R9／旧wave资格checker与C9/I1/R8生成验证工具 | tools D≥3170/A=0/N≥3170；专属tests独立退役与计量 | 已进入实现：13个wave8–20 checker及5个旧generator/verify退出；混合raw-reader继续独立核原字节。ACTIVE_MUTABLE map只允许state/kind历史化，path、IDs与hash不动；集成统一跑仍存历史reader和必要gate。tools预算不抵扣app成本 |
| R4／K1非图C8旧装配镜像＋K2无消费者report bridge | **事前数值预算缺失**，不倒填；root已接受实际source D343/A2/N341，其中K1作者D174/A2＋shared exports D16/A0，K2 D153/A0；tests D79/A4/N75另账 | K1修改`knowledge_native_contribution.py`、`typed_knowledge_contribution.py`、`knowledge_writing_contribution.py`、`knowledge_report_contribution.py`及共享`capabilities/__init__.py`，退出旧AssemblyDeclaration→definition/binding→CellBinding/rollback镜像。K2仅在`knowledge_program.py`退出closure helper与3步report build/compile；保留原handler_binding_payload、bridge bundle、5步delivery、真实native operations/profiles/codecs/program、graph及PG路径。局部78 passed／exit0，日志`/tmp/mrw-k1-k2-pure-20261008-r3.log`；未据此关闭R4 |

K3/K4局部focused最终69 passed／exit0，日志`/tmp/mrw-k3-k4-pure-20261008-r3.log`；首轮67 passed／2 failed（`/tmp/mrw-k3-k4-pure-20261008.log`），一项是3条API退役后的总数预期23改20，另一项是W04当前源码检查仍要求已退役primary loop存在。冻结packet原51个derived keys与原字节均未改；现役测试显式声明retired target并断言源文件消失，对其余50项继续严格authority比较。前端与真实PG尚未由本作者执行，归集中验证；Story和工具删减不抵source预算。

共享责任已按实际返工重新划分：集成席曾连续只完成一个小文件即结束，root已把R7自族shared base、assembly导出、`src` batch/task贡献及专属/混合fixture交回Runtime作者，使同一闭包一次贯通。集成席完成C2剩余W06与build-registry两个切口后，集中负责sync/check、pure/PG和前端build；两个owner不同时写R7共享面。该修正沿现有职责，不新建管理层。

C2曾错误整删runtime-failure closure测试，遗漏仍保留的literal、fail-closed与serialization义务；root已恢复3组并实际取得8 passed。该修复不抹去错误退役attempt，测试恢复成本计回本族；共享闭包完成前仍不宣称C2整体通过。

R7只读ABI复核以当前HEAD为对照：`batch_task.py`保留32个class/function、interpreter11、submission handler2、program15的AST均未变，保留常量/类型赋值除`__all__`外未变。SingleDispatch contract继续使用原input/ACK ObjectType、profiles及exact codec；production封闭facts分支做完整ref比较，handler保持scope/incarnation/capability及ACK关联检查。PersistentOperationHandler仍先读canonical输入并验证，再跨invoke effect，未分类错误保留UNKNOWN，输出经原adapter/UoW发布。现行链为API→dispatch Program→production/journal→Celery worker→RuntimeNode/NodeAdapter CAS→SingleDispatchHandler→terminal activation→business readback；Node纯算法、Adapter事务、Journal运行事实、ActivationBinding值与边、Reconciliation UNKNOWN原子采纳各有不同职责。这是本裁剪的静态保持证据；后续pure结果见下一段，当时真实PG待补齐，当前结果见本节集中表；该静态链不独立证明九项全局已收敛。

R7在shared收口及orphan store最终退役后实际重验83 passed／4 warnings／2 subtests／exit0；仅当前dispatch/auth/readback/catalog selectors，不是PG或全套gate。`batch_task_submission_store.py`经无Python消费者确认退出，8行唯一acceptance类型/导出计回DTO；原D2524/A145/N2379是该尾修前实绩，最终DTO为D2532/A145/N2387，outer与B分别按表中最终族量计。

以下保留本轮收口前的消费者调查，用于解释后续处置；R2仍是现役链路，R3两行所述C7声明/admission已随下文原型闭包退出，不是当前保留项。不能用sync/check统一概括这些不同状态：

| 具名声明与核 | 实际consumer与可确认范围 | 未成立的更强结论／剩余处置 |
| --- | --- | --- |
| R2 `build_retrieval_candidate_runtime_definition`：v3 contract、输入/结果/budget codecs、profiles、Program atom | `project_retrieval/execution.py`与production facts/handler共同调用该builder；native candidate lower也复用它构造默认定义 | 支持默认v3定义同源；不证明native catalog实例驱动worker，也不证明更换任意native source会自动穿透生产安装 |
| R2 `build_retrieval_leaf_definition`与CandidateWork/RetrievalControl | execution的child/root Program与production handler读取相同contract/codec/profiles；provider、review、followup、topology commit分别为原kernel | `retrieval_flow_native.py`中fixed v1独立投影及无consumer的method-flow现已退出；真实dynamic traversal仍在execution.py构造，Flow primitives由实际AgentMacro保留，动态组合与PG另验 |
| R3 已退MaterialNative及其assembly（退役前调查） | native `.assemble`显式传`canonical_write=None`、`projector_driver=None`；当前API/services/composition无实际C7 handler入口 | 这是声明/离线binding，尚非现役ingest worker安装。root已要求连同无真实user consumer的C7/C8原型岛按最大闭包退役定界，不能只退壳而因内部PG测试保全部kernel；不新增adapter凑全能力贯通 |
| R3 已退`c7_production_admission`与原型canonical writer（退役前调查） | 独立bounded runner能写C7专用canonical表并seed缺失Runtime行；既有PG见证覆盖其直接路径 | 非tests Python未发现runner真实caller，仅native字符串ref。其直接PG成功不证明现役API→worker→材料writer接线，也不构成必要保留理由；需与现役ingest/MaterialEntity、TypedKnowledge SQL、informationTopology/Graph和writing用户链逐项比较，无用户消费者的重复writer/admission整族退出 |

对“必要核”的本轮裁定以实际用户能力与事实owner为依据：native/CLI/测试回调、自seed研究表和真实PG读写本身都不能证明生产必要性。R7已完成C7/C8原型岛退役，真正源类型、provider消化、authoritative MaterialEntity及当前SQL/Graph/writing用户链保留；不同语义名字不自动保留两个同职系统。`digestion_scaffold`/`long_cycle_live_runtime`已确认无API、Celery、tasks或composition入口，queue消费与dispatch/succeed在同进程探针直接transition，所谓live flags在函数内赋值；其DB读回只是bounded rehearsal，专属checkers不使其成为生产scheduler。该岛已按实际`build_time_semantics`消费者收清闭包，冻结migration原字节保留；下文记录最终范围，不再列作待退役现存实现。

C9公开兼容性撤回已由root明确批准：`POST /api/v1/material-projections/v2/commands`与`queries`（rebuild_projection/projection_snapshot，local_only及production_registry）均退出，不加空响应或兼容路由；health的prototype projection字段退出，authority/queue/reconciliation保持。现役ingest/source-library、typed-knowledge、information-topology/Graph和llm-report接口各自承担用户能力，并非旧C9 payload的同形替代。startup、facade、health及检入权威`production_route_bindings.json`须同包同步，后者无generator，按真实路由删除3条writing、2条C9及1条旧report绑定；作者回报当前308条。startup/public mount与health已收缩，当时剩余原消费者、真实PG及route检查待集中，当前范围与结果见本节集中表。

C9退役过程的独立消费者复核曾发现前端遗漏：当时`sysSuccessorRuntime`仍经manifest与moduleContributionRule挂载`SuccessorRuntimePage`，其config和typed client仍请求已退役的`material-projections/v2`；不是只有静态export残留。该页面、导航、客户端、专属组件和测试须由前端owner纳入同族有限撤回，不能保留404入口或改指向不兼容的新payload。root已交前端owner独占执行：5个专属生产文件共2281行（client实为2004行），预算D≥2281/A≤25/N≥2256并计shared成本，3个专属测试另账。前端作者已完成同族撤回，实际source A4/D2318/N2314、tests A2/D3409/N3407；此前F1的Node结果不复用到变化后的输入，已重跑如下集中前端验证。

C9前端最终tsc、eslint、business-string、topology、layer-shell、i18n-disjoint、writing-contract、Vite build与Storybook build作者均回报exit0，日志沿`/tmp/mrw-frontend-c9-*-20261008.log`，最终构建分别为`build-final`与`storybook-build-final`。business-string仍有1267项已分类迁移gap，扫描通过不等于已消除。浏览器`business-chain-guide.spec.ts`4项加`homepage.spec.ts`3项实际7 passed（38.1s），日志`/tmp/mrw-frontend-c9-browser-final-20261008.log`；API proxy明确指向不可达`127.0.0.1:1`，只证前端导航、module装配与现WorkflowManager路由。该7项不是真实后端、Codex WebUI或本机宿主链证据；18项realbackend与direct-host的实际范围见本节集中结果。

R6当前具名保留核沿真实consumer成立：Project实体及typed CRUD/tenant bootstrap由projects API消费；context/request actor维护项目绑定；WorkflowDefinition/WorkflowStep经项目workflow服务、原CoreToolRegistry与`interpret_ordered_sync`调用真实ingest kernel，是同步组合而非第二耐久journal；ingest_config承载真实template版本/stage/rollback；retention直接维护四领域表，aggregator有真实跨库同步入口；prompt_time_density由stats端点读取Document及decision log。这些职责保留原类型/权限/失败与效果边界，不以services目录作为保留凭证，也不为统一口号把同步CRUD强行durable化。原API/PG验证仍需覆盖本轮影响。

LongCycle时间fallback的只读比较确认原9个返回字段、ISO/UTC解析、source不晚于processed＋1日选择、0.95/0.5/0.2 confidence、provenance/parse-version和7日inclusive边界一致。两个仍存gate只消费固定合法样本的effective/processed时间、provenance和窗口边界；复用现脚本fallback保持该观察，不声称DTO类身份、Failure元数据及任意窗口输入全面相同。

root已批准C7/C8/C9整族原型闭包退役，调查取得有限源码面：C7 D10573、C8 D15520，合计source D26093/A≤140/N≥25953；必要RawSnapshot及3个registry error移入现役领域文件，成本计回本族。专属tests14670独立，不抵source。C9 unwritten三源/直接C7查询壳另source3603、tests6737已纳批准闭包，已知source合计29696，shared cleanup另计；其put仅tests、API health/facade只load，不能把空研究源reader等同用户writer。以上为批准scope与调查预算，不是实际退役收益；source与tests相加的51103也不是源码D。

C7/C8/C9作者后续精确63-path清单计D39456，其中`main/backend/scripts/c9_projection_rebuild.py`为tools D1621；按职责分账，62个专属source实际D37835/A0。此前29696只覆盖已知子集，不能把补齐闭包视为额外通过证据。28个shared路径原计A178/D1625，包含config D163和tools D15；这些成本以及与R7/C2的exports/base重叠须在root全局基线账去重。必要搬入和HEAD既有workflow依赖边界修复使新增178超过原A≤140预算38行，root接受具名成本，保留偏差，不回填事前预算。

C7/C8/C9 backend在sourceContract稳定后，原material handoff、API persistence边界、route-registry精确覆盖和production bindings/startup五个selector共14 passed／3 warnings／exit0（2.73s）。`/tmp/mrw-runtime-structure-poststable-pure-20261008.log`是作者对已完成工具输出的转录，未为留档重跑；该局部通过不包含PG或整套gate。此前53 passed／2 failed中的source中间态及HEAD已有workflow assembly跨层import错误保留，后者修复成本计入shared。

上述退役闭包在当时scope下的独立只读复核确认15个现役通用文件与`a17930da`逐字节相同：Runtime node、activation、admission/coordinator、reconciliation、authority-grants，以及PG journal、nodes/adapter、reconciliation、authority/provider、session、research-admission、terminal-authority。runtime目录退出的4文件为C9 facade/projection专属；ports只退旧line-event/projection-offset桥，object_contracts只退C7 admission扩展，first-specimen现役生命周期保留；专属generic handlers后来退出，见本节集中结果。workflow assembly原跨services导入移回production owner注入，并保留真实invoke/bind/settled-failure边界；作者两个相关见证各1 passed／exit0，仅证该局部修复。后续领域Failure运输修复已改变其中的Runtime node、PG node_adapter等文件，原逐字节结论对这些文件不再有效；最终保持判断改看该修复的原消费者pure、PG和user readback，不把退役当时的scope复核写成当前全局结论。

K1/K2首轮宽集`/tmp/mrw-k1-k2-pure-20261008.log`为90 passed／3 failed／exit1；本包旧测试预期已修，二轮`/tmp/mrw-k1-k2-pure-20261008-r2.log`为91 passed／2 failed／exit1，剩余两项为C2同步中`source_native_contribution`退出后的共享catalog引用，归集成修复。本包78项局部通过不覆盖这两项，已知同因不重复跑宽集。K1/K2依据全范围推进授权执行，但漏给事前D/A/N，作为过程偏差保留，actual不冒充原预算。

M1最初把source与tests相加成D470的数字已纠正，不能用于源码净减。Host的早期“registry构造无外部effect”也已由实际DB连接尝试修正，SSE不属Core handler并不等于HTTP能力未实现；保留这些偏差用于本包收口，不用较早pure通过覆盖后续修复。R1余项、R2/R6首个可执行闭包及R4/R7/R8余项仍沿九项清单继续，不以本表局部包代替全部剩余工作。

R1第二裁剪的独立AST复核发现机械删改错误：保留的Provider/Readback/Collection类丢失`@dataclass(frozen=True, slots=True)`，Protocol丢失`@runtime_checkable`；其构造、不可变性与运行时协议检查因此不保持。原owner已按HEAD恢复；独立复核当前152个保留class/function/assign/alias完整AST差异为0，包含装饰器、字段、默认值与方法。ProviderEffectOutcome原8支、ProviderReadbackResult原3支、SourceCollectionOutcome原7成员保持；现app/src/contributions/scripts的4个importer所需10个名称全在，文件内无已删声明的剩余Name Load或精确字符串annotation。原owner随后释放`STATIC_SOURCECONTRACT_STABLE`并回报focused pure 69 passed／exit0，原输出仅在任务工具记录，无独立日志。12个文件覆盖C2 failure closure、crawler durable effect/remediation、retrieval catalog、W01 contract/request、ingest failure lifts、W03 raise inventory、API envelope/schema及两个time gates；不等同全量gate。最终git同基线A37/D1707与原A0预算存在偏差；中途A3/D1639口径未与实际git一致，不用作最终数值，返工成本计回本族。

R8本机与代理入口分别验收：`CodexAgentPage`在显式loopback HTTP页面进入`http://localhost:8172/?mrw=macro-host-v1`，WebUI复用原direct-loopback `/api/auth/bootstrap`与JWT owner；只有`/codex/`部署走MRW cookie exchange。root已裁定不为SIMP08缺cookie而新增认证方案或扩大localSingleUser allowlist。真实本机bootstrap→status→project context→macro-host→canonical读回已完成，实际范围见本节集中结果；旧cookie代理lane未运行必须明确记为未验证，mock iframe、可挂载或skip均不作为live host通过证据。

### 当前集中结果与计量边界

本段为本轮最终稳定源码读回；前述局部包保留发包预算与失败attempt，不将不同源码时点的通过数相加。按tracked Python文件的`splitlines`计：app从737文件299234行变为641文件231701行，A1319/D68852，净减67533行、22.57%。app内6个JSON共13553行另账；含JSON的245254行不能混入Python口径。从接缝修复前231465行到最终源码增加236行，覆盖本批Failure及plan-aware replay改动；installer接缝净增7行也已计入app。该236是同口径app快照差，不与不同基线的六源隔离估计混算；不以测试删除抵扣修复成本。前端A9/D8175净减8166，kit/contributions A56/D2066净减2010，tools A4/D7232净减7228，配置/其余派生A83/D1860净减1777；测试A1755/D48541净减46786，175个路径独立计量。测试不抵源码，文档最终由集成封存。机械账沿`/tmp/mrw-final-validation-20261008/current-size-account.json`，较早231457／231465快照不是终值。

collect重构四源合计A450/D2207净减1757，已包含在app总账；旧Plan/LegacySnapshot/ResourcePolicy/ElementOutcome/Sequence/Aggregate/Traversal及policy typed-view中间组织退出，既有`interpret_ordered_sync`、只读`CollectBatchRow/Counts/Fold`承担有限有序组合，adapter保留真实provider effect。原policy writer、raw digest、receipt身份未变；policy无终态观察时仍是UNKNOWN，collect按目标完成而非局部调用成功判定fail-fast和最终结果。旧typed debug envelope/error_digest为明确有损投影，policy投影版本升为v2、batch-fold为v1。修复过receipt投影失败清空实际计数、无counts隐藏错误、ACK后继续发effect、终态失败误判成功及fallback错误顺序六类偏差，返工不能省略。最后受影响用例及集中native覆盖承接rev3，较早局部43项不再累加。

`first_specimen_handlers.py`整族source D2020、专属tests D1408、kit D27及本族export D4已退；source同样已计入67533。`first_specimen_activation/terminal/reconciliation_handler`与`runtime_lifecycle`的真实生命周期保持，不能把handler退役扩大为first-specimen全族消失。写作投影仅同源contract_version和一次归一化，source A22/D19净增3，经root接受；原D85/A45预算未实现，保留偏差，不报删减收益。dry/locked的zero-writer及success/replay写次数由后续2项实际通过补齐，原16项按未变依赖kept。

| 集中观察面 | 本轮实际结果、复用与限制 |
| --- | --- |
| 原ci-pr精确清单 | 终版2444项＝原2405＋41新增−2被参数化替换的旧selector；2440项观察通过分为69本轮补修actual passed＋2371未变依赖kept，另4 skipped，missing/extra/unmapped为0，见`ci-pr-final-exact-readback.json`。原2405范围的2401 passed／4 skipped和192 subtests仍保原attempt身份，不称终版一次fullrun。backend当前collection3705＝3650＋57−2，仅收集不等于全部实跑。native首次exit1保留；writing checker已退llm-actions旧marker删除1行后原checker 4 passed替换其失败 |
| 原root suite | 当前1350项：304 actual passed＋1046 kept；其中242项architecture与41项affected、21项runtime互斥归属，七gate不再加在1350之外。`root-final-scope-mapping.json`把后续实际运行提升为actual，较早62／1288保留于原mapping；原collection中7项退役、原root-full 30 failures的attempt不抹去，不写1350项本轮全跑 |
| coverage与持久化 | 原core100/other20门槛未降；checker exit0，core409/409=100%，other62953/94953=66.30%。PG剩余durable 29项实际通过，native coverage中的p0d projection 4与request cancel 12实际通过，原必需映射缺口0；第一次PG因错误密码产生24 setup errors的attempt保留。capacity5通过但该独立调用未采到coverage，不计覆盖量 |
| 原gate/type/check | Failure/replay修复rev2七gate重新实际242 passed、公共typecheck 0 errors/0 warnings、贡献check clean。最后rev2.1仅补failure reader的Plan digest相等guard，由fresh failure selector及作者精确负向测试补验；不称rev2.1全量重跑。较早collect rev1整组及rev3受影响补验仍按原时点保留 |
| Failure／replay局部与PG | 原作者四文件85 passed／exit0，另9 subtests不加selector数；`/tmp/mrw-failure-transport-replay-pure-sqlite.xml`已核0 failure/error/skip。包括无DB单元、SQLite failure value持久化与mock control reader；不冒充真实PG。集成mixed＋p0b原19项实际通过，新增bounded failure初轮replay失败保留、修后1项实际通过；shared Node另5项真实PG通过，原19项未变依赖kept而非再次全跑 |
| 浏览器与宿主 | 原18个live selector现沿既有16项来源加本次两workflow收口，不声称一次18项全跑。attempt8两项实际passed：成功链真实provider、三node与17events；失败链保留原error正文断言，v2 canonical SQL和replay一致。rev2.1 fresh API＋worker只重跑受影响failure selector，1项actual passed；success不消费新guard，按rev2结果kept。v1正式API/SQL读回只返回原code、不虚构family/message、原body/digest不变、replay true，probe项目通过正式DELETE 200清理。原匿名身份拒绝、首次安装、错误正文及replay失败attempt均保留，auth与localSingleUser allowlist不变。实际本机8172的`project.summary.read`经macro-host完成，`direct-host-canonical-readback.json`有canonical session/messages/dispatch SQL；demo缺`retrieval_mode.json`的真实检索失败、宿主只读循环十次问题及cookie代理lane未验证独立保留 |

集中证据沿`/tmp/mrw-final-validation-20261008/integration-completion-summary.json`及其指向的原日志；源码作者、root与集成的分派/修复都计入本轮，先前402、GLM 429及负责人恢复不记作零成本。完整调用/token与首次共同验收总耗时不可得，不报提速。以上结果只证明本次有限改变在该清单下的观察，不能证明余下231701行已逐符号完成语义审计，亦不授予发布权限。

### 待重构语义组合与下一切口

下表保留本轮启动时的八项调查与实施合同；后续稳定点和中央结果记录实际进展，不把这张起始合同表作为当前仍未实施的清单。

归属先分四类：**旧整体架构组织**仍混合选择、装配、调用与投影；**迁移中介**已接新入口但保留旧协议转换；**迁移后残留**已被替代，或当前仅由自身与专属测试闭合；**新架构特殊核**是具名、不可派生的算法、领域writer或必要provider生命周期。四类按职责区分，同一文件可以包含多类，暂无生产引用只构成残留候选。整handler获得native注册、迁到领域目录或改名均不能完成重构。有限同步组合、Celery传输和provider进程本身不因此成为第二耐久运行owner；须具体识别谁写运行事实。

以下复用已调查的八个切口。用户已授权继续实施；本轮起点为已提交的`2f20e9f176087090be92f16130db740fdae593ec`，app为641个Python文件231701行。每行贯穿生产入口、旧组织、保留核与owner、既有装配、删除闭包及完成见证；完成列仍是验收要求，实际执行状态见下文，不预报净删量。此前集中PASS属于该基线，不能直接算作本轮新迁移的执行证据。

| 切口／生产入口 | 四类归属与旧组织 | 保留算法、功能与事实owner | 现有贡献／Runtime装配 | 同批删除闭包与完成见证 |
| --- | --- | --- | --- | --- |
| R1 resolver：source API／`tasks.task_run_source_library_item`→`run_source_library_item_compat`；collect→`adapters/source_library`→`run_item_payload` | **旧整体架构组织**：`resolver.py::run_item_payload/_run_handler_cluster_item/_run_single_routed_url/_run_url_routing_materialization`混合item/channel配置、mode、URL路由、fallback/refetch、材料化及dict聚合 | URL选择、crawler fallback、候选refetch的领域规则；item writer、材料writer、provider效果各归原owner | 现有`ItemResolver`、`FrontDoorExecutionProtocol`与五个orchestrator固定请求/观察，复用有限有序同步组合；无需新Plan/IR或durable source owner | 切换原adapter消费者后删重复配置合并、protocol→dict重建及重复聚合，不能只包住原handler。原resolver/item/cluster/frontdoor测试验证顺序、默认值、失败与writer调用，原source API/crawler PG验证真实效果；调用与旧闭包一起退出才完成 |
| R1 runner：上述resolver／现有source调用→`runner.py::run_channel/_run_via_crawler_provider_registry` | **旧整体架构组织**与**新架构特殊核**混合：guard、凭据、参数、灰度、provider/kind分派与JSON结果转换交织 | single-source guard、凭据边界、灰度规则、Scrapyd协议与output ingest、项目customization handler；provider保有effect和ACK/UNKNOWN含义 | 现有`provider_ports`＋`composition/source_library.py::configure_source_library_adapters`；默认只安装resolver与output-ingest，未默认安装attempt store | 消除重复解析和中间结果转换，保留具名协议核；不整删provider，也不把原runner整体保留为kernel。原gray_rollout/provider_ports与T22验证分派、真实ingest及UNKNOWN，resolver请求/结果接缝固定后才切换 |
| R5 URL submit：原Core工具→`authoring_tools.py::_ingest_url_pool_submit_handler` | **迁移中介**：参数优先级、幂等键、session artifact回放、提交引用和结果投影交织 | verified host actor、幂等与abort前后语义；session artifact只保提交视图，运行事实属原Runtime，材料事实属原writer | 原`ProjectToolAuthorSource`／Core注册；async acquisition Program→`submit_installed_program`，sync继续现有frontdoor | 固定一次规范化提交值和canonical submission/readback关系，删除重复参数／引用／结果重建；不能另建提交manager。原工具与URL durable测试、授权提交后canonical run读回共同证明，session artifact不代替运行完成 |
| R2/R5 search：原Core搜索工具→`query_tools.py::_source_web_search_handler` | **旧整体架构组织**：query/provider matrix、调用及结果装配混合；`_build_query_matrix_variants/_merge_rank_web_search_candidates`含真实算法 | query变体、最多8分支、分支失败继续、trust/rank/URL去重；provider拥有搜索效果，搜索本身不写项目、不自动ingest | 原`CandidateSearchRequest/discover_candidates`及Core工具定义；以现有Candidate值组合有序branch观察 | 拆清矩阵算法、provider调用与Core投影并删除重复raw dict组装，不增scheduler。原search/matrix测试验证局部失败、稳定排序、去重和IO边界；整handler转发到新位置不算闭包退出 |
| R2/R4/R5 discovery/clue：原Core工具→`_source_discovery_plan_handler/_clue_chain_expand_handler` | **旧整体架构组织**＋未接通的**迁移中介**：plan-only来源方向/capability matrix；`_try_clue_chain_service_expand`反射查module级三个expand名，真实实现却为实例方法 | trust plan、review、idempotency和禁止自动promotion；canonical Chain事实仍属`ClueChainService`及其writer，session artifact只为待审请求 | 原`ClueChainService.expand_chain/try_expand_chain`与Core规则；先按工具现行合同明确request/candidate/实际effect，再显式绑定现成实例 | 去掉无效反射与重复请求/结果组织；不能把当前fallback请求静默升级为真实扩展。原clue工具/service/source expansion/API验证待审与实际效果的区别、权限和幂等；目前默认fallback不证明Chain已扩展 |
| R5 tool bridge：host Core→`project_tools.py::build_project_core_tool_registry` | **迁移中介**：构造旧`ReadOnlyAgentToolRuntime/AgentControlToolRuntime`，definition→`runtime.execute`→old_call→`CoreToolResult` | 具体读取函数、task cancel/summary、structured-data query与SSE观察功能；事实owner分别保持，watcher只观察；当前有界扫描未见旧Agent Core推理loop生产caller | 原`ProjectToolAuthorSource`与Core registry；先由一个现有read工具直接连接原读取函数，再复用已证同形规则 | 每迁移一项同时删对应旧definition/execute/result桥及专属接线，保留相邻必要功能。原agent_core/tool_pool/watchers验证完整注册能力、权限、结果与观察；注册存在或单项迁移不证明全桥退役 |
| R5/R4 provider：`codex_cli.invoke_codex_cli_effect`→`mounted.invoke` | **新架构特殊核**中夹**迁移后残留候选**：`codex_app_server.py::invoke_native`及native RPC分支；当前有界生产扫描仅见自身定义，unit tests有调用 | 共享进程、thread/session、timeout、UNKNOWN与fallback；`NativeAgentBinding/native_tool_context`仍由`macro_environment`消费；workflow llm_call／llm_report仍消费platformization权限与路由 | 既有Codex provider mount、native host binding与原workflow handler；不把provider transport改造成领域Runtime | 只在共享方法、动态引用与专属tests闭包确认后删除未用native调用分支；1856行文件既不整删也不整保。原provider/native binding/platformization测试及真实原调用证明剩余生命周期、权限和失败保持 |
| R6/R7 routes：production startup→`load_production_route_bindings/build_production_composition` | **旧整体架构组织**中的重复字段须与**新架构特殊核**的独立权限区分；7629行`production_route_bindings.json`为检入权威映射，当前无generator，不能整体标为残留 | route额外权限、例外与effect授权由原声明owner保持；当前grant重读与执行权限归原Runtime，投影不mint | 既有operation/effect原生源、route loader、production binding对象与composition；只派生已经由同一源确定的字段 | 删除被证明重复录入的字段及旧装配分支，独立权威字段保留；不增第二清单。原exact route coverage／production composition证明覆盖、权限与失败保持；`production.py`先等待Failure修复稳定，不并写 |

写面按文件和真实接缝分配，不按表中语义标签直接并发。A URL提交、B旧tool桥、C未用native调用分支已派发；共享production的G路由表示与prototype注入由集成owner实施。各作者从真实闭包报告新增、删除与净变化，整类或整文件调查面不是可删预算；其余包按已固定接缝、作者席位和真实依赖连续推进，不等待八项全部实现后才验证首包。

| 自然独占写面 | 依赖与可独立部分 | 原验证入口及完成边界 |
| --- | --- | --- |
| resolver／orchestrators；runner／provider_ports／source composition分别由明确owner持有 | 请求与结果接缝由一个owner先固定；接口未定前不同时改调用两端。核已独立且接口固定后可并行，收口统一切换原consumer | `unit/test_source_library_resolver_unittest.py unit/test_source_library_item_resolver_unittest.py unit/test_source_library_handler_cluster_unittest.py unit/test_source_library_handler_cluster_frontdoor_unittest.py unit/test_source_library_provider_ports_unittest.py unit/test_source_library_runner_gray_rollout_unittest.py`；真实T22由集成运行 |
| `authoring_tools.py` | 复用未变frontdoor时可独立于resolver；如改变共用提交/结果合同则显式依赖其owner；不能各造adapter | `unit/test_agent_core_unittest.py`及原URL durable范围；必须保留真实host actor与canonical run读回 |
| `query_tools.py`内search及discovery/clue | 同一文件由一个writer持有或串行；不能因search/clue语义不同而并写。clue必须先固定请求与效果合同 | `unit/test_agent_core_unittest.py unit/test_agent_core_clue_chain_tool_unittest.py unit/test_clue_chain_service_unittest.py unit/test_clue_chain_source_library_expansion_unittest.py`；真实API由集成运行 |
| `project_tools.py`与对应agent_runtime桥 | 可与query/authoring局部核独立，但共享Core注册及manifest由一个集成owner维护；先打通一个直接read案例再展开同形替换 | `unit/test_agent_core_unittest.py unit/test_agent_runtime_tool_pool_unittest.py unit/test_agent_runtime_watchers_unittest.py`；全桥退出须原工具集合及必要观察保持 |
| `llm/codex_app_server.py`未用native分支 | 仅在共享binding保持时与host工作独立；涉及`NativeAgentBinding/native_tool_context`的改动先归并到同一owner | `unit/test_codex_cli_llm_fallback_unittest.py unit/test_codex_native_macro_binding.py unit/test_llm_platformization_unittest.py`；明确退役分支与仍存provider生命周期 |
| `production_route_bindings.json`及production装配 | `production.py`的Failure修复已稳定，后续处理重复字段仍由唯一owner承接并保留本批读回合同；所有共享catalog/派生表由集成统一同步 | `production_composition/test_route_effect_contract.py production_composition/test_production_runtime_bindings.py production_composition/test_production_composition.py`；原route权限覆盖不得缩减 |

表中验证文件均相对`main/backend/tests`，在仓库根用既有`PYTHONPATH=.:src:main/backend main/backend/.venv311/bin/python -m pytest -q main/backend/tests/<原测试路径>`执行；多文件显式列出完整路径，不新增runner。这里只登记既有入口，未执行或预判通过；实际完整清单与受影响选择由集成按既有planner收口。PG、live API/Celery、浏览器、coverage和最终组合始终由集成独占，源码互不争写不代表测试资源可以并行。

当前只读归属复核还确认`services/workflow_graph/runtime.py`为346行的具名单节点执行核，由production实际装入`PersistentOperationHandler`，旧耐久循环已退出；保留的是节点语义、项目绑定与settled Failure接口，不是整个`services`或整个workflow组织的豁免。这一处归属成立只支持该节点核的保留；八项迁移按下方各包和中央结果分别验收。

本轮执行包与固定接口如下；源码稳定、原消费者见证和集中验证未回传前均保持实施中。

- A独占`authoring_tools.py`及原`test_agent_core_unittest.py`的URL范围：一个规范化提交值派生身份、请求和提交视图；保留metadata覆盖、`strict_mode`原OR、幂等算法、history100及abort前后dispatch计数。原372行handler是调查面，不能整计删除。
- B独占`project_tools.py`、`read_only_tools.py`、`control_tools.py`及各自原测试：以`task.summary`直接调用`AgentSessionService.get_session_summary`贯通原registry，再迁移18个read和2个control工具；原唯一definition数据派生Core spec，退出`runtime.execute/old_call`协议桥。保留structured-data item的searcher fallback、结果压缩、target-session/project/context权限和真实cancel调用；不能只把execute改名。
- C独占`codex_app_server.py`及原native/fallback测试：删除七个仅内部与专属测试引用的native调用符号及其共享方法分支；保留普通invoke的进程、认证、thread、RPC拒绝、timeout/UNKNOWN，以及仍由macro environment消费的binding/context。七符号324行是调查面，最终成本包含共享部分重接。
- D resolver与E runner沿原`run_channel(channel, params, project_key, item_key)->RunnerObject`接缝独立，保留`ExecutionRequest/FrontDoorExecutionProtocol`和现有五个orchestrator。E复用`CrawlerProviderResolver.resolve`与`CrawlerOutputIngestPort.ingest`，不改D的类型；默认装配继续只安装resolver/output-ingest。原`unit/test_frontdoor_orchestrator_unittest.py`纳入D验证，PG/T22由集成持有。
- F的`query_tools.py`只有一个writer，按search、discovery、clue顺序实施；最多8分支、排序去重、partial failure和plan-only保持。clue删除无效module反射，仍按原合同完成待审session请求；`ClueChainService.expand_chain`会真实写hop，不能因接线而静默新增该effect。
- G由集成独占production源、route JSON及effect类型。显式v4保留route、operation、domain、methods、scope、approval IDs、capability、effect class、admission和适用端口；端口未绑定也须显式null。只按原类型同源规则派生无关null、非provider的NULL、空conditional字段、已知discriminator的闭分支，以及`domain:route_template`的metrics。v3继续严格读取全部原字段，v4严格拒绝缺失与未知字段；原308个binding及exemption完整展开须exact parity和digest一致。共享源码与JSON分账，不能把原7629行JSON整体计作退役。

root分派、Astra只读审查与三份现役文档维护、集成集中收口；最多三名领域作者加该三名控制/集成角色。pure测试最多两个独立资源slot，A稳定前B不运行会导入A源码的组合测试。必要局部验证后连续推进下一包，PG、服务、浏览器、最终检查及commit由集成独占；不新增Runtime、manager或审批轮次。

本轮各包实现与局部见证（均相对`2f20e9f`；整组最终验证与计量见随后汇总）：

| 包 | 源码结构与实际成本 | 已有见证及未完成范围 |
| --- | --- | --- |
| A URL提交 | 一个`_UrlPoolSubmission`直接供原handler使用，归一化、identity、原请求与提交投影同源；源A139/D159，净减20；最终统一测试账A280/D0，包含作者与集成PG见证。handler由372行减至261行，但必要typed构造与投影成本已全部计入，不能称净减111 | 只读diff确认metadata优先级、strict OR、原幂等、actor/session/project、abort0/1及history counts保持；作者最终selector16 passed、3 deselected，exit0。集成另2项Core→真实PG通过：原submit→task→COMPLETED及one attempt，abort-before无新run/work；provider受控、session内存，不能称全宿主live。首次fixture失败attempt保留，原Core跨project拒绝另有见证；作者已接E |
| C未用native链 | 七定义、native锁/状态、动态tool回调和共享方法专属分支退出；源A27/D543，净减516；测试A121/D342，净减221。真实binding/context原文件保持 | 作者原selector41 passed及2 subtests；有界源码扫描旧入口无引用，普通invoke保RPC拒绝与原生命周期。此前延后的native宏11项由集成实际补验通过，41项按未变依赖kept不重跑；作者已接D resolver |
| G路由v4与R7注入 | `EndpointEffectContract.from_declaration`复用原端口与discriminator表，原loader解释显式v3/v4；R7只去prototype import与注入。rev2源A64/D23，净增41；JSON A309/D2902，净减2593；最终统一测试账A114/D6，净增108 | 集成原effect/authority54 passed、auth/route/terminal40 passed，exit0；rev2受影响54项复验通过。改动前原loader对git-show v3展开的308 binding和45 exemption为独立oracle，新v4逐字相等，digest `3e8f8a914e0f4f87f3bc5da3b79853394c09336fbf2b96c2cb5cbf517e99dd38`；真实PG mixed2、graph2、failure1、retrieval1共6 passed（12.37s，exit0）。证据目录`/tmp/mrw-migration-20261008-2f20e9f`；最终公共类型/gates已由随后中央结果收口 |

A与G已经只读结构审查。root指出G rev1新`from_declaration`使用宽`Any`后，rev2已收窄为`Mapping[str,object]`并显式解析enum/port，无unchecked cast；定向Pyright原文件基线与当前均15项同诊断、新方法0项，不冒充整文件type PASS。

B rev2已真实退出两旧Runtime、name-dispatch和old-call桥，具名两参核经原贡献规则统一适配Core四参，原spec/emit无需逐工具重复接线；3源净减26加公共helper净增16，合计A1668/D1678、净减10；测试A357/D29另账。rev1净减30不再是当前成本。18 read与2 control的名称、schema、权限metadata及顺序经独立AST比较和作者完整CoreSpec比较均保持。原27项贡献spy只观察原native注册，迁移后新增20项前缀，测试保原27有序断言；不是改总数掩盖能力丢失。审查发现新`_session_bundle`把真实service Failure变RuntimeError后，rev2已沿typed union原对象传递，在6个Core读工具边界复用现有失败投影；context bundle第二次artifact读取失败也立即返回。这是旧未处理Failure到Core失败的局部refinement，保真实family/code/message/context，不模拟旧AttributeError。原精确8项实际通过（0.84s、exit0），3源类型0错误、spec20再比保持；rev1原33项扣受影响Failure面后按未变依赖kept，不当作rev2全部重跑。F已由同writer接续。

D r3稳定候选8源A498/D549、净减51；集成原ingest/url_pool消费者去除过窄注解A1/D1另计，D整组A499/D550、净减51，最终统一测试账A63/D10、净增53另账。r3仅比r2补既有kit边界注释并绑定实际域外拒绝见证；原prevalidation净减162及中间净减72均不再是当前成本；三mode转发壳与重复serializer callback退出，URL选择/参数/执行/观察共享，cluster拆真实search/fetch并保留原wire/debug投影；新增声明与五个orchestrator类型0错误；原8源定向检查从298项降至226项，226项均按owner、原语句与完整诊断对应基线，新增或改变诊断为空，不冒充整个resolver类型通过。D内部params、protocol.concurrency_plan与结果附加字段保开放object值，不递归套用RunnerValue拒绝provider/store注入，也不在effect之后新增wire校验。默认参数沿原str键域接收Mapping并浅拷贝，保持opaque对象身份与override顺序；非str键及iterable pairs不扩为支持形状，这一Python输入边界是明确局部refinement，不宣称所有域外无类型承载完全兼容，不新增业务schema或拒绝码；原五文件56 passed及12 subtests（1.00s、exit0），覆盖UserDict、opaque参数覆盖、extra和protocol值身份以及域外拒绝前no-call；r3的13项源码/测试manifest已读回当前字节匹配，原56项执行在r2、无行为变化的单行注释按未变依赖复用。E仅runner改变，公开原guard更名后的Git计量A314/D268、净增46，作者起始字节计量A311/D265同为净增46；测试A265/D9另账，最终全局账按统一Git口径去重。原provider ports与composition未变；统一JSON递归核和失败/重协调投影，canonical值保留到结果边界、legacy按原入口观察。该增量单列，不能借其它包删行隐藏。E审查发现畸形`ReadbackTerminal`内层失败会推迟到ingest之后，rev3已限定outer与inner均为exact canonical类型才延迟，其余按原入口投影失败；相关4项实际通过，包括no-ingest见证，最终原两文件32 passed及6 subtests（0.51s、exit0），3源Pyright0。D/E集中组合、公共类型及整批gate/coverage/host均由集成收口，结果见随后汇总；表中作者与集成执行保持归属，本轮八切口完成不代表全平台架构目标完成。

F rev2已实际重组search与discovery：规范化options持有原`CandidateSearchRequest`，分支以purpose与请求成对描述，顺序effect返回原`CandidateBundle`或原Exception；非matrix即时失败、matrix失败继续，branch与Core结果分别投影。discovery复用同一候选评估、查询构造和结果投影；clue只删除无效module反射，仍写原待审session请求，不调用会写canonical hop的`ClueChainService.expand_chain`。源A494/D567、净减73，包含全部新helper；三公共binder复用原规则。作者原clue8 passed（2.83s），集成Core4加trust4共8 passed（3.25s），capacity原5项passed；定向类型0错误。源码SHA `35581fb5cb24ca4de29edfc907deeb75f5767ae4ffe568d0ba9f76aaa4360abe`已只读核对。作者actual-byte基线探针另确认9个完整CoreSpec、typed候选及原raw标量回退、matrix完整Core wire与调用顺序、真正nonmatrix一次调用、discovery两mode结果相等；这些有界比较不提升为live provider证明。原6个未改query族不在F删除闭包，整组门禁见随后中央结果。

本轮最终成本按`current-size-account.json`和`package-costs-final.json`统一计算：从`2f20e9f`的641个app Python文件231701行到641文件231118行，源码A3205/D3788、净减583行（0.25%）；配置/派生JSON A309/D2902、净减2593，测试含历史fixture共A1757/D407、净增1350，其中测试代码与manifest/helper净增1033，非执行历史材料317行单列。kit/contribution、前端和工具本轮均0变动，文档另账；互斥路径统计不把测试删行或JSON缩短混入生产Python收益。各包局部patch计量不与最终统一Git账重复相加，E净增46与G/R7合计净增41已在总量内。相对更早`a17930da`的app299234行累计净减68116行（22.76%），其中已提交基线67533与本轮583分别有执行归属。

本轮中央已完成`check` exit0，公共边界类型修复后0错误，七项gate修复后242 passed（9.00s、exit0）；初次type/gate的exit1记录保留，不能以文件名final掩盖失败attempt。原coverage runner已实际exit0：2288 passed、4 skipped、195 subtests（245.36s），core409/409为100%，other63416/95050为66.72%，保持原100%/20%门槛；capacity沿独立Unix socket fixture另5 passed。4 skip为原live crawler/live host opt-in与两项交由Pyright negative selector的边界，本轮均未执行，不计passed。backend精确清单2509项已汇总为2505 actual passed、4 skipped，core-business与E2E分别283/16项是去重覆盖中的子集；root精确清单1350项全部actual passed，已含七gate242项，不再相加。两清单均kept0、missing0、extra0。root余集首次1099 passed、9 failed及90 subtests；8项Stage1 fixture和1项Stage0旧witness均因历史来源回读误用了当前HEAD。Stage1工具仍由Stage2 intake的`validate_bundle`与候选投影消费，冻结身份、149+11绑定、authority和create-only拒绝约束仍需见证；修复从原commit blob补reports与successor_runtime两份测试专用`.py.source`及原SHA/provenance，并去除HEAD fallback；54+263共317行、10488字节已与原blob逐字核对。Stage0只在原record commit且record字节相等前提下解析旧witness。9项修复后实际passed，原失败日志保留，不恢复生产API、不改冻史或删断言；其余已通过项不因共同fixture修复重跑。独立本机host在4193经真实native工具`project.summary.read`完成一轮并返回终态marker，canonical SQL另证一个session、两条message与一次completed dispatch；session仍为pending，不升格为研究完成，十次只读循环未验证，父iframe沿旧证据未重跑。4193进程树随后清理，原API/worker及8000/8172服务读回保持；不建立外部发布权限。

R6另有本轮真实HTTP暴露的跨架构接缝：有效Bearer已通过workflow身份校验，但`createProject`只建立业务Project及schema，新建E2E项目在`ServerProjectScopeResolver`观察到0条ACTIVE scope而不能运行；`ProjectScopeRegistryRepository`现有`revise`不承担首次create，产品项目创建与选定Runtime首次安装尚未接通。整体重构须固定该安装事实的owner与正式provisioning入口，明确项目scope/table绑定和有限operation grant的授权来源，不能把业务run变成mint入口，也不静默自动授权或另建认证/Runtime平台。

当前集成仅获准沿原PG fixture，以`compute_scope_digest`与`PUBLIC_TABLES`为全新隔离项目初始化scope/project_tables，再由原`install_runtime_authority`给实际认证actor安装workflow三个operation的有限grant；不改已有scope/grant。即使fixture下通过，也只证明显式已安装前提下的链路，不证明产品`createProject`后即可自动运行。run接口返回`queued`时，测试须等待真实Celery终态及canonical读回，不能继续沿用同步完成假设；本次已等待真实Celery终态并完成canonical读回，原身份拒绝和首次安装失败attempt均保留。

R6/R7随后暴露同一安装入口的具体多resource缺口：混合workflow含NETWORK_IO与CPU_LIGHT，原`install_runtime_authority`只接一个policy并要求所有grant limits匹配该class；拆成同epoch两条grant违反唯一约束，改成不同epoch又因current context取最大epoch、qualification只接受该epoch而失效。本轮已实现的修复仅将原`resource`参数推广为单个`ResourcePolicySnapshot`或具体tuple，保旧单resource调用；policy集合非空、class唯一且project/cap一致，每个grant limit须由匹配policy覆盖units和max_active。允许额外合法policy，policy存在本身不增加grant权限，不要求两集合相等。先验证再沿原调用方事务安装所有policy和一条同epoch有限grant，不改变max-epoch选择、qualifier或DB唯一约束，不在run中授权，也不以fixture直写repository绕过installer。该公共接缝源码已SOURCE_STABLE：仅`production_runtime.py::install_runtime_authority`函数A27/D20净增7，低于A≤50预算；与同文件此前C9退役成本分别归属，最终全局账仍统一去重。本次没有新增manager或衍生安装器。源码hash为`820693bb4680798f2412d1fb0ed7deaa6c1dca17f0a65a4ec7bc82c5e1c4d9e0`；installer阶段的`test_mixed_operation_worker.py` hash为`ae174a0f38ee4950e317109165024370a0a862578cfe6206baed59547c926659`，后续新增Failure/replay见证后不再作为该测试文件终值。只读审查确认接口与权限/事务合同一致；测试体覆盖default/alternate混合三节点、单grant双policy幂等、写前拒绝、caller savepoint回滚及extra policy不授予资格，测试体存在不算执行通过。集成已回传原mixed全文件与p0b exact共19/19实际通过，证明该多resource安装接缝；fresh API/Celery的有界失败graph随后正式FAILED并产canonical EffectFailed/RequiredStepFailed，随后错误正文与未激活节点replay暴露的缺口已按下段修复；installer通过本身仍不外推live全过。项目首次正式provisioning入口仍是上一段独立缺口。

R5/R7领域Failure运输实测缺口已修复：`WorkflowNodeSettledFailure.workflow_failure`中的family/code/message/context经原assembly、`DefiniteInterpreterFailure`与`InterpreterOutcome`完整传入原failure writer，只允许FAILED且code一致，原node错误lift、UNKNOWN和lease语义保持。六源范围内沿既有project ValueRepository、原terminal UoW写明确`RuntimeFailure.v2`／`mrw.runtime.failure.v2`的严格canonical JSON；旧code-only v1保持原body/object身份，拒绝非JSON/NaN及同attempt内容变更。composition reader从EffectFailed沿精确attempt、work/assignment、保留claim、scope/revision、Plan digest与handler读回原value并验证digest；API投影family/code/error/context，保留`required_for_live_failure`断言。事件仍为EffectFailed与独立RequiredStepFailed，journal没有重复正文事实，也未新增错误manager。

新增bounded失败graph曾出现未激活下游stored queued、replay缺节点的不一致。修复只在原workflow facade以不可变Plan和ProgramAccepted／PlanCompiled事件锚定节点身份，核对完整journal与snapshot前沿；Plan内没有任何step事件且没有task的节点才投queued，已触达节点由原journal replay覆盖。current runtime_steps只作stored侧比较；未知step、错Plan/事件与scope/claim漂移拒绝，不复制当前状态作为replay证据，不改generic AgentSession projector。修复期间app快照净增236行已计入总账，四原测试文件、真实PG及live见证范围见集中表；`workflow-v1-readback-final.json`另证v1读回保持。首次正式provisioning与宿主只读循环十次问题仍是独立未完成项。

八项是优先切口，不是剩余全量的证明。`information_topology/service.py`的412–570行经`repository.py`232–358行承担project/revision的原子writer，`api/information_topology.py`124行起为真实消费者；native adapter只是读投影。该具名写入核及其事务边界保留，不给整个service或目录发放保留豁免。已完成collect的finite fold和写作微小投影不替代本表Source/Agent组织重构，既有九项覆盖及CI通过均不关闭整体架构目标。

R7的prototype残留已固定为集成owner的最小删除包：当前installed五族（workflow、acquisition、retrieval leaf、batch、business wait）的`return_contract_ref`均为`RUNTIME_VALUE`、`admission_required=False`，`prepare_terminal`在默认admission前返回。因此删除`production.py`内`build_first_specimen_bundle`的import与`bundle_factory`注入两处，保留真正required-admission无bundle时的failclosed。`first_specimen_activation/terminal/reconciliation`及`research_admission`仍有delivery/captured-value与原消费者引用，默认研究writer不在本包删除闭包；已退generic handlers不重计。此处已由集成完成两处删除，严格required-admission边界与原terminal消费者见证见上方G稳定点；与G共享源码成本统一计量，不重复记删除收益。

### 四项遗留接缝的有限收口（2026-10-08）

本轮从干净`main@ee20e32d`接续，范围为首次项目Runtime安装、重复只读观察、demo检索声明和本机父iframe认证连续性。此前八切口与完整验证已提交，证据仍属`/tmp/mrw-migration-20261008-2f20e9f/final-integration-summary.json`，不冒充本轮新执行。本轮不扩为全库内部类型治理或Stage4–6重启，不push/deploy。

项目业务身份、Runtime scope与执行授权是三个相关事实：业务Project及schema由原projects owner建立；Runtime registry拥有scope/revision/incarnation及table绑定；正式部署声明经原installer写有限grant/resource/capability。业务创建与运行请求均不据成功结果增加授权。宿主身份则沿现有OAuth session、WebUI JWT和可信host输入关联；登录状态与工具dispatch读回不产生项目执行grant。重复读是对同一事实源的新观察，允许的观察调用不能靠返回旧缓存假装执行；真实effect重入仍受原保护。

| 包与owner | 权威输入、最小接口与独占写面 | 输出及退出条件 |
| --- | --- | --- |
| P：`workflow_resource_fix_recovery` | `api/projects.py::create_project`现只建业务Project/schema；`ProjectScopeRegistryRepository`缺firstcreate，`revise`保持已有revision更新；`compute_scope_digest`、原`project_tables`七项目表及`PUBLIC_TABLES`公共表、原`install_runtime_authority`固定身份与安装关系。写面限`successor_runtime/substrate/postgres/authority.py`的首次创建核、`composition/production_runtime.py`的显式安装组合及`main/backend/scripts/provision_project_runtime.py`本地CLI薄入口；不向业务run或项目create塞grant安装 | 正式本地deployment入口先核业务Project/schema，再在调用方同一事务创建scope/table绑定并沿原installer安装当前workflow所需的有限、未过期operation/resource声明；scope repository的exact重试只读返回；整体安装幂等只承诺事实无新增/不更新/不续期，仍运行原capability/policy/grant核对及on_conflict检查，不承诺整条SQL只读或提前返回。异值/既有撤销/过期不覆盖、事务失败无半安装。管理员来源已定为本机OS运维调用边界，CLI显式admin审计标识与target actor（或按已启用host配置派生local_host），不把HTTP OAuth trusted提升为admin。初始revision固定1、incarnation显式必填且沿原revise拒绝全局已用值，schema只读业务Project；capability/resource及grant expiry/operations/ceiling显式有限，scope/operation/ceiling由原typed构造派生digest，policy_digest沿原policy owner显式输入，同值重试不续期。CLI仅开放原workflow registry的显式operation；通用typed installer仍接收原消费者registry，不新建全域安装词表。不用测试fixture直写来冒充产品入口 |
| H：`project_tool_bridge_migration` | `skill_runtime.py::SkillRuntime.invoke/_detect_skill_loop_guard`及原`SkillSpec`是共同判断面；旧报告记录TTL内第10次相同read被拒绝，并未证明无限轮询。原`SkillSpec/register`新增默认false的`repeatable_read`，仅已证五个workflow reader在原注册标true，guard消费同一权威字段；true配非read_only声明拒绝。默认read_only不是无effect证明，未标注者仍走原guard，LLM/formalize审批协议保持。独占写面为`services/skill_runtime.py`与原`unit/test_skill_runtime_unittest.py`，如需改Core/native公开语义先归此共同owner裁定 | 同一可信host/session/目标的10次合法只读观察真实到达原reader，顺序、结果与最新状态可读；重复写/effect保护、权限拒绝、trace/session隔离保持。不能仅关掉guard、提高阈值、按工具名猜风险或加调用者绕过flag；原会话/事件读回由集成验证 |
| R：`native_branch_migration_recovery` | `project_customization/projects/demo_proj/__init__.py`导向`DemoProjCustomization`，`subprojects/demo_proj/mappings/`已有具身智能关键词与graph映射。`project_retrieval/mode.py::_load_mode_result`只读现有声明，保持不自动初始化。独占写面为demo目录的`retrieval_mode.json`初版及原`unit/test_project_retrieval_mode.py`必要见证 | 以原demo源投影一条route和已有3个关键词，source_snapshot用真实源字节/hash，source_revision由源快照决定，source_registry为空不伪造来源；有限预算为queries3/materials10/followups0，materials上限复用原google-news-scan的10；显式新增`现场`作为原检索formalization需要的观察锚点、`未评级`作为无排序状态，两者是本次mode定义，不冒称旧source投影。原materialization以mode vocabulary构造profile，GraphPage包含actual topology类型，不需更改sharedcore或FIELD_MAPPING。原current/preview消费通过，其他缺配置项目仍拒绝、跨项目身份拒绝；不复制HK研究事实、不把preview当真实provider运行 |
| K：`integration_completion_astra` | `CodexAgentPage.tsx`本机HTTP固定直连host且auth快照不reload；非本机沿`/codex/`。WebUI `web/src/routes/router.tsx`复用原cookie exchange/direct bootstrap，backend `codex_auth_webui_bootstrap`只认原static token或OAuth session加same-origin；`LOCAL_SINGLE_USER_ACTOR_PATHS`仍仅record-input/dispatch。先无源码改动验证；若缺陷成立，写面由该owner限定到对应frontend/WebUI/auth/proxy文件与原测试 | 本机真实父iframe项目context及auth刷新后iframe连续性实际通过即关闭本轮K；原无cookie、错误origin/forwarded/header、跨项目拒绝证据按未变依赖保留。非本地OAuth cookie部署lane及expiry变化单列未执行，不是本机退出条件。不把token-sink已登录当浏览器cookie，不扩localSingleUser allowlist，不以fixture session或mock冒充真实OAuth |


实际结果统一记录如下。live证据根为`/tmp/mrw-product-close-20261008-ee20e32d/`；以下成功不替代未运行的provider或远程cookie lane。

| 包 | 本轮实际结果与证据 | 保留边界 |
| --- | --- | --- |
| P | 新项目由原API创建，正式CLI首次安装后原workflow到`COMPLETED`；5次CLI覆盖首次、同值重试、history/过期拒绝及late grant冲突回滚，`p-negative-readback.json`核对四组facts不变；`ph-summary.json`记录原consumer结果。原7项pure测试及原installer/worker PG16项均实际通过 | 原Project/scope/grant owner保持。source-stable四hash独立审匹配；CLI最后仅补原derived标记，函数body AST不变，更新hash见`/tmp/mrw-first-provision-p-start-20261008T154828Z/source-stable-marker.json`；CLI限原workflow registry。mock测试不计真实PG回滚，真实facts读回单独成立 |
| H | 五个原reader同一实际actor连续各12次，threshold仍10、guard仍启用，错误token3次拒绝；`ph-summary.json`及`ph-terminal-before-poll.json`/`ph-terminal-after-poll.json`证明canonical facts未被观察修改。原局部unit/API/W02为56passed/43subtests，日志`/tmp/mrw-h-focused-final-20261008.log` | 仅五个原声明标repeatable，原权限/审批顺序与effect guard保持；局部API测试的受控持久层不冒充live |
| R | 原GET current200及POST preview200，PG55436/project_demo_proj的mode由0到1、plan1；`r-live-responses.json`及`r-live-readback.json`证明snapshot精确等于检入JSON，四源hash/bytes与source_revision独立复算一致、limits3/10/0、diagnostics为空；原mode测试12passed | source_registry为空，五channel仅registered/connectivity not_probed；没有provider或retrieval run。`现场`/`未评级`是本次mode明确新增声明 |
| K | fresh Chromium localhost5174→固定8172，bootstrap/status200，demo_proj ready/context精确source/origin，auth刷新后iframe marker保持；`k-summary.json`与`k-local-parent-observation.json`为实际观察 | 无源码修改、无用户thread/turn或领域dispatch。原auth exchange10与guard55项按ee20e32d证据kept；远程MRW OAuth cookie及expiry变化未执行，非本机退出条件 |

原source类型债保留：P scoped Pyright当前与HEAD均exit1/14，`/tmp/mrw-first-provision-p-start-20261008T154828Z/typecheck-comparison.json`逐诊断匹配，新CLI及新增接口0新增；H source0，两个原test当前与HEAD分别8/458，新增0，`/tmp/mrw-h-typecheck-baseline-diff-20261008.json`可回读。它们不等于全文件严格类型通过。H仍有11项class标签债：compile及五模板持久写、retrieval current/preview持久写、llm_call及两formalize provider；均未标repeatable，原guard有效，本轮未改审批协议。

集中check与公共边界typecheck实际exit0；原七gate最终242passed/exit0，最终证据为`check-selector-final-result.json`、`types-selector-final-result.json`与`gates-selector-final-result.json`及各原log。首轮241passed/1failed源于CLI build_parser缺derived标记；按原kit标记补齐后函数body AST不变，沿原gates runner对242项完整有限复验，不把两轮通过数相加。首次live的403为专属测试认证配置缺口，恢复既有static-token配置后原链完成，失败attempt保留。P/H测试的专属18086/55436/16379配置已恢复，`services-restored.json`记录原worker/API命令及环境、health200、queue/unacked均0；用户8000/8172原PID保持，专用5174关闭，临时token私密文件已移除。旧fullsuite和coverage只保留原基线归属，不计本轮actual或整体kept。 最后P/R仅补原unit marker，`test-selector-marker-changes.json`证明移除metadata差异后AST相同；原选择器收集3796项（比基线新增16、退役0）；原ci-pr精确required2532项（原2509，新增23、退役0：P7、R12首次纳入、H4），见`selector-exact-delta.json`。四个受改测试文件的7/12/14/38项全部进入原ci-pr及coverage选择，见`current-selector-inventory.json`。收集不计执行，新marker不改变原行为测试结果归属。

本轮是四项产品缺口收口，4/4完成；实现成本由当前diff独立计量：P app A118/D15净增103、H app A19/D2净增17，共app净增120行至641文件231238行；新CLI工具171行（含最后标记净增5），app与工具合计新增净291，不报精简收益。R配置JSON206行另账，测试P145/H净139/R102合计净增386行另账（含P/R原CI unit marker补齐8行），无vendor或前端源码增量。原初估仅约束最小充分构造，typed CLI、同源校验与必要门禁标记成本全部计入。未手写新的Runtime注册词表或第二授权协议；parser参数声明与demo领域mode是本次明确authoring输入。

现成成本记录保留初次live认证403、首次gate1失败、P初次类型检查及缺相对依赖baseline失败；这些不计通过。H局部两轮分别55passed/39subtests/12.49s与56passed/43subtests/14.20s，pytest失败0；P最终pure7和PG16、R12、公共gate242分别按验证范围记，不把局部通过数累计成新的整库suite。首次整组验收总耗时、各owner完整工具调用/token及共同设计审阅等待成本未独立统计，缺失不记零，不声明提速。文档只核对diff与历史段字节；未因此新增冻结候选、完整suite或部署审批。

P已将原installer的declaration校验同源抽取，供原安装与首次安装复用；原caller的finite/trusted→真实current scope→resource/capability/operation/limit→写入次序及失败含义保持，新入口在scope/DDL前先用同一纯规则预检。不伪造resolver、不复制校验词表，必要公共抽取全部计源码成本，原每函数80行只作初估，不以压缩可读性或省略校验满足预算。

P/H真实验证使用集成专属18086环境，临时启用原已有static-token认证，以实际token派生的actor作为CLI有限grant的显式target；沿真实API创建新项目→正式CLI→原HTTP workflow消费。此为专属测试配置，结束恢复原env，不扩产品认证或localSingleUser allowlist，不写用户8000/8172/6379。P/H的static actor与K本机WebUI JWT为不同观察链，不能混为同一登录或OAuth cookie证据。

本文列出的backend路径相对仓库根；实际执行cwd以原日志为准，backend collection及部分PG命令从`main/backend`执行。仓库根pytest入口为`PYTHONPATH=.:src:main/backend main/backend/.venv311/bin/python -m pytest -q -p no:cacheprovider`。P沿原`tests/production_composition/test_s1_operation_authority_adapters.py`与`tests/successor_runtime/test_mixed_operation_worker.py`的实际consumer扩展，PG实例由集成指定；H沿原`tests/unit/test_skill_runtime_unittest.py`和`tests/integration/test_agent_macro_host.py`；R沿原`tests/unit/test_project_retrieval_mode.py`。P另增原pytest入口`tests/unit/test_project_runtime_provisioning_unittest.py`，H实际API见证在`tests/integration/test_workflow_graph_api_unittest.py`。这些路径相对`main/backend/`；实际执行结果按上方记录，未列结果的入口不计通过。K按实际变更复用`main/ops/codex-webui`中`pnpm test -- <原auth测试>`和`web/`中原context/router测试；父iframe使用现有Playwright入口和原host读回脚本，测试环境与服务资源由集成独占。

源码独占不自动意味着测试可并行：PG、真实浏览器/host、共享服务、coverage及最终组合由集成统一排程；最多两条资源隔离pure测试。root分发、Astra只读裁定并维护原三文档；P的OS部署授权接缝已固定，H/R/K按各自真实依赖独立推进。退出按这四项真实消费者及必要受影响检查逐项读回，上轮完整suite不因本轮文档或未变依赖重跑；新增/改变语义仍须沿原门禁和清单验证。

### app外工具与vendor定制的有限覆盖

沿现有全源库存核对，42个backend migration Python文件作为既有schema升级历史保留，旧原型退出不改历史migration或drop表。14个owned ops覆盖docker-compose实际挂载的launcher agent/UI、服务start/stop/restart、真实API ingest/demo入口与fixture-only rollback合同工具；5个local入口为backend docker-entrypoint/start/stop及README明确的两个手动Codex swarm脚本，各自沿部署或人类显式入口保留，不与领域Runtime共写运行事实。以上未改必要工具记为kept；没有因目录标签取得生产权限，也不因保留脚本声称本轮已运行它们。迁移的历史保留不是旧Runtime仍在运行。

search-lab首批已退13个专属实验脚本不重计；当前11个中，7个provider比较、benchmark、trace、SearXNG/YaCy smoke及独立SQLite评估具有现有显式入口，保留原用途。余4个`wave27_vectorization_closure_gate.py`、`wave29_vector_schema_alignment_gate.py`、`wave30_vector_closure_gate.py`、`wave8_search_vectorization_contract.py`只生成固定旧artifact/fixture资格结论、仅专属tests消费，root已批准tools D1447/A0/N1447，专属tests273独立，集成owner实施；raw历史artifact保持，不以这些资格脚本代替provider运行证据。

WebUI vendor按README具名上游`LimLLL/codex-webui@44ad73a99c4d4385fa60d0c519c243baf8f160b7`分离；原对象来自README所指既有源码树，只读逐blob比当前1205条tracked路径，未修改上游blobs。403路径同blob；当前802差异路径分为736 Codex schema生成、4 API生成、32实现改/增、18定制tests、10配置、2文档。实现改/增面上游5512行→当前7315行，另6个上游源码删除596行，故**完整实现维护面38路径，净增1207行**；净增不能当维护代码总量。生成路径净增8283、定制tests净增1847、配置净增58及文档改/增净增28另账；还删上游非源码docs/images/CI，不将其当实现收益。vendor相对`c3adced`与`a17930da`均无本轮源码diff，按kept记录。

必要MRW定制具名为`src/mrw`的backend client、action registry、binding/event/permission服务，threads的prepare/bind/recordInput/endTurn调用，浏览器authenticated-layout的project context和action confirmation，以及local auth/host launchd与版本生成协议。它们服务真实宿主项目与审批链，无需为行数归零削权限；未变上游内容保持vendor。该分离是源码归属与计量证据，不是本轮WebUI执行或新性能收益。

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

## 5. 持续推进与分层退出

本轮按用户“把文档规划的精简面全部完成”从干净`main@cc1ea6c1`继续，app基线641文件231238行。§4八切口及P/H/R/K四接缝已完成，不重复发包或重记收益；§2.1、§2.2保持已提交历史。本轮已按§7完成全路径剩余闭包、services重复组织退役及必要能力同源接线，三个条件分别取得下文实际验收；具名必要核继续由原owner承担。每一R项清除具体重复职责，再把剩余符号归到唯一执行/事实owner及具名特殊核；“不需改动”须说明原能力、不可替代理由和实际consumer，不能以目录/import/分类完成替代实现完成。

同一运行绑定可以有持久化索引列与只读观察，但语义源仍是原typed绑定；写入投影与读取校验复用同一确定规则，事务、实时权限和恢复判断由原owner保留。效果分类描述调用可能改变什么，审批声明描述此次能力要求何种人类授权，二者不能因一个字符串标签被合并。本轮在这些既有对象与关系上收敛，不新建IR、Runtime、注册器、审批或证据平台。

| 本轮剩余实现包 | 权威源、原消费者与精确处理面 | 依赖、验证与事前预算 |
| --- | --- | --- |
| J：assignment索引列同源 | `RuntimeAssignment`为原绑定权威；`runtime_lifecycle.py::_assignment_values`88行与`runtime_journal.py::validate_runtime_assignment_row`112行重复投影assignment及handler字段。只在原journal定义纯投影供两者共用，writer继续拼原`AssignmentEnvelope`调度字段，reader继续canonical/opaque/recovery及column drift校验；不改SQL/CAS/事务owner | 已完成，最终app A145/D180/N35；事前D200/A_max165/N_min35中删除量未达200，净减35达到。helper及跨文件接入全计；helper只收`RuntimeAssignment`，不反向依赖envelope。Recovery的profile只在原RecoveryBinding语义内派生，INTERPRET/VERIFY_ADMIT独立recovery校验保留。原p0b PostgreSQL assignment drift、p0c lifecycle及node adapter验证，PG由集成独占；负向直接篡改真实row |
| H：11项effect class与approval分离 | 原`SkillSpec`及`approval_policy.default`维持声明权威：compile与五模板写、retrieval current/preview共8项标write_shared；llm_call与两formalize共3项标write_external并显式保留原optional行为。未显式policy按原class规则解释，外部/privileged原审批继续；未知default注册拒绝，权限/guard/五reader opt-in保持 | 原显式optional生产声明均为shared，客户端只传元数据，原interpreter为唯一审批解释者。事前D7/A_max30/N_min=-23保留，源码去掉重复调用期policy解析后实际A41/D7、净增34；注册唯一规范化，调用只消费结果。作者24 passed及10 subtests，原workflow API混合调用/审批修后实际结果见下文；不把标签修复报成净减 |
| G1/C1：静态graph资格壳与clue桥退役 | G1删除四个graph readiness/rollout/projection模块及四行export，D1128/A0；C1删除`clue_chains/graph_integration.py`及16行import/export，D702/A0。保留实际graph writer/reader/alias/backfill、curated revision约束及clue/source/external search原核 | root已发data owner，源码已稳定，app合计D1830/A0；五个专属checker D1233另账，专属测试退役不计app收益。W04 packet明确`FROZEN_WORKSTREAM_PARTITION_NOT_AUTHORITY`，保留51历史keys并对新增9个retired函数断言源文件确实不存在，现役classifications仍精确覆盖其余项；此历史分区不是现役registry豁免，现役同步由集成完成 |
| K：原生目录到实际安装同源 | 六族13项原定义由唯一effective native tuple供project投影、production facts与实际handler共同消费；原Source和具体I/O在typed闭包中保留，原candidate native.runtime直接复用，wait/dispatch显式注入同contract/codecs。服务仅bind时导入，scope/current grant由原运行边界取得。阶段八路径及最终九路径hash已只读核对，具体保持与成本见下文 | K有限包已收口：阶段同hash public类型0错误、focused186 passed/16 PG-env skipped/33 subtests、真实PG45 passed、七gate234 passed；独立负向1 passed。最后dependency修正后的当前PG45及公共检查见最终表。初估D225/A185/N40、后续A360/净增150及A500/净增280均未达；旧500/227漏leaf40/11已纠正。root先接受八路径A540/D238/净新增302，最终必要依赖修正后接受九路径A544/D240/净新增304；两次事实分别保留，不借其它包冲销。activation16行、wait恢复与child settlement为具名Program核保留，原可删估算失败留账；不将K局部验收扩称全波完成 |
| G2：Aggregator副本及专属同步链退役 | `dashboard/global/stats`改从`public.projects`当前enabled集合直读原三材料表，只返回原三counts。单连接只读REPEATABLE READ覆盖项目集与计数；复用原schema允许规则及identifier检查、引用权威绑定并quote标识，排除public/aggregator。删除副本同步service、API/payload、Celery、独用cursor model/cleanup及前端专属操作，保留retention与历史迁移 | 最终source stable，事前app D244/A_max80/N_min164，初次D250/A75/N175；最终含helper80行与共享context修复A10/D6为A94/D256/N162，新增上限超14且最低净减少2，由root按必要Failure边界修复校准。前端实际A2/D17（含tests A2/D2）另账。删除源行及disabled项目不再残留陈旧计数是本次明确修正。无项目三0，非法绑定/缺表失败不吞0；原路由权限保持，当前无独立admin角色gate，不增审批。实际PG snapshot及canonical计数四项已通过，原API权限保持及证明范围见下文；禁止为退代码DROP存量表 |
| U：URL pool旧直接batch入口 | 删除无现役生产caller的旧batch入口及专属组织；保留prepare targets、adapter、`execute_single_url`、`invoke_url_single_url`、frontdoor route summary及原writer | source stable，事前D802/A0、作者阶段账D864/A0；最终相对cc1ea6c1互斥app账D885/A0，采用统一Git口径；原同步/耐久consumer与删除闭包验证由作者交集成，测试增删独立计量，不能删除真实单URL核抵行数 |
| S：Source工具旧capability fallback | `ingest.source_library.run`是唯一剩余capability fallback，迁到既有`ProjectToolAuthorSource`后删除`_spec_from_capability/_handler_for_capability`重复桥 | 事前D75/A_max50/N_min25未达；修订后实际app A54/D49、净增5，专属新增测试A24/D0另账。AuthorSource、特定items schema及原handler是必要接线；已删多余governed声明与frontdoor metadata，保持原exclusive与ask。只读复核marker已指向实际新测试，原identity/exception/permission测试恢复为独立完整且唯一的定义；handler工厂返回确定Callable。源码修正已核，最终原三文件51 passed且collection同为51，日志与范围见下文；真实source runner/provider/writer保持 |
| E：Source终态重复投影 | `api/ingest.py::_external_terminal_payload`原本重建authority/compat/terminal；现直接消费原权威`SourceLibraryCompatResponse` projector结果，API只保原flatten、可选字段与JSON输出投影 | source stable且只读复审接受。事前D21/A0、实际app A21/D48/N27；原adapter必产terminal/authority/compat，API重复重建及缺terminal fallback确已删除。仅受影响宽Any边界收敛，不扩大为全库类型治理，原执行结果由集成统一读回 |
| G：admin graph调用边界 | 去掉API到service无语义增量的reader注入，由service直接消费原document view；content日期SQL复用相同的typed predicate，publish_date空值时才取date(created_at)。保留SQL通配匹配与Python字面过滤的原组合、reader fallback、limit前后位置和policy日期规则 | 源码复审通过，原API A0/D20、service A12/D28，互斥合计A12/D48/N36；作者初报D60/N48为加总错误，采用root独立Git账，必要import及typed调用成本校准为12。G2/G原focused组合已通过，精确范围见下文，不将源码审查计为执行。`list_admin_documents`保留具名selection kernel，原typed query、title/summary/uri搜索、空白与排序语义不同于通用DocumentQuery，不挂虚假后续迁移，也不新增DSL |

三个有界调查席已回填有限清单并完成发放。Runtime剩余面收敛为下列L/M/N三项并已实施；保留核按具体职责成立，不豁免外围整族。

| Runtime收口面 | 最终边界与实际成本 |
| --- | --- |
| L：ReplayEvent row投影 | 原`ReplayEvent`拥有事件值；run/agent-session两projector与lifecycle child-failure三处row构造已复用原事件模块纯转换，源码复审接受。事前约D88/A_max75/N_min13，阶段app A33/D53/N20，最终精确字段port后A65/D53、净增12，未达原N_min13；必要类型成本全计。测试最终A18/D0（含metadata负向与unit marker），旧A9/A17为中间输入；lifecycle以J完成后增量A4/D8分账。caller的SQL过滤、source/incarnation校验、seq/offset、projection digest及CAS继续保留；独立row负向覆盖authority和payload pair，曾重复定义的测试已修，原focused结果见下文 |
| M：CapabilityCellSpec静态壳 | 已退specification四源文件D568及macro未用optional字段D5，app D573/A0；两generator工具D214/A0，初始四专属tests D678分组保历史；最终三专属tests D619，mixed历史reader A99/D437，合计tests A99/D1056；其中w08b的D59只计G1/C1一次。B23原spec/build/compiler相关65份snapshot均仍可读且原hash匹配，C7 sidecar四manifest外部hash匹配，历史证据未改。reader改读同一候选的spec与manifest snapshot及原bytes/hash，不重编译、不把旧资格当现役执行；五个已演进current manifest不强绑旧hash。无caller的current-byte helper随旧壳退役，原direct-successor身份匹配consumer与历史只读assert保留。源码复审接受，原focused结果见下文 |
| N：source旧NonStartProof | 已退`source_contracts.py`孤旧Proof/protocol，实际app A0/D52/N52；C2 AST名单删除已不存在的原`NonStartProof`一行属tests D1/A0，不混入app。现役generated/kit绑定未见旧类型消费者；实际batch/reconcile使用`runtime/recovery.py`的另一权威Proof，provider readback/cancel与UNKNOWN保留，不得将缺receipt或lease过期推成NOT_STARTED。源码复审接受，原focused结果见下文 |

具名保留核按实际职责限定：`transitions/reducer/replay`分别承担状态表、当前step/run收缩和journal投影；scope resolver从原registry取得身份，不同effect边界的重读保护current/stale含义；`runtime/recovery.py`的readback和successor授权承担实际reconcile。`research/codec.py`与capability checksum的UTF16排序、datetime、拒绝有损值及bytes编码不同，合并会改变持久digest，当前不引入版本化codec迁移。workflow assembly及base cell binding有真实原消费者，fixture继续作为独立框架扩展见证。这些核的外围已定重复装配由K与L完成收敛；保留理由不扩大为整个目录的豁免。

Host/source剩余保留面已具名：`ProjectRetrievalService`是API/tool共同领域权威；`CandidateSearchRequest.from_legacy`等仍供discovery/smart实际兼容投影消费；前端manifest已唯一派生routes/contracts/registry，`legacyHashAdapter`保留原Playwright验证的入口投影；`request_identity`与`settings_manager`承担真实权限及配置。已退四个search-lab资格脚本/tests及现有owned ops/local entry按原账处理，不重复计量。同步HTTP CRUD无需为目录形式强建native Runtime。

J只读复审曾发现抽取后丢失effect recovery与assignment interpreter profile相等约束，集成已在原校验源恢复。原PG node `test_p0b_postgres_integration.py::test_typed_public_control_rejects_missing_tampered_and_embedded_payloads`新增独立负向：重签合法recovery JSON/ref/digest而保持不同interpreter，断言原repository拒绝。源码已核，集成回传该node实际1 passed/exit0，证据为原inline工具输出，无独立日志文件；此前连接URL未percent-encode的环境attempt为1 error且shell末尾unset掩盖退出码，不计通过。此返工及验证计入本批，不以公共helper输出自证。

H/U/E作者回传的局部执行均为原inline工具输出、pytest exit0，无独立日志：H的`test_skill_runtime_unittest.py`与`test_rapid_native_macro.py`合计24 passed、10 subtests；U的collect adapter、ingest metrics、frontdoor context、latest-service ingest boundaries和frontdoor fetch router五文件合计20 passed；E的source-library同步终态node与frontend ingest flow smoke文件合计3 passed。H的workflow API mixed修后结果见下文；S修正前旧51 passed不作为当前源证明，修正后重新执行的51项见下文。四包无tools改动；tests独立成本为H A100/D0（含mixed witness，原首次分账）、U A88/D374、S A24/D0、E A12/D0，不抵app收益。各selector使用独立tmp/cache/Hypothesis与不可达DB/Redis/ES，这些结果不构成真实provider或PG证明。

L/M/N原focused组合已由Runtime作者实际执行：最终82 passed、6 subtests、3 warnings，9.02秒、原pytest exit0。首次同样收集到82 passed，但外层zsh写只读`status`变量令命令exit1；修为`pytest_rc`后重跑，只将第二轮记为最终PASS，不累加两轮通过数。L两处测试重复定义及M历史reader适配返工计入本批；65份snapshot与四份sidecar哈希核对仅为只读证据核验，不计入测试数。此局部组合不替代Runtime真实PG、统一完整suite/coverage/公共类型与七gate；G2/G及S最终focused结果见下文。

S最终修订由作者实际重跑原三文件：`unit/test_project_tool_contribution.py`25项、`unit/test_agent_runtime_tool_pool_unittest.py`3项、`unit/test_agent_core_unittest.py`23项，合计51 passed、3 warnings、11.73秒，原pytest_rc=0；collection为51项、collect_rc=0。日志`/tmp/mrw-s-final-pure-20261009/{pytest,collect}.log`已只读核对，包含独立`test_source_library_run_is_project_tool_author_source`与完整`test_project_tool_operation_rule_preserves_identity_exception_and_permission`，无同名覆盖造成少收。此结果对应恢复exclusive/ask、撤去多余governed metadata后的当前源码，与修正前旧51项分开，不相加。

G2/G原focused组合由root回传39 passed、6 subtests、4 warnings，13.41秒、pytest exit0，源码稳定。四文件范围为`unit/test_projects_global_stats_unittest.py`、`integration/test_runtime_ops_error_contract_unittest.py`、`unit/test_consumer_sql_predicate_facade_unittest.py`及原G13 `integration/test_admin_graph_standardization_unittest.py`（均在`main/backend/tests/`）。新global-stats测试用fake connection检查单连接、事务语句顺序、enabled查询、跨schema聚合、非法schema和缺表失败；API测试检查退役sync为404及原counts envelope；日期谓词测试检查同列NULL回退及两端range，G13复用原admin graph消费者。DB/Redis/ES均隔离且未连接，故不证明真实PG并发snapshot、实际跨项目权限或disabled/删除数据行为。该时点G2 helper71行包含于app A75/D250/N175；最终helper80行与context修复纳下文互斥账，旧数不作终值。G仍A12/D48/N36，不重复计量。

现役`first_specimen_*`已核真实production组合调用：activation重开Program/Plan/QualifiedPlan，物化项目value并发布opaque ref/work；terminal/reconciliation参与原worker。其历史名称不是退役依据，claim/current authority/UNKNOWN/原子终态核保持。JournalCommandSet跨run/step/attempt/work包含revision、CAS与allocator事务列，不能只从RunSnapshot重建；它不是可直接删除的第二运行owner。

H原reader测试body已恢复完整，HEAD原38个函数成为当前39个且原reader nodeid唯一。作者最终执行workflow API整文件39 passed、33 subtests、4 warnings、23.02秒；审批窗口8个原精确node passed、4 warnings、12.90秒，pytest及collection均exit0。`/tmp/mrw-h-mixed-final-20261009/`的原两份pytest与collection日志已只读核对；前后K输入hash相同（production `e175cc500c8d6b5f3b81bfacd925e7acf89a6fd2dbbed025c5555dd69c52d3bc`、workflow assembly `f4089a51f5276fb7c3dbee83902ee4efada2ca53b63b607c59020bfd7e200ba7`），结果只归该读窗，不冒充其后K变化的整组结果。

G2新增`main/backend/tests/integration/test_projects_global_stats_postgres.py`已在专属PG实际4 passed、2.80秒、pytest exit0；`/tmp/mrw-gstats-realpg-20261009-final.log`已只读核对。见证覆盖当前canonical行数及删除后下降、disabled项目排除、项目列表snapshot建立后另一连接提交新增而本次计数不变且下次可见、非法存储schema及缺表失败；没有把该四项扩称HTTP权限或外部provider证明。root核对owned DB及active连接前后均0并释放50923。此前两attempt各1 failed/3 passed分别为fixture及regex问题，保留原失败归属且不累加通过数。

G2前端作者回传原lint/build/Ops i18n均exit0；原Ops Playwright首轮11 passed/1 failed，失败为专属action loop仍要求已退Sync Aggregator。最小test-only修正A2/D2移除该action，保留Re-extract/Topic Extract；该时点collection为11项，原11项通过沿未变source/spec主体保留为kept；最后已在当前输入实际重跑11 passed，见下文最终日志，不以kept冒充重跑。已退node单独匹配为no tests found，仅说明退役，不记一次通过；4194无残留。该lane始终为mock交互证明。

K阶段源码复审固定于以下八个SHA256前缀（最终依赖修正另列于下文）：catalog `824e05a96454`、production `97b03f9e5e8a`、retrieval execution `fa2213f78015`、workflow assembly `f4089a51f527`、dispatch handler `afc311a5a45c`、wait handler `68bda11ebaf1`、retrieval native `67fe4f7199f1`、common `c550238b03ab`。该阶段复核期间及test-only修正后均匹配。唯一`InstalledOperationView`引用原source/contract/profiles/codecs，原NativeContribution持有装配；已退Facts副本、Entry转发、identity compiler、旧kind装配分派及纯`_contract_install`。`InstalledOperationContext`仅为原engine/scope/entry/dispatch/broker参数的tuple类型别名，没有新增运行状态或owner。

六族的实际类型关系为workflow context到context、candidate invocation到attempt outcome、四个work leaf的CandidateWork到CandidateWork、两个control leaf的RetrievalControl到RetrievalControl、URL request到outcome、dispatch payload到ACK、business wait的同ACK到result。leaf的原定义改为generic并以Literal/overload固定两种I/O，原唯一invoke表返回两个typed映射，删去两处旧cast；没有第二kernel词表。原production具名核保留ordered review的prior identity和批准前缀、URL definite failure/UNKNOWN、同步candidate搜索、workflow settled Failure、dispatch ACK关联及wait result关联。绑定校验比较完整contract、binding contract/profile/authority和实际codec对象身份及payload type；worker仍重读ServerProjectScopeResolver及当前qualification，Runtime/journal/UoW拥有运行事实，领域writer不转移。

| K阶段八路径生产账（相对仓库根；最终九路径见下文） | A | D | 净新增 | 必要变化 |
| --- | ---: | ---: | ---: | --- |
| `contributions/project_catalog.py` | 2 | 0 | 2 | 消费唯一tuple派生projection |
| `main/backend/app/composition/production.py` | 246 | 200 | 46 | 原typed核具名接入，删除facts/handler两份闭集；原核保留不算删除收益 |
| `main/backend/app/services/project_retrieval/execution.py` | 10 | 15 | -5 | 唯一invoke表固定两种typed映射，删旧codec cast；此前root局部加总漏此10/15，已校正 |
| `main/backend/app/successor_runtime/assembly/workflow_assembly.py` | 0 | 1 | -1 | 原装配核保持，删除未用行 |
| `main/backend/app/successor_runtime/capabilities/retrieval_material_native.py` | 40 | 11 | 29 | 原leaf定义的generic/Literal/overload固定具体I/O；旧500/227账漏计此路径 |
| `main/backend/app/successor_runtime/substrate/postgres/batch_task_submission_handler.py` | 20 | 3 | 17 | codec/type只读观察及同实例注入，原scope/ACK检查保留 |
| `main/backend/app/successor_runtime/substrate/postgres/first_specimen_reconciliation_handler.py` | 7 | 8 | -1 | wait原构造器消费传入contract/codecs，原result检查保留 |
| `main/backend/app/successor_runtime/assembly/installed_operation.py`（新增） | 215 | 0 | 215 | 一View/native factory、只读异构接口、typed惰性装配、唯一membership、fullref lookup及无写权projection |
| **K合计** | **540** | **238** | **302** | tracked325/238加新增215；tests、派生JSON及工具另账 |

K原删除估算中的retrieval activation16行实际保留：它装配原Program的transform/merge/discriminator，wait recovery adapter与child settlement也承担具体恢复/父子观察职责。root已裁为具名必要核，不另造callback框架抵行数，不整体豁免production。原A360/净增150与后续A500/净增280未达，后一差额为40A及净22；root在该阶段接受上表精确540/238/302；最终dependency guard修复增加workflow profile路径，九路径544/240/304另经root确认，不把阶段数当终值。

K集成回传同hash实际结果：公共类型0 errors/0 warnings；9文件focused186 passed、16 skipped（缺PG环境）、33 subtests、exit0；同hash独占真实PG45 passed、3 warnings、24.02秒、exit0，涵盖mixed16、dispatch4、candidate2、ordered/leaf child、URL abort及cancel，缺PG的pure skip不计通过。原错误DB/driver attempts保留失败归属，不并入PASS。贡献sync曾先后遇到缺object与跨operation重复object，均修共同projector，最终sync/check clean；dev test38 passed、现役七gate234 passed另记，不相加作唯一总数。原新profile负向曾同时存在codec对象不等而可能误证；最后在`test_runtime_handler_assembly_rejects_drift_without_effect`改用同source native，先断言Accepted，再分别仅改变profile、authority、等值新codec而Rejected，实际1 passed、0.63秒、exit0，源码已核。此test-only修正不改变八生产hash，PG45不重复执行；该时点整波fullsuite/coverage尚待；最终结果与新源码hash见下文。

G2 gate修复曾错误引用不存在的`PROJECT_SCOPE_INVALID`，造成公共类型2 errors及invalid四项失败；旧4项PG/2.80秒只保原输入归属。改为现有`schema_binding_conflict` public Failure lift后，root回传相关13 pure及4 PG重新通过，公共类型0、七gate234通过；不以旧结果直接标kept，也不累加两轮PG数。

### 最终集中验收与完整成本（2026-10-09）

最终结果索引为`/tmp/mrw-final-integration-result.json`，本次回填读到的SHA256 `acaef416e77f9f569f2cf723422e64465d27f9ee5ef03036c37d4d7434b9876f`；23项当前检查、3段coverage和4份保留attempt共30个日志的bytes/hash已逐项核对一致。物理互斥账为`/tmp/mrw-final-machine-account.json`与`/tmp/mrw-final-package-account.json`，覆盖109个变化路径及4个新增未跟踪文件；文档回填前全变化digest为`e95db3e49908bbc1e5eb2e1e13737d1abe735fdf5966ea7824a7851981286f05`，它包含文档，不能冒充回填后digest。文档变化只重算该账及diff检查，不触发无变化源码重验。

| 原验证范围 | 最终证据与实际状态 |
| --- | --- |
| backend全集与精确补集 | 原`/tmp/mrw-backend-all-final.log`实际3732 passed、14 skipped、5 failed、280 subtests、756.31秒，exit1保留。API库存两项、W03一项及两dependency guard失败已修；原四文件在`/tmp/mrw-backend-five-failures-focused.log`实际25 passed。原全集命令明确ignore仅支持Unix socket的capacity文件，当前collection3757=原实际3751（3732+14+5）+独立socket实跑capacity5+随后新增metadata负向1。terminal-output负向已在原3751中，不另加一次；metadata已进原unit runner并实际通过。受影响范围另按以下fresh结果替换，未变已执行部分保留，不声称重跑一次3757全绿 |
| CI选择与全集覆盖 | `/tmp/mrw-nodeid-audit-current.log`及`/tmp/mrw_nodeid_audit.json`核unit1760、integration549、core283、e2e16，共2608次调用、去重2521、重复87；backend差集1236，无CI越界。backend3757和root1342无交集，dev pilots38全部属于backend且与CI交集0。原runner与直接backend全量使用同cwd/解释器/配置/plugins，现有conftest无按marker改变行为的hook/fixture；marker和core目录只选择node。因此原全集加精确补跑覆盖差集，不重复运行87项或把collection当执行 |
| root全集 | `/tmp/mrw-root-tests-final.log`实际1340 passed、2 failed、exit1；失败为两个子进程选到缺Pyright的解释器。`MRW_TYPECHECK_PYTHON=.venv/bin/python`后原两node在`/tmp/mrw-root-typecheck-probes-final.log`实际2 passed、exit0；原1340未变证据保留，非一次1342全新重跑 |
| 当前K与L | K最终真实PG45 passed、3 warnings、36.72秒，`/tmp/mrw-k-pg45-final.log`；L精确row类型pure34 passed及真实SQL RowMapping/projector/rollback PG5 passed，分别见`/tmp/mrw-replay-typed-row-focused.log`、`/tmp/mrw-replay-projection-pg-final.log`，均exit0。边界修复中间79 passed/25 subtests只归当时输入；最终L覆盖替换其受影响部分 |
| 本地PG skip补齐 | 原session1、document-unification6、information-topology3共10个本地PG skip，分别在`/tmp/mrw-agent-session-exclusive-pg.log`、`/tmp/mrw-document-unification-exclusive-pg.log`、`/tmp/mrw-information-topology-exclusive-pg.log`实际通过。required PG无未运行缺口；G2当前Failure修复后的13 pure/4 PG及J recovery-profile负向沿各自原结果保留 |
| 当前源码coverage | 原入口TCP兼容片`/tmp/mrw-coverage-current-tcp.log`2299 passed、4 skipped、1449 deselected、226 subtests，exit0；Unix socket独占capacity整文件5 passed在`/tmp/mrw-coverage-current-capacity-append.log`；新metadata负向1 passed在`/tmp/mrw-new-replay-node-ci-unit.log`原unit runner与`/tmp/mrw-coverage-new-replay-node-append.log`。同当前源码coverage data合计2305 passed/4 skipped；原阈值core409/409=100%、other62906/93716=67.12%，pytest0/threshold0。旧行号coverage未运输为当前证据 |
| 公共类型、负向与原贡献门禁 | `/tmp/mrw-public-typecheck-final.log`为0 errors/0 warnings/exit0；`/tmp/mrw-dev-sync-final.log`及`/tmp/mrw-dev-check-final.log`均clean、issues=[]、changed_paths=[]；`/tmp/mrw-dev-pilots-final.log`38 passed，`/tmp/mrw-gates-final.log`现役七gate234 passed。两个静态negative沿`/tmp/mrw-pyright-negative-selectors.log`预期exit1、17 diagnostics（含既有private-usage债）验证，不能写为全库typing clean |
| frontend | 最终前后source hash一致（`294706…`）；`/tmp/mrw-frontend-lint-final.log`、`/tmp/mrw-frontend-ops-i18n-final.log`、`/tmp/mrw-frontend-build-final.log`均exit0，build含`tsc -b`；`/tmp/mrw-frontend-playwright-final.log`实际11 passed、19.4秒、exit0。这是fully mocked Ops交互证明，不是live backend/provider证明 |

最终四项skip身份在`/tmp/mrw-coverage-skip-identities.log`：`test_live_host_material_chain.py:41`需`MRW_LIVE_HOST_MATERIAL_CHAIN=1`、`test_live_crawler_material_chain.py:143`需`MRW_LIVE_CRAWLER_CHAIN=1`，两条外部live链明确未执行；`test_collect_runtime_composition_unittest.py:108`和`test_llm_provider_boundary_unittest.py:345`由上述Pyright负向承担，不计运行通过。旧coverage2176 passed/107 skipped/24 failed、随后2301 passed/4 skipped/3 TCP errors及其当时socket补齐PASS均保历史输入；frontend首轮1 failed、G2前两PG各1 failed/3 passed、K错误DB/driver、J错误URL及L只读`status`造成外层exit1均不改写为PASS，不累加attempt计数。

集中修复的语义边界已核：K context直接引用原`capabilities.batch_business.BrokerBusinessReadback`，service也引用同一个port；assembly保留合法Engine依赖，Runtime不导入SQLAlchemy或services。workflow以原枚举相同的`NETWORK_IO`/`CPU_LIGHT`字符串构造profile，wire payload和digest输入不变。L的`_PublicJournalRow`只声明实际11字段的四组Literal overload，返回int、原Mapping[str,object]、str或str|None；无新增Any、整row cast或SQLAlchemy导入。原str/int/dict转换、authority/payload pair与digest验证保持，三个SQL消费者继续直接传RowMapping，过滤、incarnation、seq与CAS仍归原owner。最终common hash为`5af464715398`（218行）、workflow capability为`abf98b43c066`、replay为`e8ecd9a99db5`；K其余七路径保持上文hash。

库存修复同步实际API操作数323→309、router320→306、request-body155→148及原权威库存；W03逐项metadata仍核其实际31项，修正陈旧39计数，没有减少实际精确集合。E的终态正向`test_ingest_source_library_run_explicit_project_key_success`及`test_ingest_source_library_run_rejects_missing_terminal_output`、admin checker共8项在`/tmp/mrw-checker-project-key-focused.log`通过；原Core及frontend smoke fixture补齐adapter本来提供的authority/compat，未把错误状态改成成功。四共享checker只更新被退役源的真实锚点；`check_ingest_platformization_repo_local_closure.py`现锚定pure SLO合同，只证明静态SLO，不能宣称现役runtime list-rollup telemetry。

| 最终app Python语义互斥账 | A | D | 净减D−A |
| --- | ---: | ---: | ---: |
| J assignment投影（含lifecycle25/85） | 145 | 180 | 35 |
| H effect/approval | 41 | 7 | -34 |
| G1/C1静态graph壳与clue桥 | 0 | 1830 | 1830 |
| K原生安装app部分 | 542 | 240 | -302 |
| G2统计全链及共享context | 94 | 256 | 162 |
| U旧URL batch | 0 | 885 | 885 |
| S Source工具桥 | 54 | 49 | -5 |
| E终态投影 | 21 | 48 | 27 |
| G admin reader | 12 | 48 | 36 |
| L replay（含lifecycle4/8） | 65 | 53 | -12 |
| M静态spec壳 | 0 | 573 | 573 |
| N旧Proof | 0 | 52 | 52 |
| **app Python合计** | **974** | **4221** | **3247** |

K另含`contributions/project_catalog.py`A2/D0，故九生产路径总账A544/D240、净增304；第九条`workflow_native_contribution.py`A1/D2与common218均已计入，未搬家抵收益。J/L共同lifecycle物理29/93只计一次，五路径合计A210/D233、净减23。G2包含helper80和context10/6；原75/250/N175不是最终成本。H tests最终A99、E tests A40/D2、L tests A18，原局部A100/A12/A9/A17保阶段归属。M tests最终A99/D1056，w08b59归G1/C1，历史快照与sidecar字节不变。

物理类别另账：app内route JSON D16；tools/manifests13路径A37/D1472；tests45路径A1130/D2626；frontend5路径A2/D17（其中spec A2/D2）；文档回填前4路径A111/D43，含原权威API库存A19/D35。回填前109路径总计A2254/D8395、净减6141，含文档与测试，不能当生产Python减量；回填后由集成重算文档类别与总账。四共享checker A33/D24、pyproject A2/D1、context A10/D6和两个app新增文件均无漏计。app由641文件231238行变为632文件227991行；从`a17930da`737文件299234行累计净减71243行、23.81%，与本波3247分别计。vendor本波无变更，沿§4原独立账保留。

K、H、S、L未达初始净减/新增预算及G2最终N162低于原N_min164均保留；root按必要类型、权限、Failure与事实owner边界接受最终精确成本，不以总净减冲销偏差。首次共同验收总耗时、各owner完整调用/token和共同设计等待成本未完整统计，缺失不记零，不报告提速幅度。

| 原能力面 | 最终处置、保留理由与验证 |
| --- | --- |
| R1 来源与采集 | **完成。** U/S/N退旧batch、工具桥与孤Proof；单URL/provider/source runner承担实际effect，material writer保唯一材料事实。K URL/abort、source终态正负向与本波原消费者已证；两条external live链未执行，不纳本波新增义务 |
| R2 检索与资源 | **完成。** K candidate/leaf同源安装且当前PG45覆盖dispatch、child commit及读回。同步candidate、预算/topology、ordered review及activation transform/merge/discriminator为具名必要核；索引为派生表示，不新增写owner |
| R3 材料导入与读写 | **完成。** E退重复终态投影，CompatResponse与材料writer仍为权威；G2读canonical表，disabled/删除行及并发snapshot PG已证。材料/拓扑/文档统一的本地PG全部补齐，API只投影不取得写权 |
| R4 知识与写作 | **完成。** G1/C1退静态资格壳与clue桥，G退reader透传；真实graph writer/reader/alias/backfill、curated revision、clue及写作核按原职责保留。mixed/history及原writer消费者在全集与补跑覆盖，历史字节不改 |
| R5 宿主与工作流 | **完成。** H效果标签与审批解释分离，S回到原AuthorSource；原宿主推理、workflow settled Failure、dispatch ACK、wait read/cancel及business result核保留。K当前PG45和session补跑覆盖实际worker/readback，当前权限继续由原边界重读 |
| R6 项目治理与API | **完成。** G2副本同步service/API/Celery/cursor/前端全链退出，原项目/auth/retention保持；`list_admin_documents`保原selection核。当前route binding、API库存、Failure lift、权限/envelope及真实stats PG齐，未DROP存量表 |
| R7 选定Runtime | **完成。** J/L同源assignment及journal row投影、M/N静态壳退役；K六族13项实际安装同源。journal/UoW/current grant/CAS、UNKNOWN、reconcile、wait恢复及child settlement为唯一运行owner的必要核；具体类型、独立绑定负向、真实PG与回滚齐 |
| R8 前端与宿主适配 | **完成。** 本波G2旧按钮/client/endpoint/i18n撤回，fresh lint/tsc/build/i18n及11项mock Playwright通过。真实交互状态、授权、manifest与host生命周期保留；未变iframe/host及远程OAuth不追加新退出义务 |
| R9 kit与验证消费者 | **完成。** 原有效tuple、声明/route/pyright include、派生registry/sketch与原消费者一致，sync/check clean、公共类型0/0、七gate234。3757/1342精确全集与CI差集、当前coverage和实际补跑闭合；W04/I1历史字节保持，退役专属工具/tests退出，静态SLO与运行遥测证明范围分开 |

| 波次／可执行前沿 | 顺序、并发及完成后的动作 |
| --- | --- |
| A：一次有界全覆盖分类 | 3个只读调查席覆盖九项，root裁真实语义接缝；每项交精确可删/收敛闭包、具名保留核或真实blocked_by，并定D/A_max/N_min。已有充分证据的包立即执行，不等待无关项；未定预算不标ready，调查不再另起无限候选轮次 |
| B：独立整族退役与必要首例 | 最多3个互不争写的领域/Runtime作者＋1集成席。余下family assembly及工具闭包按实际消费者切出；已有同形规则直接复用。新公共规则只用一个真实原消费者打通，根因由该owner修正，依赖它的包后行，独立kernel/安全退役继续 |
| C：沿能力链合入并同批删旧 | R1→R2/R3、R3→R4、R1/R2↔R5仅在实际接口/结果依赖处串行；R6/R8跟随相应API与真实用户链。接口已定的上下游实现可并行；production/catalog/共享assembly及R9 shared selector由集成统一合入，切换、删除、见证与实际收支构成同一包 |
| D：九项总体收口 | 每项可删除/收敛子闭包均完成，具名保留核及原消费者被验证，真实blocker为0，本波精确删除闭包内未判定符号/路径为0；不把机械全路径覆盖扩称全部源码语义审计。该波收口统一运行现有原suite或其已有planner完整清单，以及七gate、公共类型、受影响真实PG/浏览器范围；先核任务覆盖与资源，不用dev test子集代替全量套件。kept与本轮passed分别记，失败修复只重验受影响部分；完成一包不能代替本波退出 |

分类闭合、组织退役与执行收敛是三个不同条件：九项全有分类/原消费者验证，只完成覆盖条件；还须实际退役services旧整体组织中的重复装配、调度和事实承载，必要类型/effect/kernel逐项固定稳定承载及理由；再独立证明只有既选Runtime拥有运行事实，所有必要能力的原生定义/规则到真实生产消费者同源接通。不能以几千行assembly删除或“全部有引用所以保留”替代后两项。

总体退出须同时满足§7：九项及全路径账无漏面；同一运行/领域事实均有唯一owner；旧loop、adapter、静态资格壳和重复装配的已定闭包不可执行；每包实际D/A/N达到原预算或由root按必要保留核明确校准，原偏差不抹除，公共及跨目录成本不漏；所有必要原验证完成且当前未解决失败清零，历史failed和明确excluded的skip保持原义。具名保留核可以稳定保留，不要求services目录按名字归零；不得以搬目录、删除文档/测试或工具净减抵消app新增。用户必要能力不因减少行数而静默撤回，有损改变须明确版本与已裁定兼容行为。规模总承诺只据实际闭包校准，旧硬帽与“6–10万”历史情景不恢复。

全局最多6名活跃Agent：root分发/裁定、Astra编排/只读审查/现有三文档各1名，作者/调查者与集成合计最多4名；Astra不写源码、不跑源码测试、不提交、不另spawn。公共接缝由root裁定，集成唯一维护共享消费者、目录、sync/check和shared selector；领域作者不能各造parser/adapter。每包回传目标、权威接口、实际产物/独占写面、D/A/N、命令/原退出码、风险及成本，沿现有记录汇总，不新建管理平台。

共同cwd为仓库根；Python为`main/backend/.venv311/bin/python`，`PYTHONPATH`为根、`src`、`main/backend`。PG专属端口50923由集成管理，PG/coverage/frontend build/E2E各独占；pure最多2进程，使用独立tmp/cache/Hypothesis目录及不可达DB/服务端口，不写共享coverage。测试并发按资源与输入判断，不按语言/文件名猜测。旧部署Stage4–6仍STOPPED；本轮本地精简与验证不授予push/deploy权限。

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
| V-wiring | `focused main/backend/tests/successor_runtime/test_c1_native_catalog.py main/backend/tests/unit/test_workflow_graph_executor_kernel_unittest.py`；C8 prototype专属见证随整岛退出，现役知识图能力沿原information-topology消费者验证；在原workflow测试与V-durable补同源变化、非默认production、类型/identity/authority负向与无effect见证；本批workflow首例覆盖见§2.1，不外推其它能力 |
| V-core | `focused main/backend/tests/successor_runtime/test_program_ast.py main/backend/tests/successor_runtime/test_compiler.py main/backend/tests/successor_runtime/test_p3_traversal_foundation.py main/backend/tests/successor_runtime/test_p0d_event_replay.py` |
| V-durable | workflow首例复用下列精确命令及`test_p0c_postgres_activation.py`相关原见证；原`main/backend/tests/successor_runtime/{test_agent_batch_api_pg,test_request_cancel,test_mixed_operation_worker,test_traversal_persistent_activation}.py`，设置实际专属`SUCCESSOR_TEST_DATABASE_URL`，fixture资源先核再运行，PG独占 |
| V-type／V-kit | `MRW_TYPECHECK_PYTHON=.venv/bin/python main/backend/.venv311/bin/python scripts/dev.py typecheck --public-boundaries`；原venv `scripts/dev.py sync`（有声明变更时）再`check`、`test`、`gates`；受影响原ruff保持，不手改派生表 |
| V-suite | `bash scripts/test-standardize.sh ci-pr -q`及原`coverage`入口，100/20不降；沿现有selector清单核精确新增/退役/资源分区，capacity原Unix-socket条件保持。只按实际交付与依赖跑，不由文档编辑触发 |
| V-host／V-ui | 沿实际改动选择原auth/typed-fetch/manifest/浏览器与写作API见证；真实provider调用需其原授权资源。无宿主适配改动不新加模型测试；vendor/generated分账 |

本波集中清单先以当前collection核对新增、退役与重复nodeid。`ci-pr`实际只执行unit、integration、core-business及e2e四个原runner，不自动覆盖contract-only或未标记测试；`dev.py test`也只执行三份pilot。集成已用原pytest全集、精确补跑及selector差分补足backend差集与根`tests/`，结果见§5；不以旧总数证明当前覆盖。`dev.py gates`运行原`tests/test_architecture.py`，公共类型沿原include并纳入K实际新增assembly/production闭包；已删aggregator include需同步到当前真实边界。`test-standardize.sh coverage`仍以unit/integration原选择与原core100%/other20%门槛执行，PG和coverage数据独占，禁止重复合并同一node结果。

G2前端只沿实际撤回范围执行原eslint、`tsc -b`/build、`check:ops-page-i18n-slice`及`tests/e2e/admin-ops-repair.spec.ts`；该Playwright文件明确mock，不替代G2实际PG/API。K真实消费者沿原mixed worker、p0b candidate/dispatch与traversal leaf/URL/ordered/cancel见证，J/L沿p0b drift及p0c lifecycle/activation/current-grant；精确最终selector与稳定源码由集成在原清单确认，结果见§5。G2真实PG4项及全部required本地PG已完成；两条外部live链明确not_run，两个静态negative由Pyright验证。

Runtime原见证沿`main/backend/tests/successor_runtime/`中的`test_p0d_event_replay.py`、`test_p0c_node_adapter.py`、`test_p0c_admission_recovery.py`、`test_p0c_delivery_recovery_postgres.py`选择受影响观察；C2 prototype专属recovery见证已随整族退出，分别进入V-core/V-durable及原fixture资源窗口。需要PG的见证必须使用已知专属数据库及原fixture，不能放进`focused`不可达DB环境；值与事务原消费者入口为同目录`test_p0c_postgres_lifecycle.py`的`test_runtime_value_index_and_staged_artifact_store_only_opaque_refs`、`test_terminal_outcome_updates_full_semantic_packet_atomically`及`test_authority_provider_rehashes_current_scope_grant_and_capability`，沿原scope fixture进入V-durable。row候选的同源变化若缺覆盖，只在原测试补最小读写/identity/失败见证，不伪称上述测试已覆盖新增义务。

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
- 需要耐久生命周期的运行由既选Runtime拥有唯一运行事实；必要操作沿原生权威定义到实际production/worker/reader或同步调用consumer，同形接线按已支持规则派生。HTTP CRUD与一次同步调用不另建native Runtime；身份、权限、版本、失败和effect见证不因此减弱。旧接线与冗余实现整族退出，每包按原或明确校准的D/A_max/N_min核算，缺失事前预算如实保留；全项目具名必要核与互斥删除闭包覆盖明确，不以分类、注册或门禁通过代替实现完成。
- 原注册/配置/派生见证/专属测试/文档同批一致；非默认同形定义到真实消费者且类型/identity/authority错误拒绝，声明/sync无effect；框架机制与项目迁移分别具备必要行为、公共类型、现役七gate及实际交付证据，operation/codec/kernel/reader保持具体类型关系，kept、skip、not_run与失败按原归属记录。
- 成本包含共同修复和跨目录新增；生产/测试/工具/前端/vendor/历史分列，不以删文档、搬家或旧dirty回撤抵扣。缺失调用/token和完整验收成本不记零，不报无证据提速。

**本轮文档规划的有限精简面已完成本地验收。** §5九面均完成具体处置，已定删除闭包、services重复组织收敛、必要能力同源接线、具名kernel与唯一事实owner已分别确认；完整collection与原runner差集、必要真实PG、当前coverage及公共门禁已按实际分步结果闭合。当前required验证无未解决失败，原failed attempt、四项skip及未执行外部live范围保持原义。内部全面类型治理、全库零冗余、UI重设计、性能和新扩展建设不加入退出条件；不再寻找无界下一包，不恢复未经证明的硬规模承诺。此完成不授予发布权限，未push/deploy，旧Stage4–6仍STOPPED。

## 8. 上一轮迁移历史及本轮状态

上一轮结果已提交为`c3adced`：完成既选Runtime迁移与保持验证，但生产净减仅29行。原`LOCAL_COMPLETE_NOT_RELEASE_AUTHORITY`是当时迁移合同的本地闭合记录，不能继续作为用户全局退役/显著瘦身目标的完成声明。原文与逐attempt记录可用`git show c3adced:docs/development/MRW平台结构精简与删减阶段.md`读取，不在新当前章节重复重写。

原证据根`/tmp/mrw-structure-20261007-w4uct7gr`，最终`integration/ci-group-resumption-2.json`的SHA256为`878665a345cd21b3ab5002595b7f0835354c2ad3e5322b70aea6fbc8edbf848c`。原ci-pr-4和native coverage-2 exit1保留；Search15替换旧9后归属2668 passed/4 skipped，186subtests另账；原431补集为426原passed＋3 PG39 kept＋W04修后1＋PG40补运行1。PG39原21、七gate291、core/e2e原分步以及合并coverage core409/409100%/other69.41%保留原依赖边界，不因本次改写撤回，也不冒充新退役执行证据。

原frontend14含route mocks及Codex iframe mock shell，direct HOST1只证明注册写作工具/approval/turn及canonical API/SQL读回；内部类型/Ruff债、4skip和缺失调用/token成本继续保留。上一轮workflow＋999/retrieval＋3763/shared＋1594的独立增长责任进入本轮定界，source下降不抵消。

首批实际完成与attempt保留于§2.1；第二批旧generator、I1外壳及workflow静态资格链退役与返工集中记于§2.2；三份当前文档随批次交回集成owner统一提交。本波§5九面有限收口与§7整体条件已依据当前源码、完整成本及分步实际证据完成；历史预算偏差、失败attempt、kept和未执行范围分别保留，不再笼统要求寻找下一闭包。三份文档回填后由集成统一重算账与提交；未push或deploy，旧Stage4–6部署任务继续STOPPED。
