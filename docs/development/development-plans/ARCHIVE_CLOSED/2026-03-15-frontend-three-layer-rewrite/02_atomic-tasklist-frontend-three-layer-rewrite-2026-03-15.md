# Atomic Task List: Frontend Three-Layer Rewrite (2026-03-15)

## Execution Status Snapshot

- `T0`: completed for baseline freeze and design-source inventory; evidence has been folded into `CURRENT_DEV` assessment and kernel manifest source refs.
- `T1`: in_progress; shared kernel contract, single module manifest, and legacy hash adapter have landed, but page-level view contracts are not yet universal.
- `T2`: in_progress; management layer shell and MCP-facing settings/process stories are in place, but C-layer pages are not yet fully container/view split.
- `T3`: in_progress; workbench shell stories for ingest/writing are in place and Storybook is now an agent-facing contract surface, but A-layer heavy pages remain container-heavy.
- `T4`: in_progress; visualization shell has landed and graph shell stories exist, but B-layer object/view contracts remain concentrated in `GraphPage`.
- `T5`: in_progress; compatibility adapter is extracted and retirement criteria are documented, but `AppShell` has not yet been reduced to compatibility-only duties.

2026-05-22 Wave3 I refresh:

- topology, module manifest, shell i18n, and theme token contracts are now covered by `npm --prefix main/frontend-modern run check:topology-platform`;
- evidence is stored at [../../../automation-runs/frontend-topology-theme/2026-05-22/README.md](../../../automation-runs/frontend-topology-theme/2026-05-22/README.md);
- do not treat the single manifest, legacy hash adapter, B-layer shell existence, locale catalog, or theme token groups as open existence gaps;
- remaining `T1-T5` risk is about retirement depth and page boundary depth, not missing platform contract primitives.

## Global Serial-Parallel Rules

- `L0` serial bootstrap:
  - `T0` must finish first.
- `L1` platform gate:
  - `T1` depends on `T0`.
- `L2` user-layer rollout:
  - `T2` depends on `T1`
  - `T3` depends on `T1 + T2`
  - `T4` depends on `T1 + T3`
- `L3` closure:
  - `T5` depends on `T2 + T3 + T4`

Parallelism rule:

- kernel route contract, design token contract, locale/theme contract, and project-context contract are serial because they all touch the same cross-layer entry boundary;
- domain feature recovery inside one layer can be parallelized only after that layer container and module contract are frozen.

## Global Module Boundaries

| Module | Purpose | Read boundary | Output boundary |
| --- | --- | --- | --- |
| `baseline-freeze` | freeze current pages, loops, hash routes, and design-source evidence | current frontend code + existing docs + concept demo + reference pool | baseline inventory and rewrite inputs |
| `kernel-rebuild` | define the new shared platform kernel | baseline outputs | layer-neutral contracts |
| `layer-c-rebuild` | rebuild management/governance surfaces | kernel contracts + current C-layer pages | new C-layer module map |
| `layer-a-rebuild` | rebuild workbench surfaces | kernel contracts + A-layer domain docs | new A-layer module map |
| `layer-b-rebuild` | rebuild visualization surfaces | kernel contracts + stabilized object contracts | new B-layer module map |
| `compat-closure` | close legacy hash compatibility and shell retirement | all prior outputs | compatibility adapter rules and retirement gate |

## Task T0: Freeze Baseline, Old Routes, and Design Sources

- 目标: 在真正开始重写前，冻结当前页面归层、旧 hash 入口、核心交互闭环、以及设计来源证据。
- status: completed
- depends_on: `[]`
- blocks: `["T1","T2","T3","T4","T5"]`
- 输入:
  - `main/frontend-modern/src/App.tsx`
  - `main/frontend-modern/src/app/shell/AppShell.tsx`
  - `main/frontend-modern/src/app/navigation/index.ts`
  - `main/frontend-modern/src/pages/*`
  - `development/latest-dev-docs/ops-frontend/F_PLAN/frontend-modern-figma-sync-PULL_STATUS_2026-02-27.md`
  - `reference-pool/oss/*`
