# Frontend Three-Layer Rewrite Closure Gap Assessment And Rollout (2026-04-02)

> 日期：2026-04-02
> 范围：`main/frontend-modern`
> 状态：current dev assessment
> 目的：基于 `2026-03-15-frontend-three-layer-rewrite` 专题原始计划与当前代码现状，判断三层重写事实上完成到哪一步，列出未封口项，并给出后续收口顺序

## 1. 结论摘要

当前前端不是“完全未做三层重写”，也不是“已经完成三层重写”，而是处于一个明显的半重构态：

1. A/B/C 三层、kernel、route manifest、module contract 这些目标术语已经进入代码主干。
2. `main/frontend-modern` 已经出现新的 kernel 入口与按层渲染路径。
3. 但旧 `AppShell` 没有真正退休，兼容层没有独立成 adapter，B 层容器没有成形，页面层仍然承载大量业务编排与副作用。

因此，本专题截至 2026-04-02 的准确判断应为：

- `T1`：部分完成，但未封口；
- `T2`：部分完成，但未封口；
- `T3`：部分完成，但未封口；
- `T4`：启动了归层和路由设计，但可视化容器未完成；
- `T5`：未开始封口。

本评估的核心结论是：

- 现在最大的风险不是“没有三层设计”，而是“计划定义了目标，代码落了一半，但收口标准没有形成可执行闭环”。
- 如果继续在当前状态下迭代页面功能，会进一步放大 `AppShell / kernel / pages / components` 之间的职责重叠。

## 2. 本次核对范围

本次判断基于以下输入：

### 2.1 原始专题文档

1. [README.md](./README.md)
2. [01_frontend-three-layer-rewrite-architecture-2026-03-15.md](./01_frontend-three-layer-rewrite-architecture-2026-03-15.md)
3. [02_atomic-tasklist-frontend-three-layer-rewrite-2026-03-15.md](./02_atomic-tasklist-frontend-three-layer-rewrite-2026-03-15.md)

### 2.2 当前代码主链

1. [`main/frontend-modern/src/App.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/App.tsx)
2. [`main/frontend-modern/src/app/kernel/FrontendKernelApp.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/FrontendKernelApp.tsx)
3. [`main/frontend-modern/src/app/kernel/contracts.ts`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/contracts.ts)
4. [`main/frontend-modern/src/app/kernel/routes.ts`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/routes.ts)
5. [`main/frontend-modern/src/app/kernel/ModuleRenderer.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/ModuleRenderer.tsx)
6. [`main/frontend-modern/src/app/kernel/AdminLayerShell.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/AdminLayerShell.tsx)
7. [`main/frontend-modern/src/app/kernel/WorkbenchLayerShell.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/WorkbenchLayerShell.tsx)
8. [`main/frontend-modern/src/app/shell/AppShell.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/shell/AppShell.tsx)
9. [`main/frontend-modern/src/app/navigation/index.ts`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/navigation/index.ts)
10. `main/frontend-modern/src/pages/*`

## 3. 已经落地的部分

### 3.1 三层基本语义已经进入代码

以下能力已经不是停留在文档里，而是进入了代码主链：

1. `LayerId` / `SurfaceKind` / `RouteManifest` / `ModuleContract` 等类型已经存在。
2. kernel 已能根据新式 route path 和旧 hash 决定模块入口。
3. 模块已经被映射到 A/B/C 层和 workbench / visualization / management 三类 surface。

主要体现在：

- [`main/frontend-modern/src/app/kernel/types.ts`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/types.ts)
- [`main/frontend-modern/src/app/kernel/contracts.ts`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/contracts.ts)
- [`main/frontend-modern/src/app/kernel/routes.ts`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/routes.ts)

### 3.2 A 层和 C 层已经出现专属 shell

当前实现里已经不再只有一个壳层：

1. A 层有 `WorkbenchLayerShell`
2. C 层有 `AdminLayerShell`

这说明“按层组织容器”的方向是成立的，不是纯概念。

### 3.3 设计来源记录已经有初版

`designSourceRecords` 已经把 Figma、concept demo、reference pool 三类来源写入 kernel contract，说明“设计来源必须被记录”这一原则已经开始落地，而不是继续口头化。

## 4. 事实上没有封口的地方

### 4.1 `AppShell` 仍然是旧世界与新世界的混合中心

原计划明确说：

1. 不在 `AppShell` 上继续补丁式演进。
2. 旧 hash 兼容应下沉为 compatibility adapter。

