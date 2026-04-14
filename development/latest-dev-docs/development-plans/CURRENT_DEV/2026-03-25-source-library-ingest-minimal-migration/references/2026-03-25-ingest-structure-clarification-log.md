# Ingest 结构澄清迭代记录

Updated: 2026-03-25 PST

## 目的

这份文件用于记录 `ingest / source-library / frontdoor` 链路的渐进式结构澄清和候选架构调整。

当前记录规则如下：

- 一次只记录一个结构修改
- `current structure` 和 `proposed structure` 分开描述
- 每一项都配一个专用 `.drawio` 用于讨论
- 后续修改持续追加到同一条澄清轨道里，直到整体架构更容易理解

关联基线文档：

- `./2026-03-25-source-library-to-db-service-flow-investigation.md`

关联图文件：

- `2026-03-25-ingest-structure-clarification-log.drawio`

建议优先查看 `draw.io` 里的最新版主图：

- `modification-2-actual-code-flow`

这页按真实代码调用重画了主流程：

- 只保留真实函数、真实对象、真实 admission
- `frontdoor` 统一接收 `ingress_envelope`
- `source_library terminal_output` 这条线会进入 `records-only defer`
- `url_pool` 和 direct provider 这两条线会进入 `document_candidate accept`
- 不再使用 `line / binding / engine` 这类解释层节点做主图

旧的抽象页仍保留，主要用于回看之前的推理轨迹；但当前讨论应以 `modification-2-actual-code-flow` 为准。

### 当前主图的代码口径

这页主图只表达下面三条真实路径：

1. `source_library terminal_output -> frontdoor defer`
   - `handle_handler_cluster(...) / unified_search_by_item_payload(...)`
   - 产出 `candidates + records`
   - `build_source_library_ingress_envelope(...)`
   - `run_postprocess_frontdoor(...)`
   - `admission = defer`

2. `url_pool / routed URL fetch -> frontdoor accept`
   - `collect_urls_from_list(...)`
   - `ingest_url_via_source_library_frontdoor(...)`
   - `run_item_with_url_routing(...)`
   - `_build_document_candidate_from_record(...)`
   - `build_frontdoor_ingress_envelope(...)`
   - `run_postprocess_frontdoor(...)`
   - `persist_terminal_document(...)`

3. `direct provider content -> frontdoor accept`
   - `policy / social / market direct-content path`
   - `build_frontdoor_ingress_envelope(...)`
   - `run_postprocess_frontdoor(...)`
   - `persist_terminal_document(...)`

## 结构修改 1

### 标题

Batch URL ingest should route first, then enter frontdoor.

### 问题描述

当前批量 URL 入口在逻辑上被拆散在这些函数里：

- `collect_urls_from_list(...)`
- `ingest_url_via_source_library_frontdoor(...)`
- `run_item_with_url_routing(...)`
- `run_postprocess_frontdoor(...)`

当前实现里，`collect_urls_from_list(...)` 仍然是 batch orchestrator，但每个 URL 都会先经过一次 `ingest_url_via_source_library_frontdoor(...)` 包装，然后再由它对单个 URL 调用 `run_item_with_url_routing(...)`。

这意味着实际执行模型是：

1. batch ingest entry
2. per-URL wrapper
3. per-URL routing
4. per-URL frontdoor
5. 回到 batch 层汇总

这套实现可以工作，但从架构视角看不够清晰，原因是：

- batch 入口看起来像 ingest writer，但同时又承担了 URL dispatch shell 的职责
- routing logic 在 `source_library/resolver.py`，而 batch orchestration 在 `ingest/url_pool.py`
- 这个 per-URL wrapper 把更直接的概念模型遮住了

### 当前结构

```text
collect_urls_from_list
  -> for each URL:
     -> ingest_url_via_source_library_frontdoor
        -> run_item_with_url_routing
        -> build_frontdoor_ingress_envelope
        -> run_postprocess_frontdoor
        -> persist_terminal_document
```

### 建议结构

```text
batch URL runtime entry
  -> collect_urls_from_list
  -> batch routing primitive
     -> run_item_with_url_routing (batch URL set)
  -> middle outputs
     -> by_url / records / stats / rejection breakdown / diagnostics
  -> frontdoor handoff
     -> record-to-document_candidate or records-only ingress decision
     -> build_frontdoor_ingress_envelope / run_postprocess_frontdoor
  -> writer output
     -> persist_terminal_document
  -> batch aggregate + compatibility output
     -> inserted / skipped / rejected / degradation_flags / debug
  -> preserve single-URL compatibility path
     -> ingest_url_via_source_library_frontdoor
```

