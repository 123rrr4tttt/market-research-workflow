# docs 根目录重构迁移映射表（development -> docs）

> 日期：2026-03-07
> 范围：`development/latest-dev-docs`、`docs`
> 状态：规划中，当前不直接移动真实文件

## 1. 结论

不建议把顶层 `development/` 直接整体改名为 `docs/`。

建议改为：

- `docs/` 作为唯一文档根目录
- `development/` 短期保留为兼容入口
- `development/latest-dev-docs` 内文档按内容性质分流到：
  - `docs/development/`
  - `docs/implementation/`
  - `docs/architecture/`
  - `docs/governance/`

本次先产出迁移映射，不直接移动文件。

## 2. 重构原则

1. 先按文档生命周期分类，再做路径迁移。
2. 先迁低歧义文档，后迁混合型目录。
3. 先补新入口与索引，再改旧引用。
4. `development/latest-dev-docs` 至少保留 1-2 个版本周期的只读兼容入口。
5. 第一阶段只做路径和索引调整，不重写正文语义。

## 3. 目标结构

```text
docs/
  development/
  implementation/
  architecture/
  governance/
  reference-pool/
```

分类口径：

- `docs/development/`：计划、草案、原子任务、设计 brief、review 过程、历史开发归档
- `docs/implementation/`：已落地流程、接口文档、运行手册、测试基线、验收记录
- `docs/architecture/`：系统结构、长期约束、主线演进方向、架构决策
- `docs/governance/`：发布口径、治理策略、review 结论、可靠性与运维基线

## 4. 一级目录迁移映射

| 现路径 | 目录定位 | 目标落点 | 备注 |
|---|---|---|---|
| `development/latest-dev-docs/development-plans` | 开发计划与执行闭环主目录 | 以 `docs/development` 为主，部分分流到 `implementation` / `architecture` / `governance` | 不能整包平移 |
| `development/latest-dev-docs/root-plans` | 顶层计划域，混合计划、证据、治理 | 拆分到四类目录 | 需保留强索引 |
| `development/latest-dev-docs/backend-core` | 开发记录 + 稳定实现说明混合 | 以 `docs/implementation` 为主 | `A_ARCHITECTURE` / `E_OPS` 单独分流 |
| `development/latest-dev-docs/backend-docs` | 后端快照与阶段性执行记录 | 以 `docs/implementation` 为主 | 少量计划/评审留在 `development` |
| `development/latest-dev-docs/ops-frontend` | 前端交付 + 运维 + 计划评审混合 | `implementation` + `development` 双落点 | `main/` 需要二次判断 |
| `development/latest-dev-docs/frontend-modern` | 设计输入 / 原型参考 | 先放 `docs/development` | 暂不进 `implementation` |

## 5. 子目录级映射规则

### 5.1 通用规则

按目录语义优先分流，若单目录内混合明显，则按文件级别分流。

默认规则：

| 子目录 | 默认目标 |
|---|---|
| `A_ARCHITECTURE` | `docs/architecture/...` |
| `B_API` | 多数进 `docs/implementation/...`，偏路线/规划的文件留 `docs/development/...` |
| `C_INGEST` | 已实施/证据类进 `docs/implementation/...` |
| `D_TEST` | 测试基线进 `docs/implementation/...`，过程性验证留 `docs/development/...` |
| `E_OPS` | 运行手册进 `docs/implementation/...`，治理/可靠性基线进 `docs/governance/...` |
| `F_PLAN` | `docs/development/...` |
| `G_REVIEW` | `docs/development/...` 或 `docs/governance/...`，默认先留 development |
| `main/` | 按正文语义判断，不能一刀切 |

### 5.2 `development-plans`

建议映射：

- 保留到 `docs/development/development-plans/`
  - `main/`
  - `CURRENT_DEV/`
  - `INDEX.md`
  - `CURRENT_DEV/INDEX.md`
  - `ARCHIVE_CLOSED/INDEX.md`
- 迁到 `docs/architecture/development-plans/`
  - `A_ARCHITECTURE/`
  - `F_PLAN/` 中长期主线演进文档
- 迁到 `docs/implementation/development-plans/`
  - `C_INGEST/`
  - `D_TEST/`
  - `E_OPS/`
  - `ARCHIVE_CLOSED/` 中含验收命令、改动清单、最小实现集的文档
- 迁到 `docs/governance/development-plans/`
  - `G_REVIEW/`

### 5.3 `root-plans`

建议映射：

- `docs/development/root-plans/`
  - `main/MERGED_PLAN.md`
  - `F_PLAN/`
  - 状态跟踪类快照