- 输出:
  - 当前页面 -> A/B/C 归层表
  - 旧 hash -> 新分层入口映射草案
  - 核心交互闭环盘点表
  - 设计来源记录表
- 验收:
  - 任一当前页面都能回答“归哪一层、为什么、保留哪些闭环”；
  - concept demo 与 Figma 来源已被明确记录；
  - 旧 hash 兼容范围被明确列出，而不是交给后续临时发现。
- 最小验证:
  - `rg -n "concept-|design-concepts|resolveStandaloneView" main/frontend-modern/src/App.tsx`
  - `rg -n "hashByMode|parseLegacyHashToMode" main/frontend-modern/src/app/navigation/index.ts`
  - `rg --files main/frontend-modern/src/pages`
- 模块边界:
  - reads: 现有前端代码与设计文档
  - writes: 基线冻结与输入清单

## Task T1: Rebuild the Shared Platform Kernel

- 目标: 重建一个不依赖旧 `AppShell` 分支堆叠的新平台内核，冻结跨层 contract。
- status: in_progress
- depends_on: `["T0"]`
- blocks: `["T2","T3","T4","T5"]`
- 输入:
  - `T0` 基线冻结输出
- 输出:
  - `layer_id` / `surface_kind` 类型定义
  - `route_manifest`
  - `module_contract`
  - `design_source_record`
  - 新平台的项目上下文、query boundary、theme/locale/token、错误边界、通知边界
- 验收:
  - 新 contract 不再以旧 `AppShell` 为中心；
  - 新入口固定按 `/#/workbench/*`、`/#/visual/*`、`/#/admin/*` 分组；
  - 旧 hash 兼容被下沉为 compatibility adapter，而不是继续扩展旧装载分支；
  - theme/locale/token 被定义为 kernel 资产，而不是页面各自维护。
- 最小验证:
  - 核对 contract 是否足以描述任一 A/B/C 模块；
  - 核对 compatibility adapter 是否只负责映射，不负责业务页面逻辑。
- 模块边界:
  - reads: 基线冻结结果
  - writes: 共享平台内核 contract

## Task T2: Rebuild Layer C First

- 目标: 先重建管理治理层，稳定项目、资源、流程、爬虫、设置等底座入口。
- status: in_progress
- depends_on: `["T1"]`
- blocks: `["T3","T5"]`
- 输入:
  - kernel contracts
  - `ProjectsPage`
  - `CrawlerManagePage`
  - `ResourcePage`
  - `ProcessPage`
  - `SettingsPage`
  - `OpsPage`
- 输出:
  - Layer C 路由与模块清单
  - C 层容器规范
  - C 层保留闭环映射
  - C 层详情面板边界
- 验收:
  - 项目切换、爬虫导入/部署/回滚、资源维护、任务监控、设置编辑被明确保留；
  - C 层采用事务型、可预测、低密度管理交互，不混入沉浸式工作台结构；
  - info card 在 C 层被限制为轻量详情面板。
- 最小验证:
  - `ResourcePage` 的搜索/筛选/推荐/入口维护/批量动作是否都在新模块表中有位置；
  - `ProcessPage` 的自动刷新、取消、历史查看是否仍是保留 contract；
  - `SettingsPage` 与 `ProjectsPage` 是否继续共享 kernel 的项目上下文与主题/语言能力。
- 模块边界:
  - reads: kernel + 当前 C 层页面
  - writes: C 层模块映射与闭环规范

## Task T3: Rebuild Layer A

- 目标: 在 kernel 与 C 层稳定后，重建工作台层并恢复最重要的深交互闭环。
- status: in_progress
- depends_on: `["T1","T2"]`
- blocks: `["T4","T5"]`
- 输入:
  - kernel contracts
  - A 层领域文档
  - `WritingWorkbenchPage`
  - `LlmDesignerPage`
  - `IngestPage`
  - `RawDataPage`
