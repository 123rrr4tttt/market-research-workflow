# MRW 平台结构精简与删减阶段

> 2026-10-07 · **当前：整族退役设计与定界，实施未开始。** 基线`c3adced5946a52b66be4494aba3dbb707ee879b5`；上一轮迁移保持结果列为§8历史，不再等同整体精简完成。平台必要能力和事实归属沿[MRW精简框架](MRW精简框架.md)，流程沿[19号规则](../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/19_direct-testing-batch-freeze-amendment.v1.md)；[06号入口](../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/06_production-deployment-stage-progress.v1.md)的旧部署任务保持停止。

## 1. 退役终点与边界

本轮终点是必要能力由最小现有核承担，旧实现族及其消费者接线整批消失，并达到发包前的净减承诺。保留用户能力、对象身份、权限、真实effect和失败观察，不默认保留目录、API、测试或checker。每包明确是停止冗余功能，还是保留能力的实现替换；前者记录撤回范围，后者证明原必要观察保持。

services旧整体组织承载与successor重复承载都在退役范围，API/胶水和其它app源码不漏账。必要领域类型、特殊kernel、provider/DB效果逐项证明后接已有原生贡献位置，不把services全量搬家或包装进新runtime/domain/DSL。唯一耐久Runtime沿既选内核，领域writer、DB/provider和host权威不转给API或投影。真实必要核可以暂在原文件承载，但必须具名、压缩且没有整文件/整目录保留豁免。

## 2. 基线、预算与完成判断