但当前 [`main/frontend-modern/src/app/shell/AppShell.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/shell/AppShell.tsx) 仍然承担：

1. 项目切换
2. 健康状态与环境状态
3. 页面装载分支
4. mode 切换
5. hash 路由写入
6. 页面级模块分发

与此同时，[`main/frontend-modern/src/app/kernel/ModuleRenderer.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/ModuleRenderer.tsx) 又复制了一套模块到页面的分发。

这意味着当前同时存在两套中心：

1. 旧的 `AppShell` 中心
2. 新的 `kernel + ModuleRenderer` 中心

这是当前最大未封口项。

### 4.2 compatibility adapter 还没有独立出来

[`main/frontend-modern/src/app/navigation/index.ts`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/navigation/index.ts) 目前仍直接承担：

1. `NavMode -> legacy hash`
2. legacy hash -> `NavMode`
3. 各页面片段与 query 的历史语义解释

而原计划要求：

1. 新入口固定为 `/#/workbench/*`、`/#/visual/*`、`/#/admin/*`
2. 旧 hash 兼容只允许以 adapter 形式存在

当前的现实是：新 route manifest 已经有了，但旧 hash 兼容还没有被隔离成“只映射、不承载业务判断”的单独模块。

### 4.3 B 层没有真正的 visualization container

当前：

1. A 层有 [`WorkbenchLayerShell.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/WorkbenchLayerShell.tsx)
2. C 层有 [`AdminLayerShell.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/AdminLayerShell.tsx)
3. B 层没有独立 shell，只是退回到 [`FrontendKernelApp.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/FrontendKernelApp.tsx) 里的 `LayerBridge`

这与 `T4` 要求的 visualization container contract 不一致。当前 B 层更像“归层已完成，容器未完成”。

### 4.4 页面没有完成 container / view 封边

从计划目标看，三层重写不只是“页面放在哪一层”，还意味着：

1. kernel 负责共享边界
2. layer shell 负责该层容器
3. 页面本身不应持续膨胀为“查询 + 状态机 + localStorage + UI + 业务流程控制”的大文件

但当前以下页面仍然非常重：

1. [`main/frontend-modern/src/pages/IngestPage.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/pages/IngestPage.tsx)
2. [`main/frontend-modern/src/pages/WritingWorkbenchPage.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/pages/WritingWorkbenchPage.tsx)
3. [`main/frontend-modern/src/pages/SettingsPage.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/pages/SettingsPage.tsx)
4. [`main/frontend-modern/src/pages/ProcessPage.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/pages/ProcessPage.tsx)
5. [`main/frontend-modern/src/pages/GraphPage.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/pages/GraphPage.tsx)

这会导致两个后果：

1. page stories 很难接近真实应用形态；
2. 新功能继续堆进 page 时，会让“归层”停留在路由名义上，而不是职责边界上。

### 4.5 模块清单存在多处事实来源

当前“模块是什么、在哪里显示、对应什么 hash、属于什么 surface、路由是什么”分散在：

