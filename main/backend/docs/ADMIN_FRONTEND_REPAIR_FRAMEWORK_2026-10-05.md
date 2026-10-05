# 后台交互与职责修复框架及分发合同

日期：2026-10-05。状态：后台修复已实施并完成聚焦验证；真实 URL 提取闭环通过，其他外部效果未执行。全局可视化依赖检查仍有具名未通过项，见第 9 节。

## 1. 范围与依据

本次以六项具体问题为入口，覆盖后台信息架构和主要页面的呈现：资源操作没有任务反馈、管理导航与页面职责重叠、任务详情字段堆叠、资源表格溢出、一键采纳和业务说明独立页。总方向是适度现代化、安静操作型视觉、简洁语言和有引导的单层工作面。默认呈现当前目标、主要动作、真实结果；高级参数和原始诊断渐进披露，能力仍有清晰可达入口。各主要后台页都应检查小窗套小窗和字段堆叠，不能以隐藏全部内容代替职责整理。按根 AGENTS.md、19 号流程缩减规则及 06 号进度顶部执行：旧生产阶段已停止，本次直接修复并做相关验证，不重新启动冻结或发布流程。

调查采用 frontend-agent-workbench 与 functorial-programming-foundations。以下行号以调查时源码为准；代码事实、建议和待 live 验证分别标明。根目录无 `.cursor/rules`，已读取 `main/backend/docs/RESOURCE_POOL_EXTRACTION_API.md`，并核对 `functorial-kit.json`、相关 registries/sketches。资源池 URL、站点入口、source-library item 是不同对象，URL 提取成功不等于 source item 已生成。

## 2. 六项问题的事实与修复目标

| 问题 | 已确认代码事实 | 修复目标与验收观察 |
|---|---|---|
| URL 提取无运行反馈 | `main/frontend-modern/src/pages/ResourcePage.tsx:1044` 调用 `extractResourcePoolFromDocuments(true)`；`:640` 的 runAction 仅把 task_id 拼成文字，`:681` 提交后立即刷新资源查询；`main/backend/app/api/resource_pool.py:656` 调用 Celery delay，返回真实 queued 回执 | 立即出现明确提交回执和任务链接；同一 task_id 可打开详情；终态后刷新 URL 及关联消费者；失败保留原因和可执行操作 |
| 导航混杂、页面重复 | `moduleManifest.ts:80` 的 ADMIN_NAV_SECTIONS 使用两个大组加 secondary；`moduleContributionRule.ts:50` 等把 process/processing、resource/extract、ops/backend、settings/llm 分别指向同一页面；多个 variant 只改标题 | 导航按对象职责呈现；同一对象只保留一个主要入口，兼容路由仍解析；页面内部限定本页职责，必要子视图用 tabs，而非全文重复 |
| 任务详情原始字段堆叠 | `ProcessPage.tsx:706` 弹层默认显示质量字段、worker、display_meta、args、kwargs、progress、result、traceback、logs 的多块 JSON | 单层详情区：任务名称与状态、当前阶段/实测进度、时间、结果摘要、下一操作；技术详情默认收起，保留原始数据检查能力 |
| URL/Site Entries 越界 | `index.css:3422` 的 `.panel.two-col` 为 `1fr 1fr`，`:3772` 才在 960px 以下拆栏；`ResourcePage.tsx:1713` 的 Site Entries 有 9 列，`:1738` 有 6 个行内按钮，table-wrap 横滚本身不保证 grid item 收缩 | 默认单表工作面，通过分栏视图 tabs 或顺序全宽区域切换；容器 min-width:0，表内有界横向滚动，长 URL 换行；390/768/1440 宽无页面级横溢 |
| 采纳操作繁琐 | `ResourcePage.tsx:907` 已有 patchSiteEntryLifecycle，显式 project/scope/site_url/lifecycle_state；`:929` 采集另外检查 review guard | 行内一键采纳；当前页批量逐项调用同一 review API；部分失败可见，成功项真实读回；不自动执行采集，不将 enabled 直接等同 accepted |
| 每页业务说明重复 | `AdminLayerShell.tsx` 全局嵌入 BusinessChainGuide；`BusinessChainGuide.tsx:19` 默认折叠但仍占每页区域；现有 business-chain-guide.spec.ts 明确断言每页内嵌 | 通过现有 moduleManifest/contribution 入口加入 `/admin/guide` 独立页；管理页只保留一个说明导航入口；复用 businessChainGuideData 唯一内容源 |

