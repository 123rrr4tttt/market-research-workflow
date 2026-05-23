<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/01_repo-logic-gap-assessment-2026-04-06.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/01_repo-logic-gap-assessment-2026-04-06.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Repo Logic Gap Assessment (2026-04-06)

> 日期：2026-04-06
> 范围：`main/backend`、`main/frontend-modern`、`main/ops`
> 状态：current dev assessment
> 目的：基于当前主代码链，识别“术语/结构已经平台化，但运行时闭环尚未完全成立”的关键逻辑缺口，并给出收口优先级

## 1. 结论摘要

这个仓库当前最大的特点不是“缺模块”，而是“很多模块已经具备正式名字、路由、服务层、测试和文档，但部分核心能力仍停留在过渡实现或单进程闭环阶段”。

截至 2026-04-06，最准确的判断是：

1. 仓库整体结构已经成形，API envelope、项目化 schema、来源库与资源池分层都已进入主链。
2. 但若按平台级闭环来衡量，仍存在若干关键逻辑缺口，主要集中在 runtime durability、真实能力边界、单一事实源和真实验证链路。
3. 当前最需要优先收口的，不是继续增加新术语或新入口，而是把已有抽象的真实运行边界补齐。

本评估的核心结论是：

1. `workflow graph` 还不是平台级 runtime，只是“单进程内可复用的编译态能力”。
2. `llm-report` 与 `writing llm action` 的对外命名强于当前实现，存在明显的能力语义落差。
3. `project_key` 隔离默认仍是软约束，不是硬约束。
4. 前端 `kernel / AppShell / ModuleRenderer` 仍是双中心甚至多中心状态。
5. 测试覆盖偏强 contract、偏弱真实端到端闭环。

## 2. 本次核对范围

本次判断基于以下主代码链与测试样本：

### 2.1 Backend runtime / policy

1. [`main/backend/app/services/workflow_graph/__init__.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/workflow_graph/__init__.py)
2. [`main/backend/app/services/llm_report_generator.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/llm_report_generator.py)
3. [`main/backend/app/services/writing/llm_action_service.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/writing/llm_action_service.py)
4. [`main/backend/app/services/collect_runtime/adapters/source_library.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/collect_runtime/adapters/source_library.py)
5. [`main/backend/app/services/source_library/resolver.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/source_library/resolver.py)
6. [`main/backend/app/services/resource_pool/unified_search.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/resource_pool/unified_search.py)
7. [`main/backend/app/settings/config.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/settings/config.py)
8. [`main/backend/app/main.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/main.py)

### 2.2 Frontend topology

1. [`main/frontend-modern/src/app/kernel/FrontendKernelApp.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/FrontendKernelApp.tsx)
2. [`main/frontend-modern/src/app/kernel/ModuleRenderer.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/ModuleRenderer.tsx)
3. [`main/frontend-modern/src/app/shell/AppShell.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/shell/AppShell.tsx)

### 2.3 Representative tests

1. [`main/backend/tests/integration/test_workflow_graph_api_unittest.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/tests/integration/test_workflow_graph_api_unittest.py)
2. [`main/backend/tests/integration/test_llm_report_api_unittest.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/tests/integration/test_llm_report_api_unittest.py)
3. [`main/backend/tests/integration/test_project_key_policy_unittest.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/tests/integration/test_project_key_policy_unittest.py)
4. [`main/backend/tests/core_business/test_source_library_core_contract.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/tests/core_business/test_source_library_core_contract.py)

## 3. 已经成立的部分

### 3.1 领域分层已经明显成形

当前代码已经不是散装脚本集合，而是有相对清晰的平台骨架：

1. backend 已有 `API -> services -> adapters / policy / runtime` 的基本分层。
2. frontend 已出现 kernel、layer、module contract、route manifest 等平台化术语。
3. source-library、resource-pool、collect-runtime、writing、workflow-graph 等业务边界已经被显式命名。

### 3.2 文档和代码之间已有较强映射

`development/latest-dev-docs` 中的大量专题，和主代码链里的命名基本能互相对上。这说明仓库的演进不是无序的，很多设计决策已经进了代码主干。

### 3.3 契约意识比较强

从接口 envelope、policy fallback、source-library contract、frontend module contract 到测试命名方式，都能看到“先定义边界，再推进实现”的倾向。这是仓库后续补闭环的基础。

## 4. 关键逻辑缺口

### 4.1 Workflow Graph 仍是单进程编译态，不是平台级 runtime

[`main/backend/app/services/workflow_graph/__init__.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/workflow_graph/__init__.py) 当前通过进程内 `_compiled` 字典保存编译结果，`run()` 再按 `graph_id` 回取。