### 澄清后的边界

这次澄清希望明确的边界是：

- `batch URL runtime entry`
  - 必须显式保留 batch 入口，而不是在图里直接从 routing 开始
  - 负责接住上游 ingest service / provider 调用 `collect_urls_from_list(...)`
  - 保留 batch 级参数、聚合结果、debug 输出和兼容返回面

- `source_library/resolver.py`
  - 负责 URL routing
  - 决定哪个 channel 抓哪个 URL
  - 返回 routed `by_url / records / stats / legacy_counts / errors`
  - 保留并发、timeout、crawler fallback、per-URL diagnostics 这些真实功能

- `ingest/url_pool.py`
  - 负责 batch ingest orchestration
  - 处理 batch normalization、aggregate metrics、debug、rejection accounting、degradation flags
  - 负责把 routed records 送进 frontdoor，而不是把 single-URL wrapper 当作主结构
  - 但仍要保留 `ingest_url_via_source_library_frontdoor(...)` 作为兼容入口

- `postprocess_frontdoor.py`
  - 负责 normalization、quality gates、structured extraction 和 writer dispatch

- `frontdoor ingress contract`
  - batch path后面仍然要收敛到 `ingress_envelope`
  - 不能把 frontdoor 前的交付物粗暴抹平成“直接写库”
  - 需要明确区分：
    - `document_candidate -> accept`
    - `records-only -> defer`

- `batch aggregate / compatibility output`
  - 不只是最终 inserted 数字
  - 还要保留：
    - `inserted / updated / skipped`
    - `inserted_valid / rejected_count / rejection_breakdown`
    - `degradation_flags / debug`
    - 兼容 single-URL 入口和现有上游调用面

### 为什么这样更清晰

主要收益：

- 心智模型可以收敛成 `batch entry -> routing -> middle outputs -> frontdoor -> aggregate`
- routing 会变成一个更明确、可复用的底层 primitive
- batch ingest 不再表现成每个 URL 都“包装一次再重新进入”同一条概念链路
- 单 URL 兼容路径和 batch 主路径会被明确区分，不再混在主图里
- `by_url / records / diagnostics / rejection_breakdown` 这些真实中间产物不会被误删
- 后续做 batch 优化会更自然
- 图上也会更容易读，因为 batch orchestration 和 routing 不再交错

### 重要说明

这次澄清记录的是目标结构，不是已经完成的 refactor。

当前代码路径仍然有效，应理解为：

- batch orchestration in `collect_urls_from_list`
- single-URL routing and frontdoor in `ingest_url_via_source_library_frontdoor`
- `run_item_with_url_routing(...)` 仍然返回 `by_url / records / stats / legacy_counts / errors`
- batch 返回面仍然要保留 aggregate metrics、rejection accounting、debug 和 degradation flags

所以这份文档是在记录期望的收敛方向，不表示仓库当前已经完成对应改造。

### 候选改造方向

后续比较合理的 refactor 形态可能是：

1. add a batch-capable routing entry under `source_library/resolver.py`
2. let `collect_urls_from_list` call that routing entry once per batch or batch-slice
3. introduce a record-to-frontdoor bulk handoff utility under `ingest/url_pool.py`
4. keep `by_url / records / stats / rejection_breakdown / diagnostics` as explicit middle outputs
5. keep metrics / debug / rejection accounting / degradation flags at the batch ingress layer
6. preserve single-URL entrypoints as a thin compatibility path
7. 在重构过程中把 `routing` 相关命名改成更贴合实际职责的名字，避免继续用 `routing` 指代“选路 + 抓取执行 + 结果整理”的混合流程

### 对照当前实现后必须保留的功能点

后续如果真的按这条思路改结构，下面这些能力不能在“batch route first”重写里被抽掉：

