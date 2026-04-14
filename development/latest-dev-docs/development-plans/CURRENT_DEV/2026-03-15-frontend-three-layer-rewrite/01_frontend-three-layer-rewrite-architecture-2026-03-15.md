# Frontend Three-Layer Rewrite Architecture (2026-03-15)

> 日期：2026-03-15
> 范围：`main/frontend-modern`
> 状态：architecture master document
> 目标：冻结“三个用户层 + 一个共享平台内核”的前端重写方案，明确保留哪些核心交互闭环，以及如何获取和验证设计信息

## 1. 目标与结论

本专题不是在现有 modern 壳层上继续补丁整理，而是为下一轮前端重写冻结一个新的主架构。

本轮必须明确四件事：

1. 新前端固定采用 A/B/C 三个用户层，加一个共享平台内核。
2. 现有业务中必须保留的核心交互闭环是什么，哪些只是旧壳层实现细节。
3. 新前端对外暴露哪些稳定 contract，确保后续实现不再靠 `AppShell` 分支堆叠。
4. 设计信息从哪里来、如何拿、如何验证没有偏离目标。

本专题冻结的最终结论如下：

- A 层：交互工作台层，承接高密度、多面板、长上下文、对象级持续操作。
- B 层：可视化分析层，承接图谱、分析、看板、空间化或图形化检查。
- C 层：管理治理层，承接项目、资源、流程、爬虫、设置等事务型管理。
- 共享平台内核是底座，不算第四个业务层，只负责项目上下文、鉴权假设、路由兼容、查询缓存、通知、主题/语言、错误边界、设计 token 边界。
- 当前 `AppShell`、模块注册、旧主题/导航实现只作为基线盘点对象，不作为目标架构延续物。

## 2. 当前基线与为什么必须重写

### 2.1 已验证的当前实现形态

当前活动前端集中在 `main/frontend-modern`，其主入口与壳层事实包括：

- `src/App.tsx`：仍承担 demo 入口和 standalone hash 分发。
- `src/app/shell/AppShell.tsx`：承担现有 shell、项目上下文、lazy page mounting、状态芯片和模式切换。
- `src/app/navigation/index.ts`：维护 `NavMode -> hash` 映射与旧 hash 归一化。
- `src/components/FigmaSideNav.tsx`：维护当前分组导航与部分模式定义。

这意味着当前系统已经有“单壳层 + 单导航 + 单 hash 兼容层”的事实基线，但没有新的三层式架构边界。

### 2.2 当前页面已呈现三类完全不同的交互密度

从现有页面可直接观察到三种交互类型：

- 工作台型：
  - `WritingWorkbenchPage.tsx`
  - `LlmDesignerPage.tsx`
  - `IngestPage.tsx`
  - `RawDataPage.tsx`
- 可视化分析型：
  - `GraphPage.tsx`
  - `DashboardPage.tsx`
  - `PolicyPage.tsx`
  - `CatalogPage.tsx`
- 管理治理型：
  - `ProjectsPage.tsx`
  - `CrawlerManagePage.tsx`
  - `ResourcePage.tsx`
  - `ProcessPage.tsx`
  - `SettingsPage.tsx`
  - `OpsPage.tsx`

### 2.3 现有壳层不应继续被视为目标架构

当前壳层已经暴露出不适合作为未来主架构继续扩展的特征：

- 页面装载依赖 `AppShell.tsx` 中的长分支判断。
- 路由语义、导航分组、模块可见性、页面标题分散在多个位置维护。
- 工作台、可视化、管理型页面被塞进同一个交互密度模型中，只是视觉包装不同。
- 当前 demo 已经给出 A/B/C 三层视觉语义，但业务页面尚未真正按 A/B/C 层被组织。

因此，本专题明确要求：

- 不在 `AppShell` 上继续补丁式演进。
- 不把旧模块注册表直接升级为新平台 contract。
- 以“重写平台内核 + 分层替换页面容器 + 兼容旧 hash”的方式演进。