### 2.1 任务事实与持久化缺口

`main/backend/app/services/tasks.py:611`、`:635`、`:659` 的文档提取、任务捕获、分批站点发现没有调用既有 job_logger。`main/backend/app/api/process.py:569` 的列表由 Celery inspect active/scheduled/reserved 和 `:683` 的 DB running fallback 组成。任务从 broker 接收到 worker reserved 前存在观察空窗；短任务完成后会从 inspect 消失。`:817` 的 history 只读项目 EtlJobRun，`:867` 未提供前端可消费的 task_id/task_name/source 字段。`:1218` 详情可读 AsyncResult；前端 `ProcessPage.tsx:158` 已支持 task_id 深链，不需要重造路由机制。

`process.py:569-682` 的 Celery 列表循环未按 project_key 过滤；DB fallback 才 bind_project。项目作用域必须根据真实 kwargs/runtime metadata 判断；不得把归属未知的任务直接归入当前项目。修复需保留 task_id 与 DB job identity 的明确关联，避免同一任务同时作为 Celery 和 db-job 两行重复出现。

本轮优先复用 `app/services/job_logger.py` 的 start_job/complete_job/fail_job 及 task_readback_metadata，在真实 worker 开始、成功、失败时写 EtlJobRun，补齐原 process 投影。提交到 worker 开始的等待窗口由真实 API 回执呈现。API 提前创建 queued 行、传 `_job_id` 或重写 dispatch 不是已选方案；只有现有 worker 记录与回执仍无法满足本次验收时，由主线依据证据决定有界补充。

两项调查推断经主线复核后排除：`api/client.ts` interceptor 已为 `/api/` 注入 project_key 与 X-Project-Key，因此 hook 未显式传参不能作为当前项目缺失证据；`job_logger.complete_job` 将结果合入 params，并不存在通用 params.result 结构，不能改成只读 params.result/progress 而丢失数据。原始 payload 保留并在 UI 折叠。状态名可以做有界展示映射，但不为视觉统一改写 Celery/EtlJobRun 的权威状态合同。

资源分页还有一项相关状态缺口：`src/lib/api/domains/resource-source.ts:212` 把列表压成数组，未保留 pagination；资源页下一页没有终页判断。API domain facade 是共享写面，由主线决定兼容地补分页数据，Resource owner消费该结果。不得仅凭当前页未满或数组为空宣称总页数已知。

### 2.2 相似动作审计面

| 消费者 | 已定位入口 | 接入边界 |
|---|---|---|
| ResourcePage | runAction:640；URL 提取:1044；发现入口:1047；source-library run 及 accepted collect | 所有返回真实 Celery task_id 的动作统一 track；同步 review/创建/绑定保持同步结果 |
| OpsPage | runAction:1022；reExtract/topicExtract/syncAggregator 等:2319 起 | 已读 task_id 但无详情链接/终态刷新；接入相同提交接口；治理 preview 保持 preview 语义 |
| IngestPage | `useIngestActions` 消费链；IngestPage:563、任务 ID 读取:229 | 清点每个异步 API response；已有业务深链保留，补缺失提交回执与终态消费者刷新 |
| RawDataPage | importMutation:54，onSuccess:55 | 原始导入 async=true 回执接入；同步结果不能显示“任务已提交” |
| CrawlerManagePage | deployMutation:166、rollbackMutation:187，deployRuns:131 | 返回 Celery task_id 才接通用反馈；crawler deploy-run/Scrapyd job_id 继续原身份与读回；部署运行终态有界轮询 |
| Projects/Settings/Successor | 原 mutation/read-only 查询 | 检查 pending/error/success、权限和跳转完整性；同步配置保存不创建虚构后台任务 |

此表是审计清单，不代表每项均存在相同后端缺陷。各实现 owner 必须报告动作数量、实际修复数量和未适用原因。worker/持久化验证由集成 owner 统一执行。

## 3. 对象、权限与展示关系

