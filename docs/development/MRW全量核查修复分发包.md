# MRW 全量核查修复框架与阶段分发包

> 后续结构整理：[MRW结构整理方案与分发包](MRW结构整理方案与分发包.md)（2026-10-04，实施结果见该文 §8）。最高优先退役现用产品、API身份和当前文档中的开发编号语义，统一为真实业务名称；本文原编号仅保留实施与证据追溯，不作为后续操作入口。既有结果及事实归属保持原义。

日期：2026-10-04。状态：`LOCAL_DAILY_FULL_CHAIN_VERIFIED / LOCAL_DEVELOPMENT_ONLY`。入口为 [清简分发包 §7.4–7.5](MRW清简分阶段实施分发包.md)。本包承接全量核查，不重启已停止的生产 Stage 4–6，不建立发布资格。

用户指定由 Astra 设计；当前子 Agent 工具未提供 Astra 模型，主线已说明并采用继承模型完成设计，不能将本文件记为 Astra 实际执行。主线保留最终设计、跨包接缝、实际分发、环境与整组验收职责；子包禁止再 spawn。调用、token、成本和可比耗时尚缺，不报告提速。

## 1. 修复对象与权威边界

修复对象由四类关系构成：用户身份到允许执行的操作；来源候选到审核、正文、索引及可读回检索结果；当前 API/页面到用户可观察行为；测试输入及断言到所验证的当前或历史合同。候选 URL、token sink、空搜索结果、历史快照及测试 PASS 分别属于不同对象，不能相互代替。

一条合法业务链必须保存项目/用户/材料身份、授权和失败归属。当前源码是当前实现权威，原合同是预期权威，历史冻结文件是历史字节权威；派生扫描和测试日志只有观察权。目录相同不建立这些身份，旧 hash 也不成为当前行为的断言。各 owner 按这一有向关系修复原消费者，不增加第二套注册、缓存、认证或业务执行系统。

本轮只复用现有 composition、kit、原 API、Celery、project schema 初始化及 indexer/search。共享规则先由一个 owner 在一个真实消费者上打通，再进行同形迁移。复合保持的见证是同项目的输入→原执行者→持久读回；测试隔离只证明观察环境独立，不推出业务步骤可交换。跨包的互不冲突同时检查文件、DB、端口、auth volume、构建目录和 mutable fixtures。

完成状态分为 `passed`（本轮原 runner 通过）、`kept`（明确未变依赖上的旧证据）、`failed`、`blocked`、`not_run`、`retired_contract`（旧合同退出当前验收且历史仍可复核）。后三类不计通过；`retired_contract` 必须给原合同、当前替代行为、退出理由及保留路径。历史测试不能只因失败就退休，当前负向安全合同不能退休。

## 2. 输入、覆盖与归属

cwd 统一为 `/Users/wangyiliang/market-research-workflow`。核查原始输入为 `/tmp/mrw-readiness-20261004/`；原日志只读，不覆盖。必读 19 号缩减规则及 06 号顶部入口继续有效。使用 `functorial-kit.json`、相关 registries/sketches 和实际安装 kit 导出；不凭旧 `Idempotent` 名称新增兼容设施。

| 输入群 | 原数量/状态 | 首要 owner | 分流条件 |
|---|---|---|---|
| 后端精确 nonexternal inventory | 4230；3852 PASS/78 FAIL/300 SKIP | R0/R5 | 原 nodeid inventory 与两段日志联合覆盖，10 个环境复验单列，不扣减基线 |
| 根目录 | 1392 PASS/71 FAIL，另 6 collection ERROR | R2/R5 | 六模块必须重新收集；71 中历史 formal_release 与当前 checker 分开 |
| 前端 | 117；95 PASS/17 FAIL/5 SKIP | R3/R0 | 17 精确日志条目逐项归属；部分 undefined table 属初始化环境 |
| 真实身份/native | 401/CLI 未初始化未登录 | R1 | 无有效用户会话/凭据是真实前置，不能由 Agent 伪造 |
| 来源→检索 | Serper 候选5，正文0；空索引搜索200 | R6 | review 阻断保持；synthetic raw-import 不能充作外部正文 |
| 可选 provider/服务 | 未配置或未执行 | R5条件分类/R0 | 按所需能力分项，不能全记通过或扩大成全局阻断 |

后端 78 项初步分组沿用 §7.4，不升级成全部产品缺陷：route 污染7、source/bytecode10、readonly fixture2、root name1、字符串误判import3、冻结/旧路径/字节20、shared-root/C9 digest4、旧owner/version13、Redis fixture1、DB fixture1、API inventory2、release version1、migration graph2、ingest mocks2、W03/W06 witness2、envelope1、退役NL1、retained retrieval2、URL unwrap3。R5 将每条实际 nodeid 唯一映射到 owner；同一 nodeid 后续复验记录链接原条目，不把分组数字当闭合证据。

300 backend SKIP、5 frontend SKIP、6 root ERROR 各自列出原原因和条件：专属 PostgreSQL/可创建测试库权限、Ruby/其他解释器、fixture、依赖包、provider/service 条件及 retired feature。适用且条件可满足的测试实际执行；选择性可选能力保留 `not_run` 与条件。未获凭据、真实账号登录或来源材料不足只阻断对应包的 live 完成。Inventory 数量变化必须解释新增/删除/退休差异。

## 3. 阶段与资源编排

| 阶段 | 可执行包 | 必须先完成 | 收敛与下一前沿 |
|---|---|---|---|
| A 契约和共同环境 | R0、R1只读、R2依赖/单案例、R3静态定位、R4、R4U、R5分类与R6材料链只读诊断可并行 | 现有审计输入 | R0固定runner/资源，R2当前kit与一个消费者读回通过；R1输出真实身份/native缺口；其余局部实现不因外部登录停工 |
| B 独立修复 | R2其余五模块验证、R3、R4、R4U、R5当前测试修复、R6局部实现、R5适用性分类 | 各包实际依赖；R2批量验证依赖单案例 | 独占文件，共享app/main.py只归R4；所有root/checker共享消费者归R5；R6不修改R4U文件 |
| C 运行链与资源测试 | R0先迁移/schema/index准备，随后R1 live、R6 live、R3真后端E2E串行占用同一栈 | B受影响实现、R0环境；live凭据/来源 | 同一DB/auth/浏览器dist不得并行写；无依赖只读检查可继续 |
| D 整组收敛 | 主线R0统一收集完整inventory并执行适用原suite、lint/build、sync/check | 各包回传、候选输入一致 | 输出实际闭合/残余缺口；不以子包绿灯宣称整组完成，不进入发布 |