## 3. 目标架构：三个用户层 + 一个共享平台内核

### 3.1 总体结构

新前端固定采用如下结构：

1. Shared Platform Kernel
2. Layer A / Workbench
3. Layer B / Visualization
4. Layer C / Management

其中 Shared Platform Kernel 不是用户层，而是所有层共享的底层约束。

### 3.2 Shared Platform Kernel 责任边界

共享平台内核必须统一负责：

- `project_key` 上下文与项目切换
- 统一鉴权假设、会话入口与 API client 约定
- 查询缓存、query key、错误 envelope、全局 loading / empty / failure 行为
- 新路由分组与旧 hash 兼容
- locale、theme、design token 与基础 layout primitive
- 全局通知、全局错误边界、跨层跳转协调

共享平台内核不负责：

- 具体业务页面布局
- 工作台的多面板容器编排
- 可视化引擎细节
- 管理页的表单与列表形态

### 3.3 A 层：交互工作台层

A 层用于“对象级持续工作”，其核心信号是：

- 会话持续时间长
- 多面板协同明显
- 上下文保留要求高
- 操作结果会继续回流到当前对象
- 信息卡片或辅助上下文需要频繁插入

固定归入 A 层的当前页面：

- `WritingWorkbenchPage`
- `LlmDesignerPage`
- `IngestPage`
- `RawDataPage`

### 3.4 B 层：可视化分析层

B 层用于“图形化或分析化检查”，其核心信号是：

- 主对象通过图谱、图形、指标板或分析视图呈现
- 用户核心动作是观察、筛选、选择、缩放、切换视图、检查对象详情
- 结果主要是分析判断而不是 CRUD 提交

固定归入 B 层的当前页面：

- `GraphPage` 全变体
- `DashboardPage` 全变体
- `PolicyPage`
- `CatalogPage`

### 3.5 C 层：管理治理层

C 层用于“管理、配置、调度、审计、维护”，其核心信号是：

- 列表、表单、状态、配置是主要交互
- 行为更偏事务提交与状态查询
- 追求可预测性、低学习成本、稳定完成路径

固定归入 C 层的当前页面：

- `ProjectsPage`
- `CrawlerManagePage`
- `ResourcePage`
- `ProcessPage`
- `SettingsPage`
- `OpsPage`

## 4. 页面归层矩阵与保留闭环

### 4.1 页面归层矩阵

| 当前页面 | 目标层 | 理由 | 必保留闭环 |
| --- | --- | --- | --- |
| `WritingWorkbenchPage` | A | 长会话、多面板、持续编辑与辅助生成 | 编辑、预览、模板、LLM 辅助、引用篮、信息卡片 |
| `LlmDesignerPage` | A | 节点编排、参数编辑、运行检查、结果回看 | 节点模板、连线、运行参数、结果查看、导入导出 |
| `IngestPage` | A | 摄取型工作链存在持续参数调整与结果回看 | 输入配置、执行、状态回流、结果检查 |
| `RawDataPage` | A | 原始数据处理具有强链路式工作流特征 | 数据输入、处理链、结果检查、继续操作 |
| `GraphPage` 全变体 | B | 以图谱视图与对象检查为主 | 2D/3D 或多视图切换、筛选、节点/关系选择、详情检查 |
| `DashboardPage` 全变体 | B | 以指标、分析、趋势观察为主 | 视图切换、筛选、钻取、对象详情联动 |
| `PolicyPage` | B | 以政策可视化与分析查看为主 | 过滤、视图观察、详情检查 |
| `CatalogPage` | B | 以类目、视图切换、对象检索为主 | 过滤、浏览、详情联动 |
| `ProjectsPage` | C | 项目生命周期管理 | 项目创建、切换、归档、删除、注入 |
| `CrawlerManagePage` | C | 爬虫项目导入、部署、回滚、状态查看 | 导入、部署、回滚、详情、刷新 |
| `ResourcePage` | C | 来源库与站点入口维护、推荐与批量动作 | 搜索、筛选、推荐、站点入口维护、批量动作 |
| `ProcessPage` | C | 任务列表与任务详情、取消、历史跟踪 | 任务列表、详情、自动刷新、取消、历史查看 |
| `SettingsPage` | C | 系统与 LLM 配置维护 | 配置编辑、模板设置、复制、保存 |
| `OpsPage` | C | 运营、后台、检查类控制台 | 状态查看、配置/控制入口、事务性维护 |