1. [`main/frontend-modern/src/app/kernel/contracts.ts`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/contracts.ts)
2. [`main/frontend-modern/src/app/platform/modules/registry.ts`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/platform/modules/registry.ts)
3. [`main/frontend-modern/src/app/navigation/index.ts`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/navigation/index.ts)
4. [`main/frontend-modern/src/components/FigmaSideNav.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/components/FigmaSideNav.tsx)

这说明“模块 contract”虽然有了，但还不是唯一事实来源。

### 4.6 导航方案没有封口

当前主链明显依赖 `FigmaSideNav`，而 `FigmaTopNav` 并未被纳入统一壳层主链。这个状态说明导航体系还处于“并存尝试”，没有收敛成一个稳定系统。

### 4.7 计划文档本身没有状态回写

这是本专题最明显的文档缺口：

1. [`02_atomic-tasklist-frontend-three-layer-rewrite-2026-03-15.md`](./02_atomic-tasklist-frontend-three-layer-rewrite-2026-03-15.md) 里 `T0` 到 `T5` 仍全部是 `pending`
2. 但实际代码已经有部分 T1/T2/T3/T4 成果

结果是：

1. 文档无法回答“哪些已经做了、做到什么程度”
2. 后续实现者只能自己读代码猜状态

这不符合 `CURRENT_DEV` 文档应承担的口径职责。

## 5. 计划文档中本来就没有收口定义的地方

以下内容在原计划中被提出，但没有变成足够可执行的完成定义：

### 5.1 `AppShell` 下线标准

原计划说要“shell retirement”，但没有定义：

1. 旧壳层剩下哪些职责时才算可退役
2. 退役前后如何验证行为无回归
3. 哪个文件集必须归零

### 5.2 compatibility adapter 完成定义

原计划说要做 compatibility closure，但没有明确：

1. 旧 hash 全量清单由谁冻结
2. 未映射 hash 如何处理
3. adapter 文件边界长什么样
4. 哪些逻辑禁止继续放进 adapter

### 5.3 query / error / context 边界没有细化到实现级

原计划把 query boundary、error envelope、required context 归到 kernel，但没有把这些收敛成：

1. 标准字段清单
2. 页面接入方式
3. 统一失败态/空态/重试态规范
4. 统一 project context contract

### 5.4 设计来源验证没有量化

`DesignSourceRecord` 说明“来源要记录”，但没有定义：

1. 何时视为已对齐 design source
2. 何时必须截图对比
3. 何时必须回写到 Storybook / Figma / demo 对照表

## 6. 建议的收口顺序

不建议继续无差别补页面或补壳层视觉，而应按以下顺序收口。

### 6.1 S1：冻结唯一模块清单

目标：

1. 收敛 `moduleKey / layer / surface / route / legacy hash / nav group`
2. 形成唯一事实来源

建议动作：

1. 合并 `kernel/contracts.ts`、`platform/modules/registry.ts`、`navigation/index.ts` 的重叠信息
2. 输出一个统一的 `moduleManifest`
3. 其他文件只消费 manifest，不再自定义映射

### 6.2 S2：抽离 legacy compatibility adapter

目标：

1. 新路由与旧 hash 彻底分层
2. adapter 只做映射，不做业务判断

建议动作：

1. 新增 `app/kernel/compat/legacyHashAdapter.ts`
2. `navigation/index.ts` 缩减为历史常量兼容入口或直接被 adapter 吸收
3. `routes.ts` 只消费 adapter 结果

### 6.3 S3：补齐 B 层 shell

目标：

1. 让 A/B/C 三层都具备自己的容器而不是只完成 A/C
2. 固定 B 层对象详情、筛选区、视图切换的组织方式

建议动作：

1. 新增 `VisualizationLayerShell`
2. 将 `GraphPage`、`DashboardPage`、`PolicyPage`、`CatalogPage` 纳入统一 B 层容器
3. 把 `LayerBridge` 退化为临时兼容逻辑或直接删除

### 6.4 S4：对重页面执行 container / view 分离

优先文件：

1. `WritingWorkbenchPage`
2. `GraphPage`
3. `SettingsPage`
4. `IngestPage`
5. `ProcessPage`

目标：

1. 容器负责 query / mutation / route / local state / persistence
2. 视图负责渲染和交互事件回调
3. Storybook 主要承载 view 和 layer shell，而不是胖 page

### 6.5 S5：把计划状态回写到专题文档

目标：

1. 把“代码现实”同步回 `CURRENT_DEV`
2. 让后续执行者不需要再重新判读现状

建议动作：

1. 在 `02_atomic-tasklist...` 中补 status snapshot 更新
2. 明确 `T1/T2/T3/T4/T5` 的实际完成度
3. 增加“当前阻塞项 / 下一步入口 / retirement gate”

## 7. 建议的完成定义

本专题后续收口应至少满足以下完成定义：

1. `AppShell` 不再直接装载业务页面。
2. `ModuleRenderer` 是页面装载唯一入口。
3. B 层拥有自己的 visualization shell。
4. 旧 hash 兼容由独立 adapter 承担。
5. 模块 manifest 成为唯一事实来源。
6. 至少 4 个重页面完成 container / view 分离。
7. `CURRENT_DEV` 文档能明确标出：
   - 已完成项
   - 未封口项
   - 下一步收口顺序
   - 旧壳层下线条件

## 8. 推荐的后续文档动作

建议把本专题后续文档更新分成两步：

1. 先在原专题下补一份状态评估与缺口文档。
2. 再补一份新的原子任务单，只针对“收口”，不要再重复原始愿景描述。

如果不做这两步，后续开发会继续在“原始架构愿景”和“当前半重构现实”之间反复切换判断标准。

## 9. Storybook MCP-First Closure Progress (implemented 2026-04-02)

本轮已经把“Storybook 只是展示页”推进到“Storybook 是 agent-facing contract surface”的可用状态，重点不是补更多裸页面，而是让 MCP 能稳定消费真实壳层与状态矩阵。

### 9.1 已落地的收口项

1. 单一模块清单已经落地到 [`main/frontend-modern/src/app/kernel/moduleManifest.ts`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/moduleManifest.ts)，并成为 kernel contract、registry、navigation 的共同来源。
2. legacy hash 兼容已经抽离到 [`main/frontend-modern/src/app/kernel/legacyHashAdapter.ts`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/legacyHashAdapter.ts)，`navigation/index.ts` 只再承担转发角色。
3. B 层 `VisualizationLayerShell` 已经补齐，并接入 [`main/frontend-modern/src/app/kernel/FrontendKernelApp.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/app/kernel/FrontendKernelApp.tsx)。
4. Storybook 共享 provider 与 shell 入口已经落地到 [`main/frontend-modern/src/pages/storybookKernelUtils.tsx`](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/frontend-modern/src/pages/storybookKernelUtils.tsx)，页面 story 不再依赖“每页单独补 provider”的碎片方案。
5. 热点页 story 已升级为 `Container + Shell` 双入口，并按层分组进入 Storybook：
   - `Pages/Workbench/IngestPage`
   - `Pages/Workbench/WritingWorkbenchPage`
   - `Pages/Visualization/GraphPage`
   - `Pages/Management/SettingsPage`
   - `Pages/Management/ProcessPage`
