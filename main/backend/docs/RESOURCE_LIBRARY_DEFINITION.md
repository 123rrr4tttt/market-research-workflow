# 信息资源库定义

> 最后更新：2026-10-26 | 文档索引：`docs/README.md`

## 1. 核心概念

### 1.1 Item（来源项）

**定义**：特定类型的信息来源集合。

- 一个 item 是一组信息源的聚合（如 URL 列表、子论坛列表、关键词集合等）
- item 只描述**来源是什么**，不描述**怎么访问**的具体参数
- 通过 `channel_key` 关联到可访问性适配器

### 1.2 Channel（通道）

**定义**：信息来源的可访问性适配。

- 网页抓取工具、API 客户端、JSON 访问类型等
- 负责将「来源」转换为可执行的采集请求
- 例如：`url_pool`（URL 抓取）、`reddit`（Reddit API）、`google_news`（新闻 API）

**各通道的「来源」字段**（item.params 或 override_params 中提供）：

| channel_key | 来源字段 | 说明 |
|-------------|----------|------|
| `reddit` | `subreddits` | 子论坛列表（或 `base_subreddits`） |
| `google_news` | `keywords` | 关键词列表 |
| `policy` | `state` | 州/地区标识 |
| `market` | 来自 override | 关键词/查询词由采集页 override_params 提供 |
| `url_pool` | `urls` | URL 列表；若无则从资源池按 scope/domain/source 拉取 |

### 1.3 来源采集（Source Collection）

**定义**：在一个 item 中，对每个来源（如 URL）发送符合 channel 的参数，通过 channel 进行信息采集。

```
item（来源集合）
    → 遍历 item 中的每个来源
    → 构造符合 channel 的请求参数
    → 通过 channel（适配器）执行采集
    → 入库
```

## 2. 职责边界

| 模块 | 职责 |
|------|------|
| **资源库** | 来源集合、可访问性适配（channel）、资源可访问性 |
| **采集配置** | 需特定结构的访问（论坛结构、子论坛、平台等）、采集事件与调度 |
| **采集页** | 运行时参数（limit、时间范围、语言等）、触发执行 |

## 3. 数据流

```
资源库：item + channel
    ↓
采集配置：结构参数（若需要）
    ↓
采集页：运行时参数（override_params）
    ↓
run_item_by_key：merge 后通过 channel 执行
```

## 4. 方式 B：URL→Channel 路由

当 item 的 `params.urls` 存在且非空时，采用 **URL→Channel 路由** 模式：

- 每个 URL 按 `url_channel_routing` 配置解析出对应的 `channel_key`
- 配置位于 `ingest_config`（config_key: `url_channel_routing`），payload 格式：

  ```json
  {
    "rules": [
      { "pattern": "default", "channel_key": "url_pool" },
      { "pattern": "reddit.com", "channel_key": "reddit" },
      { "pattern": "default", "path_suffix": ".xml", "channel_key": "generic_web.rss" },
      { "pattern": "default", "path_contains": "sitemap", "channel_key": "generic_web.sitemap" }
    ]
  }
  ```

- 规则按顺序匹配；先匹配 domain，再匹配 path 约束（若有）：
  - `pattern`：`"default"`（匹配全部）、前缀（如 `"news."`）、包含（如 `"reddit.com"`）
  - `path_contains`（可选）：URL path 须包含该子串
  - `path_suffix`（可选）：URL path 须以该后缀结尾（如 `".xml"`、`"/feed"`）
  - `path_prefix`（可选）：URL path 须以该前缀开头
- 工具型 channel 示例：`generic_web.rss`、`generic_web.sitemap`、`generic_web.search_template`、`official_access.api`
- 未匹配时回退到 `url_pool`

## 5. Item 查询链的自动构造（2026-10-11 定稿）

本节扩展来源项定义：一个来源集合必须能导出查询执行计划，以及每个成员当前可执行、待发现或受阻的具体原因。构造查询链不保证任意站点都有检索接口，也不保证任意查询都有命中。合法的辅助来源、目录和仅供审阅的 item 仍可保存；查询请求必须把未执行的成员显式报告，不能把机械探测未命中解释为来源不存在。

### 5.1 来源、局部契约与整条链

