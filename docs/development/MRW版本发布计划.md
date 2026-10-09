# MRW 1.0.0 本机版本发布计划

2026-10-09。用户选择本机可用版本，沿用现有宿主入口。本计划统一本轮类型债务、安装及上线验收；历史精简完成事实保留，旧 Stage 4–6 继续 STOPPED。当前文档是实施合同，表中基线和已发现失败不表示新候选已通过。

## 1. 交付对象与事实归属

交付当前 MRW `1.0.0` 的本机候选，保留 backend `8000`、frontend `5173`、Codex WebUI `8172` 的现有入口。`app/release_identity.py::RELEASE_VERSION`、根 `pyproject.toml`、frontend `package.json` 已为 `1.0.0`；不为本机验收再造版本序列。最终制品必须关联实际 commit、tree 和制品 digest，工作树有改动时不能用旧 HEAD 冒充制品内容。WebUI 的组件版本独立保留。

本轮交付包含全部当前 backend app 的 strict 类型清零、适用原全量测试、前端构建与真实业务浏览器检查、真实宿主工具经 worker 写入并持久读回、真实迁移与恢复演练，以及一个可安装、启动、停止和恢复原版本的本机制品。GitHub push、远程 CI、registry 和签名不在本机范围；不构建三角色 OCI，不恢复历史冻结流水线。基线可用磁盘约 14 GiB，制品不得携带虚拟环境、用户数据库、OAuth、真实 `.env`、日志或重复构建缓存。

构造上的对象是有明确版本和权限的程序、运行记录、材料及安装实例；提交、执行、持久化、读回与安装是不同关系。Runtime journal/output 是执行事实，Document writer 是材料事实，宿主 session 保存引用与审批事实；这些视图通过已有有向读回组合，不能相互代写。类型修复必须保持这一组织以及 Failure、UNKNOWN、project/actor scope、codec 与 digest 的含义。单项工具的 `completed`、dispatch event 和 HTTP health 都不足以建立整条业务完成。

主线负责派发与交付，Astra 负责本计划、公共接缝判断及只读终审。现有 `simplification_final_recovery` 是唯一集成 owner，拥有共享消费者、配置、清单、运行资源、最终验证和提交。各实现 owner 保留其他任务的修改。

## 2. 已测类型基线与互斥工作面

基线 HEAD 为 `f2003ece95bac0c81ecbf9cf33e7e94413cb2369`。原全 app 扫描实际分析 632 个 Python 文件、8074 个错误、0 警告，耗时 30.36 秒，Pyright 1.1.411。旧 include 的 120 个声明根静态覆盖其中 147 文件，8074 错误均来自其余 485 文件；294 文件含错误。旧公共边界绿色不能替代本轮全 app 绿色。

原始证据在 `/tmp/mrw-version-release-20261009/type-inventory/pyright-main-backend-app.output.json`，聚合及环境在同目录 `summary.json`、`python-config.json`。Unknown、JSON、SQLAlchemy 等家族信号存在重叠，不相加当作独立债务。以下按路径互斥分派，合计恰为 632 文件、8074 错误；表中零错误文件仍纳入最终覆盖，但无需为覆盖而改写。

路径均相对 `main/backend/app`。按表顺序匹配，剩余规则排除前面的所有路径。

| 包 | 独占 app 写面 | 文件 / 基线错误 | 权威接口、消费者与完成边界 |
| --- | --- | ---: | --- |
| T-SOURCE | `services/source_library/**` | 37 / 1021 | 原 `types.py` RoutingObservation/RoutingSummary、item resolver ExecutionRequest/ExecutionPayload、RunnerObject。先打通 terminal_output 到原 terminal unittest，再稳定 resolver/provider/external-project 消费链；ACK 不变成完成。 |
| T-INGEST | `services/ingest/**`、`services/ingest_config/**` | 57 / 1224 | 原 frontdoor、postprocess、raw_import、canary、config get/upsert；复用 SOURCE terminal 契约，保留 canonical Material/Document writer。config 输出用原 JSON 值域精确描述。 |
| T-RUNTIME-KERNEL | `successor_runtime/{research,language,capabilities,runtime}/**` | 80 / 672 | 原 Program、Assignments、ClaimBinding、Failure、codec 和 port；保留 provisional digest 构造后验证语义、failure lift 与 handler 契约。 |
| T-HOST | `services/agent_core/**`、`services/agent_runtime/**`、`api/agent_cell.py`、`api/agent_macro_host.py` | 39 / 206 | MacroHostError、AgentCoreRequest、registry 与原 session/tool API；NoReturn、缓存及映射精确化，保留 approval、project、turn、actor 约束。修复下述 canonical URL status 缺口。 |
| T-PG | `successor_runtime/substrate/**` | 50 / 354 | 原 PostgreSQL journal、assignment/authorization/qualification rows、exact binding；保留唯一 Runtime 写入归属。不能把 `model_construct` 的 provisional digest 步骤替换为提前 `model_validate`。 |
| T-RESOURCE | `services/{resource_pool,discovery,extraction,crawlers_mgmt}/**` | 43 / 1101 | 现有 unified_search、discovery/store、crawler management、article extraction；真实 SQLAlchemy row 与 provider result 各在原边界收窄，SOURCE 稳定后接其结果，不复制 parser。 |
| T-KNOWLEDGE | `services/{information_topology,typed_knowledge,clue_chains,graph,workflow_graph,writing}/**` | 73 / 1221 | 原 topology repository、typed_knowledge persistence boundary、curated workflow 与 writing readback；保持 revision、身份、governance、writer 与失败返回。 |
| T-API | 其余 `api/**` | 35 / 958 | 已有 API response schema、project_customization 工厂和 process canonical reader；服务返回稳定后对齐，不生成另一个 envelope 或假 success。 |
| T-SUPPORT | 其余 `services/**` | 129 / 1084 | 原 LLM/provider/report、agent_batch、collect_runtime/crawlers、search、projects 与 document views；当前 tasks、session 等绿色接口保持。本轮按 §6 拆为 LLM 19 与其余 110 的互斥写面，每个文件仅一个 owner。 |
| T-FOUNDATION | 其余 app 文件 | 89 / 233 | models/base/entities、contracts、composition、settings、production_contract/observability、subprojects 与 successor assembly 等；集成 owner 管理共享接缝，可授权单一后续作者。 |

不以 `Any`、无检查 cast、ignore、exclude 或关闭诊断制造清零。确为开放 Python 数据用 `object` 和局部 guard；确为 JSON 才用 `contracts/json.py` 的 `JSONValue`/`JSONObject`，不递归强制任意内部映射成为 JSON。缺失第三方声明由窄 stub 或原受支持类型边界处理；不能忽略 `pgvector.sqlalchemy` 或 bs4 的缺失。

最终只读审查同时检查受改语义链的显式 `Any`、unchecked cast 和封闭 DTO 退化；不能把封闭返回改成 `dict[str, Any]` 取得绿色。原本开放的外部输入须留下可解释边界与 guard；不把仓库旧 Any 总量变少当作类型语义已保全的证明，也不扩张为本轮 app 外全面治理。

SOURCE 的 terminal 结果是第一项共享规则，不以所有底层清理阻塞独立工作。若确需共享纯 guard，由 SOURCE 提议、集成统一修改 `contracts/json.py`，该文件不产生第二写者。`models/base.py::SessionLocal/run_with_session_retry` 是独立事务边界，由 T-FOUNDATION/集成维护：精确 Session 或必要的最小事务协议，保持 fake-session、重试、原异常 lift 与 commit/rollback。它不是所有 SOURCE/RESOURCE 直接 SessionLocal 调用的先行条件。

首波已派 SOURCE、KERNEL、HOST，另有前端 B 和本机交付 C，共五个作者。后续在作者释放后接力 INGEST、PG、RESOURCE、KNOWLEDGE、API、SUPPORT、FOUNDATION；不得把剩余 app 文件默认为下一个版本。API 依赖相应服务稳定，PG 的独立 row 类型可提前准备；INGEST 的 canary/raw-import 等独立面可先做。公共规则只通知真正依赖的 owner。