| 对象 | 身份与权威 | 允许的前端投影 |
|---|---|---|
| 项目上下文 | project_key，由现有 kernel/runtime/API 绑定 | 页面选择、query key、深链上下文；切换项目清理旧回执 |
| 操作请求与提交回执 | 原 API response 的 task_id/trace_id/async | “已提交”、任务链接；不能据此断言 worker 已执行或数据已产生 |
| 运行记录 | Celery runtime、既有 EtlJobRun/job_logger；保存 task_id 关联 | 状态名、实测阶段/数量、时间、失败说明；原字段仍可检查 |
| URL 资源 | resource_pool.extract 与持久化 URL 表，scope 明确 | URL 列表、提取结果数量；不自动解释为可采集来源 |
| Site Entry 审核 | resource_pool lifecycle/review API，project/scope/site_url | accepted/rejected/needs_review/disabled；只渲染服务器读回的 review_closure/guard |
| 采集效果 | 独立 source_library run/operator 与其权限 | 采纳成功后显示可采集操作；采纳本身不触发采集 |
| 页面与导航 | moduleManifest + moduleContributionRule | 分组、标签、兼容路由、页面视图；不新增业务状态 |

语义组织是一个带项目与 scope 上下文的对象族：请求进入原执行者，执行产生运行记录与资源变化，查询将它们投影到页面。任务摘要和导航是只读投影；review 是有权限约束的写入；collect 是另一项 effect。UI 的复合应保持原有顺序，即提交后观察、观察终态后读回资源。声明保持的是这些身份、顺序和权限，不声称所有操作可交换。

## 4. 页面职责与导航提案

| 主要页面 | 主要工作 | 次要内容及兼容入口 |
|---|---|---|
| 运行记录 `/admin/process` | 当前项目任务、历史、筛选、详情、取消 | `/admin/process/processing` 保留兼容，指向同一任务面内相应筛选；不重复一个完整页面 |
| 资料与质量 `/admin/ops` | 文档列表、筛选、质量、抽取/治理操作、项目检索 | 系统运行、技术诊断、agent session 运行细节转到系统运行职责 |
| 来源与资源 `/admin/resources` | URL 池、站点入口审核、source-library 项目来源 | URL 提取/发现放相关视图工具栏；`/admin/resources/extract` 保留兼容提取视图；导入/高级配置按需展开 |
| 采集器 `/admin/crawlers` | crawler 项目导入、版本部署、回滚与部署运行 | 不标为所有“来源与采集”的唯一入口，避免掩盖资源库 |
| 项目 `/admin/projects` | 项目列表、切换、创建与已有生命周期操作 | template 设置通过明确链接到相应设置职责，避免标签承诺没有的对象 |
| 连接设置 `/admin/settings` | 平台连接/环境配置 | LLM 模板不在默认视图重复铺开 |
| 模型与模板 `/admin/settings/llm` | 模型配置与项目 LLM 模板 | 复用 SettingsPage，但通过 variant 真正限制内容 |
| 系统运行 `/admin/backend` | 健康、队列、worker、agent session、技术诊断 | 资料 CRUD/质量操作留在 ops；Successor 是明确子入口 |
| Successor `/admin/successor-runtime` | 既有只读运行观察 | 保留专属语义与现有 query/API，不转换为普通 Celery 任务 |
| 业务说明 `/admin/guide` | 完整业务链条图与解释 | 复用唯一 businessChainGuideData；不出现在每页正文底部 |

导航采用 3 至 4 个明确职责组，建议“项目数据”（资料、来源资源、采集器）、“运行观察”（运行记录、系统运行、Successor）、“配置”（项目、连接、模型模板）及说明入口。每组常用页面完整可见，不再使用“其他”隐藏职责。模块身份/路由仍由原 manifest 统一提供；最终标签和顺序由主线集中确认。保留重复 module 身份与 deep link 兼容，variant 真正呈现对应职责；兼容路由不等于必须在主导航重复列出。

## 5. 最小组件与视觉策略

主线已实现共享 hook 和 notice 并报告共享文件 ESLint 通过；各包直接复用如下接口，最终集成验收仍待完成：