全项目计量范围、当前基线、各项硬上限和分帽以[框架§4](MRW精简框架.md#4-全项目规模预算与收支约束)为唯一权威；本文不另抄预算表。app仍为`c3adced`的758文件307472行；上一轮迁移净减29行，不计作本轮结构退役完成。现场全项目定位数据为`/tmp/mrw-whole-project-budget-20261007/whole-source-baseline.json`，可按原口径复算。

`A=main/backend/app`，`B=main/backend/tests`。全局设计上限已经确定，但可达性未证明。每包发放前仍须取得精确可删闭包、必要保留核与`D/A_max/N_min`，共享文件/符号只计一次；新增含集成接缝及跨目录转出。原130文件运行结构物理族同时受框架净减目标约束，抽出领域核及所有替代/接缝成本计回原族，不能仅改归domain声称删除；该族与全局只计一次。未定该包预算时只做定界，不先扩建实现；不等待全部包预算相加才承认全局目标。首批2149仅覆盖三个小闭包，不能代替下述三阶段退出条件。

超过分帽须由root按框架规则在固定总额内裁定；无法满足最小充分语义时报告具名反例与备选，不默增、不删必要能力、不弱类型。测试、现役文档与历史库存分账，不抵扣运行实现成本，也不能靠移入archive逃预算。

## 3. 已定首批退役包

共同执行合同：cwd为仓库根，Python为`main/backend/.venv311/bin/python`，`PYTHONPATH=.:src:main/backend`；只使用现有依赖。表内验证命令由§6的`focused`执行，当前仅设计未运行。每包输出原文档中的实际删除/新增、消费者切断、原验证结果及风险，不新建报告或平台。

| 包／目标与权威输入 | 精确源范围、消费者与最小核 | 输出与预算 | 独占写面／仍存验证／完成条件 |
| --- | --- | --- | --- |
| **运维镜像层退役**：停止已无app调用的重复ops surface；原API与生产观测继续承担健康、配置和运行查询 | `A/successor_runtime/ops_domain/{__init__,base,dashboard_admin_surface,health_matrix_surface,ops_misc_surface,projects_config_surface,runtime_ops_surface}.py`，7文件1345行；`ops_surface_failure`等仅被两专属测试消费，旧s2c装配器已不存在；无需保留kernel | 整目录及专属`main/backend/tests/functorial_debt/test_w07_ops_surface.py`、`main/backend/tests/successor_runtime/test_s2c_ops_domain_surfaces.py`退出；生产`D=1345/A_max=0/N_min=1345`，不得新增生产壳或见证来维持旧surface | 该7文件与两测试；`scripts/build_functorial_debt_packet_registry.py`路径项由集成owner串行处理。贡献权威源、派生registry/sketch/witness的实际影响沿原sync/check收口，不能手删派生条目或豁免gate。现有`src/mrw_functorial_kit/core/w07_semantics.py::ops_surface_failures`与`registries/failures.json`的`successor.ops_surface.failure`由根W07测试独立消费，保留该失败声明/历史识别，不因此保留ops模块或新增生产壳。验证V-ops及引用清零；原健康/配置/权限保持，整族消失才完成 |
| **旧本地索引功能退役**：停止无现役app能力要求的LanceDB local-index路径；保留当前search/indexer入口 | `A/services/local_index/{__init__,embedding_provider,schema,service}.py`及`adapters/{__init__,lancedb_adapter}.py`，6文件695行；唯一外部执行consumer为`main/backend/scripts/check_wave14_vectorization_provider_capability.py`；无保留核 | 目录、专属checker与`main/backend/tests/unit/test_local_index_service_unittest.py`同退；生产`D=695/A_max=0/N_min=695`。不新增另一个索引adapter | 该目录/checker/test；`main/backend/scripts/pre_release_gate.sh`对应已退selector由集成owner改。验证V-index及精确引用清零，原search/indexer能力保持；不是为了green而删现役gate |
| **来源常量壳退役**：保留source item默认capability，退出streamplus旧合同族 | `A/services/streamplus/{__init__,contracts}.py`共115行；唯一现役consumer是`A/services/source_library/item_writer.py`对`SOURCE_ITEM_CAPABILITY_DEFAULT`的读取。其余dedupe/idempotency符号无外部consumer；最小核为原5行常量 | 常量落现有item_writer，连注释空行新增最多6行；生产`D≥115/A_max=6/N_min=109`。不建新常量模块；目录与专属`main/backend/tests/unit/test_streamplus_contracts_unittest.py`同退 | 两源文件、item_writer中该常量和import；其余来源改动不授权。pre_release_gate同一owner清其专属selector。验证V-source及默认字段保持、引用清零；之后item_writer交回来源owner |
| 首批合计 | 三个生产删除集合互斥，共15文件2155行 | `D=2155/A_max=6/N_min=2149`，不是全局目标 | 非app源码、脚本/测试改动单列；不得以外移新增绕过上述上限 |

零新增包只能清理既有义务并复用仍存见证。如果当前贡献源/注册闭包要求新代码，先返回该包重新定界和预算，不能在A=0名义下偷偷新增。历史快照保持原字节；仅取消已退功能的当前生成/验证入口，仍需读取的历史失败标识继续通过原只读路径解释。

## 4. 运行结构专项与全域定界包

运行结构专项由耐久内核owner统一承担：沿既选核确定满足框架Runtime分帽的最小保留结构，在原实现内删除或合并重复codec/state、first-specimen/sample、install/admission/reconcile外壳和冻结审批生产化，保留必要typed语言、claim/commit、PG事务与读回；不先新建另一套kernel或全面重写；同时切断旧services执行owner与控制循环。领域canonical writer保持原权威，PG终态记录原子性与current grant重读不得丢失。Runtime跨目录成本全部追入该专项，不能移到领域handler或kit逃账。该专项在第一阶段达标，不能以迁移PASS推迟到最终收尾。

下表是本轮当前工作，不是无限期后置。每个owner输出“必要能力/权威或effect → 具体核 → 要退整族 → 精确消费者和注册闭包 → 互斥文件集 → D/A_max/N_min → 原验证selector”，形成可直接派发的实现包。基线行数只是调查面，不是可删承诺。先扣除§3已分配文件，再为剩余文件发预算；item_writer跨包只有按顺序交接，没有重复成本。

| 具名定界包／owner | c3精确路径范围与规模 | 必须交付的删除对象、核与消费者裁定 | 现成接口／验证入口 |
| --- | --- | --- | --- |
| **来源采集承载定界／来源owner** | `services/{source_library,collect_runtime,ingest,crawlers,crawlers_mgmt,ingest_config,http}/**`：126文件38587行 | `url_pool.py::execute_single_url_kernel`及`terminal_writer`等Material写入核，与collect入口、summary、telemetry、retry/canary/digestion脚手架分开。当前url_pool2112行，旧ThreadPool与旧1049行区间已退，禁止重计。对`digestion_scaffold.py`2903及live canary专属入口先明确停止能力或保持替换，不以checker存在全保 | 原acquisition贡献与Material writer；V-source、原URL adapter/T22 consumer。D/A_max/N_min未定，不能新增实施 |
| **检索与资源承载定界／检索owner** | `services/{search,project_retrieval,resource_pool,discovery,indexer}/**`：56文件19896行 | `project_retrieval/execution.py`2893行按预算判断、候选/URL/正式化核、装配与运行投影拆；resource/search现有入口也审能否合并，不能因mount保整族。交出每条实际检索能力最小保留核与旧服务切断点 | 原`retrieval_candidate_native`、`retrieval_material_native`、`retrieval_flow_native`及正式Material写入；V-retrieval/V-index。D/A_max/N_min未定 |
| **材料知识写作承载定界／材料owner** | `services/{document_queries,document_views,information_topology,typed_knowledge,graph,clue_chains,writing,extraction}/**`：93文件19534行 | 原Material/拓扑/引用身份和写作事务是事实依据；重审Graph投影、typed sample/live表示、查询装饰与图谱重复层。`api/policies/dashboard/admin`的引用需寻找可合并消费者，不构成graph3786行的永久豁免 | 原document query/view、typed知识和writing writer；V-data及原引用写作consumer。D/A_max/N_min未定 |
| **宿主与工作流承载定界／宿主工作流owner** | `services/{agent_core,agent_runtime,agent_batch,agent_sessions,workflow_graph,llm}/**`：85文件37575行 | host推理与MRW授权、消息/批准/业务结果分开；工作流仅`executors/kernel.py::execute_node`先定位为特殊解释核，store/runtime必须逐符号重证。旧合同壳、LLM重复adapter和批次装配全部进入退出判断，不保整文件 | 既有CoreToolSpec、workflow/batch native及已选Runtime；V-control/V-workflow/V-host。D/A_max/N_min未定 |
| **项目治理及旧工具定界／项目治理owner** | `services/{projects,aggregator,governance,local_index,stats,streamplus}/**`：19文件3307行；local_index/streamplus先扣§3 | projects scope、聚合与显式清理效果逐核保留；stats1190行与`main/backend/scripts/check_time_density_runtime_support.py`851行同义尚未证，必须查configured live/release gate/pinned consumer后给出合并或停止闭包，不臆造零新增 | 原project registry/领域事务；V-project与相关现存time semantics原checker。D/A_max/N_min未定 |
| **服务根胶水定界／服务集成owner** | `services/*.py`的19个tracked文件11659行，不含任何子目录 | 精确含`codex_oauth,derived,document_admin,job_logger,keyword_generation,keyword_memory,llm_report_export,llm_report_export_audit,llm_report_export_token_state,llm_report_generator,llm_report_source_enrichment,llm_report_trends,observability_tasks,report,request_identity,settings_manager,skill_runtime,task_readback_metadata,tasks.py`；分别核auth/写入/export效果与可退路由胶水，不能漏账或以根目录全保 | 原host auth、writer、task/skill贡献入口；对应业务owner原consumer。D/A_max/N_min未定 |
| **原生能力与样板定界／原生能力owner** | `successor_runtime/{capabilities,specification,research,ops_domain}/**`：103文件55651行；扣ops_domain已定包 | `specification`2280行连生成脚本/exact-byte历史重放查清；其余capability DTO/特殊核、acceptance/sample/强制装配分别定界。`source_contracts.py`4245、`knowledge_common.py`1597、`material_ingest_common.py`708均须逐consumer重证，禁止无依据80%目标或因测试引用整保 | 原native贡献定义及catalog；V-kit、原catalog/历史reader见证。D/A_max/N_min未定 |
| **耐久核与装配定界／耐久内核owner** | `successor_runtime/{language,runtime,substrate,assembly}/**`及其根`__init__.py`：130文件79503行 | 当前唯一Runtime的claim/commit/UNKNOWN/cancel、typed codec、恢复与effect边界保留必要语义；逐模块删重复表示、安装/样板依赖和桥。调查面79503必须受框架Runtime硬帽约束，至少收缩64503；不能把此数冒充已证明的删除闭包。`projection_contracts.py`由ports/native/projection registry真实消费，须评估最小合同，不能误删 | 原Program/compiler/Runtime ports、ValueRepository、原Postgres实现；V-core/V-durable/V-kit。族净减目标沿框架，实施子包D/A_max及闭包待定 |
| **API消费者切断定界／API集成owner** | `api/**`：39文件26297行 | 逐路由归具体用户能力，停止冗余功能入口；保留入口转回已选kernel，消除另行拼接/补写与兼容层。`api/__init__.py`与successor mount唯一集成写者，不按mount存在豁免 | 原API envelope/auth/项目scope、原native提交与reader；相关原integration/core tests。D/A_max/N_min未定 |
| **平台其余承载定界／平台owner** | app其余88文件15463行：`composition,contracts,models,production_contract,production_observability,project_customization,settings,subprojects,successor_migration`及根`__init__,celery_app,main,release_identity,startup_hooks,web_ui_routes.py` | 模型/合同权威、启动与运维effect按能力核；历史migration/sample/profile和启动胶水给整族退出终点。不得把“其它”当无需调查残差，root文件只按该owner交接 | 原composition、registry、启动与观测入口；V-project/V-ops/V-host/V-kit及真实受影响原测试。D/A_max/N_min未定 |

全项目其它具名包由root分配现有作者席，依框架对应硬帽取得精确收支：**前端owner**审`main/frontend-modern/src`的真实页面/交互与重复表达；**工具集成owner**覆盖kit、贡献、backend/root scripts、迁移、ops、search-lab、frontend tools和local入口，按当前用途停止或替换工具，selector随被测职责退役；**WebUI适配owner**相对具名上游分离vendor内MRW实现及测试增量，未知量不记零；**测试与文档集成owner**在职责退役后合并重复验证/说明并保留独立见证、现役合同及冻结历史。每包使用原入口和原测试，不新增统计平台；现役工具不可改标签逃账。

services六行恰398文件130558行；successor两行恰233文件135154行，连API与其它覆盖758文件。调查owner覆盖完整面，实施写权只按随后精确包授权。两面有真实消费者关联时必须把双方修改合入同一退役闭包，不能各保一层互相引用。

增长复审不是另一个可扩建包：workflow＋999由宿主工作流owner联合原生能力owner对`workflow_graph`、`workflow_legacy_dsl/workflow_native_contribution/workflow_slice_acceptance`定界；retrieval＋3763由检索owner联合原生能力owner对`project_retrieval`与`retrieval_*_native`定界；shared＋1594由耐久内核owner把共用codec/安装/表示成本逐项归回实际受益族。增量沿上一轮跨目录family口径保留，不与本轮独占文件基线混算；`retrieval_material_native`的真实生产引用已核，已不存在的staged/effect文件不列候选。

## 5. 工作顺序、独占写面与资源

1. **运行结构退役**：主线先压缩现Runtime并停旧执行owner，退出条件为跨目录Runtime≤15000、原130文件族达到框架净减目标及旧控制循环整族退出。独立领域必要核、前端、工具当前用途定界与纯删除可并行；依赖泛用接口替代时由一个owner先打通最小首例，不先建大kernel。具体D/A/N按实际闭包发包，未达预算不能以迁移PASS宣布本阶段完成。
2. **领域整族退出**：必要领域语义接入最小承载，同批切断旧消费者、注册、adapter、配置与实现，退出条件为app≤80000及框架各责任分帽满足。API和其它平台在所需接口具备后并行；共享消费者、贡献源和生成闭包由集成owner串行交接。第一阶段已缩减的Runtime不能在本阶段重新膨胀。
3. **整组收口**：自有实现与工具≤130000、自有测试≤100000、当前正式文档≤10000，并完成受影响typed、权限、UNKNOWN、恢复和真实消费者保持验证。工具主体职责退役才取消其selector，现役七gate不降低。新passed、依赖未变kept、skip/not_run及失败分别记录；首批小包、单项green或净减大于零均不构成整体完成。

全局最多6名活跃Agent，明确包含root分发1名和Astra编排1名，因此最多4名实际作者或调查者、最多4个独立写面。集成owner从这4个席位中指定，不能另增第7名集成层；root负责分发和预算裁定，Astra只编排、只读审查和文档维护，其它owner实施；Astra不执行代码验证。可并行的是无重叠贡献源/consumer/测试资源的实际包，不是仅文件名不同。`pre_release_gate.sh`的local-index/streamplus两已退selector由同一集成owner串行清理；item_writer先常量包后来源包。ops_domain涉及的贡献源、派生registry/sketch/witness和公共checker同样集中交接，不能两个作者各改同一生成闭包。

定界的安全拆分上限：来源采集2片（provider/source接口；ingest/collect效果与胶水）、检索资源2片（project_retrieval；search/resource/discovery/indexer）、材料知识2片（typed/topology/graph/clue关系；document/writing/extraction）、宿主工作流2片（host/core/llm授权；batch/session/workflow）、项目治理1片、服务根胶水2片（auth/tasks/skill；document/report/settings）、原生能力2片（capabilities；specification/research/ops历史生成）、耐久核2片（language/runtime语义；substrate/assembly实现）、API2片（领域入口；宿主/控制/运维入口）、平台其它2片（models/contracts/项目定义；composition/启动/观测）。这些均是只读片，结论由该包唯一owner汇合；所有片共用上述4席上限，不同时启动整张表。未定共同接口不派多个实施者各造adapter；实施并发只在互斥预算包和共享消费者交接固定后成立。

PG、coverage、frontend build/E2E各独占窗口；pure最多2并行进程，分别独立tmp/cache/Hypothesis目录及明确的DB/服务不可达端口，不写共享coverage。所有权威定义、注册和所需见证同步后才供消费者执行。测试删除不代表测试通过；停用专属功能后的验收必须指向仍在的相邻能力与引用清零。

## 6. 原验证入口

统一根cwd和原venv；下列是后续实现包的可直接执行入口，本轮未运行。不安装依赖，不恢复已停止历史部署任务，不新增测试调度/证据平台。

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
| V-core | `focused main/backend/tests/successor_runtime/test_program_ast.py main/backend/tests/successor_runtime/test_compiler.py main/backend/tests/successor_runtime/test_p3_traversal_foundation.py main/backend/tests/successor_runtime/test_p0d_event_replay.py` |
| V-durable | 原`main/backend/tests/successor_runtime/{test_agent_batch_api_pg,test_request_cancel,test_mixed_operation_worker,test_traversal_persistent_activation,test_successor_production_wiring}.py`，设置实际专属`SUCCESSOR_TEST_DATABASE_URL`，fixture资源先核再运行，PG独占 |
| V-type／V-kit | `MRW_TYPECHECK_PYTHON=.venv/bin/python main/backend/.venv311/bin/python scripts/dev.py typecheck --public-boundaries`；原venv `scripts/dev.py sync`（有声明变更时）再`check`、`test`、`gates`；受影响原ruff保持，不手改派生表 |
| V-suite | `bash scripts/test-standardize.sh ci-pr -q`及原`coverage`入口，100/20不降；沿现有selector清单核精确新增/退役/资源分区，capacity原Unix-socket条件保持。只按实际交付与依赖跑，不由文档编辑触发 |
| V-host／V-ui | 沿实际改动选择原auth/typed-fetch/manifest/浏览器与写作API见证；真实provider调用需其原授权资源。无宿主适配改动不新加模型测试；vendor/generated分账 |

所有测试路径相对根cwd；不把已删local-index/streamplus/ops专属测试写作退役后的验收命令。引用清零使用现有`rg`并明确源码/脚本/贡献源观察边界；历史快照允许残留原文本，不要求改写历史。若原声明/门禁仍绑定该专属义务，先修权威源并sync，不跳过现役七gate。

## 7. 整体完成条件

- 必要能力、事实owner、真实effect、身份/当前权限和失败语义保持；明确停用能力已撤去公开与内部执行入口。
- services旧整体承载、successor冗余族、API/胶水及其它承载均完成具体处置；必要核逐项有依据，不能把全目录改名、委托或保留互相引用当退役。
- 每个实施包整族退出并达到发包前D/A_max/N_min；框架全部规模约束和本文三阶段退出条件同时满足，不能以局部收支合格代替全项目上限。
- 原注册/配置/派生见证/专属测试/文档同批一致；必要行为、公共类型、现役七gate及实际交付要求通过，kept、skip、not_run与失败按原归属记录。
- 成本包含共同修复和跨目录新增；生产/测试/工具/前端/vendor/历史分列，不以删文档、搬家或旧dirty回撤抵扣。缺失调用/token和完整验收成本不记零，不报无证据提速。

内部全面类型治理、UI重设计、性能和新扩展建设不自动加入退出条件。它们也不能被拿来掩盖当前结构退役未完成。全项目硬预算已确定，精确包定界与实施仍未完成；上限不是已经实现或已证明可达的结论。

## 8. 上一轮迁移历史及本轮状态

上一轮结果已提交为`c3adced`：完成既选Runtime迁移与保持验证，但生产净减仅29行。原`LOCAL_COMPLETE_NOT_RELEASE_AUTHORITY`是当时迁移合同的本地闭合记录，不能继续作为用户全局退役/显著瘦身目标的完成声明。原文与逐attempt记录可用`git show c3adced:docs/development/MRW平台结构精简与删减阶段.md`读取，不在新当前章节重复重写。

原证据根`/tmp/mrw-structure-20261007-w4uct7gr`，最终`integration/ci-group-resumption-2.json`的SHA256为`878665a345cd21b3ab5002595b7f0835354c2ad3e5322b70aea6fbc8edbf848c`。原ci-pr-4和native coverage-2 exit1保留；Search15替换旧9后归属2668 passed/4 skipped，186subtests另账；原431补集为426原passed＋3 PG39 kept＋W04修后1＋PG40补运行1。PG39原21、七gate291、core/e2e原分步以及合并coverage core409/409100%/other69.41%保留原依赖边界，不因本次改写撤回，也不冒充新退役执行证据。

原frontend14含route mocks及Codex iframe mock shell，direct HOST1只证明注册写作工具/approval/turn及canonical API/SQL读回；内部类型/Ruff债、4skip和缺失调用/token成本继续保留。上一轮workflow＋999/retrieval＋3763/shared＋1594的独立增长责任进入本轮定界，source下降不抵消。

本轮实际完成：复用c3源码定位与首批定界，结合现场全项目盘点确定全项目硬预算、Runtime专项分帽和三阶段退出条件，更新框架、本文及开发README入口。纠正了旧ThreadPool区间、不存在staged/effect文件的重复删除候选，撤回projection_contracts/material_native零consumer误判和无依据80%目标。没有生产/测试代码修改、实际退役或代码验证执行；文档随本次交付统一提交；未push或deploy。下一工作按§3与§4现有包执行；旧Stage4–6部署任务继续STOPPED。
