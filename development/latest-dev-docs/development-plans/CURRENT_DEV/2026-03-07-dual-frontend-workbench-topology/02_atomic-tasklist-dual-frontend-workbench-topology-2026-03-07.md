# Atomic Task List: Modern-Based Dual-Interaction Frontend Topology (2026-03-07)

## 定位

本任务清单服务于基于 modern 技术路线的双交互前端拓扑规划。  
这里的“双交互”表示两类前端交互面：

- 高交互工作台前端
- 低交互管理前端

本清单不再包含任何旧前端共存、legacy 页面迁移、双前端兼容相关任务。

## 全局规则

- 先冻结判断标准，再给页面归类。
- 先定义共享平台层，再讨论是否共用壳层或导航容器。
- 先冻结共享契约，再决定哪些交互逻辑需要独立实现。
- 先明确导航与切换规则，再讨论具体页面改造顺序。
- 每个子任务都必须围绕 modern 技术路线展开，不得把旧前端当作活跃对象写入计划。

## Task A1: Freeze Dual-Interaction Criteria

- 目标：定义工作台面与管理面的判定标准。
- 输入：
  - 当前 modern 页面集合
  - `AppShell`、导航和页面结构现状
- 输出：
  - 一份双交互判定规则
  - 一组归类判断维度说明
- 验收：
  - 至少包含交互密度、上下文连续性、多面板协作、实时反馈、编辑深度五类维度
  - 规则可以直接用于后续页面归位

## Task A2: Produce Initial Page Placement

- 目标：对当前主要 modern 页面做第一版拓扑归位。
- 输入：
  - `GraphPage`
  - `WritingWorkbenchPage`
  - `LlmDesignerPage`
  - `ProjectsPage`
  - `ResourcePage`
  - `CrawlerManagePage`
  - `SettingsPage`
  - `DashboardPage`
  - `ProcessPage`
- 输出：
  - 一份页面归位表
  - 一份边界模糊页说明
- 验收：
  - 至少区分工作台面候选、管理面候选、待拆分候选三类
  - 每个边界模糊页面都说明判定依据

## Task A3: Define Shared Platform Layer

- 目标：冻结双交互前端的统一共享层与可定制层边界。
- 输入：
  - 壳层、导航、权限、主题、i18n、数据访问现状
- 输出：
  - 一份共享能力清单
  - 一份允许双交互前端分别定制的能力清单
- 验收：
  - 至少覆盖项目上下文、身份权限、路由深链接、主题、国际化、数据访问、全局通知
  - 明确哪些能力不能在工作台面和管理面重复建设
  - 明确共享契约不等于共享同一交互逻辑

## Task A4: Define Navigation and Context Switching

- 目标：明确用户如何识别并切换两类交互前端。
- 输入：
  - `AppShell`
  - `FigmaSideNav`
  - 当前路由和页面切换方式
  - 是否拆分独立入口的可行性
- 输出：
  - 一份一级导航表达方案
  - 一份上下文保留/重置规则
- 验收：
  - 至少说明项目上下文、筛选状态、对象选中状态在切换时如何处理
  - 至少说明工作台前端与管理前端的入口组织方式

## Task A5: Freeze Phased Delivery Plan

- 目标：把主题落成可执行的 Phase 1 / 2 / 3 计划。
- 输入：
  - A1 至 A4 的结论
- 输出：
  - 一份分阶段交付清单
  - 一份跨主题协作依赖表
- 验收：
  - Phase 1 聚焦规则和归位
  - Phase 2 聚焦导航与切换
  - Phase 3 聚焦实现排序和组件改造优先级

## Task A6: Define Minimal Validation

- 目标：为后续实现阶段预留最小验证基线。
- 输入：
  - 拓扑规则
  - 页面归位结果
  - 导航与共享层方案
- 输出：
  - 一份最小验证清单
- 验收：
  - 至少包含一个工作台面页面验证样例
  - 至少包含一个管理面页面验证样例
  - 至少包含一个跨交互面切换验证样例
  - 至少包含一个共享平台层复用验证样例
