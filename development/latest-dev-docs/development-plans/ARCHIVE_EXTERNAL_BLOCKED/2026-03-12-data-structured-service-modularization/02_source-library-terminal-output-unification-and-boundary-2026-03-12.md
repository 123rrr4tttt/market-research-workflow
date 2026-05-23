# 来源库末端收敛与统一输出格式（2026-03-12）

## 1. 目标与边界

收敛“信息来源库”业务末端定义：

1. 来源库链条仅定义到“获取数据并输出干净数据”。
2. 内容清洗、门禁、结构化抽取、入库、索引等均不计入来源库链条。
3. 本文只定义来源库统一输出格式与末端收敛规则，不直接改动后处理链实现。

边界口径：

- 来源库输入：`item + runtime search params`
- 来源库输出：`SourceLibraryTerminalOutput`
- 后处理输入：`SourceLibraryTerminalOutput`（由后处理前门接管）

## 2. 当前问题（针对来源库末端）

当前来源库虽然入口已统一到 `POST /api/v1/ingest/source-library/run`，但末端输出仍存在多形态并行：

1. 一部分结果带有历史 `single_url/frontdoor/gate` 命名痕迹。
2. 一部分结果是来源适配器自定义字段。
3. 上游看不到稳定、可回放、可重试的统一 terminal contract。

这会导致：

- 消费方理解成本高
- 回退/重试策略难统一
- 下游前门需要做大量 if-else 兼容

## 3. 统一末端输出格式（SourceLibraryTerminalOutput v1）

## 3.1 顶层结构

```json
{
  "contract_version": "source_library.terminal_output.v1",
  "status": "ok|partial|error",
  "source_mode": "protocol_search|provider_harvest|site_search|url_execution",
  "item": {
    "item_key": "string",
    "item_type": "user_defined|service_aggregated",
    "managed_by": "user|system"
  },
  "request": {
    "project_key": "string|null",
    "query_terms": ["..."],
    "time_window": {
      "start_time": "YYYY-MM-DD|null",
      "end_time": "YYYY-MM-DD|null",
      "days_back": "number|null"
    },
    "paging": {
      "page": "number|null",
      "page_size": "number|null",
      "max_pages": "number|null"
    },
    "limits": {
      "max_items": "number|null",
      "ingest_limit": "number|null",
      "max_candidates": "number|null"
    }
  },
  "results": {
    "records": [],
    "stats": {
      "fetched": 0,
      "normalized": 0,
      "dropped": 0,
      "errors": 0
    }
  },
  "errors": [],
  "meta": {
    "trace_id": "string|null",
    "provider": "string|null",
    "provider_job_id": "string|null",
    "retryable": false,
    "reason_code": "ok"
  },
  "raw_snapshot": {}
}
```

## 3.2 字段约束

1. `contract_version` 必填，固定为 `source_library.terminal_output.v1`。
2. `status` 仅允许 `ok|partial|error`。
3. `source_mode` 必填，严格对齐三分入口 + `url_execution`。
4. `results.records` 允许空，但必须存在。
5. `meta.reason_code` 使用统一 reason code 规范（默认 `ok`）。
6. `results.stats` 采用纯 fetch 语义，不承诺入库结果。
7. `raw_snapshot` 允许精简，但必须可追溯原始来源响应。

## 3.3 兼容策略（不破坏现链路）

1. 保留现有 `result` 内部结构，新增一层 terminal wrapper 输出。
2. 过渡期同时返回：
   - `legacy_result`（兼容旧消费方）
   - `terminal_output`（新契约）
3. 默认以 `terminal_output` 作为后处理前门唯一输入。
4. `legacy_result` 仅作为兼容位，允许继续存在，但不再代表来源库正式边界。

## 4. 来源库末端收敛规则

1. 来源库 resolver / adapter 不再直接承诺“入库成功语义”。
2. 来源库末端仅承诺“取数结果语义 + 统计 + 原始快照”。
3. 与内容质量相关字段（例如 `quality_score`, `structured_extraction_status`）从来源库输出中降级为可选诊断字段，权威归属后处理前门。
4. `site_search` 与 `url_execution` 主结果均应优先表达为 `records/stats/errors`，旧 ingest 风格字段只允许出现在兼容位或诊断位。

## 5. 原子任务（仅来源库末端）

执行范围约束：

1. 仅允许改动来源库 terminal 输出相关代码与契约测试。
2. 不进入后处理前门实现，不改 `03` 中定义的模块边界。
3. 不重构下游消费逻辑，只做兼容包装。

### AT-SL-01 Terminal DTO

- 目标：新增 `SourceLibraryTerminalOutput` 数据结构与构建器。
- 输入：现有各 `run_item_payload` 分支返回。
- 输出：统一 `terminal_output`。
- 验收：四种 `source_mode` 返回均含 `contract_version/status/source_mode/results/meta/raw_snapshot`。
- 最小门禁：新增 1 组 unit contract 测试（覆盖 4 类 `source_mode`）。

### AT-SL-02 旧字段兼容包装

- 目标：不破坏现有消费方。
- 输入：当前 `run_source_library_item_compat` 返回。
- 输出：`legacy_result + terminal_output` 双轨返回。
- 验收：旧测试通过，新 contract 测试可断言 `terminal_output`。
- 最小门禁：来源库相关 core contract + integration 冒烟通过。

### AT-SL-03 边界保护

- 目标：来源库层不再新增后处理字段依赖。
- 输入：来源库适配器与 resolver 代码。
- 输出：边界检查清单与 lint 规则（或 code review 清单）。
- 验收：来源库代码中不出现新增持久化/索引副作用。
- 最小门禁：code scan 无新增 `Document(` / `session.add(` / index 调用进入来源库分支。

