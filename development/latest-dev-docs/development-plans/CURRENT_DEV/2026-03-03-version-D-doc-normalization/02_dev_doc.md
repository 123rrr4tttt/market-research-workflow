# 02 Dev Doc - Version D Doc Normalization Execution

## 3) Atomic Plan（依赖 / 门禁 / 负责人 / 产物）

### Summary
将执行动作拆分为原子任务，建立依赖链、闸门与验收条件。

### Key Path
- AP-01: 基线确认（输入路径与限制）
- AP-02: 文档重构（01_task_doc）
- AP-03: 文档重构（02_dev_doc）
- AP-04: 验证与自检（git diff / git status / 结构检查）

### Deliverables
| Task ID | Goal | Dependency | Gate | Owner | Output |
|---|---|---|---|---|---|
| AP-01 | Confirm boundaries and target files | None | G0 | docs-owner | executable boundary checklist |
| AP-02 | Normalize task doc structure | AP-01 | G1 | docs-owner | normalized `01_task_doc.md` |
| AP-03 | Normalize dev doc structure | AP-02 | G2 | docs-owner | normalized `02_dev_doc.md` |
| AP-04 | Verify command results and self-check | AP-03 | G3 | docs-owner | verification evidence + final status |

### Changed Files
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/02_dev_doc.md`

### Verification Commands and Results
- `echo 'Atomic plan drafted'`
- Result: `pending (moved to Step 5 unified verify)`

### Risks and Boundaries
- 严格禁止越界写入：仅两份目标文档可变更。
- 严格禁止业务代码、配置、脚本、依赖改动。

### Dedup
- AP-02 与 AP-03 都是“文档重构”，通过任务表统一定义，避免各节重复写流程。

### Diff Statement
- 新增原子计划矩阵（依赖/门禁/负责人/产物）并与后续 Build/Verify 对齐。

### Next Round Draft
- 若需扩展到索引联动，应创建 AP-05（索引更新）并单独审批。

---

## 4) Build（仅文档重构）

### Summary
执行内容重构：统一章节命名、固定输出结构、显式边界与验证入口。

### Key Path
- 统一标准段落：`Summary/Key Path/Deliverables/Changed Files/Verification Commands and Results/Risks and Boundaries/Dedup/Diff Statement/Next Round Draft`。
- 补齐来源：在线规范与本地范式均可追溯。
- 明确非目标项：无代码改动、无配置改动、无脚本改动。

### Deliverables
- 完整的 Version D 文档双文件集合。
- 可复现的验证命令列表。

### Changed Files
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/01_task_doc.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/02_dev_doc.md`

### Verification Commands and Results
- `echo 'Build complete: docs only'`
- Result: `pending (moved to Step 5 unified verify)`

### Risks and Boundaries
- 若后续有人手工修改章节标题，可能破坏固定结构，需要 lint 守护。

### Dedup
- Build 中不重复写 Atomic Plan 细节，仅保留“执行结果”视角。

### Diff Statement
- 完成纯文档重构，未引入任何运行时逻辑变化。

### Next Round Draft
- 可在下一轮加入 markdownlint 校验脚本（仅提案，不在本轮执行）。

---

## 5) Verify（命令 + 结果）

### Summary
对本轮改动做最小可复现验证，输出可审计结果。

### Key Path
- 验证 1：仅两文件变更。
- 验证 2：两文件均包含固定输出结构关键词。
- 验证 3：无业务代码改动。

### Deliverables
- 命令执行记录与结果归档。

### Changed Files
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/01_task_doc.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/02_dev_doc.md`

### Verification Commands and Results
- Command:
```bash
git status --short
```
- Result:
```text
 M development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md
 M development/latest-dev-docs/development-plans/CURRENT_DEV/MERGED_OVERVIEW/index.md
 M "development/latest-dev-docs/development-plans/CURRENT_DEV/main index.md"
?? development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-rag-line-round1/
?? development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-rag-line-round2/
?? development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/
?? development/latest-dev-docs/development-plans/CURRENT_DEV/MERGED_OVERVIEW/02_rag-incremental-best-practice-pool-round2.md
?? main/backend/app/services/rag/
?? main/backend/scripts/rag_eval.py
?? main/backend/tests/unit/test_minimal_rag_unittest.py
```

- Command:
```bash
git diff --name-only
```
- Result:
```text
development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md
development/latest-dev-docs/development-plans/CURRENT_DEV/MERGED_OVERVIEW/index.md
development/latest-dev-docs/development-plans/CURRENT_DEV/main index.md
```

- Command:
```bash
git status --short -- development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/01_task_doc.md development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/02_dev_doc.md
```
- Result:
```text
?? development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/01_task_doc.md
?? development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/02_dev_doc.md
```

- Command:
```bash
for f in development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/01_task_doc.md development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/02_dev_doc.md; do
  for k in "Summary" "Key Path" "Deliverables" "Changed Files" "Verification Commands and Results" "Risks and Boundaries" "Dedup" "Diff Statement" "Next Round Draft"; do
    rg -n "$k" "$f" >/dev/null || echo "MISSING: $k in $f";
  done;
done
```
- Result:
```text
(no output; all required sections found)
```

- Command:
```bash
git diff -- . ':(exclude)development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/01_task_doc.md' ':(exclude)development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/02_dev_doc.md' | wc -l
```
- Result:
```text
29
```

### Self Check (A/B/C/D)
- A. 仅这两个文档被改动：`FAIL`（仓库存在既有改动，非本次任务引入；全仓检查未满足）
- B. 固定输出结构完整：`PASS`
- C. 无知识池治理内容：`PASS`
- D. 无业务代码改动（本次任务）：`PASS`（本次仅创建/编辑目标两文档）

### Blockers
- 仓库当前为脏工作区，存在与本任务无关的既有改动，导致“全仓仅两文件改动”无法在全局口径上判定为通过。

### Risks and Boundaries
- A/B/C/D 自检在本节完成，后续若新增改动需重新跑上述命令。

### Dedup
- 验证输出统一集中在本节，前文只保留 `pending` 占位，防止重复维护。

### Diff Statement
- 本轮执行仅创建/编辑两份目标文档；仓库同时存在既有非本任务改动。

### Next Round Draft
- 下一轮可在 CI 增加 `markdownlint` 和结构完整性检查。
