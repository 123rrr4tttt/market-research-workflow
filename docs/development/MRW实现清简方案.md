# MRW 实现清简方案

> 后续结构整理：[MRW结构整理方案与分发包](MRW结构整理方案与分发包.md)（2026-10-04，实施结果见该文 §8）。最高优先退役现用产品、API身份和当前文档中的开发编号语义，统一为真实业务名称；本文原编号仅保留实施与证据追溯，不作为后续操作入口。既有结果及事实归属保持原义。

> 更新：2026-10-03。状态：方案与分发包已完成实施；最终收口与验证见分发包 §7.3。第 7–8 节保留 2026-10-02 的审查快照。
>
> 分发入口：[MRW 清简分阶段实施分发包](/Users/wangyiliang/market-research-workflow/docs/development/MRW清简分阶段实施分发包.md)。实施按 SIMP-00–12 的实际依赖、独占写面和测试资源推进；Q1–Q6 继续作为业务变化定义。
>
> 依据：当前工作树的代码、消费者、既有测试和项目执行合同。第 5 节为原验证入口；第 7 节的静态检查与隔离探针属于设计阶段，后续实际产品验证统一见分发包 §7.3。

> 2026-10-02 范围修订：按用户决定，下线旧 Agent Core 及旧聊天界面，仅保留当前 Codex Core 和对应 Codex WebUI。Q2 改为退役旧实现；原“合并旧 Agent 普通/流式执行”的工作取消。旧 Agent 专属功能不要求逐项复刻到 Codex。

> 2026-10-02 目标澄清：项目以搭建通用平台为目标。清简保留这一目标及其必要基础能力，审查实现中的重复、失效兼容、重复状态和无效历史治理。代码总量、某个目录占比、包装与动作代码的行数比例均不直接构成冗余结论。

## 1. 清简后的目标

MRW 的目标是可扩展、可组合的通用平台。能力声明、组合与装配、执行、权限、持久化、失败处理和结果读回共同承担平台职责；“研究项目 → 来源与候选 → 材料 → 检索与分析 → 证据与写作 → 报告”是当前业务验证链。清简保留平台能力及其扩展边界，减少同一规则的多份实现、同一状态的多处维护，以及已失去作用的兼容和管理逻辑。

具体目标是：正文定位集中到已有抽取函数；Agent 统一使用当前 Codex Core 与 Codex WebUI；来源采集复用已有搜索与入库能力，收敛重复编排；批量任务和必要会话记录各自管理自己的事实；模板写作按同步动作运行；运行诊断只承载当前可操作的信息。

完成后，替换成熟实现时可以按平台能力边界接入，保留身份、权限、状态、组合关系和结果读回。当前研究业务的纯能力对照见 [MRW 项目能力清单](/Users/wangyiliang/market-research-workflow/docs/architecture/MRW项目能力清单_替代方案评估.md)。本文不选择供应商，也不据代码规模推断运行成本。

审查使用以下口径；候选项需指出具体重复责任、现有消费者及收敛后保留的行为，才能进入删除范围。

| 审查对象 | 冗余成立的依据 | 处理边界 |
|---|---|---|
| 平台语言、能力合同、装配、执行与存储 | 查是否重复表达同一事实或重复承担同一职责；体量集中本身不成立 | 保留平台目标所需的对象、关系、扩展点与真实运行能力 |
| 同义实现和机械接线 | 相同输入及观察边界下维护同一规则，或由同一权威定义可确定派生却重复录入 | 复用已有共同实现和生成规则；清洗、并发、权限等真实差异继续显式表达 |
| 派生状态与多处回写 | 同一可变事实由多个位置独立更新，且副本没有独立的恢复、查询或性能要求 | 收敛事实 owner；有实际用途的索引、缓存和读模型保留单向派生关系 |
| 旧执行与兼容路径 | 用户已明确退役，或新消费者完成迁移，旧路径失去服务对象 | 按依赖退役；Codex 和其他平台能力仍依赖的共享部分保留 |
| 历史治理代码 | 只承载过期批次叙述，或已结束阶段的脚本不存在活动调用、恢复或证据复核依赖 | 退出当前运行和默认检查；历史证据保留原义，必要恢复与验证入口继续保留 |
| 包装与多重校验 | 多层重复同一检查/元数据/状态判断，且没有不同的信任边界或失败职责 | 合并重复构造；身份、权限、审计、结果持久化各自必要的检查保留 |

当前已确认正文定位和部分 handler 纯处理存在重复；写作 `queued` 与实际完成状态矛盾也已确认。旧 Agent 退出依据用户的架构选择。诊断历史树需逐字段分离有效合同与过期叙述；阶段脚本需核对真实引用后判断。两种工作流的生命周期含义不同，继续保留。测试行数、写作主体与外围服务的行数差，以及 `successor_runtime` 的代码占比只用于定位检查面，不作为可删比例或平台过度建设的证据。

| 处理面 | 决定 | 实际减少的维护负担 | 优先级 |
|---|---|---|---|
| Q1 正文抽取 | 复用已有纯抽取核，保留入口清洗差异 | 删除两份 HTML 定位循环 | S1 |
| Q2 Codex 单一 Agent 方案 | 下线旧 Agent Core、旧 runtime 与旧聊天页 | 删除旧循环、双页面、runtime 选择和专属配置/诊断 | S1 解耦，S2 退役 |
| Q5 模板写作 | 同步完成，统一响应和任务记录状态 | 删除伪排队分支、重复结果元数据构造 | S1 |
| Q6 运行诊断 | 历史叙述退出当前响应，迁移真实诊断字段 | 减少历史批次嵌套和相应维护测试 | S2；消费词表与实际退役结果 |
| Q4 批量任务/会话 | 先修复重复读取，随旧 UI 退役取消无消费者的投影 | 删除重复事件写入、旧聊天投影和派生回写缓存 | S1 修复，S2 删除 |
| Q3 来源采集 | 保留两个业务入口，收敛 handler 内重复编排 | 减少关键词分批、限额和汇总规则副本 | S1 独立纯处理，按资源验收 |
| 工作流版本管理 | 保留两个领域模型，本轮不抽公共生命周期框架 | 避免新增一套带大量例外的中间层 | 保留 |

S0–S3 的准确阶段与依赖见分发文档。Q3 在调用差异确认后可并行开发纯处理，外部执行与入库验证使用单独资源；独立工作不等待无关包完成。

## 2. 保留的对象、关系与事实归属

项目是权限和资料归属范围。来源项说明怎样取得信息；候选记录待处理的入口；材料保存实际内容及来源；证据把材料与判断联系起来。任务表达执行，会话组织交互。每个对象在自己的维护位置更新，其他视图通过关联和投影读取。

| 对象或事实 | 维护位置 | 其他模块如何使用 |
|---|---|---|
| 平台对象、能力合同、组合与装配关系 | 现有 language/specification、贡献定义及派生装配 | 业务能力与原消费者沿既有扩展入口接入；不复制一份平台语义 |
| 平台执行、效果、权限、持久化与恢复事实 | 原 runtime、substrate 及各效果 owner | 投影与诊断只读消费；业务实例不接管平台事实维护 |
| 来源项定义、有效配置、执行模式 | 既有 source library 定义、resolver 与 `ItemResolver` | 采集入口传业务参数；站点搜索消费已经解析的配置 |
| 自然语言理解、工作拆解与下一步选择 | 当前 Codex 原生执行 | 通过现有工具提交结构化任务，旧 NL-command 决策循环退出 |
| 批量任务选项、查询词、目标数量与执行 | 结构化 batch 请求和原业务执行器 | 来源模块决定 mode/handler，保持查询词和目标量 |
| 候选与资源池条目 | 既有候选合同与资源池 writer | 采集结果关联候选；需要时显式物化 |
| 材料内容、来源与入库结果 | 既有 material/frontdoor/writer | 检索、分析和写作消费已保存材料 |
| batch 执行状态 | batch job 与实际执行结果 | 会话显示兼容投影，不能反向宣布执行完成 |
| Codex 对话、工具循环和原生交互 | 各自宿主中的 Codex app-server 与 WebUI | 保留原生接入，按实际支持处理继续、停止和审批 |
| MRW 原生绑定所需 session、消息和产物关联 | `AgentSessionService` 与原 store | 只保留 native binding/业务读回的消费者，不复制 Codex 会话权威 |
| 业务工作流阶段与版本 | project customization | 保持 draft/staging/active、晋级与历史恢复 |
| 图模板版本和启用指针 | `WorkflowGraphTemplateService` | 图运行消费指定版本；运行状态仍归原 run store |
| 写作动作结果与历史 | 写作 action 与既有 job 记录 | 响应、历史和诊断由同一次动作结果派生 |
| 当前运行诊断 | 原业务运行结果及其只读诊断投影 | 页面、smoke、readback 工具消费统一当前字段 |

下面表示平台上当前研究业务的能力交接，不要求拆成独立服务：

```mermaid
flowchart LR
  P[研究项目与权限] --> S[来源及候选发现]
  P --> U[用户已有材料]
  S --> C[候选与资源池]
  C --> I[正文取得与入库]
  U --> I
  I --> M[材料及来源]
  M --> R[检索与分析]
  R --> E[证据及引用]
  E --> W[写作与报告]
```

外部发现、内部搜索和项目检索继续分工；任务与会话、知识关系图与执行工作流图继续分工。前端导航已经从 `moduleManifest` 派生 registry，保留现成做法。

## 3. 六项业务变化与原验收范围

Q1–Q6 保留业务变化的定义，实际拆分与派发使用 SIMP-00–12。仓库根为 `/Users/wangyiliang/market-research-workflow`。后端路径以下写作 `main/backend/…`，前端路径写作 `main/frontend-modern/…`；解释器、Docker 入口和完整验证命令统一见第 5 节。交付为原模块改动、相关测试及简短结果说明。

声明和注册继续从既有权威定义派生；涉及 schema/catalog 接线时先修改原定义，由现有工具同步消费者，不独立手改生成物。

### Q1：正文抽取共用一份实现

**目标与依据。** [raw_import.py](/Users/wangyiliang/market-research-workflow/main/backend/app/services/ingest/raw_import.py:91) 和 [url_pool.py](/Users/wangyiliang/market-research-workflow/main/backend/app/services/ingest/url_pool.py:639) 各有 HTML 定位循环；已有 [content_extraction.py](/Users/wangyiliang/market-research-workflow/main/backend/app/services/ingest/content_extraction.py:179) 可作为共同核。

**具体改动。** 在已有 `extract_main_text_from_html` 上保留单一解析、选择器遍历、120 字阈值和 body 回退实现。把确有差异的选择器集合做成该模块内的显式参数：两个旧入口仍用原四个选择器；原共享核调用者继续包含 `[role='main']`。不在本次重构中扩大旧入口的命中范围。