```ts
useTaskSubmission({
  projectKey,
  invalidateOnSettled: readonly QueryKey[],
})
// returns { receipt, taskDetail, readbackError, isReading,
//           track(result: unknown, action: string): boolean,
//           refresh(): Promise<void> }
// receipt = { taskId, traceId?, action, projectKey }

<TaskSubmissionNotice submission={submission} />
```

track 仅接受真实 task_id 且 async !== false 的回执，提交后 invalidate process.all()；使用已有 getProcessTaskDetail 与 project-scoped query key 轮询。终态刷新传入消费者及 process.all()。页面 owner 调用 track(result, localizedActionLabel)，在相关工具栏旁呈现 notice。hook 不承担提交 API、不新增 localStorage 任务表、不将回执写成领域事实。共享组件自有 taskSubmission i18n namespace 和 scoped CSS。

ProcessPage 首层展示真实任务标题、语义状态、阶段、开始/结束时间、结果数量与失败摘要；只对存在可解释分母的 completed/total 计算百分比。只有 STARTED 没有进度时显示运行中活动指示与时间，不生成虚假百分比/ETA；读回失败显示状态暂不可读取，不改成任务失败。prefers-reduced-motion 下移除活动动画。技术详情一次展开，内部按概要/参数/日志组织，不弹第二层窗口。

资源页采用紧凑工具栏、tabs、单一当前数据表与行内操作。Site Entry 默认保留来源/类型/审核/操作等扫描列，执行计划、证据绑定、guard 细节移入一层行展开。review 操作每行 pending，批量显示成功/失败数量并允许只重试失败项；范围固定在点击时当前页的 eligible 条目，不跨分页或跨项目扩展。

复用 lucide-react、现有按钮/table-wrap/status-line/查询模式、admin tokens。每个页面拥有 scoped CSS；全局 index.css 和 i18n catalog 由主线维护。页面区块使用 full-width/unframed sections、分隔线和留白，不增营销 hero、浮动大卡或卡套卡。需要引导时用短标题、动作状态和下一步操作，不堆砌技术说明。按钮具备 pending/disabled/error/success，查询具备 loading/empty/error；长 URL、任务名和错误文字可换行。

## 6. 可并行实施包

所有包 cwd 为 `/Users/wangyiliang/market-research-workflow`。实现作者使用已分配模型，不再 spawn；保留其他作者修改。下面只列独占写面，越界必须交主线整合；ResourcePage 的反馈、布局、review 与批量逻辑必须归同一 owner。新增专属文件按所属包命名，禁止多个包各造共享任务解析器。

### A. 后端任务记录与项目读回

- 目标：URL 提取、任务捕获、站点发现具有真实 worker 运行/终态持久化；process 列表、历史和详情正确关联当前项目任务。
- 权威输入：job_logger、task_readback_metadata、现有 TaskInfo/EtlJobRun 与 process 投影；保留 resource_pool API envelope。
- 输出/独占写面：`main/backend/app/services/tasks.py`、`main/backend/app/api/process.py`，必要时 `app/services/job_logger.py` 的最小复用修复；相关 `tests/core_business/test_resource_pool_core_contract.py`、`test_process_consistency_core_contract.py`、`test_process_runtime_readback_core_contract.py`、`tests/unit/test_collect_runtime_process_fallback_unittest.py`。`api/resource_pool.py` 仅经主线确认确有 API 缺口时纳入本包。
- 完成条件：真实 task_id 与 job 关联；worker 成功/失败均落原记录器；无跨项目混入；快速完成仍能从历史/详情回读；保留具体资源结果。不要为 queued 观察空窗新增第二运行系统。
- 依赖：无前端实现依赖；真实终态集成验收依赖 A+B+C。
- 验证：后端 focused 命令见第 7 节；新增测试覆盖两个项目、完成后 inspect 为空、失败持久化、同一任务去重。
- 共享测试资源：宿主 pytest fixture DB/cache，真实 Docker broker/worker/DB。live 验证由主线单独占用。

### B. 资源页完整交互