资源：主线创建新 compose project `mrw-repair-20261004`；证据和日志放 `/tmp/mrw-repair-20261004/`。原 overlay 可参考，但必须覆盖继承的 `main/logs` 为专属日志目录。仅主线占用18004（backend）、15134（gateway）、15136（launcher）与4194（Playwright dev server）。原宿主8172只读；不得让 launcher 默认启停控制新 overlay。专属 DB/ES/Redis/auth volumes 的生命周期均归R0；不得挂用户默认DB/auth写入。各 pytest runner 各自临时目录、`PYTHONPYCACHEPREFIX`、Hypothesis样例目录；完整测试固定单进程，Postgres测试的静态数据库名称可能冲突，不能只按文件分并行。

## 4. 可直接复用的验证入口

以下命令不含凭据。最终 `IMAGE` 为主线构建的 `mrw-repair-tests-20261004:latest`；构建完成前原 `mrw-readiness-tests-20261004-backend-test:latest` 只用于隔离局部复验。R0已将 `main/backend/Dockerfile.test` 改为读取根 `pyproject.toml` 的已有dev依赖（包含Hypothesis），不另录测试版本。kit路径与导出仍执行前读回，不让包自行反复安装。宿主绝对路径挂载防止 source-location 漂移，所有写缓存走 `/tmp`。

```sh
# cwd: /Users/wangyiliang/market-research-workflow
# 后端局部示例（其他包替换明确测试路径，保持原退出码）
docker run --rm --entrypoint python -v /Users/wangyiliang/market-research-workflow:/Users/wangyiliang/market-research-workflow:ro -v /Users/wangyiliang/Desktop/functorial-kit/python:/opt/functorial-kit:ro -w /Users/wangyiliang/market-research-workflow/main/backend -e PYTHONPATH=/Users/wangyiliang/market-research-workflow/main/backend:/Users/wangyiliang/market-research-workflow/src:/opt/functorial-kit -e PYTHONPYCACHEPREFIX=/tmp/mrw-repair-r4-pyc mrw-repair-tests-20261004:latest -m pytest -p no:cacheprovider tests/integration/test_api_exception_envelope_unittest.py tests/integration/test_api_envelope_gap_fixes_unittest.py -q

# root 六模块：R0补齐依赖后，同一镜像和源树，在根cwd执行
docker run --rm --entrypoint python -v /Users/wangyiliang/market-research-workflow:/Users/wangyiliang/market-research-workflow:ro -v /Users/wangyiliang/Desktop/functorial-kit/python:/opt/functorial-kit:ro -w /Users/wangyiliang/market-research-workflow -e PYTHONPATH=/Users/wangyiliang/market-research-workflow/main/backend:/Users/wangyiliang/market-research-workflow/src:/opt/functorial-kit -e PYTHONPYCACHEPREFIX=/tmp/mrw-repair-r2-pyc mrw-repair-tests-20261004:latest -m pytest -p no:cacheprovider tests/test_collect_adapter_laws.py tests/test_counter_laws.py tests/test_example_codec_laws.py tests/test_ingest_provider_port_laws.py tests/test_llm_provider_port_laws.py tests/test_resource_pool_port_laws.py -q

# 主线受影响frontend静态验证，cwd: main/frontend-modern
pnpm lint
pnpm build

# 主线独占4194；真实后端准备好后使用，cwd: main/frontend-modern
FRONTEND_E2E_PORT=4194 VITE_API_PROXY_TARGET=http://127.0.0.1:18004 VITE_CODEX_PROXY_TARGET=http://127.0.0.1:8172 pnpm exec playwright test --reporter=line --workers=1

# 原API广度smoke，cwd: main/backend；source-item-key由R6正式入口读回
python3 scripts/repo_runtime_smoke.py --base-url http://127.0.0.1:18004 --require-base-url http://127.0.0.1:18004 --project-key readiness_repair --source-item-key "$MRW_REPAIR_SOURCE_ITEM_KEY"

# 集中机械接入检查，cwd: repo root
python3 scripts/dev.py check
git diff --check
```

路径 `/opt/functorial-kit` 只有确认实际存在才使用；若当前镜像采用不同安装位置，R0一次读回并替换全组统一命令，不由各包新造解析器。上面的宿主 `python3` 仅限已具备原脚本依赖；live smoke 首选 compose backend 中 `python /app/scripts/repo_runtime_smoke.py`，base URL用其实际后端可达地址。外部脚本需要 composition 时复用 `app.celery_app` 注册，不能再次把缺注册导入误判在线服务故障。

完整重验必须先 `--collect-only`：backend仍为 `tests -m 'not external'`，root仍为 `tests`，Playwright `--list`。此次不设20fail截断，或使用原inventory按最后实际nodeid精确续跑。pytest临时写面/fixtures先准备，不用大范围ignore回避已知错误；原 collection ERROR消除后重新完整收集。DB类测试R0按实际模块要求注入 `SUCCESSOR_TEST_DATABASE_URL` 等具名env到专属DB，测试可DROP/CREATE的数据库不能指用户库。marker external并不覆盖已知未配置provider能力，R5条件分类另列适用范围。

## 5. 分发契约

每包回传：结果、实际改动文件、原命令退出码和日志路径、未闭合nodeid/能力、风险及真实 `blocked_by`。主线把现成日志归纳到本文件，不另造审批或每作者统计表。

### R0 主线环境、清单与集成

目标：统一真实运行/测试环境，保持源树和运行输入一致，集中共享消费者和最终结果。权威输入：上节原日志、compose.audit.yml、`main/ops/docker-compose.yml`、Alembic以及项目schema初始化。独占写面：新专属overlay/logs，`main/backend/Dockerfile.test`、共享test runner配置、必要compose环境配置、分发文档与最终清单；其他包不能写。已有compose产品修改必要时由R0接受R1/R6建议后实现。