1. `collect_urls_from_list(...)` 仍然要是稳定的 batch runtime entry，而不是只剩内部 helper。
2. `ingest_url_via_source_library_frontdoor(...)` 仍然要保留，作为 single-URL compatibility path。
3. `run_item_with_url_routing(...)` 的 `by_url / records / stats / legacy_counts / errors` 不能被压缩没了。
4. 并发、timeout、crawler fallback、per-URL diagnostics 不能因为改成 batch 路由而丢失。
5. frontdoor 前仍要明确经过 `ingress_envelope` contract，而不是直接把 record 塞 writer。
6. `document_candidate accept` 和 `records-only defer` 的语义不能混掉。
7. batch 结果除了 `inserted / skipped / rejected`，还要保留 `rejection_breakdown / degradation_flags / debug`。
8. 现有 provider/ingest service 对 `collect_urls_from_list(...)` 的调用面不能被静默打断。

### 影响组件

- `main/backend/app/services/ingest/url_pool.py`
- `main/backend/app/services/source_library/resolver.py`
- `main/backend/app/services/ingest/postprocess_frontdoor.py`
- `main/backend/app/services/ingest/terminal_writer.py`
- `main/backend/app/services/resource_pool/unified_search.py`

### 当前状态

- status: proposed clarification
- implementation: not started
- confidence: high
- intended outcome: 在更大范围的 ingest 架构整理前，先把 batch entry / routing / middle outputs / frontdoor handoff / aggregate-compat 边界说清楚

## 结构修改 2

### 标题

Reframe the architecture around the real pre-frontdoor `ingress_envelope` contract.

### 问题描述

重新梳理后，原来的主图仍然有三个根本问题：

1. 把 `channel` 误画成了一层 service  
   但实际上 `channel` 只是 `item` 里的来源匹配元数据，用来把请求绑定到合适的执行实现，不应该单独被理解成一个 service。

2. 把 `public mode` 和 `execution strategy` 继续画成并列 service  
   例如 `channel search`、`single_channel_search`、`provider_harvest_service` 这类名字，本质上都不是稳定的业务 service，而更像“计划阶段里的一个分支”或“绑定后的执行路径”。

3. 把 frontdoor 前的 contract 画错了  
   当前代码里 frontdoor 真正接收的是 `ingress_envelope`。其中：
   - `collection_payload.document_candidate` 会进入 `accept` 路径
   - `collection_payload.records` 只会进入 `defer` 路径，不会直接写入
   所以前面的主图把“frontdoor 前统一交付物”直接画成 `document_candidate` 是不准确的。

所以现在更合理的理解不是：

`channel -> mode -> service -> engine`

而是：

`definition/runtime entry -> execution line -> execution binding -> concrete engine -> middle outputs + side effects -> ingress_envelope -> frontdoor/output -> compat/observability`

重新整理后，真正有意义的层次应该是：

- `definition/runtime entry`
  - 包含来源库定义同步、effective item/channel 合并、API/collect runtime/task 入口
  - `channel` 不是稳定业务 service，但它仍然是稳定的配置实体和 binding key
  - 这里不能丢：
    - `loader.py / sync.py`
    - `list_effective_channels / list_effective_items`
    - `/api/v1/ingest/source-library/run`
    - `run_collect / SourceLibraryAdapter.run`

- `execution line`
  - 决定这次运行走哪条主线
  - 到 frontdoor 前主要只有两条：
    - `candidate_discovery -> optional url_materialization -> ingress_envelope`
    - `direct_url_or_provider_materialization -> ingress_envelope`
  - 这里的 `source_mode` 更适合被理解成兼容视角下的 runtime projection，而不是最终想保留的主分层名字

- `execution binding`
  - 根据 `item + channel config + execution line` 绑定到具体实现
  - 这一层才会用到：
    - `run_channel(...)`
    - `handler_registry`
    - 各种 route / adapter dispatch

- `concrete engine`
  - 真实执行代码
  - 例如：
    - `handler.cluster / unified_search_by_item_payload(...)`
    - `run_item_with_url_routing(...)`
    - `handle_google_news / handle_reddit / handle_market / handle_policy`

- `middle outputs + side effects`
  - frontdoor 前不能只剩一个抽象对象
  - 仍然要保留这些真实中间语义：
    - `candidates`
    - `records`
    - `by_url`
    - diagnostics / fallback / concurrency stats
  - 仍然要保留这些 side effects：
    - `append_url / upsert_site_entry`
    - `resource_pool_urls / resource_pool_site_entries`
    - provider 跳转已有 ingest service 的旁路