- 目标：修复提取反馈、当前视图宽表、一键/当前页批量采纳、extract variant 的职责收敛。
- 权威输入：ResourcePage 原 API、patchSiteEntryLifecycle、review guard、共享 useTaskSubmission 契约。
- 输出/独占写面：`main/frontend-modern/src/pages/ResourcePage.tsx`、`ResourcePage.stories.tsx`、新 `resource-page-management.css`、新 `tests/e2e/admin-resource-repair.spec.ts`。
- 完成条件：所有本页 async 回执可打开运行详情；终态资源刷新；review 保留原 project/scope/身份，不自动 collect；部分失败读回；三个尺寸无页面横溢，技术详情默认收起。
- 依赖：共享 hook 接口已固定，可并行布局/review；最终接入依赖主线共享实现，持久化验收依赖 A。
- 验证：`pnpm --dir main/frontend-modern check:resource-page-i18n-slice`；专属 E2E 由主线按第 7 节执行。
- 共享测试资源：Playwright 端口/report目录与前端 build 产物；本包不得自己并行占用默认 4173。

### C. 任务页与详情

- 目标：现代、可扫描的任务详情，真实状态/进度、深链、日志及历史一致。
- 权威输入：现有 ProcessTaskDetail/ProcessTaskItem/ProcessHistoryResponse、useProcessData、task_id 深链；A 的兼容投影。
- 输出/独占写面：`main/frontend-modern/src/pages/ProcessPage.tsx`、`process-page-management.css`、`ProcessPage.stories.tsx`、`src/hooks/useProcessData.ts`、新 `tests/e2e/admin-process-repair.spec.ts`。
- 完成条件：无默认 JSON 墙和多层弹层；STARTED 未知进度无假比例；失败、取消、空/读回错误完整；深链打开快速已完成任务；未知任务归属不伪归类；reduced-motion 生效。
- 依赖：可并行前端实现；最终真实历史验收依赖 A；不得自行编辑共享 types/api/catalog。
- 验证：`pnpm --dir main/frontend-modern check:process-page-i18n-slice`；专属 E2E 统一运行。
- 共享测试资源：同 B。

### D. 资料治理与系统运行职责

- 目标：按 ops/backend variant 收紧默认内容，接入所有真实 Celery 异步回执，保留治理 preview/执行和 agent session 权限。
- 权威输入：OpsPage 原 APIs、hasAdminGovernanceEvidence、现有运行观察与 ProjectRetrievalPanel；共享 hook。
- 输出/独占写面：`main/frontend-modern/src/pages/OpsPage.tsx`、相关既有 Ops stories（如存在）、新 `ops-page-management.css`、新 `tests/e2e/admin-ops-repair.spec.ts`。不编辑 ProjectRetrievalPanel。
- 完成条件：文档质量操作只在资料职责默认呈现，系统运行细节归 backend；运行摘要可跨页链接；async 操作有回执/终态刷新；不可用/失败/preview 不显示已执行。
- 依赖：主线页面职责与共享 hook；A 不阻塞纯布局实现。
- 验证：`pnpm --dir main/frontend-modern check:ops-page-i18n-slice`；E2E 由主线统一。
- 共享测试资源：同 B；不自动触发 live governance/delete/provider 操作。

### E. 其余异步消费者与平台设置

- 目标：补齐 Ingest/RawData/Crawler 的同形反馈；Settings 两个 variant 避免重复内容；Projects/Successor 只核查已有状态与导航可达。
- 权威输入：原 useIngestActions/API 回执、RawData import、Crawler deployRuns、Settings draft/permission 和共享 hook。
- 输出/独占写面：`src/pages/IngestPage.tsx`、实际 `useIngestActions` 所在文件、`RawDataPage.tsx`、`CrawlerManagePage.tsx`、`SettingsPage.tsx` 及各自 scoped CSS、对应 stories、新 `tests/e2e/admin-secondary-repair.spec.ts`。路径均在 `main/frontend-modern` 下；Projects/Successor 若有确认缺陷由主线另行收口，不能顺手重构。
- 完成条件：清点清单中的每个真实 async 按钮；有 task_id 的使用共享反馈；crawler job/run identity 不伪装；配置页每个 variant 主责清晰；原权限和保存行为保持。
- 依赖：主线共享 hook；无 Resource/Process 文件写依赖。若主线拆为两个作者，Ingest+RawData 与 Crawler+Settings 必须分开独占文件和测试。
- 验证：`pnpm --dir main/frontend-modern check:crawler-manage-i18n-slice`、`check:settings-page-i18n-slice`，原 ingest-single-url E2E 与专属 E2E 统一执行。
- 共享测试资源：同 B；crawler deploy/rollback 为真实 effect，不通过随手点击验收。