输出：确定解释器、kit导出、Hypothesis/Ruby条件、DB/schema版本、服务/端口/日志目录，精确inventory与owner映射；每包开始/完成和实际成本缺失。验证：compose config、专属 up、原Alembic current/heads、health/deep、原worker noop，上节局部/最终命令。完成：环境错误明确闭合，全部原条目有归属，核心链与整组结果可读回，专属清理验证ownership，保留用户服务。`blocked_by`：真实凭据只阻断R1 live；材料/review只阻断R6 live；其余无全局blocker。

### R1 用户身份与容器 Codex native

目标：给用户通过原入口建立会话并使用现有 Codex core/WebUI 的准确路径，安装/登录状态可观察。权威输入：`auth-effective-settings.json`、原API与Settings。首波只读：`main/backend/app/api/codex_auth.py`、`services/codex_oauth.py`、`services/llm/codex_cli.py`、`codex_app_server.py`、`codex_user_config.py`、`settings/config.py`、compose/auth volume；8172现服务只读。

输出：MRW身份→原exchange→WebUI session、容器binary→auth→app-server turn 的契约与实际缺口；明确宿主证据和容器证据。后续独占写面仅这些认证/native模块及对应测试，compose共享修改交R0；不改 `app/main.py` 或重建入口login页。验证：上节后端runner改为 `tests/production_composition/test_production_auth_bootstrap.py tests/production_composition/test_production_codex_webui_exchange.py tests/integration/test_codex_oauth_browser_flow_unittest.py tests/integration/test_codex_auth_agent_guard_unittest.py`；运行通过原受保护status/bootstrap/device入口，读回session与app-server实际turn，前端 `simp08-codex-auth-proxy.spec.ts` 由R0运行。

先确定当前保留架构的运行owner是宿主native还是容器native，以及MRW是否实际调用该形态；现有宿主8172/native证据仅在依赖输入未变时记kept。完成：错误的身份/公开bootstrap仍拒绝；有效原会话exchange可用；当前选定的必要native形态真实认证并完成实际turn。只有容器native是实际消费者所需时才要求容器auto release binary安装及登录，不为重复运行形态新增完成门槛。外部账号登录必须由真实用户/已配置凭据完成，Agent不得生成伪造cookie/static token去当用户认证证据。`blocked_by`：R0专属栈；若没有真实登录条件，产品修复可交付，live保持具名缺口。

### R2 kit 现 API 与六个 collection error

目标：按实际kit版本和导出收敛收集错误，保持法则行为及负例。当前读回发现原 `Idempotent`、`Ordered`、`PortLawSpec`、`port_laws` 已实际导出，不能为原审计输入差异硬造迁移。输入：当前安装kit导出/原语、`functorial-kit.json`、六模块原错误。独占写面：`tests/test_counter_laws.py`、`test_collect_adapter_laws.py`、`test_example_codec_laws.py`、`test_ingest_provider_port_laws.py`、`test_llm_provider_port_laws.py`、`test_resource_pool_port_laws.py`；需src shell实现变化先报真实语义差异由主线定界，不抢共享规则。

先以counter一个真实案例匹配当前kit规格和消费者，通过后验证另外五模块；仅真实API不兼容时才迁移；不自造Idempotent compatibility wrapper、不只删除测试。输出：六模块可收集/原法则实际执行；缺失原语给唯一规则owner及最小接口，不多个包各造替代。验证：上节root六模块命令；先counter单路径，然后六个完整路径。完成：collection ERROR=0、法则及其失败检测仍有效。`blocked_by`：R0镜像Hypothesis/kit依赖；单案例只约束依赖其规则的五模块。

### R3 前端行为与17失败合同

目标：按现在平台、页面语义修复真实交互和旧断言，不能以加无意义heading/按钮改绿。输入：frontend-full-e2e.log第648–664行精确17条、frontend-project-recheck.log、当前moduleManifest/页面和typed API。独占写面：`main/frontend-modern/tests/e2e/{frontend-runtime-visual,graph-runtime-pixel-gate,graphpage,homepage,information-topology-graph,real-backend-business-lines}.spec.ts` 及已派发的 `src/pages/`、`src/features/` 中受上述失败直接影响的消费者（先定位再改），明确排除 `TopologyDetail.tsx`。shell/kernel/navigation/manifest 由R0维护，R3只回传具体修复建议。保持topology现只读角色，不能恢复旧创建能力。其他用户在该未跟踪页面的改动保留。

输出：17条逐条当前合同/真实缺陷/环境归属及修复；Graph显示/场景、workflow草稿submit与dryrun、项目选择导航、首页语义heading、topology只读投影均有用户可见证据。验证：pnpm lint/build主线集中；受影响上述六spec先由R0单worker运行，再完整117 inventory校对。完成：适用用例通过，旧topology命令断言改为原权威只读行为及负向写限制见证，5skip有条件解释。`blocked_by`：数据库缺表/索引准备由R0、真实来源由R6；本地mock行为不等待live。

### R4 全局 envelope 与当前API合同

目标：请求已有envelope分支仍准确传播 trace/project metadata，保持原status/error/data与权限。输入：具体 `test_api_exception_envelope_unittest.py` 失败、`app/main.py` early return、`app/contracts/responses.py`。独占写面：`app/main.py`、必要原contracts响应模块与 `tests/integration/test_api_exception_envelope_unittest.py`、`test_api_envelope_gap_fixes_unittest.py`；全局路由污染fixture由R5修，不能在R4扩production whitelist。

输出：具体响应语义修复、already-envelope/普通响应/异常/流观察的当前见证；项目meta不能从非权威请求metadata取代真实scope。验证：上节R4命令，受影响production stream/composition测试由R0集中，避免R5同时改同一fixture。完成：准确metadata读回且身份/失败/stream不漂移。`blocked_by`：R5仅在其污染影响同进程测试时；实现不等待R1登录。

### R4U URL 解包与 SSRF

目标：单独定位3失败是mock条件或解码/redirect缺陷，维护public target与SSRF拒绝。独占写面：`app/services/ingest/url_unwrap.py`、`tests/unit/test_url_unwrap_unittest.py`。输入：原3nodeids和对应完整trace；现DNS、cache、GoogleNews batch guard。