- `docs/architecture/root-plans/`
  - `A_ARCHITECTURE/`
  - `B_API/` 中偏标准化方向的文档
- `docs/implementation/root-plans/`
  - `C_INGEST/`
  - `D_TEST/`
  - 已落地证据矩阵、任务板
- `docs/governance/root-plans/`
  - `G_REVIEW/`
  - release / pre-release 口径文档

### 5.4 `backend-core`

建议映射：

- `docs/implementation/backend-core/`
  - `main/MERGED_BACKEND_CORE.md`
  - `main/STANDARD_INGEST_WORKFLOWS_2026-03-02.md`
  - `main/TEST_AUTOMATION_STANDARDIZATION.md`
  - `main/TEST_SCENARIO_MATRIX.md`
  - `B_API/API接口文档.md`
- `docs/architecture/backend-core/`
  - `A_ARCHITECTURE/`
- `docs/development/backend-core/`
  - `C_INGEST/INGEST_CHAIN_*`
  - `F_PLAN/`
  - `G_REVIEW/`
  - `B_API/API_ROUTE_INVENTORY_2026-02-27.backend-core.md`
- `docs/governance/backend-core/`
  - `E_OPS/OBSERVABILITY_RELIABILITY_BASELINE_2026-03-04.md`

### 5.5 `backend-docs`

建议映射：

- `docs/implementation/backend-docs/`
  - `main/`
  - `B_API/`
  - `C_INGEST/`
  - 大部分 `D_TEST/`
  - 大部分 `E_OPS/`
- `docs/architecture/backend-docs/`
  - `A_ARCHITECTURE/`
- `docs/development/backend-docs/`
  - `F_PLAN/`
  - `G_REVIEW/`
  - 明显属于阶段性任务板、证据矩阵、merge 计划的文档

### 5.6 `ops-frontend`

建议映射：

- `docs/development/ops-frontend/`
  - `F_PLAN/`
  - `D_TEST/`
  - `G_REVIEW/`
- `docs/implementation/ops-frontend/`
  - `E_OPS/`
  - `B_API/`
  - `C_INGEST/`
  - `main/` 中偏运行/API 对齐的文档
- `docs/architecture/ops-frontend/`
  - `A_ARCHITECTURE/`

### 5.7 `frontend-modern`

建议映射：

- `docs/development/frontend-modern/main/LLM_DESIGNER_UI_REPLICA_BRIEF.md`

后续只有当该类文档被提升为长期实施标准时，再迁到 `docs/implementation/frontend/`。

## 6. 第一批低歧义迁移集合

第一批只动低歧义内容：

1. `development-plans/CURRENT_DEV/`
2. `frontend-modern/main/LLM_DESIGNER_UI_REPLICA_BRIEF.md`
3. 各目录下的 `A_ARCHITECTURE/`
4. 各目录下明显的 `F_PLAN/`
5. 各目录下明显的运行手册型 `E_OPS/`

暂缓迁移：

1. 所有 `main/` 下混合型合并文档
2. `ARCHIVE_CLOSED/` 中混合“历史讨论 + 落地证据”的目录
3. `ops-frontend` 的 `main/`
4. `backend-docs` 中兼具规范与快照属性的文档

## 7. 路径与引用改造范围

当前仓内已有较多旧路径引用，迁移时至少同步处理：

- `README.md`
- `codex_settings/AGENTS.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `scripts/docs_only_workflow.sh`
- `docs/reference-pool/*` 中引用 `development/latest-dev-docs` 的说明

## 8. 执行顺序

1. 新建 `docs/development` / `docs/implementation` / `docs/architecture` / `docs/governance`
2. 先迁第一批低歧义集合
3. 为旧路径增加过渡说明或只读兼容入口
4. 批量修正索引与硬编码路径
5. 对混合目录做第二轮文件级分流
6. 链接校验通过后，再评估是否移除旧入口

## 9. 最小验证步骤

1. `rg -n "development/latest-dev-docs|docs/development|docs/implementation|docs/architecture|docs/governance" README.md codex_settings scripts docs`
2. 逐个检查以下入口是否仍可导航：
   - `development/latest-dev-docs/README.md`
   - `development/latest-dev-docs/MERGED_OVERVIEW.md`
   - `development/latest-dev-docs/development-plans/INDEX.md`
   - `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
3. 对迁移批次做一次相对链接抽样检查

## 10. 当前决定

当前先确认架构方向：

- `docs/` 是唯一文档根目录
- `development/` 不是最终归宿，只是过渡入口
- 重构核心不是目录改名，而是文档语义重分类