抽取核返回未截断、未清洗的正文。raw import 继续在调用后截到 50,000 字；URL pool 继续调用 `normalize_content_for_ingest(..., max_chars=50000)`。保留原入口的空输入、解析失败和无 body 行为；以旧路径实际输出为对照。已有 frontdoor 的“抽取 → 清洗 → 质量判断 → 结构化处理 → writer”顺序和 PDF 正文绕过逻辑保持。

**独占写面与输出。** 内容处理 owner 修改 `app/services/ingest/{content_extraction,raw_import,url_pool}.py` 及 Q1 测试。`postprocess_frontdoor.py` 默认只读；既有检索计划的结构化提取面不在本包，SIMP-00 协调实际文件交接。可保留两处单行兼容 wrapper，内部不再拥有算法。

**验收。** 运行 V1；增加覆盖选择器差异、阈值边界、长正文、解析失败的等价性用例。对同一输入比较最终正文及依赖正文的 hash；`given` 材料不发起抓取，PDF 不丢段。两个入口不再包含独立定位循环即满足删除条件。不批量重算历史内容或去重键。

### Q2：下线旧 Agent Core，只保留 Codex Core 与 Codex WebUI

**目标与依据。** 保留 [CodexAppServerCore](/Users/wangyiliang/market-research-workflow/main/backend/app/services/llm/codex_app_server.py:258) 的原生接入及 [CodexAgentPage](/Users/wangyiliang/market-research-workflow/main/frontend-modern/src/pages/CodexAgentPage.tsx:12) 嵌入的 `/codex/` WebUI。默认 `/workbench/agent` 已挂载 Codex 页；旧 `AgentChatPage` 通过 `#agent-chat-compat.html` 保留。`agent_core_v3` 即便选择 `codex_cli` provider，外层仍运行 MRW 的旧 `AgentCore.run`，属于退役对象。

**保留和删除的边界。**

| 处理 | 具体对象 | 执行要求 |
|---|---|---|
| 保留 | `CodexAppServerCore.invoke_native`、现有 native bindings、skills/tools、Codex 登录与进程生命周期 | 继续由 Codex 原生循环执行；`agent_macro_native` 与 `agent_macro_rapid_native` 是同一 Core 的两种现成绑定 |
| 保留 | `CodexAgentPage`、`flowAgentChat` 模块、`/workbench/agent`、`#agent-chat.html`、`/codex/` proxy/iframe | 作为唯一 Agent 页面；保留 WebSocket、assets、bootstrap 和当前认证链 |
| 保留必要共享部分 | MRW 工具合同、registry、业务 handler、原生绑定需要的 session、MCP bridge | 即使文件仍在 `agent_core` 目录，也按实际依赖保留；共享业务能力无需重新实现 |
| 下线 | `AgentCore.run`、其专属 provider 包装、tool-window 决策、普通/流式 turn 和旧审批续接 | 删除执行路径与自动回退，不先重构这些待删代码 |
| 下线 | `agent_core_v3`、`agent_runtime_v2`/`InteractiveAgentRuntime`、聊天 `legacy_batch` 分支 | API 不再启动旧 runtime；移除对应开关、选择器与专属健康探针 |
| 下线 | `AgentChatPage`、compat 渲染分支、旧聊天专属 hooks/styles/stories | 原兼容 hash 只导向 Codex 页；删除 Codex 页内“旧版聊天”入口，不复制旧 UI 功能 |
| 下线自然语言二次循环 | `run_agent_batch_nl_command_loop`、`/agent-batch/nl-command` 及其 direct 替代入口、工具中的 command 自动回退 | Codex 提交结构化 jobs；保留 batch 提交、状态、取消、重试和业务执行器 |
| 清理派生面 | 旧 runtime 专属 schema、配置、注册、能力宣传、测试与当前诊断 | 从原定义和实际消费者同步删除；历史数据及冻结证据保留原义 |

**先拆开共享依赖。** [codex_macro_binding.py](/Users/wangyiliang/market-research-workflow/main/backend/app/services/llm/codex_macro_binding.py:252) 和 [MRW MCP bridge](/Users/wangyiliang/market-research-workflow/main/backend/scripts/mrw_mcp_server.py:35) 仍引用 `AgentCoreRequest/CoreToolCall`、`build_project_core_tool_registry` 及部分组合能力。保留这些数据形状、工具执行和原权限；解除 `agent_core/__init__.py` 对旧循环的自动导入。只有直接依赖妨碍退役时才把共享实现移到已有适当模块，不因目录名批量删除，也不新建一套工具目录。

原生 registry 中的 `agent_batch.submit` 只保留结构化 jobs 语义，删除 command-only 分支及其 planner fallback；旧 NL 专属 tool 从原声明退役。清查 `successor_migration/legacy_agent_core.py`、provider-readiness/trace/quality 探针和贡献装配对旧 Core 的活动引用，随消费者一起退出，避免 UI 隐藏后后台仍启动旧循环。共用业务探针继续验证保留能力，历史迁移记录不改写。

旧 NL 入口的消费者一并迁移：前端 `IngestPage.tsx`、`hooks/useIngestActions.ts`、`lib/api.ts`、`lib/api/endpoints.ts`、`lib/types.ts`；后端 `agent_runtime/capability_registry.py`、`material_ontology.py` 与 `composition/production_route_bindings.json` 的原声明和派生输出。采集页移除旧自然语言执行控件，可保留前往 Codex 页的导航；原有直接采集和结构化 batch 功能继续使用。注册面不再宣传旧 NL 能力，派生 JSON 经原工具更新，不手改。

**用户入口与兼容处理。** 保留的 MRW Agent API 仅接受显式 native binding；去掉“未指定就运行 `agent_core_v3`”的默认。缺少 native 选择按新请求合同返回校验错误；明确旧 runtime 或旧 NL-command 请求在执行前返回 `410 / agent_runtime_retired`，不自动改投另一条执行链。旧专属审批 continuation 同样停用，不能借迁移继续执行旧待批准动作。浏览器旧 hash 可以导航到 Codex 页；该跳转不恢复旧 session，也不自动重放消息。

旧会话和任务记录保持原身份与读取能力；正在运行的旧任务先禁止新建，再观察其正常结束或由原取消入口结束，确认无存量执行后删除宿主。保留的 batch 业务任务继续按原 job/result 读回。退役不要求给旧对话伪造 Codex thread、全量搬历史、复刻旧 watcher 或重建旧审批系统。

**原生能力的实际边界。** 当前 MRW native binding 声明支持 dynamic tools、skills、同进程 continuation 和 interrupt；跨进程 thread resume、approval requests 尚不支持。继续明确返回不支持，不回退旧 Core。嵌入式 WebUI 的会话、工具展示和审批由它自己的宿主承担；MRW 包装页目前只显示项目名，未将 `projectKey` 注入 iframe。验收必须单独核对工具实际项目范围，不把页面项目标签当绑定证明。

WebUI 通过独立代理服务连接自己的 Codex app-server，MRW 后端通过 `CodexAppServerCore` 接入；两者当前不等于同一个进程、thread 或 store。保留现有接线，不另造会话同步桥。本次仓库检查只确认 `/codex/` proxy，外部 WebUI 的实际启动位置和运行配置在实施时有界核实，不能删除其宿主进程或凭历史端口猜运行状态。

**独占写面与输出。** 按分发包 SIMP-07/08 划分后端与前端；共享 schema/catalog、全局配置和类型由 SIMP-00 集中合入。batch/session 先由 SIMP-01 修复重复读取，再按 SIMP-07 → SIMP-12 交接实际相关文件。必要的 native binding、项目工具和 MCP 接缝须先与既有检索任务交接；旧 M 编号不作为当前 owner。后端依赖拆分与前端开发可并行，原生保留链、消费者迁移和存量执行处理完成后删除旧内核。

**退役顺序与验收。** 先用 V2 和真实入口样例确认现有 Codex 路线可用，再把共享工具与旧循环解耦、停用旧新建入口、退出旧 UI、结束存量旧执行，最后删除无引用的代码/配置/测试。实现完成必须同时满足：唯一 Agent 页面为 Codex WebUI；旧 runtime、旧 NL tool 和旧 approval 不能启动；Core 不可用时明确失败；保留工具的项目范围、权限、错误及业务读回不变。真实验收分两条现有执行链：A. `/codex/` WebUI 认证、一次真实 WebUI turn 及该宿主拥有的继续/停止与结果读回；若要求 MRW 工具在同一 WebUI turn 中执行，还须在实际宿主配置中确认该工具已注册，并在同一 thread 读回工具调用与项目 scope。B. MRW native binding 经 `/api/v1/agent-chat/turn` 调用已注册只读工具，核对 `binding.project_key/scope_id`、tool result 与目标项目已有 run 的读回。当前仓库只证明 B 的 native binding；A 的工具注册和 A/B thread/store 桥接未证实，两条结果不得拼成一次端到端验收。native route 没有暴露宏工具 stop API，WebUI 的 stop 只验证其自身宿主 thread。不能只用 iframe 加载、mock 测试或历史 PASS 宣称真实链通过。

### Q3：采集保留业务入口，收敛重复编排

**目标与依据。** `/ingest/source-library/run` 支持通用来源执行、批次、异步和幂等；`/resource_pool/source-library/collect` 是站点采集并写资源池、自动入库。二者已经复用 [unified_search_by_item_payload](/Users/wangyiliang/market-research-workflow/main/backend/app/services/resource_pool/unified_search.py:908) 和 `build_item_execution_plan`。主要清理对象是 [resolver 中的 handler 编排](/Users/wangyiliang/market-research-workflow/main/backend/app/services/source_library/resolver.py:2009) 与 [handler adapter](/Users/wangyiliang/market-research-workflow/main/backend/app/services/source_library/adapters/handler_cluster.py:45) 内相近的关键词分批、限额装配和结果汇总。

**具体改动。** 保持现有 `CollectRequest`、`ExecutionRequest`、候选合同、搜索实现和 frontdoor。共同的关键词规范化、批次限额计算、候选去重与统计汇总只在已有 source library 模块维护一份；两个 handler 消费它。并行/超时调度、`terminal_output_only`、是否自动入库和调用结束后的 frontdoor 处理仍由原执行路径控制。以一个站点关键词样例先走通两个原消费者，再迁移其余共同段。

两条路径均有实际用途：resolver 服务 site-search，adapter 经已注册的 `handler/cluster` 通道服务符合条件的 single-channel 路径。resolver 的完整 item/执行计划、并发和 URL-routing 终态，与 adapter 的简化 item、顺序循环及可选入库分别保持；不把不同输入装配硬改成同一 plan。共同函数的等价性逐路径比较重构前后输出，无需让两条路径彼此产生相同输出。

来源 mode/handler 归 `ItemResolver` 与原 runner；站点 entry/template/fallback 策略归已有 item plan 和 unified search。这两个层次保留。资源池入口继续明确 `write_to_pool=True`、`auto_ingest=True`、`enable_extraction=True`；通用入口保留自己的模式和参数，不强制所有路径都物化。

