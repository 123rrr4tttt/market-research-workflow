<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-D-doc-normalization/01_task_doc.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-D-doc-normalization/01_task_doc.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# 01 Task Doc - Version D Doc Normalization

## 1) Research（联网 + 本地，含来源）

### Summary
本轮目标是把 Version D 文档规范化到可执行、可验证、可追踪状态，且只改动两份文档。

### Key Path
- 在线规范基线：Docs-as-Code、CommonMark、GitHub Markdown authoring、markdownlint 规则集。
- 本地规范基线：`development/latest-dev-docs` 目录结构约束与 `CURRENT_DEV` 的现有 Version C 模板。
- 输出策略：将 Research -> Task Doc -> Atomic Plan -> Build -> Verify 固化为单轮闭环，并内置固定输出结构。

### Deliverables
- 本地调研结论与外部规范映射。
- Version D 任务文档模板（本文件）已规范化。

### Changed Files
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/01_task_doc.md`

### Verification Commands and Results
- `test -f development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/01_task_doc.md && echo OK`
- Result: `pending (moved to Step 5 unified verify)`

### Risks and Boundaries
- 边界：仅处理指定两份文档，不触碰业务代码、配置、脚本、依赖。
- 风险：若外部规范后续升级，需在下一轮同步更新 lint/格式约束。

### Dedup
- 去重策略：将“结构规范”“执行顺序”“验证记录”统一收敛到固定章节，避免在不同文档重复表述。

### Diff Statement
- 新建 Version D 的任务文档骨架，并补齐固定输出结构与引用清单占位。

### Next Round Draft
- 若下一轮要求执行代码或配置级改动，需先新增独立任务单并声明影响面。

### Sources
Online (accessed 2026-03-03):
- Write the Docs, Docs as Code: https://www.writethedocs.org/guide/docs-as-code.html
- CommonMark Spec 0.31.2: https://spec.commonmark.org/
- GitHub Docs, Markdown tables: https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/organizing-information-with-tables
- GitHub Docs, code blocks: https://docs.github.com/github/writing-on-github/working-with-advanced-formatting/creating-and-highlighting-code-blocks
- DavidAnson markdownlint rules: https://github.com/DavidAnson/markdownlint

Local:
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-C-atomic-plan/01_atomic-task-table-and-sequence.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-C-atomic-plan/README.md`

---

## 2) Task Doc 规范化

### Summary
将任务描述从“目标导向文本”转换为“可执行规范单”，明确输入、输出、边界、验收。

### Key Path
- 任务输入：仅两个目标文档路径。
- 任务输出：规范化后的 `01_task_doc.md` + `02_dev_doc.md`。
- 强约束：仅文档改动，不产生代码与配置副作用。

### Deliverables
- 任务定义四元组：`目标 / 输入 / 输出 / 验收`。
- 固定流程顺序：`Research -> Task Doc -> Atomic Plan -> Build -> Verify`。

### Changed Files
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/01_task_doc.md`

### Verification Commands and Results
- `echo 'Task doc normalization completed'`
- Result: `pending (moved to Step 5 unified verify)`

### Risks and Boundaries
- 不处理索引联动，不扩散到 `README` 或 `MERGED_OVERVIEW`，避免越权修改。

### Dedup
- 删除重复口径：同一约束只在“Risks and Boundaries”保留一次，其他章节引用不重复展开。

### Diff Statement
- 增加结构化任务定义和执行顺序，替换松散叙述。

### Next Round Draft
- 可追加“文档 lint 自动化”任务，但需独立批准。
