<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-F-doc-normalization/02_dev_doc.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-F-doc-normalization/02_dev_doc.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# 02 Dev Doc - Version F Doc Normalization Execution

## Summary
本文档记录 Version F 文档规范化执行过程，严格限定在项目区开发文档范围，输出可复现命令与结果，不涉及业务代码层修改。

## Key Path
`development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-F-doc-normalization/`

## Stage 1 - Research（联网 + 本地）

### Online
1. Google Developer Documentation Style Guide（清晰、一致、以项目规范优先）
   - https://developers.google.com/style
2. Google Procedures（步骤型文档采用编号流程，可复现）
   - https://developers.google.com/style/procedures
3. Divio Documentation System（文档类型与边界分离）
   - https://docs.divio.com/documentation-system/introduction/

### Local
1. `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
2. `development/latest-dev-docs/root-plans/F_PLAN/version-F-atomic-taskboard-2026-03-03.md`
3. `development/latest-dev-docs/root-plans/F_PLAN/llm-report-best-practices-2026-03-03.md`

### Research Outcome
- 文档需明确“目标、边界、步骤、验证证据”。
- 执行链路应采用编号，且每一步可落地到命令或产物。
- 任务文档与开发执行文档要分离：前者定义约束，后者记录实施与结果。

## Stage 2 - Task Doc（按项目规范）
- 已重构 `01_task_doc.md`，补齐固定输出区块与执行顺序。
- 已声明禁止变更范围，确保边界可审计。

## Stage 3 - Atomic Plan（依赖/门禁/负责人/产物）

| ID | Action | Depends On | Gate | Owner | Output |
|---|---|---|---|---|---|
| F-DOC-P1 | 汇总研究证据 | None | Source Gate | docs-owner | 参考清单 |
| F-DOC-P2 | 编写任务文档 | F-DOC-P1 | Structure Gate | docs-owner | `01_task_doc.md` |
| F-DOC-P3 | 编写开发文档 | F-DOC-P2 | Atomic Gate | docs-owner | `02_dev_doc.md` |
| F-DOC-P4 | 运行验证并记录 | F-DOC-P3 | Verify Gate | docs-owner | 命令 + 结果 |

## Stage 4 - Build
1. 创建目录：`development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-F-doc-normalization/`
2. 新建并写入双文档：`01_task_doc.md`、`02_dev_doc.md`
3. 对齐固定区块与执行顺序。

## Deliverables
1. `01_task_doc.md`（任务定义与边界）
2. `02_dev_doc.md`（执行过程与验证证据）

## Changed Files
1. `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-F-doc-normalization/01_task_doc.md`
2. `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-F-doc-normalization/02_dev_doc.md`

## Stage 5 - Verify（命令 + 结果）
已执行并记录如下：

```bash
git status --short
```
Result:
```text
 M development/latest-dev-docs/root-plans/F_PLAN/index.md
 M main/backend/app/api/__init__.py
?? development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-F-doc-normalization/
?? development/latest-dev-docs/root-plans/F_PLAN/llm-report-best-practices-2026-03-03.md
?? development/latest-dev-docs/root-plans/F_PLAN/version-F-atomic-taskboard-2026-03-03.md
?? main/backend/app/api/llm_report.py
?? main/backend/app/services/llm_report_generator.py
?? main/backend/docs/version-F-llm-report-delivery-2026-03-03.md
?? main/backend/tests/unit/test_llm_report_generator_unittest.py
```

```bash
git diff --name-only
```
Result:
```text
development/latest-dev-docs/root-plans/F_PLAN/index.md
main/backend/app/api/__init__.py
```

```bash
test -f development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-F-doc-normalization/01_task_doc.md && echo '01_task_doc.md: EXISTS' || echo '01_task_doc.md: MISSING'
test -f development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-F-doc-normalization/02_dev_doc.md && echo '02_dev_doc.md: EXISTS' || echo '02_dev_doc.md: MISSING'
```
Result:
```text
01_task_doc.md: EXISTS
02_dev_doc.md: EXISTS
```

## Verification Commands and Results
与 `Stage 5 - Verify` 一致，校验命令与结果已回填完成，可复现。

## Risks and Boundaries
- 仅文档改动，且限制在目标目录。
- 若仓库同时存在其他并行改动，需在结果解释中显式区分“本任务改动”与“既有改动”。

## Dedup-Diff Statement
本轮文档仅整理“Version F 文档规范化任务”本身，不重复沉淀已存在的 LLM 报告实现细节；差异聚焦双文档结构与验证证据。

## Next Round Draft
1. 增补目录级 `README.md` 以便快速导航。
2. 对 `CURRENT_DEV/INDEX.md` 增加该任务入口（仅在下一轮且得到明确指令时执行）。