SOURCE terminal 接口已稳定为 `types.py` 中的 `SourceMode`、`TerminalStatus`、`TerminalOutputDto`、`TerminalCollectResult`，下游直接复用原模块接口。本轮主线已回传 SOURCE 37、API 35、HOST 39、INGEST 57、KERNEL 80、PG 50 的局部类型与 pure 结果；PG 曾把 canonical `QualifiedPlan` 换为 dataclass 的回归已由原 owner 恢复 BaseModel，主线回传相关真实 PG 10/10。LLM 19 已报类型 0，运行时 guard/JSON/Failure 只读审查与适用 pure 尚需归档。以上均为包级证据，最终效力仍按当前输入和显式依赖核对，不能相加代替全 app 扫描。当前五个作者写面是 Foundation 公共 models/Session 与 89 文件、Host 接力 RESOURCE 43、Ingest 接力 KNOWLEDGE 73、Kernel 接力 SUPPORT 110、Source 接力 LLM 19；释放槽位由主线接力，不新增并行写作者。pgvector/bs4 窄 stub 仍由唯一集成 owner 管理。

Foundation 统一维护原生 `DeclarativeBase`、真实字段 `Mapped` 与 Session 默认/显式 factory 的类型关联；仅修实际诊断证实的模型字段。后续确认的 `EtlJobRun`、`KeywordHistory`、`LlmReportExportAuditEvent`、`ResourcePoolSiteEntry`、`SharedResourcePoolSiteEntry`、`Material`、`Source` 沿同一规则由该 owner 处理，不逐列审批，也不扩成全模型迁移。metadata、DDL、mapper、原生 constructor 与拒绝坏键行为须保持；消费者不得改用 `setattr`、cast 或开放 `Any` 绕过关联。未依赖该接缝的 IO、协议及业务逻辑继续推进，依赖者在公共声明稳定后验证真实消费者。

统一 cwd 为仓库根。类型运行时 `.venv/bin/python` 为 Python 3.13.12 并装有 Pyright；backend 解释器 `main/backend/.venv311/bin/python` 为 Python 3.11.14 并带 backend 依赖。包内检查把末尾路径替换为表中独占路径，最多两个 Pyright 进程：

```bash
export PYTHONPATH=/Users/wangyiliang/market-research-workflow:/Users/wangyiliang/market-research-workflow/src:/Users/wangyiliang/market-research-workflow/main/backend
export MRW_DEV_PYTHON=/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python
.venv/bin/python -m pyright --pythonpath main/backend/.venv311/bin/python --project pyproject.toml --outputjson main/backend/app/services/source_library
MRW_TYPECHECK_PYTHON=.venv/bin/python main/backend/.venv311/bin/python scripts/dev.py typecheck main/backend/app
```

此 `PYTHONPATH` 在仓库根及 backend cwd 都指向同一实际目录；backend cwd 的 `../src` 指向错误位置，不能使用。`MRW_DEV_PYTHON` 始终是装有 backend 依赖的解释器，只有 `MRW_TYPECHECK_PYTHON` 选择根 checker 环境；原 `dev.py` 也会依据 repo root 构造绝对 import 路径。

最终 include/CI 由集成更新为实际全 app，保留既有 app 外声明。各包测试复用原 runner，先从已知真实消费者选起，例如 SOURCE 的 `test_source_library_terminal_output_unittest.py`，RESOURCE 的 `test_resource_pool_unified_search_unittest.py`/`test_discovery_store_guardrails_unittest.py`，KNOWLEDGE 的 `test_workflow_graph_curated_service_unittest.py`/`test_typed_knowledge_persistence_boundary_unittest.py`，HOST 的 `test_agent_macro_host_authorization.py`/`test_agent_macro_host.py`，API 的原 schema contract。测试 cwd 为 `main/backend`，命令是 `.venv311/bin/python -m pytest -q <原测试路径>`。owner 交付精确文件/nodeid、原始退出码与依赖；共享测试文件由集成合并，不按目录名推断资源独立。

## 3. 已发现的业务与迁移修复

### 宿主 URL 任务终态读回

`ingest.url_pool.submit(async_mode=true)` 已通过 verified host authorization 和 trusted actor 提交 current URL Program，返回 `runtime_run_ref`/`work_item_ids`，通常没有旧 Celery `task_id`。当前 `ingest.url_pool.status` 仍主要读 session、旧 task events/jobs 与 URL 文档查询，没有消费该 canonical ref；任务已失败时可能仍返回 pending。

T-HOST 在原 `authoring_tools.py` 内接入现有 `read_installed_program`、`read_installed_program_outputs`、失败 reader，使用原 verified actor 与 project scope。READY/RUNNING 是 pending；COMPLETED 需解码为 `UrlSingleUrlOutcome` 并取得 `document_id`，材料查询核实同项目同 URL 后才为 verified；失败和中止明确返回对应原因。旧 submission 可保留既有读回兼容，但不能伪造 canonical 完成。session artifact 仅保存引用。focused 验证为 `tests/unit/test_agent_core_unittest.py -k 'url_pool_status or url_pool_submit_uses_trusted_actor'`，并覆盖跨项目、缺可信 actor、失败终态与材料未落库。

### 已有租户表的迁移接纳

集成已把本机用户数据库快照恢复到 `mrw_release_migration_rehearsal`，从 `20260903_000003` 执行 upgrade 时，`20260924_000001` 在 `project_batch84_matrix_proj.information_topology_states` 报 DuplicateTable。原日志在 `/tmp/mrw-version-release-20261009/integration/alembic-user-copy-rehearsal.log`。用户数据库未修改；该失败阻断实际升级。

共同来源已由源码确认：`services/projects/bootstrap.py::TENANT_TABLES` 已包含 topology 两表及 project_retrieval 三表，初始化可能先建表；`20260924_000001_add_information_topology.py` 和 `20260926_000001_add_project_retrieval.py` 都无条件再建。同一 M-MIGRATION owner 独占这两个 revision 和必要 focused 测试，作为独立紧急第六作者；所有 PG 执行仍由集成串行安排。

集成补充实测：13 个 tenant schema 的 26 个既有 topology 表与 fresh-head reference 的语义结构 26/26 一致，public 缺表；私有备份与真实 restore 已通过。该结果支持严格验证后接纳的修复方向，不等于修改后的 upgrade 已通过。隔离 PG 端口为 `50924`、Redis 为 `16380`，lane 的实际分配仍由集成控制。

后续 M 第三 attempt 已经通过原副本 upgrade/repeat：13 项 focused tests、567 项计数、65 项数据观察和隔离检查通过，额外列负例已补，源码 suppression 为 0；集成核对 `/tmp/mrw-version-release-20261009/migration/attempt3/08-final-manifest.json` hash 一致并释放 PG 槽。这关闭已知 DuplicateTable 修复阻断，仍不建立用户实例已切换或整版已通过的结论。

不存在的表按固定 revision DDL 创建；存在的表用 schema 限定反射核验列、类型/长度、nullability、语义等价 default、PK、revision 唯一约束、current partial unique index 的列序/唯一性/谓词和 id sequence。仅兼容结构可接纳；缺失且可安全补齐的约束/索引可交由 PG 校验原数据后补齐，冲突须明确失败并给出 schema/table/property。不得无条件 IF NOT EXISTS、drop/recreate、stamp 绕过；不得导入可变 app ORM 作为历史 revision 的定义源。已有固定 migration snapshot 机制可复用，不新建通用迁移平台。

验收包含空 schema、bootstrap 等价已有表及 sentinel 数据、五表部分存在，和错误列/nullability/current-index/冲突数据的负例；从原快照重新恢复后 upgrade 至唯一 head `20260926_000001`，已有行、digest、revision 与 project scope 保持，重复 upgrade head 无变更。旧 downgrade 会 drop 已接纳表，因此不能用它证明保留数据的回滚；本轮采用隔离备份恢复和原安装实例读回。

## 4. 验收矩阵与执行资源

类型进程最多两个，pytest 最多两个槽。共享 PG、Redis、worker、backend、WebUI、服务维护和模型调用由集成唯一排期；源码不同或语言不同不能证明测试资源独立。所有 raw 日志集中 `/tmp/mrw-version-release-20261009/`，本计划只汇总，不另造 receipt、审批账本或证据平台。

### 当前全集失败与五包接续

2026-10-09 本轮终审闭环更新：原三个缺口及 H 两项类型修正已落入当前源码；以下是各原执行 owner 的实际局部结果和只读核对，不是最终发布结论。