必须逐项保持 `query_terms`、`max_items/limit`、`max_candidates`、`ingest_limit`、`pool_scope`、`allow_term_fallback`、`probe_timeout` 的归属与各入口默认值。候选数量与入库数量是不同约束；同一候选只在原授权写面触发入库，不能在共用搜索与外层 frontdoor 各写一次。

**独占写面与输出。** 采集 owner 修改 `app/services/source_library/resolver.py`、`adapters/handler_cluster.py` 和确实需要复用的同目录函数，附 Q3 测试。两个 API、`collect_runtime/runtime.py`、`resource_pool/unified_search.py` 默认只读；仅当原消费者接线必须变更时由原 owner 合入。采集末步与项目工具面继续由当前检索任务 owner 维护，SIMP-00 协调接线，SIMP-10 不越界并写。

**验收。** 运行 V3；核对两个入口的站点搜索、URL 执行、crawler 接受后读回、空结果、部分失败、超时、重试与原有异步幂等分支。共用片段在两条实际调用链都被消费后删除原副本；保留必要策略参数。涉及写入的最终样例必须从原资源池和材料入口读回数量、正文、来源与任务状态。外部 provider 不可用时保留该样例的未验证状态，其他清理可独立完成。

### Q4：随旧聊天退役，减少批量执行的会话投影

**目标与依据。** [agent_batch.py](/Users/wangyiliang/market-research-workflow/main/backend/app/api/agent_batch.py:394) 投影到 session 后，又把 session 阶段等字段写回 batch metadata。沿用 [AgentSessionService 的投影和查询接口](/Users/wangyiliang/market-research-workflow/main/backend/app/services/agent_sessions/service.py:943)。

**具体改动。** 以 Q2 切换后的真实消费者重新确定投影范围。只为旧 `AgentChatPage` 创建的 session/task/event 投影停止生成；Codex 原生工具、业务 handoff 或历史查询仍在使用的关联保留。batch 执行状态继续从原 job/result 取得；需要 session 视图时从原 store 读取。仍保留的响应从现有关联派生 `session_id/current_phase/root_task_id`，停止持续回写可再生展示字段。

`session_id/root_task_id` 若承担恢复或历史关联，作为稳定引用保留；`compat_job_id`、`compat_mode`、`compat_projection_version` 和 job item/verification 标识按原生/业务消费者逐项保留，不因旧 UI 曾使用就永久续写。无剩余消费者的字段随合同一起退役；旧历史仍按旧版本读取。retry 身份不变；无 session 的结构化 batch 合法，不能把投影缺失解释为执行成功或失败。

```mermaid
flowchart LR
  B[batch job 与执行结果] -->|仅仍有消费者时派生| S[必要 session 视图]
  B --> V[batch API 响应]
  S -->|读取现有关联| V
```

**独占写面与输出。** SIMP-01 先修复重复读取，SIMP-12 在退役后集中修改 `app/api/agent_batch.py` 与实际受影响的 session service/adapter，附 Q4 测试。保持 `_BATCH_JOB_REGISTRY` 现有存储方式，不附带迁库。不并行修改 Q2 所依赖的共享 session 行为。

**验收。** 运行 V4；覆盖结构化提交、状态更新、重试、业务读回、必要投影失败、session 缺失、provider 状态未知。无旧 UI 消费者时不再创建对应投影；保留消费者仍能读取所需字段，`accepted` 或未知交付不提升为完成。历史 metadata 可被读取但不再成为新状态来源。旧 NL-command 用例改为退役拒绝见证；确认采集页不再请求 NL API、当前能力目录不再暴露旧入口、`agent_batch.submit` 只接受结构化 jobs，结构化任务与业务执行验证继续保留。

### Q5：写作按实际模板动作简化

**目标与依据。** [llm_action_service.py](/Users/wangyiliang/market-research-workflow/main/backend/app/services/writing/llm_action_service.py:45) 当前生成提纲、追加固定提示、返回选中文字或截取摘要。[报告生成](/Users/wangyiliang/market-research-workflow/main/backend/app/services/llm_report_generator.py:62) 同样明确为模板实现。写作动作已同步算出结果，却在 `async=true` 时返回 `queued` 和空内容，job/readback 则完成，需消除此矛盾。

**具体决定。** 当前模板动作统一同步执行。保留 `async` 请求字段作为兼容提示；收到 `true` 时仍同步返回真实 `completed` 和内容，并返回 `async_not_supported_executed_inline` warning，记录 `requested_async=true`、`execution_mode=inline`、`async_honored=false`。删除“已算完却返回排队”的分支，不增加队列或 worker。权限拒绝和执行失败继续使用其真实状态。

这一变化使用新的 `writing.llm_action.capability_truth.v2` 标识，随同原 API 合同、类型、测试及实际消费者一起更新；新增观察字段位于现有可扩展 metadata 内。新记录的 response、job、runtime readback 和 capability truth 都由同一个动作结果构造。旧历史记录保留原版本，不改写为新结果；无法恢复旧内容时明确缺失。

沿用 `job_logger.complete_job` 将 result 合入 job `params` 的存储合同；history/detail 从这个实际保存位置投影完成时间、warning/error 和新执行方式字段。按需要扩展已有 `request_meta/result_summary`，不虚构独立的 `job.result` 存储，不在展示时重新执行动作。

保留项目访问控制、现有角色拒绝行为、请求身份、模板版本、操作历史及错误回传。`action_boundary`、`dependency_gate` 等仍被合同消费的字段暂作同一结果的兼容投影，不各自运行一套状态流程。模板动作移除实际不参与执行的模型选择依赖；审计仍记录动作身份、执行方式和结果。此调整不得扩大任何调用者的权限。

报告保持模板组装、引用检查、质量阈值、导出审计和导出令牌约束；不为压缩包装而删这些功能，也不在本包接入新模型。后续真实生成能力可从动作边界替换实现。

**独占写面与输出。** 写作 owner 修改 `app/services/writing/llm_action_service.py`、对应 writing API、`app/contracts/schemas/writing.py` 与 Q5 测试；前端 owner 同步 `src/lib/api/domains/writing.ts`、type/mock 和 `scripts/check_writing_workbench_contract.mjs`。检查必须验证 v2 及 `requested_async/execution_mode/async_honored`、warning 的语义，不能只查字段存在。共享权限和 LLM platformization 定义如需变更交给 SIMP-00 合入，不改其他消费者。报告代码默认只读，本轮验证保留其能力。

**验收。** 运行 V5。`async=false/true` 分别检验响应、历史、job 和 readback 一致；模板动作不访问模型 provider，权限拒绝无内容交付，失败不会留下完成状态。旧版历史仍可读；报告引用与导出质量门照常生效。完成时伪排队分支为零，重复元数据构造收为一处。

### Q6：运行诊断去掉开发历史叙述

**目标与依据。** [business_lines.py](/Users/wangyiliang/market-research-workflow/main/backend/app/api/business_lines.py:770) 的 evidence matrix 包含大量历史批次嵌套。[OpsPage](/Users/wangyiliang/market-research-workflow/main/frontend-modern/src/pages/OpsPage.tsx:436) 读取其中的说明文字；测试与脚本还读取部分实际诊断合同。

**具体改动。** 当前 matrix 采用 `business_line.evidence_matrix.v2`。保留 `lines`、coverage policy、诊断 guidance、worker/readback、失败原因、unknown/blocked 等当前含义。按真实消费者把历史嵌套中仍使用的 readiness、smoke、async readback 和恢复字段迁到对应业务线或顶层当前合同；每个字段只有一个当前位置。仅删除批次号、演进说明和重复“本批已覆盖”叙述。

OpsPage 改为读取当前 coverage/diagnostics；[DashboardPage](/Users/wangyiliang/market-research-workflow/main/frontend-modern/src/pages/DashboardPage.tsx:118) 的 reset telemetry 边界也必须迁移，保持 report/export payload 的只读上下文及“界面重置不改变调度证据”的含义。同步迁移 `BusinessLineEvidenceMatrix` 类型、两个页面的浏览器 fixture，以及用户链 smoke、覆盖检查、async readback、manifest 和 trace-baseline 消费脚本。更新测试为验证当前可执行语义，去掉仅断言第几批文字的项目。每个原有效断言在迁移中保留对应检查；不能用删除失败测试代替迁移。

脚本核对范围为根目录 `scripts/` 下的 `run_business_line_user_flow_smoke.py`、`check_business_line_batch_coverage.py`、`run_business_line_async_task_readback_live_samples.py`、`build_business_line_task_readback_manifest_from_runtime.py`、`run_business_line_trace_baseline_live.py`。只改它们实际消费的字段；诊断版本迁移不顺带改 scheduler、trace-baseline 等独立合同的版本。

已有历史文档和 v1 证据按原版本解释，运行时不读取开发文档。v2 在仓库内生产者、所有查明消费者和测试一起切换；如发现外部仍使用 v1，保留一个有明确消费者和退役条件的边界适配器，暂缓删其所需字段。没有已知外部消费者时不预建双版本服务。旧字段仍有活跃消费者则该项尚未完成。

**独占写面与输出。** 诊断 owner 修改 `app/api/business_lines.py`、相关后端测试/消费脚本；前端 owner 修改 `src/pages/OpsPage.tsx`、`src/pages/DashboardPage.tsx`、相关类型和 e2e fixture。共享 `src/lib/types.ts` 与 build 由集成 owner 单写、统一执行。实施时再查一次字段引用，补齐新出现的消费者后删除旧字段。

**验收。** 运行 V6。浏览器能显示当前业务线、失败与阻塞；Dashboard 的报告详情、PDF/DOCX 导出和缺失诊断回退保留相同边界；脚本仍能找到所有原有效探针和读回路径。v1 历史与 v2 当前响应版本明确，mock smoke 和真实运行证据仍能区分。`batch_orchestration` 的有效语义迁出、所有消费者不再依赖后，删除当前响应中的历史树。

## 4. 实施次序、所有权与不扩大的范围

### 4.1 当前阶段与分发入口

[清简分阶段实施分发包](/Users/wangyiliang/market-research-workflow/docs/development/MRW清简分阶段实施分发包.md) 是当前清简工作的分发入口，覆盖 Q1–Q6、A1–A12 和第 8 节复用路径。SIMP-00 持续承担结构判断、共享接缝、资源分配与整组集成；SIMP-01–12 承担具体改动。它们表示工作职责，不新增系统组件。

实施分 S0 固定接口/owner/资源、S1 局部收敛与公共规则、S2 消费者迁移及退役、S3 整体收敛四阶段。只有实际依赖完成且文件/资源无冲突的包才能并行；没有整批等待屏障。C2 先首例再变体，词表先于诊断迁移，batch/session 按即时修复→旧入口退役→剩余投影删除交接。完整依赖图、文件顺序、测试资源和可直接下发合同统一在分发文档维护。

