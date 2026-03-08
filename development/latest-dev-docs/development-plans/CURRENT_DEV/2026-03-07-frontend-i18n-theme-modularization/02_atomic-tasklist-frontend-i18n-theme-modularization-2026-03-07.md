# Atomic Task List: Frontend I18N Theme Modularization (2026-03-07)

## 定位

本任务清单用于把 `main/frontend-modern` 的国际化、主题系统和模块化装配拆成可交付的原子任务。

本清单的唯一前提是：

- 活跃前端只有 `main/frontend-modern`
- “双交互”指基于 modern 技术路线的两类前端共享必要平台基础设施，而不预设必须共用同一壳层

## 全局规则

- 所有任务都必须锚定 `main/frontend-modern` 的真实代码入口。
- 所有需求都必须落到壳层、导航、设置页或模块注册机制，不允许停留在抽象口号。
- i18n、theme、module 三层要分别写清楚对象、状态来源、接入点和验收。
- 必须区分“共享平台契约”和“共享交互逻辑”，不得默认高低交互前端必须同构。
- 子任务文档必须同时写明当前基线、目标状态、阶段安排和最小验证。

## Task A1: Freeze Modern Frontend Baseline

- 目标：确认 modern 前端当前在语言、主题、导航和模块装配方面的真实基线。
- 输入：
  - `main/frontend-modern/src/app/shell/AppShell.tsx`
  - `main/frontend-modern/src/app/navigation/index.ts`
  - `main/frontend-modern/src/components/FigmaSideNav.tsx`
  - `main/frontend-modern/src/pages/SettingsPage.tsx`
  - `main/frontend-modern/src/index.css`
- 输出：
  - 一份基线摘要
  - 一份明确缺口清单
- 验收：
  - 说清当前哪些能力已存在
  - 说清哪些地方仍是硬编码或手工装配
  - 全文只围绕 `main/frontend-modern`

## Task A2: Freeze I18N Scope And State Model

- 目标：冻结 modern 前端第一阶段 UI 国际化范围，以及语言状态的单一来源。
- 输入：
  - 壳层、导航、设置页和通用状态区现状
- 输出：
  - 一份 i18n 覆盖范围定义
  - 一份语言状态与持久化方案
  - 一份文案资源分层建议
- 验收：
  - 明确第一阶段必须覆盖的组件和页面入口
  - 明确语言状态由谁持有、如何持久化
  - 明确 UI 国际化与业务内容双语化的边界

## Task A3: Freeze Theme State And Token Boundary

- 目标：把当前 modern 前端零散的主题样式收敛成可执行的主题基础设施方案。
- 输入：
  - `AppShell` 当前主题状态写法
  - `index.css` 中现有主题 class 片段
- 输出：
  - 一份主题状态模型
  - 一份最小 token 分层清单
  - 一份设置页接入建议
- 验收：
  - 明确主题枚举值和状态来源
  - 明确刷新后与跨模式切换时的主题行为
  - 明确哪些视觉属性进入 token 层

## Task A4: Freeze Module Registration Model

- 目标：明确 modern 前端内页面模式、导航项和模块装配的主对象。
- 输入：
  - `AppShell` 中的页面装配逻辑
  - `navigation/index.ts` 中的模式映射
  - `FigmaSideNav.tsx` 中的导航分组
- 输出：
  - 一份模块注册对象定义
  - 一份导航装配建议
  - 一份模式可见性规则草案
- 验收：
  - 说清模块最小注册字段
  - 说清导航如何消费注册信息
  - 说清哪些模块属于默认展示，哪些允许按交互形态收敛

## Task A5: Clarify Dual-Interaction Frontend Boundary

- 目标：把“双交互”从模糊描述收敛为双交互前端共享基础设施的明确边界。
- 输入：
  - 现有标准管理/看板页
  - 现有高交互工作台页
- 输出：
  - 一份共享项与差异项定义
  - 一份基础设施复用原则
- 验收：
  - 明确两类交互共用哪些语言、主题和模块规则
  - 明确哪些局部能力允许按交互类型扩展
  - “双交互”定义不再被锁死为单壳层实现

## Task A6: Define Phase Plan For First Implementation Wave

- 目标：把本主题拆成可执行的 Phase 1 / Phase 2 / Phase 3。
- 输入：
  - A1 到 A5 的输出
- 输出：
  - 一份阶段推进计划
  - 每阶段的目标、落点、依赖和完成信号
- 验收：
  - Phase 1 只冻结基础对象与入口
  - Phase 2 明确首轮接入范围
  - Phase 3 明确如何支撑工作台和复杂页面扩展

## Task A7: Define Minimal Validation Pack

- 目标：为后续实现预留最小回归验证集合。
- 输入：
  - i18n、theme、module 三层方案
- 输出：
  - 一组最小验证步骤
  - 一组关键回归观察点
- 验收：
  - 至少包含一个语言切换验证
  - 至少包含一个主题持久化验证
  - 至少包含一个模块注册或导航装配验证
  - 至少包含一个高交互页面接入后的稳定性验证

## 交付要求

- 最终主题文档必须能直接指导子 agent 继续深化，而不是让子 agent 再次从零猜题。
- 文档必须同时具备需求清单、阶段计划、边界说明、风险和最小验证。
- 任何段落如果仍然依赖“后续再看”才能成立，说明任务没有完成。