输出：实际公共URL可解包、重复token cache、私有地址/重定向目标拒绝仍有效；测试mock DNS与requests取真实调用边界。不放松SSRF或恢复私网访问。验证：上节backend命令将测试路径换成 `tests/unit/test_url_unwrap_unittest.py`。完成：原3失败与同模块负向安全用例通过，缓存隔离不依赖用例顺序。`blocked_by`：无；不调用共享live provider，R6不得重复改此文件。

### R5 测试隔离、当前检查器与历史合同

目标：把78后端、71root及skip/error精确分派并修当前适用合同，保留冻结史。输入：完整日志/nodeids、当前实现/权威版本、冻结输入实际bytes/hash。首波只读分类。后续独占写面：明确分配的后端测试fixture/contract/debt/production/successor测试（排除R1/R4/R4U拥有文件）、root tests/formal_release和当前checkers、原检查器实现；不写 `app/main.py`、源产品能力、冻结artifact或历史候选。

规则：route污染用局部app或finally恢复原路由，生产拒绝不扩白名单；readonly fixture写/tmp；root/bytecode用R0环境修复；donor import扫描解析实际import结构，不匹配任意字符串；Redis/DB mock补其原消费者边界；当前API/schema/W03/W06见证按当前权威调整；NL410与lottery/AgentCore退休保持。版本与retained retrieval测试用显式当前/旧版本输入，不能重写旧快照。历史formal_release checker的必要能力保留，用隔离fixture恢复历史合同测试；若仅针对已停止阶段的实时checkout hash断言，记录 `retired_contract` 或环境前置并给当前替代，不造新release候选使之变绿。

输出：唯一nodeid→owner→类型→修复/保留路径；若未知实现缺陷，具名转产品owner、不放进历史豁免。验证：对应原nodeid用统一Docker runner执行；共享检查器涉及root71时由R0完整root tests一次收敛；历史bytes SHA保持原值。完成：所有条目覆盖、当前适用负向合同通过，历史状态可复核，不无差别xfail/ignore。`blocked_by`：R0环境；特定未知只阻断其nodeid，禁止笼统全局blocked。

### R6 来源审核→正文→索引→非空检索

目标：走通原来源item及审核条件、worker正文持久化、indexer、检索真实读回。输入：source-keyword-live-attempt2.log、raw-import证据、search-init-readback.json、原source item契约。独占写面：`app/services/source_library/relevance_review.py`、`item_resolver.py`、`item_plan.py`、相关原orchestrators、`services/ingest/search_and_ingest.py`、`services/indexer/application.py`、`services/search/indexes.py` 与各自原unit/integration测试；API公开契约跨包变化交R0，R4U URL模块不动。

先只读确认真实缺口：review阻断可能是合法材料不足，不能预设实现坏。实际执行使用原项目/资源/来源API、原registered handler/Celery；需要领域判断由工作流注册执行者产生，Codex不能手写accepted/relevance receipt。验证：原 `scripts/run_resource_source_lifecycle_smoke.py --base-url http://127.0.0.1:18004 --project-key readiness_repair --output /tmp/mrw-repair-20261004/source-lifecycle.json` 的测试材料仅证明该script声明的原场景；另通过正式来源采集读回真实正文id/provenance，再 `_init`/原indexer与search API读回至少一条lexical命中及适用vector/hybrid命中，检索命中的document必须等于项目内真实持久材料。原repo_runtime_smoke带实际item_key最终exit0。

完成：不降低relevance门槛、不绕review，候选/正文/索引/命中具同项目身份、无越scope，明确真实embedding/backend/fallback。配置未支持的vector backend单列条件，不能以lexical代替全部检索形态。`blocked_by`：R0专属schema/索引；真实可接受来源/凭据或review合同不足由对应原能力owner说明；只阻断该live链。

### R5-C skip、可选能力与边界核验（归R5同一owner）

目标：补适用未执行见证并准确限定平台可工作范围。输入：300backend/5frontend skip和未配置providers表。独占输出：回传主线的具名条件清单与精确选择命令；需要fixture改动交R5，test-image/provider env交R0，不另建探针框架。

逐一确认 PostgreSQL测试env/建库权限、Ruby显式运行条件、可选Azure/Google/SerpAPI/社媒凭据、SearXNG/YaCy/Scrapyd profile与project/spider部署。已有provider/script执行者保持；probe HTTP200不代替正文/持久结果。R0依明确用户所需能力运行原runner，缺配置可选能力保留不可用/未核验及owner。完成：所有skip/error/external未执行原因归属，必需能力执行，剩余条件不冒充PASS。`blocked_by`：具名服务/凭据，只限对应能力。

## 6. 整组退出条件与回传

主线按真实当前输入完成：R1合法身份与实际所需native运行形态可观察；R6来源至非空检索实际读回；R3当前用户行为适用浏览器合同；R2收集错误闭合；R4/R4U及R5当前产品/安全合同；所有旧失败、skip/error有唯一处置。实际服务未登录或材料不足时，必须给精确仍缺能力与条件，不宣称全平台工作就绪。

完整适用原suite失败不得被历史退休统计抹去。整组报告同时列baseline、此次passed、kept、retired_contract、failed、blocked/not_run，清楚说明scope变动；通过实现/测试不建立生产发布权限。必要检查完成且无新变化后停止扩测，不另建冻结/审批循环。修复记录仍写此文档及§7.5，可写工作树保持，只有真实交付要求才统一封存。

## 7. 实际首波派发与已有回传

主线已实际派发，以下为已发生路由，不将偏好模型名称当执行证据：