既有 [信息检索实施计划](/Users/wangyiliang/market-research-workflow/main/backend/docs/INFORMATION_RETRIEVAL_IMPLEMENTATION_DISPATCH_PLAN.md) 当前采用 R0–R6。清简前核对实际在途任务和具体文件，不根据旧 M 编号推定占用，也不改写该计划的历史状态。SIMP-00 负责与原 owner 交接共享 Agent、材料、collect、project_tools 和 catalog 面；未释放的文件只约束依赖它的包。

遵循 [直接测试与批次封存规则](/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/19_direct-testing-batch-freeze-amendment.v1.md)。当前 [阶段进度](/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/06_production-deployment-stage-progress.v1.md) 的停止和延后发布状态保持；S0–S3 是本次清简的开发阶段。

### 4.2 局部缺口如何处理

当前工作树已有大量未提交修改。文件 dirty 本身不是 blocker；实施时确认其中尚在工作的 owner 和具体写入范围，避免覆盖。无法协调的文件只阻断依赖它的包。

既有检索任务中仍未关闭的 Rapid/native live/持久化交付项按其当前记录保留。Q1、Q6 不以解决这些缺口为前置条件；Q2 的实际切换只要求其保留路线的真实调用与项目范围验证，不要求补齐整个 Rapid 或宏框架。Codex/WebUI 不可用时可完成旧代码的依赖拆分和离线验证，但不宣布在线切换完成。Q3、Q4 缺真实 provider/DB 读回资源时分别记录未验证场景。

测试共享资源按数据库、project key、队列、provider 账户、native session、端口和 build 输出区分。同一资源上的写入串行；不因测试文件不同就并发。集成 owner 分配资源，包作者复用既定入口。

### 4.3 本轮明确保留的结构

平台 language/specification、assembly、runtime、substrate 继续承担通用平台职责。其内部如果存在同义声明、重复投影或过期兼容，按第 1 节逐项审查；不按目录整体裁减，也不为了减少代码把平台收缩为单一研究流程。平台可扩展性、跨能力组合、权限/效果边界、持久读回及适用的定律/合同测试均属于保留能力。

业务工作流的阶段晋级/历史恢复与图模板的版本启用，拥有不同对象、版本身份和回滚语义。当前证据不足以证明共用生命周期 helper 能减少总体复杂度，因此本轮不抽取。将来只有出现可直接复用的同一行为时，才提取具体函数。

基础设施裁减、存储合并、batch 迁库、新 Agent runtime、全面目录重组、权限放宽和供应商接入均不进入这六个包。Q2 授权退役旧 Agent 实现及专属功能；保留 Codex 现成功能和真实依赖，不以旧 UI 的全功能等价迁移作为完成条件。

## 5. 验证入口与场景

以下为实施使用的验证入口，实际执行范围与结果见分发包 §7.3。已退役测试不重新恢复；导入失败导致的 skip 不能计作通过。

### 5.1 统一运行环境

优先复用既有 Docker focused 入口。先检查各测试的 fixture：只有全部副作用已隔离或 mock 的测试才可用 `--no-deps`；不能让 Compose 默认连接串落到用户正式数据。需要持久化的样例由 owner 配置独立测试资源，沿用原测试 runner。

```bash
cd /Users/wangyiliang/market-research-workflow
bk_test() (
  cd /Users/wangyiliang/market-research-workflow || exit 1
  docker compose -f main/ops/docker-compose.yml --profile test run --rm --no-deps \
    --entrypoint python --workdir /workspace/main/backend \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -e DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:1/postgres \
    -e REDIS_URL=redis://127.0.0.1:1/0 \
    -e ES_URL=http://127.0.0.1:1 \
    -e PYTHONPATH=/workspace/main/backend:/workspace:/opt/functorial-kit:/workspace/src \
    -v /Users/wangyiliang/Desktop/functorial-kit/python:/opt/functorial-kit:ro \
    -v /Users/wangyiliang/market-research-workflow:/workspace:ro \
    backend-test -m pytest -p no:cacheprovider -q -rs "$@"
)
```

Docker 不适用且本地依赖核定后，使用已有环境；V1–V6 参数不变，将 `bk_test` 换成 `m_test`：

```bash
cd /Users/wangyiliang/market-research-workflow/main/backend
m_test() (
  cd /Users/wangyiliang/market-research-workflow/main/backend || exit 1
  PYTHONPATH=/Users/wangyiliang/Desktop/functorial-kit/python:/Users/wangyiliang/market-research-workflow/src:/Users/wangyiliang/market-research-workflow/main/backend \
  PYTHONDONTWRITEBYTECODE=1 \
  /Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python \
  -m pytest -p no:cacheprovider -q -rs "$@"
)
```

### 5.2 各包现成测试入口

V1：抽取、清洗、材料交接和原 frontdoor 消费。

```bash
bk_test tests/unit/test_content_extraction_unittest.py \
  tests/unit/test_raw_import_structuring_unittest.py \
  tests/unit/test_retrieval_material_handoff.py \
  tests/unit/test_source_library_url_pool_adapter_unittest.py \
  tests/unit/test_postprocess_frontdoor_unittest.py \
  tests/unit/test_meaningful_gate_unittest.py \
  tests/unit/test_admin_reextract_unittest.py
```

V2：保留的 Codex 原生接入、共享工具/session、认证及旧入口退役。

```bash
bk_test tests/unit/test_codex_native_macro_binding.py \
  tests/integration/test_agent_macro_entry.py \
  tests/integration/test_agent_chat_api_unittest.py \
  tests/unit/test_agent_macro_native.py \
  tests/unit/test_rapid_native_macro.py \
  tests/unit/test_agent_sessions_service_unittest.py \
  tests/integration/test_agent_sessions_api_unittest.py \
  tests/integration/test_codex_auth_agent_guard_unittest.py \
  tests/integration/test_codex_oauth_browser_flow_unittest.py \
  tests/unit/test_codex_cli_llm_fallback_unittest.py
```

先更新 `test_agent_macro_entry.py` 中“默认仍为旧 AgentCore”的历史断言，以及 `test_agent_chat_api_unittest.py` 中旧 runtime/approval 的接受断言，改为 native 显式接入和旧请求退役见证。`test_codex_cli_llm_fallback_unittest.py` 仅保护仍被业务模型调用使用的 provider 接线，不能重新启用旧 AgentCore 作为聊天回退。删除旧内核后同步退役其专属测试和注册；共享工具、错误、权限等有效检查迁到保留消费者。

MCP bridge 补充一次无业务副作用的导入与工具清单检查，确认共享 registry 不再加载旧执行循环；真实只读工具调用通过 Q2 的当前 Codex/WebUI 样例验证。已有 `test_agent_core_unittest.py` 和旧 watcher 测试不再作为保留旧功能的验收要求。

V3：来源解析、handler、资源池与原采集合同。

```bash
bk_test tests/unit/test_source_library_item_resolver_unittest.py \
  tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py \
  tests/unit/test_collect_runtime_source_library_adapter_unittest.py \
  tests/unit/test_resource_pool_unified_search_unittest.py \
  tests/unit/test_resource_pool_api_unittest.py \
  tests/unit/test_ingest_source_search_contract_unittest.py \
  tests/unit/test_ingest_source_collect_authority_unittest.py \
  tests/core_business/test_ingest_core_contract.py \
  tests/core_business/test_resource_pool_core_contract.py \
  tests/integration/test_external_project_collect_runtime_integration_unittest.py
```

V4：结构化批次执行、必要会话投影、工作流交接与 NL 入口退役。

```bash
bk_test tests/unit/test_agent_batch_api_unittest.py \
  tests/unit/test_agent_batch_approval_binding_unittest.py \
  tests/unit/test_agent_sessions_service_unittest.py \
  tests/integration/test_agent_sessions_api_unittest.py \
  tests/integration/test_agent_batch_workflow_closure_unittest.py
```

`test_agent_batch_loop_unittest.py` 中只验证已退役自然语言循环的部分随其退出；仍验证补充来源、查询词/数量和任务合同的用例迁入原业务执行器测试。旧接口拒绝、无新 effect 的检查纳入 batch API 测试。

V5：写作结果、权限与历史，以及报告/导出保留行为。

```bash
bk_test tests/unit/test_writing_llm_action_service_unittest.py \
  tests/integration/test_writing_llm_actions_api_unittest.py \
  tests/unit/test_llm_report_generator_unittest.py \
  tests/unit/test_llm_report_export_service_unittest.py \
  tests/unit/test_llm_report_export_audit_service_unittest.py \
  tests/unit/test_llm_report_export_token_state_service_unittest.py \
  tests/integration/test_llm_report_api_unittest.py
```

V6：当前证据矩阵和 Ops 消费；被迁移的脚本按自身原合同增加对应验证。

```bash
bk_test tests/core_business/test_business_line_evidence_contract.py \
  tests/successor_runtime/test_s2b_c9_evidence_matrix.py \
  tests/successor_runtime/test_s2c_ops_domain_surfaces.py \
  tests/core_business/test_admin_dashboard_process_core_contract.py \
  tests/contract/test_admin_dashboard_schema_contract_unittest.py \
  tests/unit/test_admin_dashboard_consumer_boundary_unittest.py
```

前端有修改时在输入稳定后集中执行一次 build；Q5 运行写作合同检查，Q6 运行 business-line 和 runtime smoke 的 mock 浏览器检查。复用现有 npm 入口和依赖；Playwright 配置启动服务使用 pnpm，实施前统一核定二者可用，不改 lockfile 或临时安装依赖。端口 `4196` 是拟用测试端口，使用前确认未占用；真实用户链另显式绑定隔离 API。

```bash
cd /Users/wangyiliang/market-research-workflow/main/frontend-modern
npm run build
node scripts/check_writing_workbench_contract.mjs
FRONTEND_E2E_PORT=4196 npx --no-install playwright test \
  tests/e2e/business-line-browser-actions.spec.ts \
  tests/e2e/runtime-smoke.spec.ts --workers=1 --reporter=line
```

以上现成测试不能替代各包明确列出的新增行为见证。新用例追加到相关现有测试文件；如仓库 planner 管理这些 runner，同步其真实依赖和测试资源，不另建调度器。

Q2 前端验收在更新相关测试后运行；旧页专属交互用例退役，保留 Codex route/iframe 见证并加入兼容 hash 导航、旧控件消失及 `/codex` 失败呈现的检查。采集页补上无 NL 请求及直接采集仍可用的见证：

```bash
cd /Users/wangyiliang/market-research-workflow/main/frontend-modern
FRONTEND_E2E_PORT=4196 npx --no-install playwright test \
  tests/e2e/agent-chat.spec.ts \
  tests/e2e/agent-chat-writing-crossflow.spec.ts \
  tests/e2e/agent-chat-real-backend-long-task.spec.ts \
  tests/e2e/ingest-single-url.spec.ts --workers=1 --reporter=line
```