- 输出:
  - Layer A 路由与模块清单
  - workbench container contract
  - info card workbench contract
  - A 层保留闭环映射
- 验收:
  - 写作工作台的编辑、预览、模板、LLM、引用篮、信息卡片闭环完整保留；
  - 流程设计的节点模板、连线、运行参数、结果查看、导入导出闭环完整保留；
  - A 层容器支持长会话、多面板、上下文连续性；
  - A 层不退化成普通 CRUD 页面集合。
- 最小验证:
  - `WritingWorkbenchPage` 的选择上下文、引用篮、LLM 辅助是否都被映射到新 workbench contract；
  - `LlmDesignerPage` 的模板、边界节点、运行参数、JSON 导入导出是否都在保留列表中；
  - `IngestPage`、`RawDataPage` 是否被明确定义为工作台而不是管理页。
- 模块边界:
  - reads: kernel + A 层领域基线
  - writes: A 层容器与模块 contract

## Task T4: Rebuild Layer B

- 目标: 在对象上下文和工作台 contract 稳定后，重建可视化分析层。
- status: in_progress
- depends_on: `["T1","T3"]`
- blocks: `["T5"]`
- 输入:
  - kernel contracts
  - `GraphPage`
  - `DashboardPage`
  - `PolicyPage`
  - `CatalogPage`
- 输出:
  - Layer B 路由与模块清单
  - visualization container contract
  - B 层对象详情与 info card contract
  - B 层保留闭环映射
- 验收:
  - 图谱页面的视图切换、过滤、对象选择、详情检查被完整保留；
  - Dashboard / Policy / Catalog 保持分析与对象观察语义，不退化为普通列表页；
  - B 层 info card 以对象详情入口形态存在，而不是复制 A 层写作卡片。
- 最小验证:
  - `GraphPage` 的 2D/3D、多视图、选择状态、详情联动是否都有明确容器位置；
  - Dashboard / Policy / Catalog 是否被统一纳入 visualization container，而不是各自独立定义壳层。
- 模块边界:
  - reads: kernel + B 层页面基线
  - writes: B 层容器与对象联动 contract

## Task T5: Compatibility Closure and Shell Retirement

- 目标: 收口旧 hash 兼容，定义旧壳层下线条件，关闭重写尾部开放决策。
- status: in_progress
- depends_on: `["T2","T3","T4"]`
- blocks: `[]`
- 输入:
  - A/B/C 层模块清单
  - kernel route manifest
  - 旧 hash 盘点表
- 输出:
  - compatibility adapter 清单
  - 旧 hash -> 新入口映射表
  - 遗留壳层下线条件
  - 评审 closure checklist
- 验收:
  - 当前旧 hash 仍能落到正确层入口；
  - A/B/C 三层都能证明各自保留了约定闭环；
  - info card 在 A/B 两层边界清晰；
  - closure checklist 明确包含“无开放性架构决策残留”。
- 最小验证:
  - 逐条核对旧 `hashByMode` 的兼容映射；
  - 核对每一层是否都有路由、模块、闭环、设计来源记录；
  - 核对旧 `AppShell` 只剩兼容职责或可被安全下线。
- 模块边界:
  - reads: 所有前置阶段结果
  - writes: 兼容收口与下线标准

## Final Review Checklist

- 主架构文档是否已经明确 A/B/C 固定归层。
- 新前端是否已被定义为“一套新前端 + 分阶段替换”，而不是长期双轨。
- 任一实现者是否只看文档就能知道：
  - 新入口是什么；
  - 旧 hash 如何兼容；
  - 核心闭环要保留什么；
  - 设计信息去哪拿；
  - 哪一阶段先做、依赖什么、验收什么。
- 若以上任一问题仍需实现者自行判断，则本 tasklist 视为未完成。