| 包 | 实际 Agent | 实际路线 | 当前状态 |
|---|---|---|---|
| R1 | repair_auth_native_assessment | GLM Flash / low | 只读诊断，先判断宿主/容器默认owner |
| R2 | repair_root_law_collection | GLM / high | `FULL_LOCAL_PASS`；counter 2PASS，六模块局部及正式新镜像均20PASS/1warning/0skip；六tests无改动 |
| R3 | repair_frontend_contracts | GLM / high | 已派实现；不跑共享build/Playwright；TopologyDetail暂不写 |
| R4 | repair_envelope_metadata | GLM / high | 已派实现，main.py全局响应唯一owner |
| R4U | repair_url_unwrap | GLM / high | `FULL_LOCAL_PASS`；仅3正向测试mock公共DNS，runtime不改；局部/正式镜像均12PASS/8subtests |
| R5 | repair_failure_inventory | GLM Flash / low | 只读逐ID归类，后续修改另定精确文件 |
| R6诊断 | repair_material_chain_assessment | GLM Flash / low | 只读材料链，输出 `/tmp/mrw-repair-r6-material-assessment.json` |
| R0 | 主线 | 当前主模型 | dev依赖测试镜像构建、共同环境与集成 |

R2证据 `/tmp/mrw-repair-r2.log`、`/tmp/mrw-repair-r2-six.log`；第一entrypoint错误保留，随后counter及六模块成功分别记独立尝试。当前kit读回已消解“必然需要旧API迁移”的假设；正式新镜像已构建exit0，日志 `/tmp/mrw-repair-test-image-build.log`；主线按宿主绝对路径及当前kit挂载复验六模块20PASS/1warning/0skip、exit0，日志 `/tmp/mrw-repair-r2-final.log`。R2标记 `FULL_LOCAL_PASS`，不等于整组通过。原审计3852/1392/95 PASS属于基线，本轮不另计新passed；仅按真实依赖充分见证记kept。

文档中列出的原脚本与关键测试/消费者路径已检查存在；repo_runtime_smoke 的base/require-base/project/source-item参数及resource_source_lifecycle_smoke的base/project/output参数已按源码argparse确认。Docker示例显式当前kit只读挂载与覆盖ENTRYPOINT；完整命令的环境前置仍由R0统一承担。

R4U真实修复归类为test isolation：容器真实DNS把示例域名解析为198.18 reserved网段，原SSRF guard正确拒绝；仅三个正向用例mock getaddrinfo为公共IP，不放松runtime规则。局部日志 `/tmp/mrw-repair-r4u.log`，主线新镜像正式复验 `/tmp/mrw-repair-r4u-final.log`，均12passed/8subtests、exit0；runtime源码未改。

## 8. 第二波推进（2026-10-04）

首波回传已收齐。R4E关闭真实HTTP JSON envelope读取与metadata缺口，并保留重复header、background、字符串chunk及SSE/NDJSON行为；新镜像18PASS/4subtests，日志 `/tmp/mrw-repair-r4e.log`。缺省服务版本改为canonical release owner；显式env保持原义。R5-A三文件路由隔离正反序组合31PASS，追加原auth失败节点33PASS/15subtests，日志 `/tmp/mrw-repair-r5a-original-seven.log`。R5-D将写fixture限制到临时副本、canonical字节保持，18PASS，日志 `/tmp/mrw-repair-r5d.log`。

R3完整117浏览器复验111PASS/1FAIL/5SKIP，日志 `/tmp/mrw-repair-20261004/frontend-full-e2e.log`；唯一graph标签切换重复读取属于实际cache identity缺陷，原owner继续最小产品修复，不降低断言。前端lint/build均exit0。R6 BM25沿既有project binding补ES term filter与原API参数接线，52PASS/7subtests，日志 `/tmp/r6-search/final-consumers.log`；vector部分尚未以此证明。

第二波已实际派R5-B观测fixture（GLM high）、R5-C当前contract/import/migration/retained version测试（GLM high）、R5-D临时fixture（复用GLM high）、R1宿主backend解释器与指定launchd恢复（复用Flash low）；R4E复用为R4O真实HTTP/SSE/deep health观测接线owner（GLM high）。R5-B独立fixture修复通过，但保留9项观测接线失败，交R4O产品owner，不伪造observer。R5原分类含退役功能误作产品缺陷及默认rebind建议，主线已要求逐项修正，不消费其52产品缺陷统计，也不执行rebind。

专属应用stack `mrw-repair-20261004` 已启动DB/ES/Redis/backend/worker，新项目readiness_repair与正式索引初始化均HTTP200；logs与.data显式任务专属挂载。测试另用 `mrw-repair-test-db-20261004`，与浏览器/原worker业务库分开；宿主8172保留。整组仍IN_PROGRESS，生产发布仍停止。

### 第二波集成读回更新

R1宿主依赖恢复完成：当前权威kit构建wheel并安装到repo `.venv311`，指定launchd后端8000健康200；CLI/token sink可用，已有static actor exchange200。8172/8790/4222未重启。真实browser OAuth会话仍未建立，不能由机器路径代替，身份与恢复记录 `/tmp/mrw-repair-r1-runtime-result.json`。

R4O产品HTTP/SSE终态、early auth、真实typed deep-health readers接回原observability owner，组合41PASS/4subtests；R5-B两旧fixture迁移后10PASS，并确认全局controller/bindings状态恢复。证据 `/tmp/mrw-repair-r4o.log`、`/tmp/mrw-repair-r5b-observation-final.log`。专属backend/worker已重启，18004健康与deep-health均200，当前DB/ES读回正常；本地没有controller的状态不冒充生产观测验证。

R5-C当前合同125PASS/1FAIL的剩余C3反向依赖已由R5-P0C修复：runtime引用校验保留，兼容实现liveness归migration builder；55PASS，`/tmp/mrw-repair-r5p0c-final.log`。retained HK真实v2历史材料仍缺失，不补造快照。R5-E继续隔离root历史fixture与当前checkout检查器；R5-N另收敛nightly checker的原失败节点，均不得改冻结身份。

R6-S显式vector scope与SQL fallback一致，94PASS/35subtests；R6-I ES身份与删除范围携project，冲突在effect前拒绝，6PASS及4项APIerror PASS。可选Qdrant数字point跨项目风险保留 `QDRANT_PROJECT_ID_MIGRATION_BLOCKED`，当前默认未配置该路径。专属PostgreSQL拓扑/DDL集成首组12PASS，缺外部framework只读挂载的剩余1项修正环境后PASS；Ruby原合同另以宿主runner 1PASS，均不当作整个suite已通过。

R3数据query key已剥离展示ID，focused复验转为3D重显示超时，原owner继续处理真实显示/cache复用关系，断言不降低。先前117组111PASS/1FAIL/5SKIP仅代表该次运行；后续产品变化使受影响节点待重验。