上述 runner 的 mock/隔离结果不证明外部 WebUI 正常。真实验收按核实的现有宿主配置显式设置 `VITE_API_PROXY_TARGET` 与 `VITE_CODEX_PROXY_TARGET`。分别读回 `/codex/` 的认证状态、真实 WebUI turn 与宿主 thread 生命周期，以及 MRW native `/api/v1/agent-chat/turn` 的只读工具结果和 `binding.project_key/scope_id`。`CodexAgentPage` 上的认证徽标或 iframe 可见不能代替任一链路；native API 的 tool result 不能代替 WebUI 同一 thread 内的 MRW 调用。如果宿主确实把 MRW 工具注册到 WebUI，再额外验证该 WebUI tool call 的真实 project scope；不自动使用当前页面项目标签选定写入对象。

### 5.3 受影响集成与最终读回

共享声明、catalog 或贡献入口实际变化后，由集成 owner 在一致工作树上统一运行原检查；只改本文不触发这些命令：

```bash
cd /Users/wangyiliang/market-research-workflow
main/backend/.venv311/bin/python scripts/dev.py sync
main/backend/.venv311/bin/python scripts/dev.py check
main/backend/.venv311/bin/python scripts/dev.py gates
```

`sync` 会写派生物，不能与包作者共同编辑共享输出。若实际经过 C7 writer，使用专属测试服务器执行原 C7 验证；其固定测试数据库会被重建，不能连接共享数据库。未触及该边界的包不等待 C7。

最终只重验本次受影响的用户链：Q1/Q3 从材料入口读回正文和来源；Q2 从当前 Codex/WebUI 读回 turn、工具结果与继续/停止，并验证旧入口不执行；Q4 从 batch 和必要 session API 读回业务状态；Q5 比对返回结果和历史；Q6 从页面及原诊断脚本读取当前合同。成功、拒绝、失败、部分完成与未知分别记录；HTTP 200 或 mock 页面通过不建立持久化完成。

## 6. 完成标准与退役清单

| 项目 | 完成时应看到的变化 | 仍须保留 |
|---|---|---|
| 通用平台 | 同义声明、派生副本及失效兼容按证据收敛；不设置总行数削减指标 | 已定义的扩展点、能力组合、运行与存储合同及原消费者见证 |
| 正文定位 | 两份入口算法副本退出，调用共同核 | 原清洗顺序、正文/hash、PDF 与 given-material 行为 |
| Agent 执行与界面 | 仅当前 Codex Core 与 Codex WebUI 可启动，旧 runtime/页面/NL 二次循环退出 | 原生已支持能力、实际工具权限、必要业务 session 与历史记录 |
| 来源编排 | 共同关键词/限额/汇总规则不再双写 | 两入口用途、调度差异、候选/入库限额和写入权限 |
| batch/session | 旧页专属投影停写，可变 phase 等字段不再双向维护 | 结构化业务执行 owner、必要原生关联、历史读取与重试身份 |
| 写作 | response/job/readback 状态一致，无伪 queued | 项目权限、模板内容、历史、报告引用和导出约束 |
| 诊断 | 当前响应无历史叙述树，消费者迁入 v2 | 全业务线诊断、有效探针、失败/blocked/unknown 语义 |

实施记录复用原 owner 的进度位置，记清删除了哪些重复实现、仍保留哪些适配、通过哪些原消费者以及哪些真实运行尚未观察。不另建兼容平台、证据库或逐项审批流程。

清简收益以实际少维护了多少份规则、状态副本和失效分支，以及平台扩展能力是否保持判断。代码总行数只是规模记录，不设按比例裁剪目标。没有统一负载下的前后测量时，不报告性能提升百分比。每个旧实现满足上述退役条件后就在该包删除；尚有实际消费者的兼容层明确列出消费者及解除条件。

第 3–6 节定义六项业务变化及验证入口；第 7–8 节给出审查与设施复用；第 9 节固定实施框架。阶段与独占写面以分发文档为准。产品代码、服务状态、历史证据和发布状态未由文档工作改变。

## 7. 实际代码冗余审查（2026-10-02）

### 7.1 结论与检查范围

当前实现存在可确认的冗余，平台内部也包括在内。最需要先处理的是重复投影造成的额外写入和错误状态；其次是同一规则的多份手写实现、同一词表的独立维护，以及历史叙述进入当前运行合同。平台能力的保留与这些实现的收敛可以同时完成。

本轮执行了后端结构筛查、定向调用链阅读、前端及治理消费者核对，并由四个只读工作包分别收集平台、业务、治理和界面证据。主线复核结论、差异和关键调用者，未修改产品代码。

| 检查 | 实际范围与结果 | 结论边界 |
|---|---|---|
| 后端 Python 结构筛查 | `main/backend/app` 的 840 个 Python 文件、10,243 个函数/方法节点，全部 AST 解析成功 | 查找函数体重复；不等于逐函数完成语义审查 |
| 平台定向筛查 | `successor_runtime`、`src/mrw_functorial_kit`、`contributions` 共 306 个 Python 文件；长度至少 15 行的函数找到 11 组跨文件同体候选 | 忽略位置、注释及首个 docstring；签名、默认值、全局依赖和调用边界另行核对，候选不直接计为可删代码 |
| 词表静态核对 | 根 `scripts/` 中 15 个脚本有 19 处字面量定义，内容为同一 7 条业务线或 4 条 worker 业务线 | 未把不同版本的合同或独立测试预期自动合并 |
| 行为探针 | 两项原函数的内存隔离执行，结果见 A1/A2 | 从当前源码 AST 提取函数，使用内存替身；没有导入应用、连接数据库或访问 provider，不能作为线上集成通过证据 |
| 前端与治理 | 核对 Agent 路由、Codex 包装页、launcher 两页、Ops/Dashboard、诊断消费者及相关 CI 入口 | 未运行浏览器、Docker、构建或 CI；仓库外调用覆盖仍未知 |

代码相似度只用于发现候选。下面每个结论另给出具体规则、消费者、影响和收敛边界；不从这些局部发现推算全仓冗余百分比。

### 7.2 优先修复的行为问题

#### A1：读取 batch 状态会重复写完成事件，并改变完成时间

**确认程度：原函数隔离复现。对应 Q4，优先于一般去重。**

[GET job](/Users/wangyiliang/market-research-workflow/main/backend/app/api/agent_batch.py:1400) 和 [GET items](/Users/wangyiliang/market-research-workflow/main/backend/app/api/agent_batch.py:1438) 都调用 session 投影。[投影方法](/Users/wangyiliang/market-research-workflow/main/backend/app/services/agent_sessions/service.py:1012) 对每个已有 item 无条件更新任务、再次更新 summary、追加 `task.completed` 等事件；终态还会重新赋值 `completed_at`。方法末尾的 `last_projection` 比较只保护 job 级投影事件，没有保护前面的逐任务写入。SQL store 的 [append_event](/Users/wangyiliang/market-research-workflow/main/backend/app/services/agent_sessions/store.py:692) 每次插入新序号事件。

隔离探针使用同一份 `success` snapshot、一个已存在 item、无 verification task，连续调用原方法两次；替换时钟及 store，抑制末尾 session 同步与 memory 刷新：

| 观察 | 第一次调用后 | 第二次相同调用后 |
|---|---|---|
| `update_task` 累计调用 | 2 | 4 |
| `task.completed` 累计事件 | 1 | 2 |
| `compat.job_state_projected` 累计事件 | 1 | 1 |
| item 的 `completed_at` | 第一次观测时间 | 被改为第二次观测时间 |

这会让轮询制造重复历史，并把完成时间混成最近读取时间。另有 [session → batch metadata 回写](/Users/wangyiliang/market-research-workflow/main/backend/app/api/agent_batch.py:463)，在进程内 registry 再存一份 `current_phase`；这里是内存副本，不能称为另一份持久数据库。

**减法与保留。** 无消费者的旧聊天投影随 Q2 退出；仍有消费者的投影按实际变化写入，稳定引用保留，完成时间只在进入终态时确定。同一 snapshot 再读应不追加状态转换事件。不要等待整个旧 Agent 退役才处理这一缺陷，也不为它新建状态存储或调度器。

#### A2：写作的 async 分支没有异步执行，却隐藏已经生成的结果

**确认程度：原函数隔离复现。对应 Q5。**

[写作 API](/Users/wangyiliang/market-research-workflow/main/backend/app/api/writing.py:423) 同步调用服务。[服务](/Users/wangyiliang/market-research-workflow/main/backend/app/services/writing/llm_action_service.py:220) 已得到模板内容，随后仅因 `async_mode` 返回 `queued` 和空内容，同时调用 `complete_job`、把 readback 记为 `completed`。该路径没有排队动作。

隔离探针执行原 `try_dispatch_action`、模板函数和 capability-truth 函数；身份、权限、路由、响应构造和存储使用替身。相同 Markdown 输入得到：

| 请求 | 响应状态 | 响应正文 | 完成调用的 job/readback 状态 |
|---|---|---|---|
| `async_mode=false` | `completed` | `- A`、`- B` | 均为 `completed` |
| `async_mode=true` | `queued` | 空 | 均为 `completed` |

完成调用的 `result` 也不包含正文，[detail/history](/Users/wangyiliang/market-research-workflow/main/backend/app/services/writing/llm_action_service.py:302) 返回的是摘要，不能依靠它取得这次被隐藏的输出。`job_logger.complete_job` 把 result 合入 params 是当前存储合同，读取 params 本身没有错误。

**减法与保留。** 按 Q5 删除伪异步分支，当前模板动作统一同步返回结果；保留权限拒绝、审计、历史和项目范围。避免为维持一个没有执行者的 `queued` 状态补造异步设施。

### 7.3 平台内部的实现冗余

#### A3：同一个 Program AST 的原子遍历维护了三份

**确认程度：函数体 AST 相同，并已核对共同类型和消费者。**

[captured_values._atoms](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/substrate/postgres/captured_values.py:104)、[first_specimen_handlers._atoms](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/substrate/postgres/first_specimen_handlers.py:329)、[first_specimen_delivery_handler._atoms](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/substrate/postgres/first_specimen_delivery_handler.py:213) 各维护相同的 `Atom/Then/MapOutput/ZipOrdered/TraverseOrdered/Decide` 遍历，分别用于精确输入、效果和交付的回放检查。[原装配](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/substrate/postgres/first_specimen_assembly.py:198) 与 [C8 装配](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/substrate/postgres/c8_production.py:644) 仍引用这些消费者。

新增语法节点时，三个存储适配器都需要同步理解相同的遍历规则。收敛为语言层的一处纯遍历函数，保留三个调用者的精确匹配、错误类型及权限检查即可。这里遍历的是所有静态分支，不是选择运行中的分支；不能误换成执行遍历，也无需引入通用 visitor 框架。

#### A4：能力合同的固定拼装规则仍逐能力手写

**确认程度：同形机械规则已确认，具体业务 profile 必须保留。**