### I. 主线集成、导航、共享入口与验证

- 目标：统一共享任务回执、导航/说明独立页、i18n/类型接入、实际用户链验证。
- 独占写面：新 `src/hooks/useTaskSubmission.ts`、`src/components/TaskSubmissionNotice.tsx` 及自有 CSS；`src/app/kernel/{AdminLayerShell,moduleManifest,moduleContributionRule,types,contracts,routes,moduleChrome,BusinessChainGuide}.tsx/ts` 的实际相关文件；`src/app/platform/i18n/catalog.ts`、`src/lib/api.ts`、`src/lib/types.ts`、`src/lib/queryKeys.ts`、`src/index.css`；新说明页面；`tests/e2e/business-chain-guide.spec.ts` 与共享 E2E fixtures/check scripts。
- 权威入口：新增说明模块必须经 manifest + moduleContributionRule 原通路，相关闭合类型/图标映射同步；不另外硬编码路由表。共享 catalog 的页面词条由各包提交精确 key/value 需求，主线集中合并。
- 完成条件：六项需求均有具体浏览器证据；原导航/legacy route 可达；至少 URL 提取完成真实入口到 worker 到 URL/运行记录读回；项目切换不显示旧项目回执。聚合结果同时报告领域执行缺口，不能以 E2E mock 替代。
- 依赖：先完成共享 hook 的一个真实消费路径，再让依赖包接入；其余布局/review可并行。共享文件、构建和 E2E 最后收敛。

主线可将 kernel 导航与独立说明页单独分给 K 包，独占 `src/app/kernel/` 中实际相关文件、新说明页及 `business-chain-guide.spec.ts`，主线保留 index.css、locale、共享 API、测试端口和最终设计。同时 E 包可分成 E1（Ingest/RawData）、E2（Crawler）和 E3（Settings）；Settings 必须独占其页面与 CSS。每次分派明确实际写面；不得让 kernel owner 与主线并写同一 kernel 文件。已有清晰职责的 Projects/Successor 也纳入主线视觉验收，存在呈现缺陷时再给对应独占小包。

## 7. 验证入口与证据边界

调查只做源码/文档及运行环境只读检查，未触发 live domain effect。导航调查包实际执行 `npm run check:layer-shell-contract` 通过，报告现有 32 个 module、Layer C 11 个、shell coverage 11/11；这只是修改前结构基线。其余测试与浏览器未运行。已实际确认 `/opt/homebrew/bin/pnpm` 可用、现有 Compose backend/worker 在运行；backend 容器无 pytest，宿主 `main/backend/.venv311/bin/python` 可导入 pytest 9.0.3。该环境检查不表示代码测试通过。

后端聚焦命令，cwd=`main/backend`：

```sh
.venv311/bin/python -m pytest -q tests/core_business/test_resource_pool_core_contract.py tests/core_business/test_process_consistency_core_contract.py tests/core_business/test_process_runtime_readback_core_contract.py tests/unit/test_collect_runtime_process_fallback_unittest.py
```

前端统一命令，cwd=`main/frontend-modern`：

```sh
pnpm exec tsc -b
pnpm build
pnpm check:layer-shell-contract
pnpm check:i18n-page-shell-disjoint
FRONTEND_E2E_PORT=4183 pnpm exec playwright test tests/e2e/business-chain-guide.spec.ts tests/e2e/admin-resource-repair.spec.ts tests/e2e/admin-process-repair.spec.ts tests/e2e/admin-ops-repair.spec.ts tests/e2e/admin-ingest-receipt-repair.spec.ts tests/e2e/admin-settings-crawler-repair.spec.ts --workers=1 --reporter=line
```

新增 E2E 文件在所属包实际创建后纳入命令；原 `business-line-browser-actions.spec.ts` 是明确 mocked rail，按受影响范围运行，不能当作 live backend proof。`playwright.config.ts` 默认端口 4173，代理默认 fail-closed 到 127.0.0.1:1，reuseExistingServer=false。主线应统一占用端口和 test-results/playwright-report；并发仅允许为每个 runner 声明不同端口及输出目录后执行。