### 4.2 必须保留的核心交互闭环

本专题保留的是“能力 contract”，不是旧页面布局，也不是旧组件文件结构。

必须保留的闭环如下：

1. 写作工作台闭环
   - 编辑
   - 预览
   - 模板起稿
   - LLM 辅助
   - 引用篮
   - 信息卡片
2. 图谱与分析闭环
   - 2D/3D 或多视图切换
   - 过滤与范围控制
   - 节点/关系对象选择
   - 详情检查
3. 流程设计闭环
   - 节点模板
   - 连线
   - 运行参数
   - 结果查看
   - 导入导出
4. 资源/来源库闭环
   - 搜索
   - 筛选
   - 推荐
   - 站点入口维护
   - 批量动作
5. 流程监控闭环
   - 任务列表
   - 详情
   - 自动刷新
   - 取消
   - 历史查看
6. 管理治理闭环
   - 项目切换
   - 爬虫导入/部署/回滚
   - 设置编辑

### 4.3 Info Card 的跨层边界

`info card` 是跨层能力，但不跨层同形态复用。

- A 层：保留为沉浸式上下文卡片，用于写作、工作台辅助、对象上下文补充。
- B 层：保留为图谱/分析对象详情入口，用于节点、关系、指标对象的上下文检查。
- C 层：不承载沉浸式 info card，只保留轻量详情面板或只读详情抽屉。

## 5. 新前端必须冻结的 contract

本专题要求下一轮实现不再靠零散约定推进，因此必须先冻结稳定 contract。

### 5.1 核心类型

建议以下类型作为新前端的稳定外部 contract：

```ts
type LayerId = 'A' | 'B' | 'C'

type SurfaceKind = 'workbench' | 'visualization' | 'management'

type RouteManifest = {
  layer_id: LayerId
  surface_kind: SurfaceKind
  route_path: string
  legacy_hashes: string[]
  module_key: string
}

type ModuleContract = {
  module_key: string
  layer_id: LayerId
  surface_kind: SurfaceKind
  entry_route: string
  required_context: string[]
  keep_loops: string[]
  supports_info_card: boolean
}

type DesignSourceRecord = {
  source_type: 'figma' | 'demo' | 'reference_pool'
  source_ref: string
  target_layers: LayerId[]
  reuse_target: 'interaction' | 'structure' | 'visual_semantics'
  validation_method: string
}
```

### 5.2 route_manifest

新路由分组固定按层组织：

- `/#/workbench/*`
- `/#/visual/*`
- `/#/admin/*`

迁移期兼容规则固定为：

1. 当前 `hashByMode` 对应的旧 hash 继续可访问。
2. 旧 hash 进入 compatibility adapter。
3. compatibility adapter 只负责把旧入口归一化到新分层入口，不继续承载业务页面装载逻辑。
4. compatibility adapter 的存在只服务于分阶段替换，不允许成为新的永久壳层。

### 5.3 module_contract

每个业务模块至少需要定义：

- 属于哪一层
- 属于哪种 surface kind
- 新入口路径
- 所需上下文
- 必须保留的闭环
- 是否支持 info card

模块 contract 要优先替代当前以下分散维护方式：

- `AppShell` 的页面分支装载
- `hashByMode`
- 侧导航分组与标题元数据
- 页面标题与可见性分支

### 5.4 design_source_record

每个层或模块在进入实现前，都必须补齐设计来源记录。

