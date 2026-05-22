# 2026-03-15 Frontend Three-Layer Rewrite

## 文档列表

1. [01_frontend-three-layer-rewrite-architecture-2026-03-15.md](./01_frontend-three-layer-rewrite-architecture-2026-03-15.md)
2. [02_atomic-tasklist-frontend-three-layer-rewrite-2026-03-15.md](./02_atomic-tasklist-frontend-three-layer-rewrite-2026-03-15.md)
3. [03_frontend-three-layer-rewrite-closure-gap-assessment-and-rollout-2026-04-02.md](./03_frontend-three-layer-rewrite-closure-gap-assessment-and-rollout-2026-04-02.md)

## 2026-05-22 状态刷新

Wave3 I 补充了 topology / i18n / theme / module manifest 的静态合同门禁：

- evidence: [../../../automation-runs/frontend-topology-theme/2026-05-22/README.md](../../../automation-runs/frontend-topology-theme/2026-05-22/README.md)
- command: `npm --prefix main/frontend-modern run check:topology-platform`

该证据说明三层重写里的 shared platform kernel 基础合同已经具备可重复检查：31 个模块都进入 `moduleManifest`，placement baseline 与 baseline inventory 完整，`zh-CN` / `en-US` shell/nav catalog 完整，`light` / `dark` / `brand` token groups 完整，`AppShell` 与 `FigmaSideNav` 均消费当前平台合同。

因此后续收口不要再把 S1/S2/S3 当成未开始项；剩余重点是 `AppShell` compatibility-only retirement、`WritingWorkbenchPage` / `GraphPage` 等重页面的 container/view 封边、以及更完整的运行态 E2E。

## 阅读顺序

1. 先读 `01_frontend-three-layer-rewrite-architecture-2026-03-15.md`，冻结三层重写的目标形态、保留闭环、跨层契约、设计信息获取方法。
2. 再读 `02_atomic-tasklist-frontend-three-layer-rewrite-2026-03-15.md`，按固定阶段顺序拆解后续执行工作。
3. 最后读 `03_frontend-three-layer-rewrite-closure-gap-assessment-and-rollout-2026-04-02.md`，了解截至 2026-04-02 的实际完成度、未封口项与建议收口顺序。

## 本专题与既有前端规划的关系

1. 本目录是前端重写主线，目标是“框架逻辑完全重构，业务核心交互闭环保留，分阶段替换旧壳层”。
2. `2026-03-07-dual-frontend-workbench-topology/` 提供了早期 workbench / management 拓扑基线，但本专题将其升级为 A/B/C 三层重写方案，并固定新的路由和模块契约。
3. `2026-03-07-frontend-i18n-theme-modularization/` 提供共享平台层的旧基线，本专题仅复用其中“主题、语言、模块元数据应被平台化”的原则，不继承既有 `AppShell` 结构。
4. `ARCHIVE_RETIRED/2026-03-07-builtin-writing-workbench-design/` 的历史设计稿与 `2026-03-07-writing-workbench-evolution/` 仍然是 A 层写作工作台的领域输入，但不再承担前端总体架构主线职责。

## 使用说明

1. 该专题默认服务于 `main/frontend-modern` 的下一轮整体重写，不规划长期新旧双轨产品。
2. 任何实现任务若涉及页面归层、跨层契约、路由兼容、设计信息来源，应以 `01_...architecture...` 为唯一口径。
3. 任何实现任务若需要排期、并行边界、验收标准，应以 `02_...atomic-tasklist...` 为唯一口径。
4. 任何实现任务若需要判断“现在到底做到哪里、下一步先封什么”，应先读取 `03_...closure-gap-assessment...`。
