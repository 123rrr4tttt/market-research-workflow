# Topology Risk Freeze: Compat Caller Matrix And Rollout Guards (2026-04-06)

> 日期：2026-04-06
> 范围：`workflow_graph`、`agent runtime / agent_batch`、`source-library / ingest`、`frontend kernel / shell / legacy hash`
> 状态：current dev topology-risk freeze
> 目的：冻结本轮高风险收口任务的现状拓扑、compat caller matrix、parity checklist 与 rollout guards，避免因为结构理解不足而破坏当前功能

## 1. 为什么需要这份冻结文档

前两份文档已经明确了收口方向和原子任务，但这还不够。

当前真正的失败风险不是“任务拆得不够细”，而是：

1. 现有结构中已经同时存在新旧路径。
2. 若只按目标架构理解，而忽略当前真实 caller 拓扑，就会把“兼容入口”误当成“可立即删除的旧代码”。
3. 一旦默认行为被过早切换，现有功能就会直接回归。

因此，这份文档只做一件事：

把当前最容易因为拓扑理解不足而改坏的部分，先冻结成显式矩阵和护栏。

## 2. 本轮高风险任务

高风险任务如下：

1. `AT-RCL-04`：agent runtime canonical path 收敛
2. `AT-RCL-07`：source-library authority vs compat split
3. `AT-RCL-08`：frontend render/shell ownership convergence
4. `AT-RCL-09`：legacy hash adapter + B-layer shell closure

中风险但仍需护栏：

1. `AT-RCL-02`：workflow graph durable runtime
2. `AT-RCL-05`：project key hard-gate rollout

## 3. 全局安全规则

### 3.1 不允许先改默认行为

以下动作在 parity checklist 跑通前一律禁止：

1. 删除旧 response 字段
2. 删除 compat adapter 入口
3. 删除 unknown-route fallback
4. 修改 legacy hash 默认解析
5. 全环境切换 `project_key_enforcement_mode=require`
6. 用新 runtime 直接替换旧 runtime 主链

### 3.2 只允许三类安全改动

当前可接受的改动类型只有：

1. `freeze`
2. `additive`
3. `switchable`

解释如下：

1. `freeze`：文档、mapping、caller matrix、checklist、验证补充
2. `additive`：新增 store、metadata、adapter、双写、验证、日志、告警
3. `switchable`：通过显式 knob 切换新行为，且能一键回退

### 3.3 所有切换必须有旋钮

如果某条收口线还没有现成旋钮，则在引入新默认行为前必须先补旋钮；不能通过“直接改代码路径”完成切换。

## 4. Workflow Graph: Frozen Current Topology

### 4.1 当前主链

当前真实调用链为：