主线启动单runner后端完整收集与复验，专属test DB与应用DB分离，无20fail截断。新inventory为4249（基线4230），新增覆盖需要按实际nodeid解释；运行日志 `/tmp/mrw-repair-20261004/backend-full-inventory.log` 与 `backend-full.log`，未完成前不预报通过。真实材料非空索引/检索链由R6继续原入口验证，领域审核receipt不得手工替代。整组仍 `IN_PROGRESS`。

### 集成返工与运行阻塞

R3 focused已闭合：真实cache身份修复后，standalone fixture补正常kernel/topology读回边界，保留原读取次数与3D断言；graphpage整文件8PASS，lint/build exit0，`/tmp/mrw-repair-r3-followup.json`。R5-N current nightly checker原8项/2subtests通过，仅测试默认解释器改当前runner。

R5-E保留历史ABI与负例，11个formal_release测试改用隔离HEAD/历史消费者fixture，无退休豁免、无rebind。宿主当前wheel环境11组首轮381PASS/1FAIL/45subtests，唯一Stage2历史fixture闭包路径继续修；日志 `/tmp/mrw-repair-r5e-host-final.log`。真实CI compose必需 `CODEX_OAUTH_COOKIE_SECURE` 已补workflow为true；StrictYamlParser注释strip后空行过滤已修，保留混合sequence拒绝，新回归由R5-E补。

只读R4O集成review证实observer抛错会覆盖JSON/原SSE异常与取消/deep-health结果，转原owner补失败隔离与回归。此前41PASS/10PASS未覆盖此组合，不能宣称该项已闭合。

Docker执行出现实测阻塞：backend全量停11%、root collector无输出、container top/exec超时、18004两health curl超时。已终止主线两个挂起Docker客户端，未取得pytest终态，不计FAIL或PASS；容器/应用恢复需Docker恢复。未重启全局Docker或用户服务，已请求用户允许重启后恢复任务stack。原frontend本轮92PASS/10FAIL/12NOT_RUN/3SKIP、exit1，`frontend-full-final.log`；运行期间backend失联，10项逐trace归类中，不能统一归产品缺陷或默默变PASS。宿主root收集1479项无collection error；Docker4249项收集通过只证明收集，不证明执行通过。具名环境记录 `/tmp/mrw-repair-20261004/docker-execution-blocker.json`。

### 宿主验证与最后执行边界

R4O observer失败隔离已通过宿主27PASS/4subtests，另core/exception17PASS；日志 `/tmp/mrw-repair-r4o-observer-isolation-host-lazyoff.log`。R5-E历史ABI最后一项由完整candidate前置闭包+registry真实successor bytes恢复到tmp解决，34PASS/34subtests，不改原字节/hash；`/tmp/mrw-repair-r5e-host-focused.log`。原11组381/1结果保留，不与focused重叠加总。

前端全量10FAIL精确分类为6项真实backend依赖+4项缺kernel/topology mock，无确认产品缺陷；分类 `/tmp/mrw-repair-r3-final-attempt-classification.json`。4个线索链fixture已补且完全fail-closed mock-only runner4PASS，`frontend-clue-fixture-final.log`；未把12NOT_RUN或3SKIP计通过。

宿主root全量首轮因 `test_generate_c7_exact_byte_rebind` 导入Scrapy provider触发Docker lazy-start而停顿，主线精确终止自己的pytest与该子进程，原runner未完成，保留attempt，不计PASS。关闭测试环境 `CRAWLER_LAZY_START_SCRAPYD=0` 后完整1481项第二轮正在运行。实际产品执行边界缺陷另分R4S：复用已有纯URL resolver构造provider，把原ensure-ready保留到真实dispatch/合法poll时，不恢复旧core、不禁用crawler能力。source变动后的验证必须另记受影响原runner。

Docker重启许可仍pending，未擅自重启其他Docker服务。材料链原脚本两次均blocked_by_environment，不产生review/receipt；恢复后原raw import→indexer→BM25非空检索的必要单chunk embedding batch属于用户当前本地全量核查授权，由主线在已明确预算内执行，不再另建provider审批。

### 完整宿主结果与第三波精确收敛

Root完整1481项1478PASS/3FAIL/91subtests，日志 `root-host-full-attempt2.log`。三项原失败均在后续集中301PASS组通过：dev compose按当前内部服务无host端口合同验证已有暴露仍loopback；health snapshot补既有非权威view标记及真实witness；P0 failure registry仅顺序不同，按kit completeness既有无序成员语义比较排序列表，重复/缺项仍失败，registry原字节不改。该组额外crawler新回归暴露纯resolver参数名错误，主线修为真实签名，四个crawler consumers27PASS/6subtests；`crawler-lazy-boundary-final.log`。Scrapy构造不再启动服务，原dispatch/poll能力与failclosed保持；app实际导入、原registry含scrapy且ensure调用0的探针PASS，`provider-import-no-effect.log`。

后端完整host nonexternal4257项4112PASS/33FAIL/112SKIP/173subtests，日志 `backend-host-full.log`；不替代Docker专属PG全量。33项精确分包：R5-L三个文件5个失败，18PASS/1个专属PG未配置SKIP；R0 rollback原入口8个失败是PYTHONPATH下namespace main被backend main.py遮蔽，脚本复用脚本目录内同一production_contract正式模块修复；另project-key-policy1失败将无关production metrics port注入fixture而保持权限失败闭合，原两个文件48PASS；R5-H余下19项归12个successor历史/当前生成器文件。R5-H先真实kernel ABI3PASS再展开共因迁移，不用历史退休豁免，不生成新冻结身份。GLM既有三包遇429后保留产物，主线接回小修；R5-H复用既有主模型继承owner，R5-L另实际分派可用继承worker，未把它们声称为GLM/Astra执行。

贡献原CLI使用宿主当前权威wheel：`python -m functorial_kit contributions check --catalog contributions/project_catalog.py --root ...` exit0、clean true、无changed_paths，`contributions-wheel-check.json`；七项gate集中通过。`scripts/dev.py check`当前仍因强制editable-origin拒绝R1为后台运行安装的同源wheel；root旧editable venv import也超时。保留为开发入口具名条件，不把原CLI通过冒充该wrapper通过，不恢复使宿主服务卡住的安装方式。