记录至少回答：

- 设计信息来自哪里
- 服务哪一层
- 复用的是交互、结构还是视觉语义
- 实现前如何做偏差验证

## 6. Design Information Acquisition and Validation

本章节是强制章节。后续实现不能跳过，也不能用“凭感觉设计”替代。

### 6.1 来源一：Figma

当前已验证的 Figma 设计来源记录在：

- `development/latest-dev-docs/ops-frontend/F_PLAN/frontend-modern-figma-sync-PULL_STATUS_2026-02-27.md`

已知可直接复用的事实：

- Source file: `1IGWKEkcI40MUEAW4HJyv3`
- Root node: `427:6918`
- 已拉取 top nav light sample: `461:24152`
- 已拉取 side nav light sample: `1186:27288`
- dark / brand 变体是基于 design token 本地生成
- 后续继续拉取时曾被 Figma MCP plan limit 阻塞

继续获取 Figma 设计信息的方法固定为：

1. 先查看该状态文档，确认 file id、root node、已拉取节点和阻塞原因。
2. 节点级继续拉取时，优先补 A/B/C 三层入口、共享导航、关键容器，而不是先补零散原子组件。
3. 若 Figma MCP 仍受 seat / plan 限制，先在文档中记录阻塞，再转向 demo 与参考池补足结构判断，禁止无记录地拍脑袋改设计。

Figma 主要服务于：

- 共享平台内核的导航与顶层容器节奏
- C 层的稳定信息层级与导航骨架
- 三层之间共用的 token、间距、状态表达边界

### 6.2 来源二：Concept Demo

当前 concept demo 的直接实现位于：

- `src/pages/ConceptLabIndexPage.tsx`
- `src/pages/ConceptQuietPage.tsx`
- `src/pages/ConceptOrbitalPage.tsx`
- `src/pages/ConceptMonolithPage.tsx`
- `src/pages/concept-lab.css`

当前 demo 路由入口由 `src/App.tsx` 处理，已知 hash 包括：

- `#design-concepts.html`
- `#concept-quiet.html`
- `#concept-orbital.html`
- `#concept-monolith.html`

这些 demo 的角色必须被明确解释：

- `ConceptQuietPage`：A 层视觉语义样本，强调编辑、阅读、连续性、软性上下文。
- `ConceptOrbitalPage`：B 层视觉语义样本，强调空间感、分析场、对象观测和多轨信息。
- `ConceptMonolithPage`：C 层视觉语义样本，强调治理、秩序、硬边界、稳定操作。
- `ConceptLabIndexPage`：只作为设计索引页，不参与业务信息架构。

这些 demo 不等于最终业务页面，它们只承担：

- 视觉语义定向
- 布局气质和信息密度边界
- 层与层之间的风格差异说明

禁止把 demo 直接误当成最终产品页面原型。

### 6.3 来源三：本地 OSS 参考池

本地 OSS 参考池主要位于 `reference-pool/oss/`，本专题固定引用以下方向：

- Outline
  - `reference-pool/oss/outline/app/components/Sidebar/`
  - `reference-pool/oss/outline/app/components/Template/`
  - `reference-pool/oss/outline/app/components/TemplatizeDialog/`
  - `reference-pool/oss/outline/app/components/HoverPreview/`
- SilverBullet
  - `reference-pool/oss/silverbullet/client/`
- SilverBullet AI
  - `reference-pool/oss/silverbullet-ai/src/chat-panel.ts`
  - `reference-pool/oss/silverbullet-ai/src/prompts.ts`
  - `reference-pool/oss/silverbullet-ai/assets/chat-panel.html`
- Logseq
  - `reference-pool/oss/logseq/src/main/frontend/search/`
  - `reference-pool/oss/logseq/src/main/frontend/handler/search.cljs`
  - `reference-pool/oss/logseq/src/main/frontend/commands.cljs`
  - `reference-pool/oss/logseq/src/main/frontend/handler/route.cljs`