## 5.1 可执行拆分（本次由我负责）

### AT-SL-01A 定义 DTO 与常量

- 目标：定义 `source_library.terminal_output.v1` 常量与最小字段模型。
- 输入：`run_item_payload` 现有返回结构。
- 输出：DTO 构建函数（含默认空值与 reason_code 归一）。
- 验收：空结果/错误结果/部分成功结果均能生成合法 DTO。

### AT-SL-01B 四分支映射器

- 目标：为 `protocol_search/provider_harvest/site_search/url_execution` 建立统一映射。
- 输入：四分支现有 raw result。
- 输出：单一 `build_terminal_output(...)` 映射入口。
- 验收：四分支的 `stats` 语义一致（`fetched/normalized/dropped/errors`）。

### AT-SL-02A 兼容返回包装

- 目标：在兼容层追加 `terminal_output`，保留 `legacy_result`。
- 输入：`run_source_library_item_compat` 输出。
- 输出：向后兼容的双轨返回体。
- 验收：原有调用方读取旧字段不报错；新测试可读取 `terminal_output`。

### AT-SL-02B 契约测试补齐

- 目标：为 `terminal_output` 增加固定断言。
- 输入：来源库相关 contract 与 integration 用例。
- 输出：最小可维护断言集合（字段存在+枚举合法）。
- 验收：测试可稳定识别契约回退。

### AT-SL-03A 边界扫描规则

- 目标：形成“来源库末端不入后处理职责”的检查清单。
- 输入：来源库服务目录代码。
- 输出：扫描规则 + 本轮扫描结果（文档记录）。
- 验收：本轮改动中无新增越界副作用调用。

## 5.2 执行状态板

1. `AT-SL-01A`：`completed`（2026-03-14）
2. `AT-SL-01B`：`completed`（2026-03-14）
3. `AT-SL-02A`：`completed`（2026-03-14）
4. `AT-SL-02B`：`completed`（2026-03-14）
5. `AT-SL-03A`：`completed`（2026-03-14）

## 5.3 边界扫描规则与本轮结果

扫描目标目录（来源库主链 + collect runtime 适配入口）：

- `main/backend/app/services/source_library`
- `main/backend/app/services/collect_runtime/adapters/source_library.py`

可执行扫描命令（仓库根目录执行）：

```bash
# 1) 直接入库对象构造（应避免在来源库末端新增）
rg -n "Document\\(" main/backend/app/services/source_library main/backend/app/services/collect_runtime/adapters/source_library.py

# 2) ORM 持久化副作用（应避免在来源库末端新增）
rg -n "session\\.add\\(" main/backend/app/services/source_library main/backend/app/services/collect_runtime/adapters/source_library.py

# 3) 索引相关副作用（应避免在来源库末端新增）
rg -n "index_" main/backend/app/services/source_library main/backend/app/services/collect_runtime/adapters/source_library.py

# 4) 末端主链二次过滤（排除 sync 历史路径后复核）
rg -n "Document\\(|session\\.add\\(|index_" main/backend/app/services/source_library main/backend/app/services/collect_runtime/adapters/source_library.py | rg -v "main/backend/app/services/source_library/sync.py"
```

本轮扫描结果（2026-03-14 PDT）：

1. `Document(`：`0` 命中。
2. `index_`：`0` 命中。
3. `session.add(`：`2` 命中，均在 `main/backend/app/services/source_library/sync.py` 既有同步路径。
4. 排除 `sync.py` 后，来源库末端主链（runner/resolver/adapters/collect runtime adapter）命中 `0`。

结论：本轮未发现新增越界副作用调用，AT-SL-03A 边界约束满足。

## 5.4 本轮实现记录

代码与契约侧已完成：

1. `terminal_output` 已切换为 clean terminal contract，主结构为 `records/stats/errors/meta/raw_snapshot`。
2. `stats` 已统一为 `fetched/normalized/dropped/errors` 口径，不再以 `inserted/updated/skipped` 作为正式末端语义。
3. `url_execution` 的 `terminal_output_only` 已从占位路径改为真实 fetch-only 执行。
4. `site_search/handler_cluster` 主结果已转为 `records + stats + fetch_diagnostics`。
5. `legacy_result` 仍保留兼容，但已降级为废弃兼容位。
6. 来源库执行层已补齐 lane orchestrator 模块，resolver 主干进一步收敛为 compile + dispatch。
7. `ItemResolver` 已独立模块化，`ExecutionRequest` 不再内联定义在 resolver。
8. `protocol_search/provider_harvest` lane 已补充各自的 orchestrator metadata 与参数准备逻辑，不再只是单纯透传包装。
9. 历史 `single_url.py` 已物理移除；同步/异步单 URL 正式入口均已改走 `source_library url_execution -> postprocess_frontdoor`。
10. `frontdoor_ingress` 中的 `single_url` ingress type 与 builder 已删除。
11. 历史 `task_ingest_single_url` 与 `single_url_*` 参数兼容层也已删除；当前代码主链仅保留 `url_routing`/`source_library` 命名。

验证命令占位（后续可直接执行）：

```bash
# 文档关键小节存在性检查
rg -n "5\\.3 边界扫描规则与本轮结果|5\\.4 本轮实现记录|AT-SL-03A" \
  development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-12-data-structured-service-modularization/02_source-library-terminal-output-unification-and-boundary-2026-03-12.md
```

## 6. 完成定义

满足以下条件即可判定“来源库末端收敛完成（v1）”：

1. `source-library/run` 始终输出统一 `terminal_output`。
2. `terminal_output` 主语义为 clean records/stats/errors，不再以入库计数为权威字段。
3. 旧消费链路不受破坏（兼容字段保留）。
4. 文档与 contract 测试对齐。