Item 和其中的来源保持原身份。一个站点可能提供搜索表单、官方 API、RSS、sitemap，也可能只有根地址。`supports_query_terms=false` 只描述该入口当前已知的直接查询能力，不否定同站点可发现其他入口或可通过受允许的外部搜索获得候选。

在固定项目、来源身份和访问权限的上下文中，来源声明构成对象；接口发现、查询、抓取、解析是有序的操作。发现结果形成依赖于具体来源的局部契约族，每个契约携带候选来源、实际检查和适用范围。它们通过原 `ItemResolver` 和 `handler.cluster` 组织成 item 的执行，不另建 scheduler 或 Runtime。来源集合的并集不授予额外权限，来源间的并发还取决于请求预算、共享 provider 和原执行器的资源限制。

$$
\operatorname{Declaration}(s)
\xrightarrow{\mathrm{derive}}
\operatorname{Plan}(s)
\xrightarrow{\mathrm{discover\ and\ validate}}
\operatorname{LocalContract}(s)
\xrightarrow{\mathrm{search}}
\operatorname{Candidate}(s,q)
\xrightarrow{\mathrm{fetch}}
\operatorname{Response}
\xrightarrow{\mathrm{parse}}
\operatorname{Record}.
$$

`derive` 是无网络的投影。其后每条箭头均由现有执行入口解释，并受既有授权与失败边界限制。局部契约有效性是具体检查上下文下的判断，不能由静态类型、HTTP 200 或一个猜测 URL 推出。这里仅主张有序组合及来源身份可追踪，不主张不同来源的执行可交换，也不主张有限探测已覆盖站点全部入口。

### 5.2 自动构造与执行的边界

| 对象或动作 | 含义与权威位置 |
| --- | --- |
| Item 声明 | `item_writer.upsert_project_item` 规范化、验证并保存；原 item writer 保持事实写入权 |
| Query readiness | `item_plan.build_item_query_readiness` 的纯派生结果；不写回 `extra`，不发网络请求 |
| Entry 与已保存契约 | 原 site-entry writer 拥有事实；运行中的候选/验证结果不能自行覆盖它 |
| Candidate-source plan | `candidate_source_plan` 从声明和策略导出将尝试的路线；不是执行日志 |
| Query-time discovery | 原查询消费者在请求预算下发现并检查入口；临时契约仅用于本次调用 |
| Search/fetch/parse 结果 | 原消费者和 provider 返回的实际观察；保留 HTTP、领域 Failure 和解析错误归属 |
| 调度、URL 入池、文档入库 | 各自沿原明确开关和 writer 执行；item 的保存、批准、启用与 readiness 均不代为授权 |

`schedule=null`、`write_to_pool=false`、`auto_ingest=false` 和现有终端输出模式必须原样保留。自动构造是查询请求的准备和解释行为，不建立后台轮询、自动调度或隐含入库。

### 5.3 纯派生 readiness

`source_library.item_query_readiness.v1` 描述声明是否足以选择下一条合法路线，而非网络可达性。成员状态为 `ready`、`discovery_required`、`not_applicable` 或 `blocked`。直接配置的搜索模板、原生 feed/sitemap 或已有原消费者支持的 API 可以是静态 `ready`；未知 domain root 为 `discovery_required`；查询语义不适用的合法来源为 `not_applicable`；禁用、配置不一致等有明确原因的情况为 `blocked`。不能把未知当成 `blocked`。

结果包含 `entry_rows`、按状态计数、原因、`automatic_assembly=true` 与 `network_verified=false`。没有提供 site-entry 定义时只能从 item 自身声明保守推导。整组有待发现成员时汇总为 `discovery_required`，其余成员仍可执行；只有全组无可尝试查询路线且有实际阻碍时汇总为 `blocked`。全部不适用时为 `not_applicable`。汇总不替代逐成员状态，也不改变 item 保存的合法性。

### 5.4 查询时的积极发现

入口不足时，先复用现有已保存模板、首页真实表单、明确链接、alternate feed 和现有发现逻辑。常见路径和 Agent 推断只产生待检查候选。候选至少保留原来源 URL、提出方式、证据 URL/表单位置及提出的模板；同一来源不同候选的身份不能被一个 `best_template` 覆盖。