| 已指出项 | 当前修复与证据 | 尚未证明的范围 |
| --- | --- | --- |
| C-FRESH 依赖复用失败传播 | `reuse_dependency_tree` 的 `ln -s` 与三次复用调用均显式传播失败。原 prepare 入口在临时目标根执行 existing-conflict、link-failure 两个负例，均退出 `1`，源依赖未变；原 launcher gate 为 `29/29 / exit 0`。记录 `/tmp/mrw-version-release-20261009/c-fresh-recovery/source-ledger.final.json`，SHA256 `d5202e7f969b648030417717db784748bd92d787dc095d06a0ce6bd6a9e472a4`。 | 负例与 launcher gate 不证明最终 bundle 已安装、启动或回退。 |
| H 原始索引异常及类型承诺 | 原 `int` 的 `ValueError` / `TypeError`、消息与 cause 经既有 Failure/lift 保留，`memoryview` 输入保留；模型坏索引仍跳过。topic 新增两处 `Any` 已收紧为 `object`，内部 map 视图如实使用 object keys，auto guard 新增 cast 已移除。当前 source ledger 为 `/tmp/mrw-version-release-20261009/h-source-stable-ledger.json`；集成 `h-final-focused` 的两个 exact selector 实际 `2 passed / exit 0`，输入稳定读回 `0`。 | 两项 focused 不替代当前全部 app strict 或完整 suite。 |
| S 开放参数与字符串键承诺 | 开放参数沿原 Python 调度链使用 `Mapping[object, object]` / `dict[object, object]`，item/channel/result 顶层记录不变；原 crawler `_mapping` 拒绝及 customization `_json_object` 转换保留，无新增过滤或提前字符串化。Source 37 文件 strict 实际 `0 error / 0 warning / exit 0`；记录 `/tmp/mrw-version-release-20261009/type-source-s6/source-s6-open-map-ledger.json`，SHA256 `4b36fa4a54a34a5a95bf1012d2e5ac03dc7e0f4a8ebc05611469fcfddb724be9`。外侧 `SearchTemplateService` 只读参数与 composition 已由集成同步，原相关 32 项测试回传通过。集成 S6 最新实际 `6 passed, 2 subtests passed`，URL 相关实际 `16 passed, 2 subtests passed`。 | 原局部失败尝试保留：开放键/opaque identity 在转换前观察，嵌套 result 遵守原 JSON 投影；`url` 与 `urls` 各拒绝一次的原错误数为 2，修正测试硬编码，不新增去重。局部通过不替代全集。 |

S/H 稳定后，集成全 app strict 已实际分析 `632` 文件，`0 error / 0 warning / native exit 0`，耗时 `14.104s`，输入 pre/post 完全相等；NoThrow 原 selector实际 `1 passed`。K 与共享接缝稳定后的最终全 app strict 再次实际分析同一 `632` 文件，结果仍为 `0 error / 0 warning / native exit 0`，耗时 `14.616s`，输入前后相等；共享投影、registry 与 NoThrow 合并见证实际 `3 passed`。这些是对应稳定输入的真实结果，不是占位 `current` 文件。

最新两套原全集均已执行结束，前后 `1338` 项输入完全不变。Root 实际为 `1364 passed, 90 subtests passed, 5 failed`，耗时 `158.13s`；五项失败均定位到新增 Failure code 的 registry/expected 静态见证漂移，集成正在统一源同步，尚未记为关闭。Backend 实际为 `3665 passed, 291 subtests passed, 153 skipped, 15 failed, 4 errors`，耗时 `144.20s`；集成正在聚合共同原因，153 个 skip 不计通过。两次全集均未通过；下文首次 Root 失败与其局部修复仍作为历史 attempt 保留。

隔离 URL 链已完成首次模型提交及独立 worker 对唯一 Redis task 的实际消费，现原 run `url-single-agent-566b26c9b069d6cf35e8622f` 为 `RECONCILING`，原 attempt 为 `OUTCOME_UNKNOWN`，无 receipt/commit intent；reconcile work 为 `WAITING / INTERPRETER_UNAVAILABLE`。证据为 `/tmp/mrw-version-release-20261009/live-host-url-chain/run/outcome-unknown-readback.txt`，只摘录状态，不复制 claim 凭据。根因是 localhost 测试来源被原生产 URL 安全规则在 HTTP 前拒绝，adapter 明确错误在 routed 汇总中丢失，空记录被投影成 partial，installed handler 再误报 UNKNOWN。Source 已修原错误传播并取得上述 URL 局部见证；原拒绝不放宽，原 run 历史不擦除。该隔离 grant 已预先授权，原 helper 错误要求 `approved_action` 的退出码 `1` 仍保留，不重复模型提交补断言。

K 已获源码写窗，正在实施 URL 的两项 exact 身份接线：保留实际旧 run 所需的 `1.0.0` 原声明/绑定，新请求默认采用 `1.1.0` 的 truthful UNKNOWN/readback 声明；kind、owner、未变 authority/resource 与 codec 形状保持。两版本共用原 `PostgresLocalEffectReconciliationHandler`，从 runtime/project 两侧已持久结果及一致 digest/provenance取证，仍由 `PostgresReconciliationOwner` 唯一 CAS 终结；不建新恢复平台、不重编旧 Program、不把历史绑定转成新 digest。原 installed catalog 只保留这两个实际需要的 exact 版本；原 CLI 的 operation 存在性查询由集成改用 `requires`，不在多版本中静默选择。K 实施及生产接线验收尚未完成。

旧 run 缺少两侧权威结果时，安装 handler 后正确结果仍是 `WAITING / LOCAL_RUNTIME_VALUE_ABSENT` 或 `LOCAL_PROJECT_VALUE_ABSENT`，不能用缺 Document、租约过期或事后纯函数拒绝证明旧 attempt 已 FAILED；不引入 NonStart adoption，不造 receipt或重执行 effect。`RECONCILING` 本身不占满 `max_active=1`：原 UNKNOWN 提交释放执行 reservation，容量只计活跃 reservation/CLAIMED work；新正例前由集成读回当前槽位并与 reconcile 串行，不调高 ceiling。新的显式公网来源正例使用独立 case/run/idempotency identity及同一有限隔离策略，不覆盖旧 UNKNOWN。

原全集失败已按共同来源全部完成受影响闭合：Root 新增 Failure family 的 registry/expected 同步、backend 四组确定性实现/测试漂移及 PostgreSQL-owner contract 均有原 selector 实际通过，历史全集原退出码不改写。当前 collection 对账为 Root `1369`，相对原集合无增删；backend `3839`，相对原集合新增 5 个已具名节点、移除 0。最终原 coverage 入口实际 `2257 passed, 108 skipped, 1474 deselected, 237 subtests passed`，pytest 与阈值退出码均为 `0`；core `409/409 (100%)`、other `61570/97747 (62.99%)`，1279 项输入前后相等。

真实应用链也已闭合：七业务线浏览器以原六项结果加当前 `search_discovery_index` 的 `bm25` 精确重跑组成 7 项实际 PASS；唯一公网 URL 正例经真实模型、Redis、独立 worker、canonical Runtime、Document API/PG 与 backend 重启后读回通过，原 localhost UNKNOWN 仍按原身份保留且未重提 effect。当前只剩集中 commit、bundle 的实际解包启停与代码/数据回退、用户数据库 upgrade/cutover、三项应用凭据轮换及 local tag。用户 Project 的 URL scope 选择仍待明确，用户 URL capability 本轮未启用；隔离 grant 不推广到用户库，该选择不阻止其它技术安装。完成这些剩余项前仍不得宣布 Release PASS。

Root 原全集真实执行结果为 `1368 passed, 90 subtests passed, 3 failed`，原退出码 `1`，耗时 `151.91s`；证据为 `/tmp/mrw-version-release-20261009/full-suites/root-suite.output.txt`、同前缀 `junit.xml` 与 `nativeexit`。其中两项 checker-routing 失败已由主线回传在正确 `MRW_TYPECHECK_PYTHON` wrapper 下原 exact selector 重跑 `2 passed / exit 0`；该局部修复不改写首次全集失败。另一项是 `tests/test_architecture.py::TestArchitecture::test_INVARIANT__no_throw_in_core` 的 26 处新 violation，现已由原五个 owner 实际接续：