整组仍IN_PROGRESS；Docker重启授权pending。开发节奏账本仅复用现成日志，未新增作者表/审批：全量root一次有效结束、backend host一次有效结束，另Docker与root前尝试受实际运行阻塞中断；各子包focused计数不相加冒充整组。当前工具不提供可靠分Agent token/call成本，相关成本缺失，不记0也不报提速。

### 第三波宿主修复收齐

R5-H原12模块最终78PASS/2warnings、exit0，日志 `/tmp/mrw-repair-r5h-final.log`；新增1个独立历史基线字节测试，部分nodeid随历史输入scope明确而改名。历史输入按claimed SHA从真实Git版本或既存snapshot恢复到tmp，当前native27个cell、历史30个cell及历史60项movement分别验证；两个semantic movement脚本既有docstring明确是冻结回顾用途，当前退休checkout拒绝旧输入属于scope条件，不新建current generator，不恢复C6，不改冻结字节。P5复制脚本外部进程尝试中止状态保留；最终对应通过的是原CLI main handler，不能冒充该外部进程通过。其余既有外部CLI正反例仍真实执行。

后端host全量原33FAIL已分别由R5-L（5项）、rollback/project-policy（9项）、R5-H（19项）在受影响原runner闭合；root原3FAIL亦已闭合。这里是原全量结果加后续局部修复证据，不把重叠focused计数相加，也不将旧full exit1改成新full PASS。主线最终 `git diff --check` exit0。产品注册与七项gate已通过的范围沿用对应实际输入证据，文档维护不触发重复整套运行。

剩余执行前沿为Docker运行恢复后的专属PG full、浏览器117项复验与来源/正文/索引/非空检索读回；Docker重启授权仍pending，不能以“继续”代替对中断其他Docker服务的明确同意。真实browser OAuth仍需用户会话；同源wheel的原contribution CLI成功，但editable-only开发wrapper仍拒绝该安装方式。可选Qdrant身份迁移、HK v2真实历史材料缺失继续保留具名条件。整组状态 `IN_PROGRESS · HOST_REMEDIATION_CLOSED · LIVE_RECHECK_PENDING`，不建立上线或发布完成结论。


### Docker恢复后的整组本地收敛（2026-10-04）

当前状态 `LOCAL_REPAIR_COMPLETE_READINESS_CONDITIONAL`。用户“可以”授权Docker Desktop重启，已完成并恢复本轮专属backend/worker/DB/Redis/ES栈。以下覆盖上方重启许可pending、wrapper未闭合及全量运行中的过程状态。恢复时旧 `/tmp/mrw-repair-20261004` 测试日志、runner和overlay已缺失，历史回传仅保留历史摘要归属，未重构日志。新证据全部持久落在 `.data/readiness-repair/20261004-recovery/`；机器可读入口为 `recovery-state.json`。

| 验证面 | 本轮实际结果 | 原始证据 |
| --- | --- | --- |
| root完整 | 1481PASS、91subtests、exit0 | `root-full-final.log` |
| 前端完整117项 | 112PASS/5SKIP、exit0；4项退休AgentCore合同、1项真实浏览器OAuth | `frontend-full-attempt2.log` |
| 最后修改后真实前端消费者 | 7PASS、exit0 | `frontend-live-final.log` |
| 后端完整 | 4258PASS/4FAIL/2SKIP、173subtests、exit1，原退出码保持 | `backend-full-final.log` |
| 后端最后inventory | 4265项收集成功；全量后新增1个vector编译见证 | `backend-collect-final.log` |
| 后端4个失败节点复验 | W03有效fixture与indexer组合12PASS；P0D原独立runner5PASS，socket-only、残留清理通过 | `w03-preflight-consumers.log`、`capacity-validation.json`、`capacity-junit.xml` |
| 最后检索消费者 | 39PASS、exit0 | `search-final-consumers.log` |
| 七项gate与贡献入口 | 280PASS；check clean=true、issues=[]、changed_paths=[]，均exit0 | `architecture-gates-final.log`、`dev-entry-check-final.json` |
| 可选门禁条件 | 宿主7PASS/1SKIP；Ruby原parser补验通过；真实provider矩阵未启用 | `optional-gates-final.log` |

P0D要求只含capacity schema的专属DB，topology测试要求预置topology schema，不能用同一DB作全量运行条件。原独立PostgreSQL runner创建并清理临时非superuser DB/role，5项通过；没有删除其他测试schema、放宽白名单或skip断言。全量原4FAIL加正确fixture/环境复验构成本轮覆盖，不改记整套exit0，不将重叠focused计数相加。worker PG9PASS、topology/retrieval12PASS、C9历史字节5PASS见同目录各focused日志。

本轮真实材料链另修四处产品问题：indexer在provider/DB删除/ES副作用前完成全payload校验；raw import新文档Source只由terminal writer创建，保留旧重复Source；失败任务异常经原process接口投影成可序列化message/type而保持FAILURE；pgvector L2表达式使用显式public operator，保留tenant-only search_path、3072维bind和项目过滤。W03 fixture补合法URI/created_at；C9冻结测试读真实历史字节按原hash验证，未rebind；topology测试按UUID项目隔离并清理自己的写入。

专属18004原入口实际完成本地合成材料raw import→注册Celery worker→正文/URI持久读回→index成功1文档→BM25自然refresh后命中doc2→pgvector命中同文档及readiness_repair项目证据。向量请求HTTP200；原探针误断言result顶层project_key导致exit1，保存响应按evidence_hits.provenance/global_vector_object及meta项目归属复核通过，见 `vector-response-readback-verification.json`，无额外provider请求。修复后完整hybrid未再次live执行，不把旧only-lexical结果记为完整hybrid成功。lifecycle脚本5步和worker SUCCESS只证明其注册运行，example.com RSS没有正文采集证据。

外部调用实际含2次document embedding batch（第一次后置拒绝前已发生浪费）、至少2次query embedding调用；内部HTTP重试次数未知，不宣称计划中的单batch预算准确实现。vector owner首次失败的局部断言日志被覆写，final15PASS日志仍在，保留此证据偏差。