- `ingress_envelope`
  - frontdoor 前唯一统一 contract
  - 但内部存在两种合法形态：
    - `document_candidate ingress`
    - `records-only defer ingress`

- `frontdoor / output`
  - `run_postprocess_frontdoor`
  - `persist_terminal_document`
  - `sources / documents`

- `compat / observability`
  - 不是主业务分层，但必须显式保留
  - 包括：
    - `terminal_output`
    - `frontdoor_ingress / postprocess_frontdoor` compatibility output
    - `start_job / complete_job / fail_job`
    - `etl_job_runs`
    - stats / debugging / traceability

### 当前结构

```text
item
  -> channel
  -> ItemResolver.resolve(...)
     -> source_mode in {
          protocol_search,
          provider_harvest,
          site_search,
          url_execution
        }
  -> run_item_payload(...)
     -> site_search 时改写到 handler.cluster
     -> run_channel(...)
        -> handler_registry / handle_xxx(...)

问题在于：
- channel 被画成像 service
- source_mode 被画成像 service
- engine 又反过来暴露成 channel
- frontdoor 前的真实 contract 被画错了
```

### 建议结构

```text
definition sync / effective config / runtime entry
  -> loader / sync
  -> list_effective_channels / list_effective_items
  -> API / task / collect runtime / SourceLibraryAdapter
  -> item + channel config
  -> execution line
     -> line A: candidate_discovery
        -> optional url_materialization
     -> line B: direct_url_or_provider_materialization
  -> execution binding
     -> run_channel / registry / route dispatch
  -> concrete engine
     -> handler.cluster / unified_search
     -> run_item_with_url_routing
     -> provider handlers
  -> middle outputs + side effects
     -> candidates / records / by_url
     -> resource_pool writes
     -> provider -> existing ingest service
  -> pre-frontdoor unified contract
     -> ingress_envelope
        -> document_candidate accept path
        -> records-only defer path
  -> frontdoor / output
     -> run_postprocess_frontdoor
     -> persist_terminal_document
  -> compat / observability
     -> terminal_output / legacy result / job logging / etl_job_runs
```

### 澄清后的边界

这次重整后，希望边界收敛成：

- `definition / runtime entry`
  - 是主图里必须显式出现的第一层，不只是背景信息
  - 负责来源定义同步、effective source 合并、运行入口、异步任务边界、project 绑定
  - 包括：
    - `loader.py / sync.py`
    - `list_effective_channels / list_effective_items`
    - `/api/v1/ingest/source-library/run`
    - `run_source_library_item_compat / run_collect / SourceLibraryAdapter.run`

- `channel`
  - 不是 service
  - 主要承担 config entity + binding key 的角色
  - 用来把 item 绑定到合适的 execution implementation

- `execution line`
  - 才是第二层
  - 负责决定前 frontdoor 主线
  - 回答“这次是先发现候选，还是直接 materialize”
  - `source_mode` 在现阶段仍是重要运行语义，但更适合作为兼容口径和 runtime projection 保留

- `execution binding`
  - 才是第三层
  - 负责根据 line 和 channel metadata 选具体实现
  - 包括 `run_channel(...)`、registry dispatch、route dispatch

- `concrete engine`
  - 才是真正的 service / engine 层
  - 包括 `handler.cluster`、`run_item_with_url_routing(...)`、各类 provider handler

- `middle outputs + side effects`
  - 这一层必须显式保留，不然会把真实运行能力误删掉
  - 包括：
    - `candidates / records / by_url`
    - batch / concurrency / timeout / crawler fallback / per-URL diagnostics
    - `append_url / upsert_site_entry`
    - provider 跳转已有 ingest service 的旁路

- `ingress_envelope`
  - 是 frontdoor 前唯一统一 contract
  - 不管上游来自 candidate discovery 还是 direct URL/provider materialization，最终都要收敛到这里
  - 其中只有 `document_candidate` 形态会走 `accept`
  - `records` 形态在 `run_postprocess_frontdoor(...)` 里会被标记为 `defer`

- `compat / observability`
  - 这层不该被压扁到图外
  - 必须保留：
    - `terminal_output` 的统计口径
    - `frontdoor_ingress / postprocess_frontdoor` 兼容输出
    - `start_job / complete_job / fail_job`
    - `etl_job_runs`
    - trace/debug/stats

### 为什么这样更清晰

