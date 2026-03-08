# E线-DB 文档规范化开发执行文档（Dev Doc）

## Summary
- 本文记录 E 线文档规范化的实际执行过程，严格按既定顺序完成：
  1. Research（联网+本地）
  2. Task Doc（按项目规范）
  3. Atomic Plan（依赖/门禁/负责人/产物）
  4. Build
  5. Verify（命令+结果）
- 执行结果：两份目标文档已落盘，边界控制符合要求（仅认领文档变更）。

## Key Path
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-E-doc-normalization/01_task_doc.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-E-doc-normalization/02_dev_doc.md`

## Deliverables
- 已交付：
  - `01_task_doc.md`：任务目标、边界、执行顺序、原子计划、验证集合。
  - `02_dev_doc.md`：执行记录、验证命令与结果、风险边界声明、下一轮草案。

## 执行过程（按顺序）
### 1) Research（联网+本地）
- 联网来源：
  - Google Developer Style Guide（结构与表达规则）
  - Write the Docs（Docs as Code 与风格一致性）
  - Microsoft Learn Style Guide（参考文档可检索性）
- 本地来源：
  - `CURRENT_DEV` 下既有 Version C 原子任务文档与 2026-03-03 当日 DB 相关封口文档。
- 产出：确定采用“固定输出区块 + 原子任务表 + 可复跑验证命令”的收口格式。

### 2) Task Doc（按项目规范）
- 生成并规范化 `01_task_doc.md`。
- 固化字段：Summary / Key Path / Deliverables / Changed Files / Verification Commands and Results / Risks and Boundaries / Dedup-Diff Statement / Next Round Draft。

### 3) Atomic Plan（依赖/门禁/负责人/产物）
- 在 `01_task_doc.md` 中给出 E-AT-01~E-AT-05 原子任务链。
- 每个任务绑定依赖、门禁、负责人（docs-owner）与产物。

### 4) Build
- 文档 Build 动作：创建目录并写入两份 Markdown。
- Build 输出：文件存在、可读取、路径归一。

### 5) Verify（命令+结果）
- 已执行命令见下方 `Verification Commands and Results`。
- 结果按实际输出记录，包含仓库既有变更噪声。

## Verification Commands and Results
### A) git status --short
```bash
git status --short
```
结果（执行后记录）：
```text
 M development/latest-dev-docs/backend-docs/INDEX.md
 M main/backend/.env.example
 M main/backend/app/main.py
 M main/backend/app/models/base.py
 M main/backend/app/settings/config.py
?? development/latest-dev-docs/backend-docs/E_OPS/DB_ATOMIC_TASKS_E1.md
?? development/latest-dev-docs/backend-docs/E_OPS/DB_BEST_PRACTICES_RESEARCH_2026-03-03.md
?? development/latest-dev-docs/backend-docs/E_OPS/E_DB_ROUND1_CLOSURE.md
?? development/latest-dev-docs/backend-docs/E_OPS/INDEX.md
?? development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-E-doc-normalization/
?? main/backend/migrations/versions/20260303_000006_db_perf_indexes_and_observability.py
?? main/backend/scripts/db_observability_probe.py
```

### B) git diff --name-only
```bash
git diff --name-only
```
结果（执行后记录）：
```text
development/latest-dev-docs/backend-docs/INDEX.md
main/backend/.env.example
main/backend/app/main.py
main/backend/app/models/base.py
main/backend/app/settings/config.py
```
说明：`git diff --name-only` 默认不包含未跟踪文件；本次新增文档在 `git status --short` 中可见。

### C) 路径存在性检查（两份文档）
```bash
test -f development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-E-doc-normalization/01_task_doc.md && echo "01_task_doc.md exists"
test -f development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-E-doc-normalization/02_dev_doc.md && echo "02_dev_doc.md exists"
```
结果（执行后记录）：
```text
01_task_doc.md exists
02_dev_doc.md exists
```

### D) 目标目录定向状态检查（补充）
```bash
git status --short -- development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-E-doc-normalization
```
结果（执行后记录）：
```text
?? development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-E-doc-normalization/
```

## Changed Files
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-E-doc-normalization/01_task_doc.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-E-doc-normalization/02_dev_doc.md`

## Risks and Boundaries
- 仅文档改动，不修改代码/脚本/配置。
- 不触碰工作区记忆文档。
- 不执行知识池治理动作。
- 仓库已有并行改动存在，本任务通过“目标目录定向状态检查”隔离交付边界。

## Dedup-Diff Statement
- 去重原则：
  - 任务定义与执行记录分文档承载，避免单文档冗余。
  - 固定输出区块统一命名，避免同义字段重复。
- Diff 声明：
  - 本任务目标交付为 E 线目录双文档。
  - 无业务代码、脚本、配置变更由本任务引入。

## Next Round Draft
1. Round-2 如需补充审阅闭环，可新增“Reviewer Findings”区块并关联验证命令编号。
2. 如需纳入更高层入口，可更新 `CURRENT_DEV/INDEX.md` 增加本目录链接（保持文档边界）。
3. 若需要可审计复跑，可加上 `date` 时间戳与命令输出摘要快照。