原 `search_contract_discovery.resolve_query_contract` 在有界网络调用中返回 `verified`、`unresolved`、`blocked` 或 `budget_exhausted`。`verified` 只表示本次探测已经取得足以交给原消费者的正向结果；零命中、无解析结果、通用首页响应、仅 HTTP 成功或 LLM 推荐均不足以证明搜索契约。不得由外部搜索的成功冒充站内模板的验证成功。

网络请求继续经过 `resource_pool.http_port` 和原 composition adapter。自动探索必须在发请求前检查目标权限、协议、公共地址与同源约束，重定向逐跳检查；读回 `final_url` 后才拒绝不能防止此前的越界请求。若原端口不能保证这些条件，具体报告 `unsafe_target_policy_unavailable`，由端口 owner 补齐；不能在发现模块另开一个绕过端口的 HTTP 客户端。跨源搜索服务沿原 provider 权限执行，不能借同站点探索自动访问任意第三方地址。

探索预算限定候选数、请求数、每次超时及总截止时间；底层重试、重定向和备用服务均计入实际预算。预算由当前调用解释，不能为每个分支重新获得一份无限额度。到期停止新请求并保留已经取得的局部结果。

机械探测仍未解决时，受允许的 `execute_external_site_search` 可以独立获得该域候选，并明确标为外部搜索来源。未解决的接口同时产生 `exploration_request`，包含项目、item、来源、查询、尝试记录、具体 gap、剩余预算与建议动作。已注册的 `source.discovery.plan` 负责规划，`source.web.search` 允许运行中的项目 Agent 主动搜索接口线索、同站资料和不同查询表达。`auto_classify.use_llm` 目前仅分类 URL，不是该探索动作的实现。

项目内所有 Agent 调用统一经过现有 Cell 中继：`exploration_request` 交给真实绑定项目的 Cell-bound Agent，对话、辅助推断、接口探索、委派、工具调用及结果回传均保持 Cell 的项目身份、授权与预算边界，原 Runtime 和事实 owner 不变。`auto_classify.use_llm` 与原 `search_capabilities` 语义扩展/候选选择的 `model.invoke` 直调尚未符合该约定，属于已确认的能力接入缺口，不是完整全仓审计清单。本次查询接口验证强制 `allow_candidate_semantic_llm=false`，不调用原直接模型推断；未匹配候选继续以探索请求交 Cell-bound Agent 判断。验证以外的旧语义匹配和分类路径仍需接入 Cell，不能声称已完成全量 LLM 迁移。Cell 不可用或绑定/工具缺失时保留具体 gap，禁止静默改走 direct provider、Agent SDK 或未绑定 Agent。

Agent 提案必须再次走相同检查与原查询消费者；不能把提案直接当作可执行接口或材料证据。需要浏览器交互、登录、验证码、站点脚本或未注册的探测工具时，显式说明能力/权限缺口。探索请求本身不等于已调度工作，不得报告 `enqueued=true`，除非有原工作流真实登记结果。托管对话、普通临时子 Agent 和临时脚本不能替代项目运行中的 Agent 产生探索完成证据。

### 5.5 阶段观察与兼容

`service_chain` 和 readiness 保持计划语义；实际调用另记 `executed_chain` 和阶段状态。搜索未执行、搜索执行但空结果、候选已找到但抓取失败、响应存在但解析失败、解析成功但未获写入权限必须可区分。搜索候选不是已抓取正文，正文不是解析记录，解析记录也不是已入库事实。下游未执行时报告 `not_run` 及依赖原因；原消费者没有足够观察时报告 `unknown`，不得由上游候选数量推定解析成功。

本次为原消费者的扩展。旧 item 按当前声明即时派生 readiness，不要求一次性重写所有历史 items；非 site-search 类型、external-project item 和已有 URL 路由继续由各自原消费者解释。合法 `auxiliary`/review-only 的来源角色不以本次新枚举取代，是否适用沿现有声明判断。实现包与验收见 `RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md` 第 2026-10-11 更新节。

## 6. 外部库分类与项目参数规格（2026-10-26）

`app/services/source_library/external_integration.py` 是外部集成规格的唯一声明位置。实验适配池通过既有同步工具复制这份纯模型，JSON Schema 从模型派生，不独立维护另一套字段或验证规则。一个条目绑定一种执行接口、一种访问方式和一个项目；同一库的匿名/登录接口可以登记为不同 `item_key`。它们共用参数模型，但不合并账号或权限。

分类有三个独立维度：