主要收益：

- 第一层把“定义同步 / effective config / runtime entry”明确放回图里，不再误以为架构从 `ItemResolver` 才开始
- 第二层不再出现伪命题式的 `channel search`
- 第三层不再继续平行堆一排“看起来像 service 实际不是 service”的名字
- `channel`、`line`、`binding`、`engine`、`middle outputs`、`ingress contract`、`compat/observability` 七种概念拆开
- `handler.cluster`、`url_pool`、`generic_web.*` 这类实现会自然下沉到 engine/binding 侧
- `candidate_discovery` 不再被误读成完整入库线，而只是 `ingress_envelope` 生成链的一段
- 中间对象、资源池副作用、provider 旁路、作业日志不会再被新分层“顺手抽掉”
- 后面的重构也会更好落，因为每层都在回答不同问题

### 重要说明

这次是重新整理后的目标结构说明，不表示仓库当前已经完成对应收敛。

当前仓库里：

- `handler.cluster`、`url_pool`、`generic_web.*` 仍然是实际可见的 `channel`
- `terminal_output.py` 仍然依赖 `site_search` / `url_execution` 这类细粒度语义来判断 `fetched` 和结果形态
- `build_source_library_ingress_envelope(...)` 会把 `records` 包成 `ingress_envelope`，并显式声明 `run_extraction=False / run_writer=False`
- `run_postprocess_frontdoor(...)` 对 `records` 的 admission 是 `defer`，不会直接写入
- `ingest_url_via_source_library_frontdoor(...)` 会先把单条 `record` 转成 `document_candidate`，再进入 frontdoor 的 `accept` 路径

所以如果后面真的改实现，不能只改图，还要把 `definition/runtime entry / execution line / binding / engine / middle outputs / ingress contract / compat-observability` 这几个层级在代码里逐步落实出来。

### 候选改造方向

1. 把 `channel` 从图和文档里降级为 binding metadata，而不是 service。
2. 重写 `ItemResolver` 的概念输出，让它更接近 `execution line`，而不是一组混合 mode。
3. 把 `site_search` / `url_execution` 从“并列 lane”改成 line 内分支或 binding 结果。
4. 把 `run_channel(...)` 明确成 binding bridge，而不是业务 service。
5. 把 `handler.cluster` 明确限定为 `candidate_discovery` engine，把 `run_item_with_url_routing(...)` 明确限定为 `url_materialization` engine。
6. 在 frontdoor 前统一到 `ingress_envelope` contract，并明确区分 `document_candidate accept` 和 `records-only defer` 两种合法入口。
7. 保留现有能力不丢失：
   `candidate_discovery` 仍然保留，
   direct URL 抓取仍然保留，
   provider handlers 仍然保留，
   只是它们在 frontdoor 前的交付物统一为 `ingress_envelope`。
8. 把 `handler.cluster` / `url_pool` / `generic_web.*` 逐步降为 compatibility entry，而不是主要 public channel 抽象。
9. 调整 terminal output / stats / debugging，使其同时保留 `execution line`、具体 engine、中间对象状态和 `ingress_envelope` 交付状态。

### 影响组件

- `main/backend/app/services/source_library/item_resolver.py`
- `main/backend/app/services/source_library/resolver.py`
- `main/backend/app/services/source_library/runner.py`
- `main/backend/app/services/source_library/orchestrators/protocol_search.py`
- `main/backend/app/services/source_library/orchestrators/provider_harvest.py`
- `main/backend/app/services/source_library/orchestrators/site_search.py`
- `main/backend/app/services/source_library/orchestrators/url_execution.py`
- `main/backend/app/services/source_library/adapters/__init__.py`
- `main/backend/app/services/source_library/adapters/handler_cluster.py`
- `main/backend/app/services/source_library/adapters/url_pool.py`
- `main/backend/app/services/source_library/adapters/generic_web.py`
- `main/backend/app/services/source_library/terminal_output.py`
- `main/backend/app/services/resource_pool/unified_search.py`

### 对照基线后必须补回的功能保留清单

对照
[2026-03-25-source-library-to-db-service-flow-investigation.md](./2026-03-25-source-library-to-db-service-flow-investigation.md)
之后，当前这版新分层还缺少下面这些“必须保留”的真实功能点。

这些功能不一定都要出现在主图同一层，但后续任何结构重写都不能把它们抹掉：