实机截图至少 1440x1000、768x1024、390x844；检查导航、任务列表/详情、资源三个视图、ops/backend、settings/llm、crawler、guide。断言 document.scrollWidth <= viewport.width，表格内部横滚不计页面溢出；长 URL/任务名、空/失败、pending、技术详情和 reduced-motion 均须覆盖。

真实 URL 提取验收由主线独占当前本地 project/DB/broker/worker：读取基线 -> 页面点击一次提取 -> 保存原 API task_id -> 观察同一 task_id 的 worker/operator -> process history/detail 持久化读回 -> GET resource_pool/urls 读回。允许没有新增 URL 的去重结果，但扫描/提取/重复计数必须来自真实任务结果。若验证采纳，则只选择明确本地当前页条目，读回 lifecycle/review_closure，且确认未因采纳自动创建采集任务。清单内其他外部/provider/部署效果按已授权范围验证，不因 UI 测试扩大作用域。

## 8. 回传格式与剩余风险

每包回传结果、改动文件、动作覆盖数、验证命令与退出码、未通过项、真实 live 状态。主线记录已派发/完成包、共享修复成本及失败次数；工具未提供 token/耗时时明确缺失，不记零，不以子包通过冒充整体验收。

已知风险：任务结果后端 TTL 与 DB 关联、旧无项目归属任务、共享 CSS 优先级、现有 i18n/checker 的页面结构断言、review 部分失败、快速任务漏过 inspect。各风险都归本合同对应 owner；缺口只阻断依赖验收，不升级成整个项目停止。没有新增项目全量 gate、发布资格或冻结要求。

实际调查路线：Astra owner 负责架构与收敛，直接分派三个 `default + glm-5.3-flash-zhipu-glm-en / low` 只读包：async_chain、admin_navigation、resource_process_ui；下游没有再 spawn，没有修改实现文件。主线保留最终设计与实际实施分发权。

### 实施路线更新

主线派发后的 GLM standard kernel/ops 两包实际返回 429，未反复重启同一 provider。kernel 包由既有 Astra 调查 owner 接管，不再 spawn。已实现三职责组完整导航、保留全部既有 module/route、通过 manifest/contribution 新增 `sysBusinessGuide` 与 `/admin/guide`（兼容 hash `#business-guide.html`）、独立说明页渐进披露、scoped CSS、相应导航测试。原 AppShell 只移除 BusinessChainGuide import 和页底挂载，其他修改保持。catalog/index.css/共享任务 hook 与最终浏览器集成仍归主线。

kernel 包局部 ESLint 通过，覆盖 AdminLayerShell/types/moduleManifest/moduleContributionRule/BusinessChainGuide/BusinessGuidePage、导航 spec、checker，以及 moduleChrome/AppShell；`pnpm check:layer-shell-contract` 通过，33 个模块、Layer C 12 个、C 导航覆盖 12/12；`git diff --check` 通过。本包未运行 build、E2E、浏览器或 live effect，实际视觉与交互仍由主线统一验收。保留并发任务对 VisualizationLayerShell/moduleChrome/index.css/graph/checker 的修改，仅在闭合图标映射局部补 sysBusinessGuide。

## 9. 主线集成结果

### 实施与职责

七个实施写面已完成：后端任务持久化、资源工作面、任务详情、资料/系统运行、Ingest/RawData 回执、Settings/Crawler、kernel 导航与独立业务说明。Astra 三个只读调查包完成；kernel 由原 Astra 接管。GLM kernel/ops/settings 路线出现 429 后保留已有产物并更换执行路线，未声明失败路线已完成。

导航按资料与来源、任务与运行、设置与帮助分组，12 个管理入口完整呈现。原 module/route 身份保留；guide 的 legacy hash 通过 manifest 派生索引解析。资源页采用三个独立全宽表视图，常用字段使用业务标签，发现参数默认收起、预览模式用 checkbox。采纳当前页是逐项原 review API，保留部分失败/重试及项目切换取消，采纳不自动执行 collect。