1. `compile` 请求进入 [`main/backend/app/services/workflow_graph/__init__.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/workflow_graph/__init__.py)
2. `WorkflowGraphCompilerService.compile(...)` 调 `compile_workflow_graph(...)`
3. 编译结果写入进程内 `_compiled`
4. `run` 请求再次进入 `WorkflowGraphRuntimeService.run(...)`
5. 先通过 `compiler.get_compiled(graph_id)` 回取内存态编译结果
6. 再交给 `WorkflowGraphRuntime(store=build_run_store())`
7. 最后把结果投影到 agent session service

补充说明：

1. 当前仓库已经有 run/event persistence 与 handoff persistence 基础件。
2. 这些基础件并不等于 compiled artifact registry 已持久化。
3. 因此 `AT-RCL-02` 的目标应是“补齐 compiled artifact durability，并和现有 run/handoff contract 对齐”，而不是重做已有 handoff/run-event 存储。

这意味着：

1. run store 已经支持 DB / memory 两种模式
2. compiled graph registry 仍是进程内内存态
3. run store / handoff store 已存在，但 compile durability 尚未对齐
4. runtime durability 和 compile durability 并不对称

### 4.2 现有 rollout guards

现有旋钮：

1. `settings.workflow_graph_db_store_enabled`
2. `settings.workflow_graph_db_store_fail_closed`

对应代码：

1. [config.py:94](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/settings/config.py#L94)
2. [config.py:95](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/settings/config.py#L95)
3. [store.py:290](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/workflow_graph/store.py#L290)

当前没有旋钮的部分：

1. compiled artifact registry 的持久化切换
2. compile path 与 run path 的版本化语义

### 4.3 冻结规则

在 `AT-RCL-02` 期间：

1. 不先删 `_compiled`
2. 不先改 compile/run API 外形
3. 只允许新增 durable compiled store 和双读/双写验证
4. 默认执行路径在 replay / reload / run parity 跑通前不切

### 4.4 必须通过的 parity checklist

1. compile 后立即 run 仍可成功
2. compile 后跨进程或重启模拟仍可 run
3. `get_run`、`get_run_events`、`replay_run` 外形不退化
4. session projection 仍能拿到 `session_id / current_phase / root_task_id`

## 5. Agent Runtime / Agent Batch: Frozen Current Topology

### 5.1 当前主链不是单核

当前并存的真实结构是：

1. `agent_runtime/*` 提供 coordinator、task_bus、watchers、memory、tool_policy 等新骨架
2. `agent_batch/*` 仍承载大量 task contract、retry、approval、planner、loop 语义
3. `workflow_graph` run 完成后又会投影到 agent session service

这说明“新 runtime 已存在”不等于“旧 runtime 已可退场”。

### 5.2 当前风险

最容易误判的点是：

1. 把 `agent_runtime` 误当成已经完整覆盖 `agent_batch`
2. 把 `agent_batch` 误当成单纯 legacy shell

实际上从 [`task_contract.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/agent_batch/task_contract.py) 可以看到，旧链上仍持有完整的 channel spec、override 白名单、retry action schema、fail-closed policy 语义。

### 5.3 冻结规则

在 `AT-RCL-04` 期间：

1. 不先删除 `agent_batch` 入口
2. 不先改变 approval / retry / task manifest 默认语义
3. 只允许先补 canonical-path mapping、session lifecycle mapping、compat adapter map
4. 只有当 old entrypoint -> new core 的 caller matrix 明确后，才允许引入 switchable default

### 5.4 必须通过的 parity checklist

1. `agent_batch` 现有 API 仍可调用
2. approval binding 行为不退化
3. retry / planner 合同字段不丢失
4. session current phase 能从现有 task status 正常投影

## 6. Source-Library / Ingest: Frozen Current Topology

### 6.1 当前主链

当前 source-library 的响应不是单一 contract，而是聚合 contract：

1. `SourceLibraryAdapter.run(...)` 执行 `run_item_payload(...)`
2. 先构造 `terminal_output`
3. 再通过 `build_source_library_ingress_envelope(...)`
4. 再通过 `run_postprocess_frontdoor(...)`
5. 最终 `to_source_library_response(...)` 同时返回：
   - `terminal_output`
   - `frontdoor_ingress`
   - `postprocess_frontdoor`
   - `legacy_result`
   - `legacy_result_is_deprecated`

这不是“重复字段没清理”，而是当前真实兼容拓扑。

### 6.2 现有 rollout guards

现有旋钮：

1. `settings.url_batch_path_default_mode`
2. caller override `url_batch_path_mode`
3. `settings.ingest_frontdoor_rollout_mode`
4. `settings.ingest_frontdoor_canary_projects`

对应依据：

1. [config.py:82](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/settings/config.py#L82)
2. [config.py:83](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/settings/config.py#L83)
3. [config.py:84](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/settings/config.py#L84)
4. [url_pool.py:254](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/ingest/url_pool.py#L254)
5. [batch precedence matrix](../2026-03-25-source-library-ingest-minimal-migration/references/2026-03-26-batch-switch-rollout-dispatch-precedence-matrix.md)

### 6.3 冻结规则

在 `AT-RCL-07` 期间：

1. 不先删 `legacy_result`
2. 不先删 `terminal_output`
3. 不先删 `frontdoor_ingress`
4. 不先删 `postprocess_frontdoor`
5. 不先改 `to_source_library_response(...)` 默认字段集
6. authority output 只能先作为 additive path 引入

### 6.4 必须通过的 parity checklist

1. `legacy_result` 仍存在
2. `legacy_result_is_deprecated` 仍存在
3. `terminal_output`、`frontdoor_ingress`、`postprocess_frontdoor` 仍可回取
4. `test_source_library_core_contract.py` 不退化
5. frontdoor writer 相关 side effects 不丢

## 7. Frontend Kernel / Shell / Legacy Hash: Frozen Current Topology

### 7.1 当前主链

当前前端实际存在三层真实路径：

1. backend `web_ui_routes.py` 负责把旧 html 入口重定向到 modern 前端 hash
2. `FrontendKernelApp` 先按 layered route / legacy route / default / unknown route 解析
3. 若是 unknown route，则直接回退旧 `AppShell`
4. `AppShell` 自己维护：
   - `parseLegacyHashToMode(...)`
   - `handleModeChange(...)`
   - 页面分发
   - hash 同步
5. `ModuleRenderer` 又维护第二套页面分发
6. `FigmaSideNav` 根据 registry + surface 过滤导航项

补充判断：

1. `moduleManifest -> contracts -> registry` 已经基本形成模块 metadata 的派生链。
2. 当前真正未收敛的中心矛盾，不是 metadata registry 是否存在，而是 render ownership、legacy hash compatibility 与 shell fallback 仍然分散。

所以当前不是“只有一套 kernel 路径”，而是“kernel + AppShell + ModuleRenderer + backend legacy entry redirect”四层叠加。

### 7.2 现有 rollout guards

现有旋钮：

1. `MODERN_FRONTEND_URL`
2. `ENABLE_DEFAULT_MODERN_FRONTEND`
3. `MODERN_FRONTEND_HOST`
4. `MODERN_FRONTEND_PORT`

对应代码：

1. [web_ui_routes.py:19](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/web_ui_routes.py#L19)
2. [web_ui_routes.py:22](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/web_ui_routes.py#L22)
3. [web_ui_routes.py:25](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/web_ui_routes.py#L25)
4. [web_ui_routes.py:26](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/web_ui_routes.py#L26)

当前没有现成旋钮的部分：

1. unknown route 是否回退 `AppShell`
2. legacy hash 是否继续接受旧页面别名
3. `AppShell` 分发与 `ModuleRenderer` 分发的优先级

因此，这三项在 parity checklist 通过前不能直接改默认行为。

### 7.3 冻结规则

在 `AT-RCL-08` 和 `AT-RCL-09` 期间：

1. 不先删 `AppShell` 内旧分发
2. 不先移除 `FrontendKernelApp` 中 unknown-route fallback
3. 不先修改 legacy hash 默认解析
4. 不先改 backend `/ingest.html`、`/dashboard.html`、`/graph.html` 等旧入口重定向目标
5. 只允许先补：
   - metadata registry parity matrix
   - render ownership parity matrix
   - legacy hash support matrix
   - B-layer route/shell/nav checklist

### 7.4 必须通过的 parity checklist

1. `moduleManifest` 与 `registry.ts` 每个模块一一可对照
2. `AppShell` 与 `ModuleRenderer` 的页面分发差异有清单
3. 每个 `LayerId='B'` 模块具备：
   - route
   - shell
   - nav visibility
   - backend redirect compatibility
4. old html route -> modern hash -> kernel route 的映射不丢

## 8. Project Key: Frozen Rollout Guard

### 8.1 当前主链

当前真实行为是：

1. header 优先
2. query 次之
3. 否则 fallback 到 active/default project

对应代码：

1. [main.py:227](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/main.py#L227)
2. [config.py:56](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/settings/config.py#L56)

### 8.2 现有 rollout guard

现有旋钮：

1. `project_key_enforcement_mode=warn|require`

### 8.3 冻结规则

在 `AT-RCL-05` 期间：

1. 不先全环境切 `require`
2. 不先删除 fallback warning header
3. 不先移除 fallback request log
4. 先做环境分层 rollout，再切默认值

### 8.4 必须通过的 parity checklist

1. `warn` 模式行为保持兼容
2. `require` 模式缺 key 必失败
3. fallback observability 仍可见

## 9. Rollout Knob Matrix

| 主题 | 现有旋钮 | 当前可用 | 本轮策略 |
|---|---|---|---|
| workflow graph run store | `workflow_graph_db_store_enabled` / `workflow_graph_db_store_fail_closed` | 是 | 只先用于 run store，不代表 compiled graph 已可切换 |
| source-library batch path | `url_batch_path_mode` / `url_batch_path_default_mode` | 是 | 继续作为 batch path 唯一回退旋钮 |
| ingest frontdoor | `ingest_frontdoor_rollout_mode` / `ingest_frontdoor_canary_projects` | 是 | 不得复用于 source-library authority/compat rollback |
| project isolation | `project_key_enforcement_mode` | 是 | 先环境化 rollout，再切 default |
| modern frontend redirect | `MODERN_FRONTEND_URL` / `ENABLE_DEFAULT_MODERN_FRONTEND` / host/port | 是 | 只控制 backend -> modern 前端入口，不等于 kernel 内部拓扑切换 |
| frontend internal fallback | 无 | 否 | 未补 dedicated knob 前，不允许移除 unknown-route fallback |
| compiled graph durable registry | 无 | 否 | 未补 dedicated knob 前，不允许替换 compile/run 默认主链；run/handoff store 不能被误当成 compiled registry 替代物 |

## 10. 推荐安全执行顺序

1. 先冻结 caller matrix 和 parity checklist。
2. 再补 additive path、metadata、guard 和双读/双写。
3. 再引入 dedicated knob。
4. 先小范围或非默认切换。
5. 最后在 regression pack 跑通后切默认。

## 11. 一句话规则

当前这几条高风险收口线都不能按“目标架构已经很清楚”来改，而必须按“现有 caller 拓扑仍然复杂且双中心共存”来改。

也就是：

先冻结现状，再补加法路径，再加显式开关，最后才允许碰默认行为。