1. 来源库定义入库链本身不能丢。
   需要保留 `loader.py -> sync.py -> shared_ingest_channels / shared_source_library_items`，以及项目级 `ingest_channels / source_library_items` 的写入边界。

2. API / collect runtime 入口层不能被抽象掉。
   需要保留 `/api/v1/ingest/source-library/run`、`run_source_library_item_compat`、`run_collect`、`SourceLibraryAdapter.run` 这一段真实入口。

3. async task / Celery 边界不能丢。
   调查文档里已有 `task_run_source_library_item`、`task_ingest_url_via_source_library`、`task_ingest_market`、`task_collect_policy_regulation`、`task_collect_data_api`，这些是实际运行能力，不只是实现细节。

4. job logging / `etl_job_runs` 不能丢。
   新图里现在没有把 `start_job / complete_job / fail_job` 和 `etl_job_runs` 表现出来，这属于真实运行链能力。

5. collect runtime 的兼容输出层不能丢。
   `SourceLibraryAdapter.run` 除了调 `run_item_payload`，还会包装 terminal output、frontdoor ingress 兼容结构、postprocess 兼容结构。后面如果重构，只能重命名/重分层，不能丢功能。

6. 资源池 side effects 不能丢。
   `candidate_discovery` 线不只是“发现候选 URL”，还会涉及 `append_url / upsert_site_entry`，以及 `resource_pool_urls / resource_pool_site_entries` 写入。

7. `generic_web` / `official_access` 这类 entry 类型不能只被当作普通 engine。
   它们在基线文档里既参与 candidate generation，也参与资源池写入，需要在新结构里明确它们属于哪条 line、哪一层 binding。

8. provider 直连已有 ingest service 的事实不能丢。
   `google_news` / `reddit` / `market` 不是简单返回 record，它们会跳转到已有 ingest service，再经 `collect_urls_from_list` 或 `run_postprocess_frontdoor` 完成写入。

9. `policy` 这条线的特殊性不能丢。
   它不是标准的 candidate discovery，也不完全等同于普通 URL materialization，需要在后续结构里单独确认它归属哪类 engine。

10. `document_candidate` contract 之前还存在一层 `record` / `by_url` / `candidates` 的中间语义。
   新结构已经把 frontdoor 前统一成 `document_candidate`，这是对的；但重构时仍要保留这些中间结构用于调试、统计、fallback、兼容输出，不能强行抹平成只剩一个对象。

11. batch / concurrency / fallback 能力不能丢。
   尤其是 `run_item_with_url_routing(...)` 里的并发、timeout、crawler fallback、per-URL diagnostics，这些是实际功能，不只是实现噪音。

12. `terminal_output.py` 的统计口径不能丢。
   现有 terminal output 会根据 `site_search` / `url_execution`、`by_url`、`candidates`、`records` 组合计算 `fetched / normalized / dropped / errors`。如果后面改成 `execution line`，必须保留同等级别的可观测性。

13. shared / project / builtin 三种 channel-item 来源层级不能丢。
   `list_effective_channels` / `list_effective_items` 背后合并了 shared、project、builtin channel/item，这一层能力现在主图里也没有表达出来。

14. compatibility entry 不能直接删除。
   `handler.cluster` / `url_pool` / `generic_web.*` 即便后面降级成 compatibility entry，也必须明确保留兼容入口，不然会影响现有配置和运行面。

### 建议下一步补图范围

如果继续补图，建议优先把下面这几项加回主图或旁注：

1. `API / collect runtime / SourceLibraryAdapter` 入口泳道。
2. `resource_pool` side effects 泳道。
3. `job logging / etl_job_runs` 泳道。
4. `provider -> existing ingest service` 的旁路说明。
5. `document_candidate` 前的中间对象：`candidates`、`records`、`by_url`。

### 当前状态

- status: proposed clarification
- implementation: not started
- confidence: high
- intended outcome: 把 definition-runtime / execution line / binding / engine / middle outputs / ingress contract / compat-observability 几层拆开理解

## 后续追加模板

下一项继续按下面的 section 命名：

- `## 结构修改 3`
- `## 结构修改 4`
- ...

每个新条目都应包含：

- 标题
- 问题描述
- 当前结构
- 建议结构
- 澄清后的边界
- 影响范围
- 当前状态