任务详情为单层 accessible drawer，实测进度严格使用同一记录的计数对；未观测比例不生成百分比。真实检查发现终态耗时递增，已补 DB `ended_at/elapsed_seconds` 与消费端终态判断；缺失实测结束信息时显示未观测。历史摘要兼容 logger 扁平 params 的 `urls_extracted`，完整任务名使用已投影 `task_name`。所有共享回执只接受真实 task_id 且 async 非 false；Scrapyd/run/submission/retrieval 身份保留独立。

### 实际验证

- 后端首批四文件聚焦 pytest：exit 0，67 passed、7 subtests passed；时间字段补修后的三文件聚焦 pytest：exit 0，22 passed、7 subtests passed。F/E9 ruff 通过；默认历史 ruff 规则存在旧项，未声明全量 lint 通过。
- 前端最终 `pnpm build`：exit 0，包含 TypeScript 与 Vite；本轮所属 TS/TSX、stories、共享 catalog/hook/API、测试文件集中 ESLint 通过，最后 Process/test 补修再次通过。`git diff --check` 通过。
- 新增/更新的后台 E2E 共 37 个用例，分轮实际通过：guide 4、resource 4、process 7、ops 10、ingest/raw 3、settings/crawler 9。最后受影响 Process 文件完整 7/7 通过（14.3 秒）；其他未变化用例沿原运行保留，不冒充一次全新 37/37 执行。
- E2E 修复过程保留失败归属：首轮 19/34 失败、第二轮 12/36 失败、第三轮 5/16 失败、第四轮 1/5 失败；主要是 query 匹配、项目 key 规范化、折叠 DOM 与定位文案问题，另有真实终态耗时缺陷。按受影响 selector 复验，输出目录使用 `test-results/admin-repair-attempt2` 至 `attempt5` 和 `admin-repair-process-final`。首两次构建有类型/story 接线错误，修复后通过，不将返工成本记为零。
- 各页面 i18n slice 通过；i18n/page-shell disjoint 与 business string audit 通过，仅分别证明当前边界/审计可执行，不代表 legacy shell 退役或所有业务字符串迁移完成。
- CUA 实机资源表在 1280、1440、390 宽的布局检查及截图；资源表页面 scrollWidth 等于 viewport，guide 768 宽无页面溢出。Mock E2E 覆盖 Ops、Settings 等三尺寸以及任务 focus/Escape、读回错误、严格进度和审核失败。独立临时页后续 viewport 切换未应用时不计为新的尺寸证据；其他独立页没有额外全量视觉审计声明。

### 真实执行闭环

本地项目 `hk_water_investigation`，通过页面只点击一次 URL 提取。任务 ID `8b3996e3-3b50-4fef-b7c5-7e44ba67e816`，worker `celery@3329eee96ac6`；`process/{id}` 读回 `completed/ready=true/source=db/readback_source=etl_job_runs`，持久化 run_id=5。扫描 327 文档、提取 317 URL、新增 0、重复 317；提取前后 URL 池均 317 条，去重结果与实际读回一致。开始 `2026-10-05T10:22:21.264056+00:00`，结束 `2026-10-05T10:22:21.390955+00:00`，实测 0.126899 秒。页面回执、详情 deep link、历史读回均观察到同一 ID。

本地 `http://127.0.0.1:5174` 已更新最终 dist；后端/worker 在任务接线后重启，时间补修仅重启 backend。没有重新构建 Docker 镜像，现有 frontend 容器内静态文件更新不等同镜像已封存。未执行发现站点、采纳真实条目、外部采集、部署/回滚、治理删除或配置保存；这些效果的测试为隔离 mock，不冒充真实业务执行。没有提交或推送本批改动。

### 具名未通过项与成本边界

最终 layer-shell 检查的 C 层覆盖为 12/12，但全局检查 exit 1：`Visualization template navigation must not display a cached list while loading or after an error`，属于并发可视化修改的检查面，保留其改动，后台修复未接管该任务。旧 batch 58 跨页面 rail 在进入后台前因可视化统计页已改为“统计视图”而不再出现原“数据仪表盘”被阻断，后台后段本轮未执行；batch 108 后台诊断 rail 通过。不能声明整个仓库 gate 或旧全链通过。

工具没有提供可比的各 owner token/调用成本、完整首派开始时间或统一首次共同验收耗时，记录为缺失；不报告提速比例。七个实施写面完成不等于全局并发任务完成，环境故障、主线补修与测试失败均保留上述归属。