- CodeMirror View
  - `reference-pool/oss/codemirror-view/src/tooltip.ts`
  - `reference-pool/oss/codemirror-view/src/panel.ts`

参考池的使用原则固定为：

1. 借交互骨架，不照抄视觉。
2. 优先借“完成一条闭环所需的面板组织、hover/preview、selection、chat panel、搜索入口、tooltip/panel”，不借其品牌风格。
3. 参考池只提供交互成熟度和信息结构启发，不能覆盖项目自身的 A/B/C 视觉语义。

### 6.4 设计来源到层能力映射表

| 来源 | 支撑层 | 主要复用目标 | 实现前验证方式 |
| --- | --- | --- | --- |
| Figma top nav / side nav / tokens | A / B / C / Kernel | structure + visual_semantics | 对照 file id、node id、状态文档，确认导航骨架与 token 口径一致 |
| `ConceptQuietPage` | A | visual_semantics | 检查是否保持工作台的阅读节奏、连续上下文与非管理型气质 |
| `ConceptOrbitalPage` | B | visual_semantics | 检查是否突出空间化分析、对象观察、视图切换感 |
| `ConceptMonolithPage` | C | visual_semantics | 检查是否体现稳定治理、硬边界、事务型操作氛围 |
| Outline Sidebar / Template / HoverPreview | A / C | interaction + structure | 检查是否提升工作台侧栏、模板入口、轻预览效率，而非复制视觉 |
| SilverBullet / SilverBullet AI | A | interaction + structure | 检查编辑、预览、AI 面板是否服务写作闭环，而非独立玩具功能 |
| Logseq search / route / commands | B / C | interaction + structure | 检查搜索、命令入口、对象定位是否增强分析和管理效率 |
| CodeMirror tooltip / panel | A / B | interaction | 检查 selection、tooltip、详情卡片是否简化对象上下文查看 |

### 6.5 实现前的统一设计校验

任何模块在进入实现前，必须完成以下校验：

1. 明确该模块服务哪个层。
2. 明确该模块至少绑定一个设计来源记录。
3. 明确复用的是交互、结构还是视觉语义。
4. 明确如何判断“没有跑偏”。

若无法完成以上四项，不允许直接进入 UI 实现。

## 7. 分阶段替换策略

本专题明确采用“分阶段替换”，不采用一次性切换，也不规划长期双轨产品。

### 7.1 替换原则

- 先重建共享平台内核，再按 C -> A -> B 的顺序替换用户层。
- 替换期保留旧 hash 兼容，但不保留旧壳层作为长期目标。
- 每一层切换都以“闭环可用 + contract 到位 + 兼容未断”为验收边界。

### 7.2 固定替换顺序

1. 基线冻结
2. 平台内核重建
3. C 层先行
4. A 层重建
5. B 层重建
6. 兼容收口

该顺序固定，不留给实现者重新排序：

- C 层先行是为了先稳定项目、资源、流程、设置等底座入口。
- A 层第二是为了尽早恢复工作台与关键深交互能力。
- B 层第三是因为其依赖前两者提供的平台内核、对象上下文与路由边界。

## 8. 文档评审与验收标准

本主文档完成后，评审时必须能够直接回答：

1. 任一当前页面归 A/B/C 哪一层，为什么。
2. 任一页面迁移后必须保留哪些闭环。
3. 新前端为什么不是在 `AppShell` 上继续补丁。
4. 新路由如何兼容当前 `hashByMode`。
5. Figma、concept demo、参考池的设计信息分别从哪里拿、怎么验证。

若仍存在“实现者需要自己再做架构决策”的空白，则该文档视为未完成。

## 9. 非目标

本专题明确不做以下承诺：

- 不在本轮定义最终像素级视觉稿。
- 不在本轮承诺新旧前端长期并行运营。
- 不在本轮重写 backend API 语义。
- 不把所有领域专题重新写一遍，只重写前端总体架构与迁移主线。