[C2.1 bundle](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/capabilities/source_library_c2_1.py:713) 与 [C2.3 bundle](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/capabilities/source_library_c2_3.py:453) 各用 67 行拼装七种 profile 引用、OperationContract、codec 和 profile map。除常量、bundle 类型和实际 profile 来源外，拼装形状相同；[C2 assembly](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/assembly/c2_assembly.py:96) 与 [native contribution](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/capabilities/source_library_c2_native_contribution.py:174) 都消费它们。当前 native contribution 仍调用这些 builder，未替它们生成这段代码。

公共合同字段新增或引用规则调整，需要重复改多个 builder。建议在现有 capability 构造位置收敛 typed profile → operation/bundle 的机械规则，作者保留对象类型、效果、权限、codec 和失败语义。C2.1 的解析与 C2.3 的 provider effect 不合并；现有 digest、profile-ref 格式与注册身份必须保持。不能直接把其他家族的不同编码规则套过来。

#### A5：七个规格模块重复读取同一份 P1 资料并计算 cell digest

**确认程度：读取与摘要责任重复；部分异常行为有差异。**

C2/C3/C4/C5/C6/C8/C9 各有本地读取/定位/digest 代码。代表位置为 [C2](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/specification/c2_p3.py:149)、[C5](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/specification/c5_p3.py:181)、[C9](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/specification/c9_p4.py:105)，实际消费者包括 [共享 fragment CLI](/Users/wangyiliang/market-research-workflow/main/backend/scripts/generate_family_fragment_shared.py:28)、exact-byte rebind 脚本及相关 generator 测试。

其中六份先建 `cell_id → cell` 字典；[C3](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/specification/c3_p3.py:210) 用 `next` 查找，缺键/重复 cell 的处理不完全相同。根路径、编码和失败语义需显式处理。建议复用既有 specification/shared generator 的一次读取与精确定位规则，各家族只给资料路径和 cell 身份；保留权威资料与各自 binding target。此项属于维护与生成过程冗余，未测量线上时延，也不建议引入跨运行缓存。

#### A6：canary 权威转换重复，但应先结合旧 Agent 退役范围处理

**确认程度：公共代码重复已确认；删并顺序依赖消费者。**

[C2.1 authority_digest](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/substrate/postgres/source_library_c2_1_canary.py:163) 与 [C6 authority_digest](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/substrate/postgres/agent_core_c6_canary.py:224) 的函数体相同；权威事件构造、work binding 校验和转换事务也存在同体或同构代码。查到的消费者主要是 Postgres canary 测试及证据生成/绑定，未确认这是当前线上请求开销。

先核对 Q2 后 C6 迁移实现是否仍需服务恢复、历史验证或共享消费者。若两家族都要保留，再共用 authority-row digest 等纯规则；事务收敛必须保留锁顺序、CAS、epoch 和审批绑定。若 C6 可随退役退出，直接减少该副本，避免先做公共 canary 框架再删除使用方。

### 7.4 业务与界面的重复实现

#### A7：彩票能力整体退役

**确认程度：原同形解析证据是 2026-10-03 前的审查结论；当前执行决定已由用户升级为整体退役。**

此前审查发现 Mega Millions 与 Powerball 的 `fetch_records` 函数体完全相同，并把彩票适配器保留在项目边界。该“保留具体游戏 adapter/handler”的决定已作废：彩票专用项目、数据采集和 MarketStat 写入/查询产品接口整体退出活动产品面。通用市场搜索、市场文档、指标点和图谱功能继续保留。

退役边界保留 MarketStat ORM/schema，仅用于既有数据随项目 schema 迁移和读取保全；本轮不清理、迁移或删除数据库中的现有记录。历史生产 evidence、冻结快照和 `ARCHIVE_CLOSED` 文档不因退役改写。

#### A8：HTML 正文定位重复三处，差异可局部表达

**确认程度：共同规则和真实差异已复核。对应 Q1。**

[raw_import](/Users/wangyiliang/market-research-workflow/main/backend/app/services/ingest/raw_import.py:91)、[url_pool](/Users/wangyiliang/market-research-workflow/main/backend/app/services/ingest/url_pool.py:639) 和 [content_extraction](/Users/wangyiliang/market-research-workflow/main/backend/app/services/ingest/content_extraction.py:179) 重复维护选择器遍历、120 字阈值和 body 回退。原入口分别承担截断、清洗，共享核另有 `[role='main']` 选择器及空输入处理。

复用正文定位核，保留入口的选择器范围、清洗顺序、截断、空输入和失败行为。直接把 raw import 改成整个 frontdoor 分析流程会扩大行为变化，不能作为这项去重的捷径。

#### A9：两个 handler 入口重复候选聚合与参数计算

**确认程度：局部共同规则已确认，完整编排有实际差异。对应 Q3。**

[resolver](/Users/wangyiliang/market-research-workflow/main/backend/app/services/source_library/resolver.py:2009) 与 [handler_cluster adapter](/Users/wangyiliang/market-research-workflow/main/backend/app/services/source_library/adapters/handler_cluster.py:45) 已调用同一 `unified_search_by_item_payload`，仍各自维护候选限额计算、站点/URL 去重、诊断汇总和写入计数。

并发计划、URL 路由、terminal-output 模式、auto-ingest 及错误去重策略并不完全相同。例如 adapter 保留重复错误文本，resolver 对文本去重；resolver 的诊断行处理也不像 adapter 那样先过滤非字典。只抽已确认相同的纯计算，差异保留为明确策略或另行修正的缺陷。把两个入口整体合并不能由当前证据支持。

#### A10：launcher 两页重复 Codex 状态与登录面板逻辑

**确认程度：静态调用及部署消费者已核对。**

[首页 app.js](/Users/wangyiliang/market-research-workflow/main/ops/launcher-ui/app.js:182) 和 [settings.js](/Users/wangyiliang/market-research-workflow/main/ops/launcher-ui/settings.js:157) 分别实现相同 CLI/auth/core 状态渲染、失败文案和 `/api/launcher/codex/status` 查询；登录按钮也重复调用相同 bootstrap 端点。[Dockerfile](/Users/wangyiliang/market-research-workflow/main/ops/launcher-ui/Dockerfile:4) 同时发布两页，它们都有消费者。

共用 launcher 内的状态/设备码显示与调用逻辑即可；首页的启停控制、设置页的配置保存保持独立。MRW token sink 与外部 Codex WebUI JWT 属于不同宿主，不把它们作为同一份冗余认证状态合并。

### 7.5 治理代码中的重复事实与过期状态

#### A11：当前诊断响应承载历史批账，已有失效结论

**确认程度：源码、消费者、测试及路径现状已核对。对应 Q6，优先处理失效事实。**

[build_evidence_matrix](/Users/wangyiliang/market-research-workflow/main/backend/app/api/business_lines.py:770) 的当前返回值有 57 处 `batch` 字面量，涉及第 66–120 批；其中混合当前探针合同、历史说明、临时证据路径和当时的通过状态。[OpsPage](/Users/wangyiliang/market-research-workflow/main/frontend-modern/src/pages/OpsPage.tsx:436) 读取批次说明，[Dashboard](/Users/wangyiliang/market-research-workflow/main/frontend-modern/src/pages/DashboardPage.tsx:118) 还消费历史树中的 reset telemetry 合同。smoke/readback/manifest 等脚本也有真实依赖，不能只按两个页面的需要删字段。

具体漂移例子：[第 87 批字段](/Users/wangyiliang/market-research-workflow/main/backend/app/api/business_lines.py:1511) 硬编码 `install_status=installed_codex_app`、spec-verified 和历史通过结果；2026-10-02 文件检查确认其指向的仓库 `automation-spec.json` 不存在，而外部 `automation.toml` 文件仍存在。[spec checker](/Users/wangyiliang/market-research-workflow/scripts/check_business_line_worker_readback_project_matrix_automation_spec.py:24) 的默认路径仍指向前者。因此这段历史安装说明不能继续充当当前配置就绪证据；未由文件存在与否推断调度器已停止或正常运行。

[单个 evidence contract 测试](/Users/wangyiliang/market-research-workflow/main/backend/tests/core_business/test_business_line_evidence_contract.py:790) 占 3,207 行，把多批历史扩展与当前合同绑在一起；[CI core-business gate](/Users/wangyiliang/market-research-workflow/.github/workflows/backend-tests.yml:362) 会选择该测试目录。问题是被锁定的历史叙述与当前职责混杂，不能把整个测试判作无效。

按 Q6 将真实字段迁入当前版本合同，历史安装/通过信息退回其历史证据位置，当前就绪状态从相应只读检查结果派生。保留 worker/readback、失败分类、恢复、Dashboard 边界和全部有效断言；不手写新的“当前已通过”替换旧的“过去已通过”。

#### A12：同一业务线词表在平台、API 和 15 个脚本独立维护

**确认程度：AST 字面量统计与消费引用已核对。**

[C9](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/capabilities/c9_evidence_matrix.py:59) 与 [API](/Users/wangyiliang/market-research-workflow/main/backend/app/api/business_lines.py:94) 各定义 7 条业务线及 4 条 worker 业务线；根目录 15 个 runner/checker/builder 又定义了 19 份相同集合。例子包括 [smoke runner](/Users/wangyiliang/market-research-workflow/scripts/run_business_line_user_flow_smoke.py:37)、[覆盖 checker](/Users/wangyiliang/market-research-workflow/scripts/check_business_line_batch_coverage.py:24)、[readback builder](/Users/wangyiliang/market-research-workflow/scripts/build_business_line_async_task_readback_artifact.py:28)。

新增业务线会触发多处手工同步，否则可能出现生产者支持而检查器拒绝、或检查器遗漏的情况。应固定当前版本词表的一个权威定义，并通过已有贡献/派生入口提供 API、runtime 和脚本需要的表示。独立脚本不应为了几个常量导入整个应用，也不应另手抄一份 scripts 专属事实源。历史版本的 checker 固定其版本身份，独立测试的预期不能全部从被测值自证。

### 7.6 本次没有判作冗余的项与实施调整

以下区分已结合代码核对：

- `language.checksum` 是 `research.codec` 的重导出；其他 digest helper 有 ASCII、dataclass、bytes、特殊值和失败规则差异。先核定编码合同，不能按名称统一全部摘要算法。
- 平台声明、执行、权限、存储、失败与恢复有实际职责；这些职责内部的机械重复仍按 A3–A6 审查，目录分层不构成免审理由。
- 两种 workflow 生命周期、两个 source handler 的完整编排、Codex WebUI 与 Python native binding 的宿主区别继续保留。
- 当前 contribution/registry 的定向核对未发现足以新增“多事实源”结论的旁路；生成表示本身不计为手写重复。
- nightly wrapper 的执行前准备与 scheduled checker 的事后证据分类承担不同角色。本轮没有证实跨 CI job 重复运行同一校验，未据脚本数量裁掉验证。
- 本地启动器与 Docker launcher 具有不同运行宿主，本轮仅确认同一 launcher 内两页的重复；未获得删除某个宿主的依据。