| 字段 | 当前取值 | 含义 |
|---|---|---|
| `integration.framework_type` | `api_client`、`browser_client`、`media_downloader`、`feed`、`parser`、`crawler` | 库提供的功能类型 |
| `execution_mode` | `http_api`、`python_library`、`cli_or_container`、`rss_feed`、`sitemap`、`article_extractor` | 复用原 provider registry 的执行接口 |
| `integration.access_mode` | `anonymous`、`api_key`、`oauth2`、`account_login`、`session` | 当前条目选择的访问方式 |

`parameters` 是以 `kind` 区分的参数族。`config` 声明普通值的类型（string/integer/number/boolean）；`credential` 只接受 `env:NAME` 引用；`registration` 声明开发者注册或研究访问审批入口。`bindings` 必须包含 `project_key`，分别以 `config`、`credential_refs`、`registrations` 绑定相同的参数 key。重复定义、未知 key、跨种类绑定和错误值类型会被拒绝。用户名、密码、API key、API hash、cookie、会话信息应使用凭据引用；模型不读取环境变量、不保存凭据值，也不执行登录。普通配置及描述字段应只填写非敏感元数据。

注册状态可填 `pending`、`approved`、`denied`；缺失保留为未配置。`approved` 仅表示用户声明，`license` 也仅记录使用者提供的许可证标识，不构成平台授权或许可核验。`configuration_ready` 表示必填普通参数和凭据引用齐备、必需注册已声明 approved；`credentials_verified` 始终为 false。凭据引用是未来复用 MRW `runner.resolve_credential` 的输入标识，本轮未接通其解析与注入。

例如，API key + 开发者注册使用如下同型规格（示例地址及引用不是真实账号）：

```json
{
  "item_key": "social.demo.api",
  "name": "Social API example",
  "project_link": "https://example.com/developer",
  "source_scope": "social_media",
  "execution_mode": "http_api",
  "runner_ref": "https://example.com/api/search",
  "integration": {
    "framework_type": "api_client",
    "access_mode": "api_key",
    "parameters": [
      {"key": "api_key", "kind": "credential"},
      {"key": "developer_app", "kind": "registration", "registration_url": "https://example.com/register"},
      {"key": "page_size", "kind": "config", "value_type": "integer", "required": false}
    ],
    "bindings": {
      "project_key": "organization-investigation",
      "config": {"page_size": 20},
      "credential_refs": {"api_key": "env:SOCIAL_API_KEY"},
      "registrations": {"developer_app": "pending"}
    }
  }
}
```

同一个模型也可表示 twscrape/Instaloader 类会话库：使用 `python_library` 接口和 `session` 访问方式，声明会话凭据参数；这不表示这些库已安装或其 runner 已注册。

### 6.1 接入 MRW 的路径与版本

1. `GET /api/v1/source_library/external-projects/integration-schema` 返回模型派生的 JSON Schema。
2. `POST /api/v1/source_library/external-projects/prepare-integration?project_key=...` 接受上述规格，返回原 Item 形状及 readiness。该入口不调用 Cell/LLM、不写业务库、不发起 HTTP 抓取；保留原 manifest URL 校验可能进行的 DNS 解析。
3. 将返回的 `data.item` 交给原 `POST /api/v1/source_library/items?project_key=...`，由原 writer 校验并持久化；写入项目必须与 `integration.bindings.project_key` 一致。准备接口本身不等于已保存。

纯 `IntegrationSpec.to_mrw_item()` 与实验池导出使用同一投影，产出 `external_project.manifest` 通道的禁用 Item，参数规格保存在 `extra.external_project_manifest.integration`。manifest 使用新身份 `external_item.manifest.v2`，原 v1 行为保持；v1 携带 integration 会被拒绝，旧 MRW 也会拒绝未知 v2，避免静默丢失访问要求。

v2 只通过声明的 bindings 管理参数，暂不接受旧 `runtime`/`runtime_config` 的非空配置；公开项目、注册和 HTTP runner 地址不接受 userinfo、query 或 fragment。未来接通执行须明确定义参数到注册 runner 的注入，查询值也须通过该映射传入。参数齐备仍返回 `execution_available=false`、`integration_runtime_not_connected`；手动启用 Item 不能绕过原 runner 的 v2 拦截。规范化与读回保留 integration，readiness 是从它派生的只读观察，不成为凭据或授权的事实源。