日常8000与8172入口健康；宿主ES已恢复且8000deep health正常。最新四项产品修改加载于专属18004，宿主8000尚未重启。宿主未观察到项目Celery worker；浏览器OAuth真实会话未本轮验证，token sink认证不能替代用户身份。可选Qdrant未配置、旧数字point迁移仍 `QDRANT_PROJECT_ID_MIGRATION_BLOCKED`；retained HK v2真实历史材料缺失。上述条件具名保留，整组本地修复完成不建立日常全链可工作或生产上线结论。生产Stage4–6保持STOPPED/RELEASE_DEFERRED，未commit、rebind或发布；任务栈和数据保留用于读回。

开发成本沿实际日志记录：本轮root、frontend与backend各有一次完整终态，失败尝试保留；最终consumer/gate按影响复验，不重复第三次后端全量。子包结果不作为整组通过计数；工具未提供可靠agent调用/token成本，明确缺失，不记零、不报提速。


### 日常入口整链闭合与宿主 OAuth 同步（2026-10-04）

当前本地状态 `LOCAL_DAILY_FULL_CHAIN_VERIFIED`，覆盖上一段日常8000未重载、worker未观察及浏览器入口待验证的条件。机器入口为 `.data/readiness-repair/20261004-daily-chain/daily-chain-state.json`。本机单用户入口以宿主 `~/.codex/auth.json` 为OAuth权威，WebUI的 `~/.codex-mrw-agent/auth.json` 符号链接共享该文件；不复制token，不要求重复浏览器登录。实际浏览器 `authenticated=false / token_sink_authenticated=true` 时，明确localhost HTTP入口嵌入loopback8172，iframe root、JWT与native status200均实际读回且无page error，见 `local-host-browser-chain.json`。远端域名sink-only不获得此入口；MRW匿名exchange与代理bootstrap401、directloopbackbootstrap200见 `auth-boundary-live.json`。

backend8000、frontend5173、正式Celery worker与Elasticsearch9200已由宿主launchd持久运行；重载前queue0/unacked0，backend与worker现已加载最后索引/材料修复。`local-deploy.sh status`能正确识别launchd worker，原非macOS及无plist路径保留。WebUI8172绑定127.0.0.1；运行源码已由结构整理包迁入主仓 `main/ops/codex-webui`，依赖固定 Codex0.160.0，LaunchAgent、SQLite与宿主OAuth读回通过。最新生命周期脚本实际重启及浏览器iframe/JWT/status/WebSocket、新旧回合marker读回均通过，见 `.data/structure-cleanup/20261004/live-browser-readback.json` 和 `webui-lifecycle-live-final-attempt1.log`。容器模式的HOST配置保留；本次验收为宿主模式。

日常5173→8000→正式host worker完成独立项目 `readiness_daily_20261004` 的合成policy导入、doc1正文/URI持久读回、索引1、BM25命中及pgvector3072维命中；hybrid实际200且报告lexical/pgvector，融合后的赢家branch不替代独立vector命中证据。首次索引因ES旧read_only_allow_delete失败；只解除该索引锁，磁盘约92%、阈值原样保留，前后设置见 `elasticsearch-write-lock-recovery.json`。ESbulk现在在已有try内，失败记原fail_job再抛出；已提交PG不能由rollback撤销，未宣称跨存储原子。indexer/W03原回归13PASS。

真实公开URL `https://www.rfc-editor.org/rfc/rfc9110.txt` 首次HTTP200、CelerySUCCESS却只存69chars，原task与正文失败见 `http-source-task.json`、`http-source-before-repair.json`。修复实际Content-Type到现有ResourceRef/FetchedResource/PreparedMaterial及frontdoor投影：原fetch一次，保留resource身份、响应字节digest与plain/markdown格式；typed正文保持全文，提取chunk上限不截存储正文。混合输入保留给定正文，原URI保持文档身份，overwrite清除旧格式见证；HTML、无header旧mock及质量gates继续原路径。原URL通过正式API/worker覆盖同doc2，task `d18a9e98-3c74-4b75-a68c-93a5a406de20` 成功，正文502906chars、resource/text/plain、main ratio1.0，见 `http-source-repair-document.json`。材料focused35PASS/2subtests、frontdoor13PASS/3subtests，HTML和非法UTF8回归已覆盖。

Native Codex经正式WebUI创建thread `01a1060e-968e-7502-bfbb-cbb615369e3b`，分页turn实际completed并读回 `MRW_NATIVE_CHAIN_OK`，见 `native-turn-history.json`；未再发provider echo。认证消费者89PASS/19subtests；前端focused5PASS、日常业务7PASS、当前inventory119，未宣称119新全量执行。最后材料修复后的Docker七gate280PASS、贡献wrapper absolute-source mount检查clean=true/issues=[]/changed_paths=[]，均exit0；旧全量结果按上段原归属保留，不将focused重叠相加或把旧exit1改绿。

执行偏差保留：indexer实际日志原落main/backend/.data，字节复制到根证据；材料修复首次命令漏src的collection错误与后续attempt日志均保留。重载后首次立即replay遭proxy500、未提交任务，健康读回后重试通过；首次Docker wrapper挂/opt导致预期absolute kit路径缺失，原exit1日志保留，正确绝对挂载attempt2 exit0。worker恢复时既有16项队列实际8SUCCESS/8FAILURE，未对旧项目表缺失任务制造领域成功。调用/token/成本及准确首次整组验收耗时缺失，不报告提速。

本地已验证链可供日常工作。当前容量风险、可选Qdrant旧point迁移与HK真实历史材料保留具名边界；远端生产发布仍延后。

结构整理后的运行刷新：后端与正式worker在queue0/unacked0时重载；前端5173提交材料、独立worker完成task `7afe6c39-5732-448e-ad67-4530481b0443`，doc3正文与URI两次持久读回一致，doc1原材料保留。新证据见 `.data/structure-cleanup/20261004/live-user-chain-result.json`；之前BM25/pgvector/hybrid证据保持原执行归属，本轮没有再次调用provider。整组结构验收统一见[结构整理方案 §8](MRW结构整理方案与分发包.md)。