| 包 / owner | 原失败点数 | 独占修复面与语义边界 |
| --- | ---: | --- |
| F / Foundation | 1 | `models/base.py::require_model_table`：保留原 SQLAlchemy metadata 类型前置与坏值拒绝，用真实程序契约见证说明边界，不新增领域失败族。 |
| H / Host + RESOURCE | 10 | `agent_core/macro_registration`、`clue_chains/external_search_expansion`、`discovery/deep_search`、`extraction/{extract,topic_workflow}`、`resource_pool/{auto_classify,site_entries}`：内部预期分支直接表达；真正坏输入走所属领域 Failure 和原 lift；保留 JSON/结构化提取回退、单条坏结果跳过及整体 confidence 回退的区别。H 独占 `provider_port_failures.py` 的准确 `extraction_payload_invalid` 声明。 |
| I / Ingest + KNOWLEDGE | 6 | `ingest/{raw_import,terminal_writer}`、`information_topology/adapters/native.py`、`information_topology/io/retrieval.py`、`workflow_graph/curated_service.py`：保留单条导入错误、原生 ORM 身份、物料身份拒绝、导出失败 cleanup 与坏 audit 拒绝；不将一条错误升级成整批失败，不丢弃坏记录制造成功。 |
| S / Source | 5 | `source_library/{external_project,resolver,url_router}`：已知 `get_config` 恢复直接类型关联；相同整数默认与 clamp 规则复用；routing 值验证保留。S 独占 `application_failure_semantics.py` 的准确 `routing_value_invalid` 声明；无效 `_as_runner_object` 保持原 `TypeError`，该 code 的 `_resolver_failure` context 与 lift 对应 `TypeError`，其余 resolver lift 保持 `ValueError`。最终记录为 `/tmp/mrw-version-release-20261009/type-source-s5/source-s5-ledger.json`，主线核对 SHA256 `e91c4c338654bc264ec100eba178a765c3d75b102e6d013c5afcace437a5d523`。 |
| K / Kernel | 4 | `capabilities/batch_task_program.py`、`language/program.py`、`runtime/replay.py`：非空构造消除重复不可能分支，未知 codec kind 与坏 replay 字段复用既有 typed Failure / legacy lift，保留顺序、元数据与公共异常。 |

点数按首次失败源码位置统计，修复后行号可以变化，不据新行数改写原失败。五作者上限不变；共享声明由指定 owner 修改，registry 等派生接入由唯一集成 owner 一次同步。不得通过伪类型桥、空 marker、基线豁免、删 guard、错用 Failure family 或只为扫描新增 wrapper 收口；已有 Failure 只在对应语义成立时复用，新增 code 仅限上述真实缺口。结构化 boundary 标记及测试名存在只是扫描器的机械条件，必须有实际 caller 的拒绝、回退、原异常或 cleanup 行为见证。

各包稳定后，集成按当前输入核对原 focused 结果与共享声明，执行必要的派生同步/检查，再复跑原 NoThrow selector 与全 app strict；准确 collection 对账后按受影响输入完成原完整 suite、coverage 和最终一致性验证。失败 attempt、局部重跑和未变依赖的 kept 分别记录，不把原全集改记为通过；源码若在某项最终检查后变化，仅重验实际受影响范围。主线已回传的独立 PG 五项及 canaryRegistry 原脚本 `7 + 7`、真实 HTTP `200` 与无残留结果不属于这 26 处阻断，无相关依赖变化不重复执行。真实 browser/host worker、bundle 启停回退及用户实例切换仍须各自真实证据，NoThrow 或 app 类型通过不替代它们。

**剩余收敛顺序（本机 1.0.0）：**

| 执行段 | 当前可继续的工作与真实前置 | 交给下一段的证据 |
| --- | --- | --- |
| 独立准备 | 集成核对 exact collection、原 runner/资源槽和适用 skip；准备原宿主 worker witness、隔离 project/URL/grant 的有限输入；核现有 bundle 清单与依赖来源。前端无变更结果按实际输入复用。无需等待所有 ORM 字段修完才准备。 | 准确 nodeid/资源与制品输入；准备工作不记为测试、安装或业务完成 |
| 共同类型与行为闭合 | 五写面各自稳定；Foundation 原 metadata/DDL 比对与构造行为、Session 关联先交真实依赖消费者；LLM 只读发现的具体回归交原 owner。集成统一检查 SUPPORT 129 与全部当前 app，贡献 check 发现真实漂移才 sync。 | 原全 app strict 0/0、原贡献/适用 gate、一致源码身份；局部 pure 与复用项分账 |
| 全集与持久边界 | 稳定输入上运行原 Root 全集、backend `not external` 全集及 coverage 阈值；在已声明独立资源上最多两 pytest 槽。PG 四类资源共用一个串行槽，跑全适用原 PG nodeid。已通过的迁移 attempt3 与 PG 局部证据仅在其依赖未变时复用，不能替代其余 PG 覆盖。 | 当前 exact collection 对账、原退出码、逐项 skip/未执行范围；PG/迁移/恢复分别标明实际与 kept |
| 真实应用链 | 用同一候选、owned backend/WebUI/Redis/PG 启动独立 worker；先完成真实七业务线浏览器，再依原 witness 完成 host 写作与 URL worker 链、重启后读回。测试 grant 仅限原隔离 fixture。 | 真实 OAuth/model/审批、唯一提交、Redis transport、worker、canonical output、Document API/PG一致；不以 mock 或 dispatch 返回替代 |
| 制品与本机切换 | 全部必需项收敛后一次确定提交/树与前端产物，使用现成 bundle 构建入口生成 checksum/manifest；从真实制品启动并验证现有宿主入口。确认用户备份和恢复路径后由集成执行原安装切换、已授权静态 token 轮换及新旧认证验证。 | artifact/运行实例身份一致、实际启动停止重启、原版本与数据恢复证据、切换后持久读回；不包含远端发布 |

每段失败只阻断真实下游，未受影响准备与独立验证继续；同因失败不重复全跑。测试新增/删除或输入变化后重新对账精确覆盖；源码全部稳定之前的包级通过不充当最后全量运行。当前实现规模增加属于类型修复成本，不宣称精简或提速收益；闭合 DTO 变开放对象、冗余 guard 或新层仅依据具体关联/行为问题裁定，不以减行作为降合同理由。

| 验收面 | 原入口与必要观察 | 本轮完成条件 |
| --- | --- | --- |
| app 类型与贡献 | 全 app typecheck；`scripts/dev.py check`、适用七 gate；漂移时集成单独 sync 再 check | 全当前 app 0 error/0 warning，贡献与派生一致；旧 public strict 与本轮 full strict 分开 |
| Root 全集 | 仓库根 `main/backend/.venv311/bin/python -m pytest -q -p no:cacheprovider tests` | exact nodeids 无漏项，原退出码 0；gates 是全集成员时不重复相加 |
| Backend 全集 | backend cwd `.venv311/bin/python -m pytest -q -p no:cacheprovider tests -m 'not external'` | 包含未标 marker 测试；原退出码 0，skip/外部项逐项注明；不设置排除 flaky 开关 |
| Coverage | 原 coverage runner与阈值脚本，独占 `.coverage`/XML | pytest 与阈值命令各自成功；不能以末端管道码代替 |
| PostgreSQL | 原 successor PG runner、实际相关 integration nodeids及独立迁移 smoke | migrated 普通 DB、受限 socket、CREATEDB C1/global-stats、pristine capacity 四类隔离串行；BLOCKED/skip 不计 PASS |
| 前端 | 现有 node_modules 上执行原 lint、tsc/build、相关 i18n/页面 shell/business-string 及 contract checks | 真实构建成功；保留现有锁文件，不为本机验收重装；mock browser 与 real backend 分账 |
| 真实浏览器 | 原 `test:e2e:real-backend-business-lines` script，注入集成分配的 backend/WebUI代理 | 七业务线真实 HTTP 和持久投影检查；不得设置 `FRONTEND_E2E_SKIP_BACKEND_CHECK=1` |
| 真实宿主写作 | 原 `test_live_host_material_chain.py` | 实际 OAuth/model→审批→registered create/read→API/PG读回；仅声明直接 writer 证明范围 |
| 真实宿主 worker | 下述 URL 单次提交链与必要最小 integration witness | 独立 Celery消费、canonical run/output、材料 API/PG一致，重启后可读 |
| 安装和恢复 | 原 local-deploy/local-service-control/WebUI start-stop；实际 artifact checksum/identity；私有 dump 恢复副本 | 从制品启动/停止/重启，版本身份匹配；原实例回退可启动，原数据摘要可读；不能把 compose 文件回退当数据恢复 |

原 `scripts/test-standardize.sh all` 只选四种 marker，不是完整 backend 全集。集成先确定当前 exact collection 和资源清单；能复用现有真实 planner 时复用，否则运行原全集，不建设新 scheduler。Root 与无 PG opt-in 的 backend 全集仅在独立 basetemp/Hypothesis cache 等资源确定后并发。所有 opt-in/live skip 保留 ID 和原因；相关 PG 能执行者另跑，外部 crawler 等与本机交付无关项列为未执行范围，不能计入通过。

集成当前精确 inventory 为 backend 3770；standardized `all` 只覆盖 2615，另有 1155 完全无 marker。这是本轮必须按真实路径执行全集的直接证据，后续新增测试后须重新核对节点集合，不能固定旧数量作为完成条件。

