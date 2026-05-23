<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-A-doc-normalization/01_task_doc.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-A-doc-normalization/01_task_doc.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# 2026-03-03 Version A Doc Normalization - Task Doc

## 1. Objective
将当前轮次开发文档整理为可执行、可验证、边界清晰的项目规范文档，仅在目标目录内交付。

## 2. Scope
- Allowed files:
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/01_task_doc.md`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/02_dev_doc.md`
- Forbidden changes:
  - Any business code
  - Any non-target document
  - Any file outside project root

## 3. Mandatory Sequence
执行顺序必须严格为：
1. Research（联网+本地）
2. Task Doc
3. Atomic Plan
4. Build
5. Verify

Completion criteria by phase:
- Research: 形成可引用的本地和在线依据。
- Task Doc: 明确目标、边界、验收与风险。
- Atomic Plan: 形成原子任务与依赖/门禁映射。
- Build: 完成两份目标文档规范化。
- Verify: 运行最小文档验证并记录结果。

## 4. Research Baseline
### 4.1 Local research targets
- Existing doc style and acceptance sections under `development/latest-dev-docs/development-plans/`.
- Current target files baseline content.

### 4.2 Online research targets
- CommonMark fenced-code and heading/list规范。
- Markdown lint rule set（heading increment、duplicate headings、fenced code blank lines等）。

### 4.3 Research outputs
- 可执行文档结构模板（phase-first）。
- 验证命令模板（文件范围、禁用词、顺序与结构完整性）。

## 5. Acceptance Criteria
- Sequence `Research -> Task Doc -> Atomic Plan -> Build -> Verify` is explicitly present and reflected in execution record.
- `01_task_doc.md` 包含完整原子任务表，至少包含：依赖、门禁、负责人、产物。
- `02_dev_doc.md` 包含实施与验证章节，含可运行命令、预期结果、实际结果。
- 仅目标两文件发生改动。
- 文档不出现指定的知识池动作关键词。

## 6. Atomic Task Table

| Task ID | Phase | Goal | Input | Output | Dependency | Gate | Owner (负责人) | Deliverable (产物) | Acceptance |
|---|---|---|---|---|---|---|---|---|---|
| DN-A01 | Research | 收集本地文档规范样式与当前文件基线 | 目标文件 + `development/latest-dev-docs/development-plans/` | 本地研究结论 | None | G0 | Codex | Baseline notes | 有可复现的本地路径与结构依据 |
| DN-A02 | Research | 收集在线 Markdown 规范与lint规则依据 | CommonMark + markdownlint官方文档 | 在线研究结论 | DN-A01 | G0 | Codex | External references | 至少2个可引用在线来源 |
| DN-A03 | Task Doc | 重写任务约束、边界、验收和阶段定义 | DN-A01/DN-A02输出 + 用户约束 | 更新后的`01_task_doc.md` | DN-A01, DN-A02 | G1 | Codex | Task contract | 约束清晰且与用户目标一致 |
| DN-A04 | Atomic Plan | 在任务文档中补全原子任务编排 | `01_task_doc.md`草稿 | 原子任务表（含依赖/门禁/负责人/产物） | DN-A03 | G1 | Codex | Executable atomic plan | 表格字段完整且可执行 |
| DN-A05 | Build | 完善执行文档实施章节 | DN-A04输出 | 更新后的`02_dev_doc.md`实施章节 | DN-A04 | G2 | Codex | Build record | 实施步骤与文件改动可追溯 |
| DN-A06 | Verify | 运行最小文档验证并回填结果 | 当前工作区状态 + 两目标文档 | `02_dev_doc.md`验证章节（命令/预期/结果） | DN-A05 | G3 | Codex | Verification evidence | 命令可运行，结果与边界一致 |
| DN-A07 | Closure | 输出收口说明并形成下一轮草稿 | DN-A06输出 | 最终简报结构草稿 | DN-A06 | G4 | Codex | Closure summary | 八段结构完整且无空段 |

## 7. Gate Definition
- G0 Research Gate: 本地与在线依据齐备。
- G1 Planning Gate: Task Doc 与 Atomic Plan 完成并互相一致。
- G2 Build Gate: 两个目标文档均完成更新。
- G3 Verify Gate: 最小文档验证命令全部执行并记录。
- G4 Closure Gate: 最终简报段落完整。

## 8. Risks and Boundaries
- Risk: Out-of-scope file edits.
  - Control: `git diff --name-only` and path-restricted status checks.
- Risk: 文档可执行性不足。
  - Control: 在`02_dev_doc.md`给出可直接运行命令 + 预期结果 + 实际结果。
- Risk: 指定关键词误入文档。
  - Control: verify阶段执行关键词扫描。

## 9. Minimal Verification Plan
```bash
test -f development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/01_task_doc.md
test -f development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/02_dev_doc.md
if perl -ne 'if(/\\x{5165}\\x{6C60}|\\x{7D22}\\x{5F15}|\\x{5F52}\\x{6863}|\\x{6CBB}\\x{7406}/){print \"$ARGV:$.:$_\"; $f=1} END{exit($f?0:1)}' development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/01_task_doc.md development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/02_dev_doc.md; then echo "FAIL: forbidden terms found"; else echo "PASS: forbidden terms not found"; fi
git status --short -- development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/01_task_doc.md development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/02_dev_doc.md
```