旧 AgentCore、旧 runtime、compat 聊天页和旧 NL 循环仍按 Q2 的用户决定退役。当前 [路由](/Users/wangyiliang/market-research-workflow/main/frontend-modern/src/app/kernel/moduleContributionRule.ts:69) 仍能进入旧页，所以它是待退出的活动路径，不是已经无人使用的死代码。`agent_core` 中仍被 Codex/业务工具消费的共享合同按依赖保留。

建议先处理 A1/A2 的状态行为和 A11 的失效事实；A3/A4/A5/A8/A10 可以在各自边界收敛。A7 已随彩票能力整体退役关闭，不再作为共享解析器抽取目标。A12 的词表 owner 与派生入口由现有集成 owner 一次确定，再迁移消费者；A9 保留策略差异；A6 结合旧 Agent 退役范围先决定是否仍需要两套消费者。既有 Q1–Q6 保留，平台公共规则和 launcher 内部复用作为本次审查新增实施面，不扩展成新的通用管理框架。

本轮交付的是有证据的审查与方案修订。两项隔离探针确认了具体行为缺陷；其他结论为静态实现与消费者证据。尚未执行修复、删除、线上迁移或性能测量，未给出可削减代码总量或性能提升承诺。

## 8. 用现有函子设施进一步精简

### 8.1 精简的对象与当前设施边界

现有设施最适合减少三类负担：同一能力事实的重复声明、由声明确定的机械构造、随这些构造重复维护的检查接线。通用平台继续保留能力、组合、权限、执行和恢复；同形能力的作者只需维护领域定义、特殊内核及必要见证，公共规则承担其余构造。

一个能力定义确定身份、输入输出、操作顺序、效果与权限。项目规则把它转换为原 runtime 能消费的合同、codec 和装配，同时投影出注册信息和检查义务。迁移的验收点在原消费者：给定相同输入、外部结果和初始状态，输出、操作顺序、权限拒绝、失败分类及写入行为应保持约定的关系。删除重复拼装属于行为保持；A1/A2 的状态修正和旧 Agent 退役属于已明确的行为变化，分别按原实施包验证。

```mermaid
flowchart LR
  D[一份原生能力定义] --> R[已有项目贡献规则]
  R --> B[合同与 codec 及装配绑定]
  B --> C[原 runtime 与业务消费者]
  R --> M[registry 与静态描述]
  R --> V[检查义务与原 runner 接线]
  K[特殊业务内核与实际资源] --> C
  C --> O[原 writer 的结果与状态]
  O --> P[只读诊断与界面投影]
```

这条路径已有实际实现，但覆盖程度不同：

| 已有承载 | 当前实际作用 | 本轮确认的边界 |
|---|---|---|
| kit `NativeContributionRule` | 组合 `lower/project/assemble/validate_binding/verification`；一次 lower 后保留同一 definition | 项目仍需实现具体转换规则；kit 不从名称推断业务语义 |
| MRW C8 native rule | 从 author source 构造 profiles、操作合同、dataclass codec、atom wiring 与装配绑定声明 | handler 和执行内核仍由能力提供；graph projection 有独立规则，pure profile 不能套到外部 provider |
| MRW C3 native rule | 从既有 bundle 派生 catalog/registry，保存 source 的 program wiring，再构造装配 | 不自动推导程序流程；原 bundle 仍是合同来源 |
| MRW C2 native rule | lower 校验 source，贡献投影读取现有 builders，显式装配委托原 assembly | 接入 contribution 尚未消除原 bundle 的手写构造 |
| kit verification | 从同一 catalog 组合检查义务、前置依赖和选择范围，接回原 runner | 不自动发现完整代码依赖；局部 definition law 不覆盖全部数据库与外部效果 |
| MRW shared family generator | 共用路径约束、精确绑定、canonical digest、确定性检查和写入入口 | 七份 P1 cell 读取规则尚需在此补齐，不能称为已完全统一 |
| 前端 module manifest | 派生 registry、路由相关描述和 renderer binding | 这是现有 TypeScript 项目规则；当前没有接入 kit compiler，页面交互仍由组件实现 |

原生贡献接口见 [kit compiler](/Users/wangyiliang/Desktop/functorial-kit/python/functorial_kit/contribution_compiler.py:30)；最完整的本地样例是 [C8 lowering](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/capabilities/c8_native_contribution.py:316) 与 [C8 装配绑定](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/capabilities/c8_native_contribution.py:532)。[C3 lowering](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/capabilities/c3_native_contribution.py:339) 从现有 bundle 出发，不能把它与 C8 作者声明的派生程度混为一谈。

### 8.2 第一优先：让贡献规则消除能力内部的机械拼装

**对应 A4。现成 compiler 可用，MRW 的 bundle 构造规则需要补一处。**

C2.1 与 C2.3 各自的 67 行 builder 都在构造 profile 引用、OperationContract、codec 和 profile map。目前 [C2 native rule](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/capabilities/source_library_c2_native_contribution.py:266) 继续消费这些手写 builder。进一步精简应把共同构造放入现有 capability 层，让旧 builder 成为薄入口或直接退出；native contribution 与原 assembly 共用同一结果。

作者仍提供实际 profile、输入输出类型、操作身份、codec 选择及领域内核。共用规则只派生这些声明已经决定的内容，不再为每个能力手填七组引用、合同字段和注册映射。优先复用当前类型与 profile 工厂；无需另造一套描述语言。

先用 C2.1 打通声明到原 assembly 的最小路径，再用 C2.3 的外部 provider effect 验证规则能容纳真实差异。两者的权限、effect profile、失败语义、codec identity、profile-ref 格式和 digest 均保留。C8 的 `network=False` 等 pure 默认值不能成为新的 C2 公共默认。

完成的依据是原消费者已使用共用构造、两份机械段退出维护、非默认声明能改变正确的产物。仅新增 contribution wrapper、同时保留旧 builder 的全部拼装，不计为精简。现成验证入口包括 [C2 catalog 测试](/Users/wangyiliang/market-research-workflow/main/backend/tests/successor_runtime/test_c2_native_catalog.py:32)、[C2.3 合同测试](/Users/wangyiliang/market-research-workflow/main/backend/tests/successor_runtime/test_p3_c2_3_contracts.py:97) 以及原 assembly 的权限和 gateway 用例。规则在两个原消费者成立后，再按同形证据逐项扩展其他能力。

### 8.3 第二优先：词表与静态描述只维护一份

**对应 A12，并支撑 Q6/A11。词表原语现成，消费者需要收敛到同一原生定义。**

业务线、worker 子集、状态或失败 code 中，已经确认属于同一版本和同一语义的成员，可由一个依赖轻的原生定义提供。用现有 `Literal/get_args` 与 [define_vocabulary](/Users/wangyiliang/Desktop/functorial-kit/python/functorial_kit/core/vocab.py:28) 建立关系，再由贡献入口投影 registry；API、C9 与脚本直接消费该定义或它的明确版本化导出。worker 子集的成员资格仍需声明，不能从名称猜测。

这里可减少的是 A12 中 API、C9 和 15 个脚本的独立字面量维护点。独立脚本只读取轻量定义或已有导出，避免为几个常量启动应用依赖。历史版本 checker 保持其版本，独立测试预期仍能发现生产词表的错误。

kit 的 `sync` 当前写出 registry、sketches 和 ownership 等 JSON，没有任意 Python/TypeScript 常量代码生成能力。跨语言消费者确有需要时，在现有投影入口补一个具体导出；同语言能直接引用的定义优先直接引用。不同领域的错误即使名称相近，也不合并为一个大 failure family。

Q6 可沿同一方式把“支持哪些能力、需要哪些探针、各字段表示什么”集中声明，再派生 API 所需的静态描述。当前是否就绪、最近一次执行是否通过，仍从相应检查结果与原事实 owner 读取。registry 有某个条目不能推出该能力已部署、已运行或已通过验收。

### 8.4 验证接线随贡献派生，共同规则集中验证

**C2/C3/C8 已有落点；后续迁移直接复用。本轮尚未确认这些验证接线中有可删副本。**

[C8 verification slot](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/capabilities/c8_native_contribution.py:632) 已把 definition law 挂到贡献规则，[C8 catalog](/Users/wangyiliang/market-research-workflow/src/mrw_functorial_kit/contributions/c8.py:36) 从同一份 native catalog 派生计划；[C2](/Users/wangyiliang/market-research-workflow/src/mrw_functorial_kit/contributions/c2.py:36) 也已有相同承载。无需为此次清简另建检查注册表。

后续共同规则可以承载“合同与原生定义对应、操作顺序保持、codec 与 profile 引用正确、投影没有获得写权限”等同形检查及其注册。每个贡献通过既有 verification 槽提供特有检查；原 runner 继续执行。原消费者完成迁移后，只删除已确认由同一机制承担的重复声明和注册。领域结果预期、拒绝路径、外部调用、事务和恢复测试仍验证实际业务行为，独立合同预期不能全部由被测声明生成答案。

kit 的局部 `complete=True` 仅针对声明的检查范围。输入或依赖不完整时，使用现有 unknown/full 回退；不能用 `inspect` 的文本命中决定完整影响范围，也不能把 `blocked/not_run` 算作通过。本轮没有证实 MRW 存在两套重复测试调度器，不新增 suite planner、持久缓存或调度配置；当前完整交付所需 gates 沿既有合同执行。

### 8.5 复用规格生成器，减少七份资料读取规则

**对应 A5。在已有共享模块补小规则即可。**

[shared_family_generator](/Users/wangyiliang/market-research-workflow/main/backend/app/successor_runtime/specification/shared_family_generator.py:1) 已承担共同的路径、序列化、摘要、绑定、确定性和输出责任。各家族继续提供 `FamilyFragmentConfig`、binding targets、特殊 fragment body 与观察代码。

在此补一处有明确输入的 P1 cell 定位/摘要函数，把七个规格模块中的共同读取段收回。根路径限制、UTF-8/canonical 编码、缺 cell 和重复 cell 的结果都必须明确；C3 的 `next` 与其他模块的字典行为差异先按合同处理。特殊 schema 留在原 body builder，历史 exact-byte 证据继续保持原义。

收益是资料读取规则和修错位置从七处收敛到一处，现有生成 pipeline 继续使用。验证复用 [共享 generator 测试](/Users/wangyiliang/market-research-workflow/main/backend/tests/successor_runtime/test_shared_family_generator_all.py:1) 与受影响家族用例；不引入跨运行缓存或新的证据库。

### 8.6 读模型与前端使用现成单向派生

**对应 A1/A11，以及现有前端 manifest 内的机械映射。**

A1 的核心改动是改变实际写入路径：batch owner 更新执行事实，保留的 session/界面投影消费事实；相同 snapshot 的 GET 不再生成新完成事件或新完成时间。kit 的 [derived 标记](/Users/wangyiliang/Desktop/functorial-kit/python/functorial_kit/core/authority.py:85) 可以表达来源与非权威身份，但它不拦截数据库写入，也不使函数自动成为纯函数。标记只在明确有消费者的返回边界复用，删除重复写入仍需修改原方法。