`run_successor_postgres_validation.py` 使用 NOCREATEDB 角色并收窄子进程环境，不能偷偷承载 C1/global-stats。capacity 固定角色及 pristine schema 不能复用已迁移 DB。`scripts/run_backend_migration_live_smoke.py` 必须使用明确 disposable admin URL 和唯一 DB 名，禁止 `--allow-blocked`；fresh migration 与用户副本升级分别证明。

本轮实际前端工具链为 Node 26.4.0/npm 11.17.0；B 已在现有 node_modules 上用 `npm run lint`、`npm run build`（含 `tsc -b`）和 18 项静态检查取得成功，未改变依赖。Node 22/pnpm 11.22.0 属于 CI/锁来源背景，不能登记为本轮执行环境。目录中既有 `package-lock.json` 和 `pnpm-lock.yaml`，保留二者，不为本机验收重装、不另造锁。原 package 内 page i18n slice、page-shell-disjoint、business-string 及 graph/topology/writing checks 保留逐项结果。

Playwright 原 webServer 命令是 `pnpm dev`，需要它时使用实际可用 pnpm 并记录实测版本，不由 CI 声明推断。可从 frontend cwd 用 `npm run test:e2e:real-backend-business-lines` 启动原 script；`FRONTEND_E2E_PORT`、`VITE_API_PROXY_TARGET`、`VITE_CODEX_PROXY_TARGET` 由集成给出当前 owned 服务地址。Playwright 独占其端口/输出，与服务维护串行。`live-workflow-result-chain.spec.ts` 的旧 18086/55436 硬编码属于待修 fixture 资源缺口，已由原 B 接力改为 fail-closed 注入 owned DB/API；不得触碰受保护旧用户 PG、移除真读回断言或伪造 bearer 获绿，也不另建 fixture 平台。只读调查员禁服务操作不等于整次已授权发布禁止服务切换。

真实 worker 见证由集成维护现有 `test_live_host_url_worker_chain.py`。原 localhost 成功前提已被实际生产安全拒绝证伪，正例须显式注入获准、稳定、内容可识别的公网 HTTP(S) 来源，继续经过原地址/重定向安全检查；不新增 private-network 开关或扩大 allowlist。准备专用 project及独立 case/run/idempotency identity，先核原 `local_host` actor 对 `acquisition.url.single_url.v1` 的 current AuthorityGrant与执行槽；可信认证不代替授权。维持原有限期限、operation及 `NETWORK_IO=1 / max_active=1`，不自动扩 grant。worker 停止时，真实模型经 host prepare/bind/record-input/dispatch 只提交一次 `ingest.url_pool.submit`，审批依据真实合同；本轮隔离 grant已预授权，不虚构待批动作。观察 canonical run/work item 与真实 Redis 消息，再启动独立 worker核实际消费 `app.services.tasks.task_successor_runtime`。新正例与旧 localhost UNKNOWN分开报告，网络失败不默认重试。

完成必须同时读到 run `COMPLETED`、decoded `UrlSingleUrlOutcome.document_id`、`GET /api/v1/admin/materials/{document_id}` 的同项目同 URL 材料及 PG 记录。通过 `GET /api/v1/process/runtime-run:<run_id>?project_key=...` 和修复后的 host status读回；backend 重启后复读。事件或工具提交返回仅作辅助，既有 fake apply_async/direct `.run()` 测试不能替代 Redis transport。服务恢复到约定本机状态，不能遗留测试 worker 或错误 DB 配置。

## 5. 本机交付、收敛与退出

B 前端 owner 独占 frontend source/tests/scripts/dist；package/lock 的版本及共享投影由集成协调。C 本机交付 owner 独占现有 `scripts/local-deploy.sh`、`scripts/local-service-control.sh`、backend start/stop-local 与 ops WebUI start/stop 的必要修复，先核既有 `.venv311` 与 requirements digest 安装逻辑，修复实际 PID、解释器、安装及身份缺口。必要制品入口沿这些脚本补齐；不建立另一个服务控制器。

集成确认用户数据库实际 endpoint，不能照搬 5432 或旧 local-user 55436 假设。运行前保护数据与现有 OAuth/认证。数据库 dump 使用私有权限且不进入制品；`pg_restore --no-owner --exit-on-error` 恢复到独立 owned DB，核 migration head、项目材料和 runtime journal 摘要。当前 `main/ops/rollback.sh` 只恢复 compose/.env、docker rollback-drill 只做生命周期，不足以证明代码和数据回退。

当前 local-user compose 的旧 Stage4/r13x image、checkout mounts 和外部 sibling kit 不能作为新安装制品。C 与集成应形成足够本机安装的最小宿主 bundle/归档，内容、依赖来源和 checksum 明确，使用候选源码/前端产物及现有宿主入口，不打包用户状态。安装预检、loopback、服务 key、approval/actor 边界及实际依赖审计复用既有检查；仅当选择镜像制品时才出现镜像扫描义务，本次不构建 OCI。

集成已有 `/tmp/mrw-version-release-20261009/integration/build_local_release_bundle.py`，读取 exact clean commit 并纳入指定 UI build trees；这是现存打包入口，尚不表示已产出或安装最终制品。先核源码、必要 untracked 修复纳入提交及实际 UI 产物一致，再使用该入口；不能因脚本拒绝 dirty tree 而在日常修复中反复提交/封存，也不另建打包框架。归档能生成与 checksum 通过仍须接上真实解包、依赖解析、原启动入口和安装后 readback。

当前可执行接缝由 C / 集成在原入口补齐：bundle manifest 的 `./scripts/local-deploy.sh start` 默认不 provision，而归档明确排除 `.venv311` 与 `node_modules`；原 frontend preview 与 WebUI pinned Codex CLI 仍依赖这些运行依赖。解包目标、依赖安装或精确复用路径、私有配置的外部引用，以及旧安装根的停止/恢复路径必须在实际安装调用中确定，不能把从开发 checkout 启动登记为从 bundle 启动。复用原脚本即可，不新增安装控制器。现有 `test_live_host_url_worker_chain.py` 已取得真实首次提交、Redis transport和独立 worker消费证据，但旧 case仍 UNKNOWN，尚未证明材料完成；`test_live_host_material_chain.py` 的写作 selector不能替代此链。安装与宿主正例仍沿现有交付合同完成，不另加发布门禁。

### 最终切换时的静态认证 token 轮换

集成检查 LaunchAgent 时，redaction 未覆盖 plural 配置键，当前 backend `CODEX_AUTH_TOKENS` 的值进入了工具 transcript；先前 live-host 测试输出还涉及 WebUI 静态入口凭据。只记录实际暴露范围，不将其写成外部公开泄漏或零暴露；计划、日志和制品不得复述、复制这些值。制品此前未包含真实 token。主线已授权最终稳定 cutover 同时随机轮换 `CODEX_AUTH_TOKENS`、`WEBUI_API_KEY`、`MRW_BACKEND_API_KEY` 及其实际消费方引用，以私有 0600 原子更新并真实检验旧拒绝和新成功；OAuth 与领域数据不在此次轮换范围。

本轮 coverage 准备的进程检查还使宿主继承的 `DEEPSEEK_API_KEY` 进入了私有工具输出。仓库有界符号核对确认 MRW app、测试和交付入口均不读取该槽，只有 `reference-pool` 示例提及，因此它不属于 MRW 应用凭据轮换或本机发布 blocker；宿主 DeepSeek 账号 owner 仍需在原 issuer 侧轮换该宿主槽。共享报告只保留键名、provider、MRW consumer-read 为 false 和脱敏证据 hash，不保留值或 hash 后缀。

已核源码：`main.py::_static_codex_token_actor` 使用 `actor_id_from_secret("actor:codex-token", token)`，`request_identity.py` 以 token 的 SHA-256 前 16 个十六进制字符派生 actor。更换静态 token 会改变 actor；`AuthorityGrantRepository.current_for` 精确匹配 project、actor、capability、未撤销和有效期，`PostgresAuthorityProvider` 还将 actor、grant 集合与 epoch/digest 绑定到资格。`local_host` 由 WebUI/backend 之间的 server key 派生，仅在真正 loopback、无 forwarded client header 且指定 record-input/dispatch 路径成立；本轮轮换该 key 会产生新的 local_host actor，可信身份仍不代替 capability grant，旧 actor 的 grant 或历史记录不得复制给新 actor。