与此同时，[`main/backend/app/services/workflow_graph/store.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/workflow_graph/store.py) 与 [`main/backend/app/services/workflow_graph/handoff_store.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/workflow_graph/handoff_store.py) 已经提供了 run/event 与 handoff 的持久化基础件。

这意味着：

1. 服务重启后，已编译 graph 会丢失。
2. 多 worker 或多实例部署时，`compile` 与 `run` 不保证落在同一个进程。
3. `graph_id` 当前更像 session-local handle，而不是平台级持久标识。
4. 当前缺的不是“所有 durability 都不存在”，而是 compiled artifact registry 仍未和 run/handoff persistence 对齐。

因此，这块最大的缺口不是 compiler 本身，而是“编译产物没有 durable store / registry / lifecycle”。

### 4.2 LLM Report 与 Writing 的能力语义强于当前实现

[`main/backend/app/services/llm_report_generator.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/llm_report_generator.py) 现在更接近“固定章节结构 + 来源内容拼接/裁剪”的报告构造器，而不是真正的 LLM 报告生成器。

[`main/backend/app/services/writing/llm_action_service.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/writing/llm_action_service.py) 也主要通过规则化分支返回 `outline_generate`、`section_expand`、`selection_rewrite` 的结果，并未形成真实模型能力的稳定主路径。

逻辑缺口不在于“没有接口”，而在于：

1. 对外命名像成品 AI 能力。
2. 内部实现仍偏模板/规则/替身。
3. 文档与上层调用方容易把它误解为“真实 LLM 已经封口”。

### 4.3 Source Library / Resource Pool 仍处于多合同并存的过渡态

[`main/backend/app/services/collect_runtime/adapters/source_library.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/collect_runtime/adapters/source_library.py) 一次执行结果同时暴露：

1. `legacy_result`
2. `terminal_output`
3. `frontdoor_ingress`
4. `postprocess_frontdoor`
5. `legacy_result_is_deprecated`

这类信号说明 source-library 主链虽然已经很强，但仍处在兼容层尚未完全退休的阶段。

再结合 [`main/backend/app/services/source_library/resolver.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/source_library/resolver.py) 与 [`main/backend/app/services/resource_pool/unified_search.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/services/resource_pool/unified_search.py) 的策略密度，可以得出两个现实判断：

1. 能力不少，但系统可预测性正在被复杂 policy 压缩。
2. 统一权威 contract 仍未完全收口，兼容输出仍在主链中占位。

### 4.4 Project Isolation 默认还是软约束

[`main/backend/app/settings/config.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/settings/config.py) 中 `project_key_enforcement_mode` 默认是 `warn`，[`main/backend/app/main.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/app/main.py) 的 project context middleware 会在缺失 `project_key` 时 fallback 到 active/default project。

再结合 [`main/backend/tests/integration/test_project_key_policy_unittest.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/tests/integration/test_project_key_policy_unittest.py)，可以确认这种 fallback 不是遗漏，而是当前默认策略。

这带来的逻辑缺口是：

1. README 叙事强调项目隔离。
2. 默认运行策略却允许无 `project_key` 继续执行。
3. 多项目边界在默认配置下并不是强制性安全边界。

### 4.5 Frontend Kernel / AppShell / ModuleRenderer 仍是多中心

[`main/frontend-modern/src/app/kernel/FrontendKernelApp.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/FrontendKernelApp.tsx) 已成为新入口，但 unknown route 仍会回退到旧 [`main/frontend-modern/src/app/shell/AppShell.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/shell/AppShell.tsx)。

