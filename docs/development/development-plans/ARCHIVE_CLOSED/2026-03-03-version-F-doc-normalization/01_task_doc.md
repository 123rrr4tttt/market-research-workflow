<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-F-doc-normalization/01_task_doc.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-F-doc-normalization/01_task_doc.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# 01 Task Doc - Version F Doc Normalization

## Summary
本任务用于在 `Version F (LLM报告线)` 内完成文档规范化，仅处理项目区任务文档与开发文档，不涉及业务代码、脚本、配置、知识池治理或工作区记忆文档。

## Key Path
`development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-F-doc-normalization/`

## Execution Sequence (Mandatory)
1. `Research`（联网 + 本地）
2. `Task Doc`（按项目规范）
3. `Atomic Plan`（依赖/门禁/负责人/产物）
4. `Build`
5. `Verify`（命令 + 结果）

## Research（联网 + 本地）
### Online References
1. Google Developer Documentation Style Guide: https://developers.google.com/style
2. Google Style - Procedures: https://developers.google.com/style/procedures
3. Divio Documentation System Introduction: https://docs.divio.com/documentation-system/introduction/

### Local References
1. `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
2. `development/latest-dev-docs/root-plans/F_PLAN/version-F-atomic-taskboard-2026-03-03.md`
3. `development/latest-dev-docs/root-plans/F_PLAN/llm-report-best-practices-2026-03-03.md`

## Deliverables
1. 标准化任务文档：`01_task_doc.md`
2. 标准化开发文档：`02_dev_doc.md`
3. 两份文档均满足固定输出区块完整性与可执行性。

## Atomic Plan

| Task ID | Task | Dependency | Gate | Owner | Artifact | Acceptance |
|---|---|---|---|---|---|---|
| F-DOC-AT-01 | 收集规范依据（联网 + 本地） | None | G0: 来源可追溯 | docs-owner | 研究来源清单 | 至少 2 个外部来源 + 2 个本地来源 |
| F-DOC-AT-02 | 重写任务文档结构 | F-DOC-AT-01 | G1: 固定区块齐全 | docs-owner | `01_task_doc.md` | 包含执行顺序、范围边界、验证段 |
| F-DOC-AT-03 | 重写开发文档结构 | F-DOC-AT-02 | G2: 原子计划可执行 | docs-owner | `02_dev_doc.md` | 包含依赖/门禁/负责人/产物 |
| F-DOC-AT-04 | 执行校验命令并回填结果 | F-DOC-AT-03 | G3: 命令可复现 | docs-owner | Verify 结果块 | 含 `git status --short`、`git diff --name-only`、路径存在性检查 |

## Build
1. 创建目标目录并落盘两份文档。
2. 按统一章节重构内容，补齐边界说明与可执行流程。
3. 回填实际验证命令与结果。

## Changed Files
1. `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-F-doc-normalization/01_task_doc.md`
2. `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-F-doc-normalization/02_dev_doc.md`

## Verification Commands and Results
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

## Risks and Boundaries
- Boundaries:
  - 仅允许修改上述两份文档。
  - 禁止修改任何业务代码/脚本/配置。
  - 禁止触碰工作区记忆文档。
  - 禁止写入知识池治理动作。
- Risks:
  - 工作树若存在并行任务改动，`git status --short` 结果可能包含无关项；本任务以“仅新增/更新目标双文档”为验收边界。

## Dedup-Diff Statement
本次输出不复制已有 F 线业务实现说明，仅保留“文档规范化任务本身”的执行链路与验证证据；差异集中在本任务目录，避免与既有 `root-plans/F_PLAN` 内容重复。

## Next Round Draft
1. 若进入下一轮，可在不改代码前提下补充 `README.md` 与 `index.md` 目录导航。
2. 若需审计可追溯性，可增加“文档字段完整性脚本化检查”但仅作为建议，不在本轮执行。