切换前由集成在私有进程内推导旧静态 actor，只输出各项目依赖数量与状态：current grants、未完成 runtime work 和待消费 approvals，以及当前 local_host 原 grant 是否存在。token、hash 后缀、完整 actor 和数据库行内容不输出。没有旧静态 actor 的活动授权/工作依赖时，直接替换私有认证配置及实际消费引用并重启 backend，不写 authority 或领域表。发现依赖时保留原记录，报告具名范围、数量和原 owner 所需 transition；不得直接 UPDATE grant.actor_id、改写历史 approval/session/runtime identity，或为新 actor 自动复制用户 grants。新静态 actor 没有 grant 时仍须拒绝 capability；不能把 local_host 的原 grant 转赠给它。

集成后续在实际用户 `5432/postgres` 只读核对：backend/worker 各有一个静态 token，集合一致；旧静态 actor 的 current grants、未完成 runs、awaiting、pending agent approvals、runtime approvals 均为 0。因此当前状态为 `SECURITY_ROTATION_READY`，表示依赖审计允许上述轮换，尚未表示已轮换。独立 server key 存在，但 local_host 的 current grant 也为 0；这是具体业务 capability 尚未启用，不是认证失效或全项目阻断。

现有正式管理员入口为 `main/backend/scripts/provision_project_runtime.py`。其 issuer 是持有数据库配置与本机执行权限的 OS 部署 operator；`--administrator-id` 只提供审计身份，不把 HTTP/OAuth 身份提升为 admin。CLI 显式接收已有 project、初始 incarnation、target actor 或 `--target-local-host`、原 capability/resource-policy JSON、grant ID/epoch/有限 expiry、operations、resource limits 和 max-active，在同一事务调用 `install_project_runtime` 建立初始 scope/原项目表，再调用 `install_runtime_authority` 写权威记录。业务 Project 创建、startup 和 first-use 请求均不自动签发 grant。

该 CLI 已接入 `composition/installed_operation.py::installed_operation_catalog` 的原已安装契约；未知 operation 在创建 engine 前拒绝。零 scope 历史且已有 enabled 业务 Project 时，才调用 `install_project_runtime`；已有历史沿 `ServerProjectScopeResolver` 读取并调用 `install_runtime_authority`，读取错误或 scope冲突不回退成首次安装。集成真实 CLI 曾暴露安装调用位于 `engine.begin` 之外的 `ResourceClosedError`，现两分支均恢复到同一原事务；原四项测试及三个 subtests、隔离 URL CLI 与 current grant读回已通过。`/tmp/mrw-version-release-20261009/live-host-url-chain/provision-attempt2.nativeexit` 与 `provision-readback.nativeexit` 均为 `0`。这些是隔离部署证据，用户库尚未获本轮 URL启用声明。现存/撤销/过期声明的异值重试不能覆盖或续期，必须沿原 owner transition。

隔离 release DB 可依已授权原 fixture 为其精确 local_host/URL operation 安装有限 grant，证明真实 worker 链；该证据不能当作用户项目已授权。用户项目 URL 业务的最小处理是由 OS 部署 owner 明确目标 project、原 local_host、唯一 URL operation、期限及资源额度，并沿上述原 typed installer 执行一次有限部署声明，保留 approval/rollback 引用与实际 readback。若需要可重复命令，范围仅为原 provisioning CLI 接入现有 installed catalog 与已有 scope 分支；不新增授权平台、不从登录或 first-use 推出 grant。声明范围未确定时仅报告该项目该 capability 未启用，继续其它独立验收；不能把测试 grant 或旧 actor 权限自动推广到用户 DB。

本机版本的用户 URL 启用范围以一个明确选定 Project、原 `local_host` 和 `acquisition.url.single_url.v1` 为最小单位，不要求所有项目获得所有 capability。若最终宣称该宿主 URL 业务可用，须在所选用户项目完成有限启用与原链路读回；仅隔离测试通过时，结论仍应写明用户 URL 执行未启用。项目、到期时间和资源上限由用户明确选择，OS 部署 owner 根据批准范围生成原生声明与摘要；并发/units ceiling 不得误写成累计请求数或费用额度。原 CLI 的 installed catalog、已有 scope 和首次绑定三项关联已经修复，剩余是用户范围选择及获准后的实际执行，不能把 scope冲突或读取错误当作首次缺失。其余技术身份、digest、grant id 与审计引用由原 owner 派生，不要求用户填写底层 JSON，也不修改原用户授权记录。

多项真实配置引用由唯一集成 owner 在服务维护窗口协调更新：值只在私有进程内传递，文件在私有目录中以 0600 暂存并原子替换；不输出 plist/environment 全文、命令参数中的密钥或 HTTP 响应 token。只替换已授权的三个应用槽及其相等消费引用，其余认证配置保持；失败时修复配置/服务，不启用旧 token fallback。原 OAuth、用户数据和 authority 的保全通过脱敏相等性与数量读回记录。

旧拒绝/新成功使用 `POST /api/v1/codex-auth/webui/bootstrap` 的显式 bearer 分支：旧 token 得到 401/`invalid_token`，新 token 得到 200，且返回的短期 `accessToken`/有效期字段存在。验证只保留状态码和必要布尔，响应 token 不落日志。普通 protected-path middleware 对无效静态 token 会继续尝试现有 OAuth token-sink，因此普通 API 的成功响应不能单独证明旧静态 token 仍有效或已经失效。保留 OAuth fallback 的原行为，此次不改认证模型；另用新 token 的可信 actor 读回及原 local_host 宿主链确认实际入口可用。轮换完成后同时核配置不再接受旧静态值，不能只凭服务 restart 成功消除此阻断。

本计划不预先宣称通过。集成把各包结果、改动文件、真实验证、未执行项和 blocker 收回本文件或现有交付记录，保留失败 attempt。只有全 app 类型、完整适用 suite、真实业务链、迁移、安装与恢复都成立，才宣布本机 `1.0.0` 可用。测试通过不扩大外部发布权限。普通修复留在当前工作树、最小相关验证，批次稳定后一次集中确定候选和提交；不逐小修冻结。

执行成本沿现成日志汇总：派发/完成数、首轮共同验收时间和失败次数、规则建设/主线补修/等待、各 owner 的调用与 token。不可得项明确缺失，不记零；包内绿色不算整组完成，缺少可比基线时不宣称提速。

## 6. 后续类型包的直接派发清单

本节是 §2 同一划分的具体文件展开，不创建新包或第二清单文件。下面花括号是文件集合记法；每一行以 `main/backend/app/` 为根，不包含目录内未列出的新增文件。当前七个待接力包共 476 文件，首三包共 156 文件，合计 632。文件新增/删除由集成在本计划同处核对归属。每包交付为目录/明确文件 strict 0、原消费者相关测试、改动文件、原退出码及未执行资源；测试列表是第一组真实见证，不能替代最终全集。

所有测试命令在 backend cwd 使用 §2 的绝对 PYTHONPATH 和 backend 解释器。PG相关测试在资源未分配时仅报告待执行，不能把skip当成功。基础 strict 命令见§2，目标使用该包§2路径；T-SUPPORT/T-FOUNDATION必须用下面展开的明确文件，不把已交其他owner目录重新包含。无源文件修改、依赖变化或新失败时复用结果，不重复跑。

### T-FOUNDATION：89 文件

**接力 owner：**C 本机交付稳定后接力；共享消费者/配置/注册仍交集成。

**目标与权威输入：**先处理 models/base.py 的 Session、事务 callback 和池状态；保留 retry Failure 与原异常 lift。production_observability 的输入/receipt 只投影原事实。模型及 schema 的变化先通知实际调用包，绿色 composition/identity 不为文件归属而改写。pgvector/bs4 stub 文件不在本包，由集成独占。

**第一组直接验证：**

```bash
.venv311/bin/python -m pytest -q tests/functorial_debt/test_w01_effect_failures.py \
  tests/unit/test_schema_startup_boundary_unittest.py \
  tests/integration/test_project_schema_guard_unittest.py
```

**独占 app 文件：**