A11 的当前诊断视图按“静态探针说明 + 实际观测结果”构造，历史批账留在已有证据位置。当前字段、失败类型和真实消费者完成迁移后，才能删除 API 中失效的历史叙述及相应测试锁定。不要再手填一套当前通过状态。

前端 [moduleManifest](/Users/wangyiliang/market-research-workflow/main/frontend-modern/src/app/kernel/moduleManifest.ts:109) 和 [moduleRendererBindings](/Users/wangyiliang/market-research-workflow/main/frontend-modern/src/app/kernel/moduleContributionRule.ts:94) 已有单源派生。进一步可删除两份按固定前缀逐项列出的 title/nav key map：在 `defineModule` 中直接由已经传入的 `moduleKey` 构造两个 key，用现有类型检查约束结果，不再维护另一份 key 数组。现成 key 不符合规则时保留明确例外。翻译文本、页面组件、导航分组和排序是实际产品信息，继续显式维护。Q2 去掉旧聊天 variant 后，相应 renderer 分支与专属配置一并退出，不新增第二份页面贡献清单。

### 8.7 适合普通函数复用的部分

共享实现按已经确认的输入、输出、顺序和失败行为建立。以下项目无需为了套用 contribution 而增加一套协议：

| 审查项 | 最小公共实现 | 必须保留的差异 |
|---|---|---|
| A3 Program AST 三份遍历 | 语言层一个纯原子遍历函数 | 全部静态分支、既有顺序；各消费者的匹配与权限判断 |
| A8 三处 HTML 定位 | 现有抽取模块的公共定位函数 | 选择器、清洗、截断、空输入与失败行为 |
| A9 候选聚合 | 限额与聚合的纯函数 | 候选顺序、截断、错误去重策略、调度与是否写入 |
| A10 launcher 两页 | launcher 内共享查询和显示模块 | 首页启停、设置保存；不同宿主的认证状态 |
| A6 canary 同形段 | 两个消费者均保留时再共享纯 digest/转换规则 | 事务、锁、CAS、epoch 与原权限；随 Q2 退役的实现直接退出 |

尤其注意 [kit fold_ordered](/Users/wangyiliang/Desktop/functorial-kit/python/functorial_kit/core/fold.py:17) 会先按全序 key 排序，并拒绝重复 key。它不能直接替代 AST 的语法顺序遍历，也不能直接替代候选的先到顺序聚合。共享函数使用原顺序即可。

A7 原来的同形实现已随彩票能力整体退役；MarketStat ORM/schema 继续作为 persistence-only 边界保留，用于既有数据保全和 schema 迁移。

### 8.8 实施次序、依赖与本轮验证

本轮实际解释器 `main/backend/.venv311/bin/python` 导入的是本地 `/Users/wangyiliang/Desktop/functorial-kit/python`。不过 [pyproject 固定依赖](/Users/wangyiliang/market-research-workflow/pyproject.toml:5) 和 [backend requirements](/Users/wangyiliang/market-research-workflow/main/backend/requirements.txt:34) 仍指向 `785ff25e201c9eae84c862e68e786bc975e7a800`；该提交缺少 `contribution_compiler.py`、`native_contribution.py` 和 `contribution_verification.py`。本地已有 API 与按固定依赖安装的能力存在差距。进入依赖这些 API 的实现和交付时，应由集成 owner 把依赖统一到实际包含所需接口、已验证的具体版本；本轮未修改依赖或推定线上部署版本。

实施继续复用 Q1–Q6 和本节对应的代码 owner：

1. A1/A2 的行为修复、Q2 的旧 Agent 退役、A11 的失效事实清理保持优先；独立共享函数可并行收敛。
2. 集成 owner 固定词表 owner 与可用 kit 版本；能力规则 owner 用 C2.1/C2.3 完成一条真实构造路径。新规则未完成前只约束依赖它的能力迁移。
3. 在同一规则的原消费者验证后，再迁移确实同形的其他能力；规格生成器和前端映射可在各自写面独立推进。
4. 每项检查删除了哪些手写规则、减少了哪些独立事实源、哪些原消费者已使用共用结果。新规则本身的代码与验证成本一并计算；生成文件数量下降不是必要目标，新增 wrapper 数量也不计为精简收益。

本轮实际运行了 Python import 来源检查和只读 `scripts/dev.py inspect --id mrw.successor.c8.c8-2.writing.v1`，后者退出码 0、`ok=true`，成功读出该贡献的对象关系、词表与失败族。其输出明确 `complete_dependency_graph=false`，并记录一个扫描路径不存在；因此它只证明该本地声明可被当前工具读取。本轮还核对了相应原消费者与测试源码，未运行产品测试、`sync`、gates、迁移或服务。这里交付的是已核对设施的精简路线，实施效果仍按各包真实验证确认。

## 9. 清简实施框架（2026-10-03）

### 9.1 以能力及其解释关系组织实现

平台的基本单位是有身份、输入输出、允许效果、失败含义和组合关系的能力。业务流程按有序关系组合能力，具体资源由原 runtime/handler 绑定，事实由原 writer 更新，界面和诊断读取其投影。声明、执行与展示是同一能力的不同表示，表示转换只有在存在消费者和边界理由时才保留。

框架把实现收敛为以下职责。这些职责可在同一模块内承担，不要求增加目录或服务：

| 职责 | 原生承载与事实 owner | 应继续由人确定 | 应由已有规则派生或复用 |
|---|---|---|---|
| 领域定义 | 当前类型、词表、profile、失败族及能力 author source | 身份、效果、权限、顺序、领域差异 | 可从原定义确定的重复成员和引用 |
| 项目构造 | MRW native contribution rule、shared family generator、前端 defineModule | 项目规则怎样保持上述语义 | 合同、codec 选择接线、registry、模块描述和装配引用 |
| 执行与资源绑定 | Codex Core、现有业务 runtime/handler、原 assembly | 特殊执行内核、资源与失败处理 | 已支持形状的参数绑定；不再手写第二套执行循环 |
| 事实写入 | 原 job/session/material/writer 和事务边界 | 实际状态转移、权限、幂等与恢复 | 读取结果的视图，不反向写回可推导展示字段 |
| 消费与展示 | API、脚本、Codex WebUI、业务页面 | 必要版本转换、交互、排序和宿主差异 | 同一来源的标题、导航、当前诊断和其他只读表示 |
| 见证与验证 | 原测试、贡献 verification、原 runner/gates | 独立结果预期、语义反例、效果/恢复见证 | 共同规则的检查组合与确定的注册接线 |

用函子方法看，能力定义到合同/装配是一条实现解释，定义到 registry/页面描述是另一条派生解释；执行结果到诊断是只读投影。清简要求这些关系保持身份、原有顺序、权限和失败。通过具体原消费者见证相容性，不从“用了同一规则”直接推出所有运行行为等价，也不把并列模块推断成可交换执行。

### 9.2 六个需要固定的接缝

以下合同的语义在本方案已有依据；S0 只需把它们绑定到真实符号、消费者和写面。详细字段在原声明维护，不在分发文档重写第二套 schema。

| 接缝 | 实施决定 | 负责与依赖 |
|---|---|---|
| C2 profiles/operation → bundle → assembly | typed 原定义只有一份；保持 ref/digest、codec identity、effect 与权限；先 C2.1 后 C2.3 | SIMP-05 构造；SIMP-00 统一 kit 与 catalog |
| 当前业务线/worker 子集 → API/C9/脚本 | 轻量原生定义为 owner，registry 是投影；历史版本按原版本解释 | SIMP-06 首例与迁移；SIMP-11 接收后改诊断 |
| batch snapshot → 必要 session/展示 | 同 snapshot 重读不增加完成事件；终态时间由真实转换确定；退役后删无消费者投影 | SIMP-01 修复；07 退出旧入口；12 收尾 |
| 写作请求 → 同步结果/历史 | Q5 的 v2 显式表达 requested 与 actual 执行，不返回伪 queued | SIMP-02；全局类型由 00 合入 |
| Codex/native 与旧 Agent 请求 | 当前 Codex/WebUI 保留；native 选择明确，旧 runtime/NL/审批请求在 effect 前退役 | SIMP-07/08 共用合同；00 验证真实宿主和 scope |
| 实际能力/观测 → diagnostic v2 | 当前字段有唯一位置，历史叙述退出；unknown/blocked 和有效恢复/readback 合同保留 | SIMP-11；依赖 06 词表和 07 的实际退出结果 |

### 9.3 把层级职责核对放进实施

现有审查已确认局部冗余；以下三条代表链补足跨层判断。SIMP-00 在 S0 追踪原调用关系，实施中沿变化复核，在 S3 核对清理结果。它是实施设计与最终验收的一部分，不另加审批阶段。

| 代表链 | 要判定的问题 | 发现重复后的落点 |
|---|---|---|
| C2 原生定义 → 合同/bundle → contribution/assembly → 业务 handler | 哪一层确定新语义，哪一层只重新录入同一规则；哪些类型转换对应真实边界 | 公共构造归 05；catalog/共享接线归 00；保留 provider 特殊内核 |
| Codex → MRW tool → batch/必要 session → 结果读回 | 是否还套旧决策循环、重复维护阶段、读取制造事件；哪些 session 关系仍被业务使用 | 01/07/08/12 按已定文件顺序处理 |
| C9/实际探针 → API → checker/Ops/Dashboard | 是否同一词表多处录入、历史 PASS 冒充当前状态、多个 DTO 独立拥有同一事实 | 06 → 11；不削减真实探针和独立 oracle |

每个有争议的层用现成文档记录“输入/输出、实际消费者、独立职责、保留或合并理由、对应验证”。有权限/生命周期/恢复/替换边界的层保留；仅复制事实或没有观察差异的手写转发归原 owner 收敛；尚未核清的消费者具名保留并写明解除条件。不能为完成层级审查新建通用 runtime、DTO 平台或审批账本。

### 9.4 分发与最终收口

执行采用 [四阶段分发包](/Users/wangyiliang/market-research-workflow/docs/development/MRW清简分阶段实施分发包.md) 的 13 个职责包。规则建设与规则使用在同一 owner 内串行打通首例；其他独立包直接并行。共享文件先交接，测试按真实资源排队，失败只阻断所属依赖。

“足够干净”的标准是：一个事实只有一个维护位置；共同规则只有一份实现且原消费者已经使用；每个保留层都有真实职责；旧执行连同入口、分支、专属配置/诊断和测试完整退出。新增同形能力只提交领域差异、特殊内核和必要见证，已确定的表示不再要求多处人工同步。新规则和验证自身的维护成本计入收益。

局部等价性、实际行为修正、功能退役分别验证。所有已确认重复完成处置，适用用户链及 gates 通过，必要运行未观察项如实列出；满足真实完成条件后停止继续抽象。本框架已按分发包完成产品实施和必要验证；旧生产发布阶段保持原已停止状态。最终结果统一见分发包 §7.3。