与此同时，[`main/frontend-modern/src/app/kernel/ModuleRenderer.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/ModuleRenderer.tsx) 和 `AppShell.tsx` 又都维护了一套页面分发关系。

更细看当前结构，模块 metadata 本身已经明显朝 [`main/frontend-modern/src/app/kernel/moduleManifest.ts`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/moduleManifest.ts) 集中，并通过 [`main/frontend-modern/src/app/kernel/contracts.ts`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/contracts.ts) 与 [`main/frontend-modern/src/app/platform/modules/registry.ts`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/platform/modules/registry.ts) 派生；真正仍然双份维护的，是 render ownership、legacy hash compatibility 和 shell fallback。

这说明当前前端的真实状态不是“新架构已完成替换”，而是：

1. 新 kernel 已进入主链。
2. 旧壳层仍承担实际兼容职责。
3. 模块元数据正在收敛，但页面归属和渲染入口仍没有唯一事实源。

这会直接放大后续迭代成本，因为每新增一页或调整一个模块，都可能需要同时维护两到三处事实来源。

### 4.6 测试强 contract，弱真实闭环

[`main/backend/tests/integration/test_workflow_graph_api_unittest.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/tests/integration/test_workflow_graph_api_unittest.py) 主要通过 patch `_invoke_*` 测 API 包装与分支。

[`main/backend/tests/integration/test_llm_report_api_unittest.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/tests/integration/test_llm_report_api_unittest.py) 也是通过 patch source resolver、job 状态、settings 来验证 envelope。

[`main/backend/tests/core_business/test_source_library_core_contract.py`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/tests/core_business/test_source_library_core_contract.py) 也更偏向 contract/filter/validation。

这些测试并非无效，相反它们对守住 API 外形很有价值；但当前缺少的是：

1. compile -> persist -> reload -> run 的真实链路验证。
2. source-library item -> execution plan -> adapter -> frontdoor 写通的真实 smoke。
3. writing / llm-report 在真实 provider 或真实 fallback 主路径上的可观测验证。

## 5. 风险判断

若继续在当前状态下叠加新功能，而不先补收口，会出现以下风险：

1. 新能力挂到“平台术语”之上，但底层 runtime 依然是 session-local 或 fallback-heavy，导致看起来像平台，实际上仍是局部能力。
2. 上层产品、前端或后续文档容易高估已有 AI 能力，产生错误集成预期。
3. 多项目、多 worker、多实例部署时，实际行为与单机开发体验逐步背离。
4. 前端继续迭代会持续放大双中心路由/分发问题。
5. contract 测试继续增长，但真实跨层回归问题仍可能漏出。

## 6. 收口优先级建议

### P0

1. 为 `workflow graph` 引入 durable compiled artifact store 或 registry，使 `graph_id` 从进程内句柄变成平台级可回取标识。
2. 明确区分“真实 LLM 能力”和“模板/规则 fallback 能力”，包括命名、文档与 API 语义。
3. 将 `project_key` 默认 enforcement 从 `warn` 收紧到 `require`，至少在非开发环境启用硬约束。

### P1

1. 收拢 source-library 的权威输出 contract，逐步移除 `legacy_result` 在主链中的占位。
2. 收敛 frontend 页面分发事实源，明确 `FrontendKernelApp`、`ModuleRenderer`、`AppShell` 的唯一职责边界。
3. 补真实 smoke 与小规模 E2E，覆盖最关键的 compile/run、source-library write-through、writing/report 路径。

### P2

1. 对 policy-heavy 模块做边界瘦身，把“策略表”“执行编排”“兼容层”进一步拆开。
2. 回写专题文档状态，避免文档口径停留在“计划中”而代码已经进入“半完成”状态。

## 7. 推荐执行顺序

推荐的最小可执行顺序如下：

1. 先补 `workflow graph` durability。
2. 再拆清 LLM 命名与真实能力边界。
3. 再强化 `project_key` 默认策略。
4. 然后统一 frontend 路由/模块事实源。
5. 最后用真实 smoke 把前述几条做成可持续回归校验。

这个顺序的原因很简单：

1. 前三项决定平台是否真的可运行、可隔离、可被正确理解。
2. 第四项决定前端后续迭代成本是否继续上升。
3. 第五项决定上述收口能否长期稳住，而不是再次退化回“文档已完成、真实闭环未完成”的状态。

## 8. 一句话判断

截至 2026-04-06，这个仓库已经具备明显的平台化结构，但其最主要的逻辑缺口仍是：

“平台化命名和模块边界已经先走到了前面，真正的平台级 runtime durability、能力语义真实性、唯一事实源和真实验证闭环还没有完全追上。”