```text
{__init__.py,celery_app.py,main.py,release_identity.py,startup_hooks.py,web_ui_routes.py}
composition/{__init__.py,collect_runtime.py,discovery.py,ingest.py,installed_operation.py,llm.py,production.py,production_runtime.py,resource_pool.py,source_library.py}
contracts/{__init__.py,api.py,errors.py,json.py,materials.py,responses.py,tasks.py}
contracts/schemas/{__init__.py,clue_chains.py,information_topology.py,policies.py,workflow_graph.py,writing.py}
models/{base.py,entities.py,information_topology_entities.py,ingest_registry.py,llm_report_export_audit.py,llm_report_export_token_state.py,llm_report_trends.py,project_retrieval.py,typed_knowledge_entities.py,writing_entities.py}
production_contract/{__init__.py,policy.py,types.py}
production_observability/{__init__.py,alerts.py,config.py,contracts.py,decision.py,errors.py,health.py,http.py,metrics.py,observations.py,receipts.py,runtime.py,worker.py,worker_telemetry.py}
project_customization/{__init__.py,defaults.py,interfaces.py,registry.py,service.py}
project_customization/projects/__init__.py
project_customization/projects/business_survey/{__init__.py,customization.py}
project_customization/projects/demo_proj/__init__.py
project_customization/projects/hk_water_investigation/{__init__.py,customization.py}
project_customization/projects/hk_water_macro_registration_trial_20260928/{__init__.py,customization.py}
settings/{config.py,graph.py}
subprojects/{__init__.py,base.py,default_adapter.py,registry.py}
subprojects/demo_proj/{__init__.py,customization.py,extraction_adapter.py}
subprojects/demo_proj/mappings/{__init__.py,fields.py,llm.py,menu.py,workflow.py}
successor_migration/{__init__.py,document_canonical_read.py}
successor_runtime/__init__.py
successor_runtime/assembly/{__init__.py,base.py,workflow_assembly.py}
```

### T-INGEST：57 文件

**接力 owner：**待首个类型作者释放后派；SOURCE terminal 已可消费。

**目标与权威输入：**先 postprocess_frontdoor/frontdoor_ingress 的 terminal 和 raw import 数据边界，再 canary metrics/handoff 与配置 DTO。使用 SourceMode/TerminalStatus/TerminalOutputDto/TerminalCollectResult；不重复 normalizer，不把 UNKNOWN/accepted 转 completed。

**第一组直接验证：**

```bash
.venv311/bin/python -m pytest -q tests/unit/test_ingest_frontdoor_context_unittest.py \
  tests/unit/test_raw_import_structuring_unittest.py \
  tests/unit/test_ingest_canary_handoff_unittest.py \
  tests/unit/test_ingest_canary_metrics_readback_unittest.py
```

**独占 app 文件：**

```text
services/ingest/{__init__.py,canary_handoff.py,canary_handoff_live.py,canary_metrics.py,canary_metrics_readback.py,canary_strict_promotion.py,cleanup_executor.py,commodity.py,content_cleaner.py,content_extraction.py,doc_type_mapper.py,ecom.py,frontdoor_contract.py,frontdoor_ingress.py,frontdoor_orchestrator.py,frontdoor_router_contract.py,frontdoor_slo.py,gate_reason_codes.py,guardrail_rollout.py,keyword_library.py,light_filter.py,llm_dirty_review.py,market_web.py,material_ingress.py,material_input.py,meaningful_gate.py,metrics_payload.py,news.py,policy.py,postprocess_frontdoor.py,provider_ports.py,raw_import.py,retry_policy.py,search_and_ingest.py,social.py,social_application.py,source_search_contract.py,structured_extraction.py,terminal_compat.py,terminal_normalizer.py,terminal_writer.py,url_pool.py,url_unwrap.py}
services/ingest/adapters/{__init__.py,base.py,ca_legislature.py,http_utils.py,legiscan_api.py,news_google.py,social_nitter.py,social_reddit.py,social_twitter.py,submission_registry.py}
services/ingest/reports/{__init__.py,general.py}
services/ingest_config/{__init__.py,service.py}
```

### T-PG：50 文件

**接力 owner：**待 KERNEL 或另一类型作者释放后派；PG写槽由集成授权。

**目标与权威输入：**从 runtime_journal.ExactQualificationBinding 和 runtime_values 的真实 rows/codec 着手；KERNEL 公开 binding 稳定前仅做独立 row 窄化。保持 provisional digest 后 validated constructor、authority/qualification identity、transaction 和 Runtime writer。原 runner 的普通、CREATEDB、pristine lanes 不合并。

**第一组直接验证：**

```bash
.venv311/bin/python -m pytest -q tests/successor_runtime/test_p0b_schema_contract.py \
  tests/successor_runtime/test_authority_grant_runtime_classification.py \
  tests/successor_runtime/test_traversal_persistent_activation.py
```

**独占 app 文件：**

```text
successor_runtime/substrate/__init__.py
successor_runtime/substrate/blob/{__init__.py,internal_export.py,store.py}
successor_runtime/substrate/postgres/{__init__.py,approvals.py,authority.py,authority_provider.py,batch_task_submission_handler.py,capacity.py,captured_values.py,commit_intents.py,composition_root.py,delivery_gate.py,delivery_runtime.py,deployment_backlog.py,effect_reconciliation.py,failure_policy.py,gap_successor.py,idempotency.py,internal_delivery_handler.py,models.py,node_adapter.py,nodes.py,owner_bindings.py,plans.py,programs.py,projection_offsets.py,qualification_store.py,reconciliation.py,research_admission.py,research_ledger.py,resources.py,runtime_activation.py,runtime_failures.py,runtime_journal.py,runtime_lifecycle.py,runtime_values.py,session.py,source_library_c2_1_canary.py,staged_artifacts.py,terminal_authority.py,terminal_commit.py,unit_of_work.py,values.py,work_items.py}
successor_runtime/substrate/projections/{__init__.py,agent_session.py,research_ledger.py,runtime_run.py}
```

### T-RESOURCE：43 文件

**接力 owner：**SOURCE消费接口稳定后，空闲作者接力；独立解析核可先做。

**目标与权威输入：**先 unified_search/resolver 的已有 provider ports，再 discovery/store SQLAlchemy rows、crawler management service 与 article extraction。保留真实 source identity、project binding、部分失败与原搜索 contract，不能把同形 JSON 解码在四个目录分别造一遍。

**第一组直接验证：**

```bash
.venv311/bin/python -m pytest -q tests/unit/test_resource_pool_unified_search_unittest.py \
  tests/unit/test_discovery_store_guardrails_unittest.py \
  tests/unit/test_resource_pool_article_extraction_service_unittest.py \
  tests/core_business/test_resource_pool_core_contract.py \
  tests/core_business/test_discovery_core_contract.py
```

**独占 app 文件：**

```text
services/crawlers_mgmt/{__init__.py,orchestration.py,service.py,workbench.py}
services/discovery/{adapters.py,application.py,deep_search.py,ports.py,store.py}
services/extraction/{__init__.py,application.py,extract.py,json_utils.py,models.py,numeric.py,numeric_general.py,service.py,topic_extract.py,topic_workflow.py}
services/resource_pool/{__init__.py,append_adapter.py,article_extraction_service.py,auto_classify.py,candidate_source_plan.py,capture_config.py,extract.py,http_port.py,llm_validator.py,open_source_source_importer.py,open_source_source_presets.py,ports.py,resolver.py,search_capabilities.py,search_contract_discovery.py,search_result_parser_profiles.py,search_result_parser_service.py,search_template_adapters.py,search_template_service.py,site_entries.py,site_entry_discovery.py,site_search_policy.py,unified_search.py,url_utils.py}
```

### T-KNOWLEDGE：73 文件

**接力 owner：**空闲作者接力；真实PG见证等待集成资源。

**目标与权威输入：**先 typed_knowledge/persistence_boundary 与 information_topology/io/retrieval 的输入/row输出，再 workflow_graph/curated_service、clue chain/graph/writing 原消费者。保持版本冲突、revision/current、类型对象身份、材料归属、writing权限。migration文件由M独占，不在此修表。

**第一组直接验证：**

```bash
.venv311/bin/python -m pytest -q tests/unit/test_typed_knowledge_persistence_boundary_unittest.py \
  tests/unit/test_information_topology_retrieval.py \
  tests/unit/test_workflow_graph_curated_service_unittest.py \
  tests/integration/test_workflow_graph_api_unittest.py \
  tests/integration/test_information_topology_repository.py
```

**独占 app 文件：**