6. `SettingsPage`、`ProcessPage` 与 `IngestPage` 已经从胖 page 中抽出显式 `View` 组件，当前生产代码可同时提供：
   - container page
   - view contract
   - shell story

### 9.2 已落地的热点页状态矩阵

上述 5 个热点页目前都已经具备下面至少 4 类中的大部分：

1. `ContainerDefault` 或等价真实数据态
2. `ContainerLoadingState` / `ContainerSelectionLoading` 之类的加载态
3. `ContainerEmptyState`
4. `ContainerErrorState` / `ContainerActionError` / `ContainerSelectionError`
5. `Container...Focus` 之类的模式差异态
6. `Shell...` 高保真壳层态

这意味着 agent 经由 Storybook MCP 可以直接：

1. 发现热点页在 A/B/C 三层中的归属；
2. 读取高频页面的状态矩阵，而不是只看到一个 happy path；
3. 在接近真实应用壳层的前提下预览页面；
4. 基于已有 story 修改页面而不是直接猜运行时上下文。

### 9.3 仍未封口的地方

本轮没有假装把所有问题一次做完，下面这些仍然是后续收口重点：

1. 五个热点页里已有三个完成真实 `View` 抽离，但 `WritingWorkbenchPage` 与 `GraphPage` 仍然主要是胖 container。
2. `AppShell` 还没有缩减到只剩 compatibility wrapper。
3. 非热点页虽然都已进入 Storybook，但大部分仍属于“存在 story”而不是“agent-ready matrix”。
4. `GraphPage` 仍然是 B 层最重页面，后续要继续拆对象详情、模式切换和模板编辑边界。

### 9.4 当前推荐执行顺序

在本轮基础上，后续应按下面顺序继续，而不是重新发散：

1. 先处理 `WritingWorkbenchPage` 的多浮窗 contract。
2. 再处理 `GraphPage` 的对象详情与模板编排拆分。
3. 最后回收 `AppShell` 的 legacy wrapper 边界。

## 10. Wave3 I Contract Gate Refresh (2026-05-22)

Wave3 I added a source-backed static gate for the topology, i18n, theme, and module-manifest contracts:

- Evidence: [../../../automation-runs/frontend-topology-theme/2026-05-22/README.md](../../../automation-runs/frontend-topology-theme/2026-05-22/README.md)
- Command: `npm --prefix main/frontend-modern run check:topology-platform`

The gate currently verifies:

1. `KernelModuleKey` and `moduleManifest` both cover 31 modules.
2. `PAGE_PLACEMENT_BASELINE` and `BASELINE_PAGE_INVENTORY` cover every module exactly once.
3. topology placement surfaces and baseline inventory surfaces agree.
4. shell title, nav label, and nav group keys exist with non-empty `zh-CN` and `en-US` catalog values.
5. `light`, `dark`, and `brand` themes expose the shared token groups.
6. `AppShell` consumes locale/theme contracts and applies theme tokens.
7. `FigmaSideNav` consumes the module registry, filters by interaction surface, and resolves labels through i18n keys.

This changes the 2026-04-02 gap interpretation:

- S1 single module manifest: source-backed and statically gated.
- S2 legacy compatibility adapter: source-backed through `kernel/legacyHashAdapter.ts` and static manifest/hash checks.
- S3 B-layer shell existence: no longer an open existence gap; remaining B-layer work is object/view contract depth, especially in `GraphPage`.
- i18n/theme platform basics: no longer an open planning gap; remaining work is business-content localization and legacy CSS cleanup.

Still open:

1. `AppShell` is not yet compatibility-only.
2. `WritingWorkbenchPage` and `GraphPage` remain heavy container pages.
3. The new static gate complements but does not replace runtime E2E and visual evidence.