```text
services/clue_chains/{__init__.py,contracts.py,external_search_expansion.py,service.py,source_library_expansion.py,store.py}
services/graph/{__init__.py,backfill_graph_nodes.py,builder.py,compat.py,doc_types.py,exporter.py,mapping.py,models.py,ports.py,projection.py,relation_ontology.py}
services/graph/adapters/{__init__.py,generic.py,market.py,policy.py,reddit.py}
services/graph/persistence/{__init__.py,graph_node_alias_resolver.py,graph_node_reader.py,graph_node_writer.py}
services/information_topology/{__init__.py,bindings.py,catalog.py,contracts.py,document_materials.py,mapping.py,profiles.py,repository.py,service.py,structural_schema.py}
services/information_topology/adapters/{__init__.py,native.py}
services/information_topology/io/{__init__.py,retrieval.py}
services/information_topology/modules/{graph_view.py,method.py,report.py,retrieval.py}
services/typed_knowledge/{__init__.py,baseline.py,contracts.py,persistence_boundary.py}
services/typed_knowledge/adapters/{__init__.py,live_service.py}
services/workflow_graph/{__init__.py,compiler.py,contracts.py,curated_service.py,edit_contract.py,governance_contract.py,handoff_store.py,observability.py,runtime.py,schema.py,store.py,templates.py}
services/workflow_graph/executors/{__init__.py,join.py,kernel.py,llm_call.py,vector_search.py}
services/writing/{__init__.py,citation_service.py,document_service.py,keyword_card_service.py,search_suggest_service.py,template_service.py}
```

### T-API：35 文件

**接力 owner：**相应服务返回稳定后由空闲作者接力；host两API已排除。

**目标与权威输入：**先 project_customization API的工厂/返回schema，再 resource_pool和process response。reuse既有schema与canonical reader；HTTPException helper用真实NoReturn而不是假return。兼容原错误码/envelope，禁止把API返回值统一改dictAny。

**第一组直接验证：**

```bash
.venv311/bin/python -m pytest -q tests/contract/test_api_schema_discovery_project_customization_contract_unittest.py \
  tests/contract/test_api_schema_ingest_resource_contract_unittest.py \
  tests/contract/test_api_schema_lane_e_response_models_unittest.py \
  tests/contract/test_api_schema_writing_search_small_contract_unittest.py \
  tests/contract/test_api_schema_auth_agent_web_contract_unittest.py \
  tests/contract/test_api_schema_inventory_contract_unittest.py
```

**独占 app 文件：**

```text
api/{__init__.py,_error_responses.py,admin.py,agent_batch.py,agent_sessions.py,business_lines.py,clue_chains.py,codex_auth.py,config.py,crawler.py,dashboard.py,discovery.py,functorial.py,governance.py,indexer.py,information_topology.py,ingest.py,keywords.py,llm_config.py,llm_report.py,policies.py,process.py,products.py,project_customization.py,project_retrieval.py,projects.py,resource_pool.py,search.py,skills.py,source_library.py,stats.py,topics.py,typed_knowledge.py,workflow_graph.py,writing.py}
```

### T-SUPPORT：129 文件

**本轮并行 owner：**API/SOURCE 作者释放后，由 `release_source_recovery` 接力下面清单的整个 `services/llm/**`，实际为 19 文件（顶层 17、adapters 2）；`release_types_kernel` 保留其余 110 文件。两面合计仍为 129，全组同时最多五个作者。原 owner 停止 LLM 子树新编辑并交接当前字节和已完成的 `config_loader.py` 等修复；接力者保留这些改动，不回退或从旧基线重做。下方完整清单仍是唯一文件分母，LLM 面就是两条 `services/llm` 展开行，其余逐项归母包；不另建清单或按预估的 26 文件派发。

**公共接口与独占边界：**LLM 面消费原 `ports.py` 的 `ChatModel`、`EmbeddingModel`、`ChatModelOptions`、provider registry/JSON parser，以及原 native Codex binding、app-server 与 tool context。`config_loader.py::format_prompt_template` 的已定接口随 LLM 文件交接，由接力者唯一维护；先用已稳定真实入口接通消费者，再展开同形使用，不复制 parser/client、改成通用 `Any` 或重建 native 执行路径。`services/search/smart.py`、`services/http/client.py`、`services/codex_oauth.py` 和全部 `services/llm_report_*.py` 留母包；需要这些接口变化时只向母包 owner 回传具体缺口。`models/**`、`contracts/json.py` 和 composition 注册仍由原公共 owner 维护，LLM 作者不跨写。特别保留 OAuth token sink 的原只读消费边界、native invocation identity、provider Failure/TypeError ABI 与 cache 生命周期。

**目标与权威输入：**先 llm_report_trends/export_token_state及llm provider/config的封闭结果，再agent_batch、stats和剩余search/crawler边界。tasks、agent_sessions、projects/context等当前绿色接口保持。authoring_tools的status修复留T-HOST，不跨包再实现worker或session状态。

**母包第一组直接验证（backend cwd）：**

```bash
.venv311/bin/python -m pytest -q tests/unit/test_llm_report_trends_service_unittest.py \
  tests/unit/test_llm_report_export_token_state_service_unittest.py \
  tests/unit/test_llm_report_generator_unittest.py \
  tests/unit/test_agent_batch_dispatch_lowering_unittest.py \
  tests/unit/test_agent_batch_approval_binding_unittest.py \
  tests/integration/test_codex_oauth_browser_flow_unittest.py
```

**LLM 面直接纯验证（backend cwd，沿用 §2 绝对 PYTHONPATH）：**

```bash
.venv311/bin/python -m pytest -q tests/unit/test_llm_provider_boundary_unittest.py \
  tests/unit/test_codex_cli_llm_fallback_unittest.py \
  tests/unit/test_llm_platformization_unittest.py \
  tests/unit/test_llm_cache_location_unittest.py \
  ../../tests/test_llm_provider_port_laws.py ../../tests/test_llm_provider_registration.py
```

两面各自提交精确源码与原 pure 结果；本组 pure 不证明真实模型、OAuth、worker 或数据库执行。涉及共同 imports、provider registry、环境变量、cache 或数据库的测试按原测试资源槽协调，不因源码写面互斥就自动并发。局部 strict 使用各自精确 19/110 文件，最后由集成 owner 在同一稳定输入上对原 129 文件统一 strict 验证，并纳入全部 632 app 的最终扫描；新输入上的 `passed` 与未变化依赖上复用的 `kept` 分开记录，不把两个子包局部 0 相加充当联合通过。

**独占 app 文件：**

```text
services/{codex_oauth.py,derived.py,document_admin.py,job_logger.py,keyword_generation.py,keyword_memory.py,llm_report_export.py,llm_report_export_audit.py,llm_report_export_token_state.py,llm_report_generator.py,llm_report_source_enrichment.py,llm_report_trends.py,observability_tasks.py,request_identity.py,settings_manager.py,skill_runtime.py,task_readback_metadata.py,tasks.py}
services/agent_batch/{__init__.py,approval_binding.py,benchmark.py,business_readback.py,dispatch.py,executor_health.py,routing.py,search_quality_replay.py,task_contract.py}
services/agent_sessions/{__init__.py,service.py,store.py}
services/collect_runtime/{__init__.py,contracts.py,delivery.py,display_meta.py,runtime.py}
services/collect_runtime/adapters/{base.py,crawler_scrapy.py,search_market.py,search_policy.py,source_library.py,url_pool.py}
services/crawlers/{__init__.py,base.py,bridge.py,durable_effect_bridge.py,registry.py,scrapyd_bootstrap.py,scrapyd_client.py,scrapyd_result_ingest.py,scrapyd_runtime.py}
services/crawlers/providers/{__init__.py,base.py,registry.py,scrapy.py,scrapy_provider.py}
services/document_queries/{__init__.py,consumer_predicates.py,contracts.py,identity.py,policy_filters.py,search_endpoint.py,statement_builder.py,structured_data_search.py,writing_documents.py,writing_material_queries.py}
services/document_views/{__init__.py,common_view.py,consumer_boundary.py,market_view.py,policy_view.py,social_view.py,stats_view.py,writing_card_view.py,writing_view.py}
services/governance/{__init__.py,retention.py}
services/http/client.py
services/indexer/{__init__.py,application.py,policy.py}
services/llm/{__init__.py,cache.py,chains.py,codex_app_server.py,codex_cli.py,codex_macro_binding.py,codex_user_config.py,config_loader.py,config_service.py,extraction.py,macro_work.py,native_tool_context.py,platformization.py,ports.py,prompts.py,provider.py,service.py}
services/llm/adapters/{__init__.py,langchain_provider.py}
services/project_retrieval/{__init__.py,contracts.py,execution.py,formalization.py,hk_loader.py,mode.py,proposals.py,rapid_macro.py,service.py,skill.py,topology.py}
services/projects/{__init__.py,bootstrap.py,context.py,global_stats.py,schema_initialization.py,workflow.py}
services/search/{candidate_contracts.py,candidate_search.py,es_client.py,facets.py,history.py,hybrid.py,indexes.py,retrieval_runs.py,smart.py,vector_contracts.py,web.py}
services/stats/{__init__.py,prompt_time_density.py}
```
