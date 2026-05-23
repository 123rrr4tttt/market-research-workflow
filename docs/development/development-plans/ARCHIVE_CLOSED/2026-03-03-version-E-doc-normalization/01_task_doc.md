<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-E-doc-normalization/01_task_doc.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-E-doc-normalization/01_task_doc.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# E线-DB 文档规范化任务书（Task Doc）

## Summary
- 任务日期：2026-03-03（US/Pacific）。
- 任务目标：将 Version E 文档工作整理为“纯项目规范水准”，仅处理任务文档与开发文档，不触碰业务代码、脚本、配置、工作区记忆文档、知识池治理动作。
- 强制执行顺序：
  1. Research（联网+本地）
  2. Task Doc（按项目规范）
  3. Atomic Plan（依赖/门禁/负责人/产物）
  4. Build
  5. Verify（命令+结果）

## Key Path
- 主路径：`development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-E-doc-normalization/`
- 主文档：`01_task_doc.md`（本文件）
- 配套执行文档：`02_dev_doc.md`

## Deliverables
- D1：任务规范文档（本文件），明确目标、边界、执行顺序、原子计划、验证口径。
- D2：开发执行文档（`02_dev_doc.md`），记录 Research/Build/Verify 的过程证据与结果。
- D3：验证证据（命令与结果）覆盖：
  - `git status --short`
  - `git diff --name-only`
  - 两份目标文档路径存在性检查

## Execution Sequence (Strict)
1. Research（联网+本地）
2. Task Doc（按项目规范）
3. Atomic Plan（依赖/门禁/负责人/产物）
4. Build
5. Verify（命令+结果）

## Research（联网+本地）
### Online Research
- 参考 1：Google Developer Documentation Style Guide（强调 active voice、清晰标题、序列步骤编号）。
  - https://developers.google.com/style
  - https://developers.google.com/style/headings
  - https://developers.google.com/style/voice
- 参考 2：Write the Docs（Docs as Code、结构一致性、文档可维护性）。
  - https://www.writethedocs.org/guide/docs-as-code.html
  - https://www.writethedocs.org/guide/writing/style-guides.html
- 参考 3：Microsoft Learn Style Guide（参考文档结构一致性与可检索性）。
  - https://learn.microsoft.com/en-us/style-guide/developer-content/reference-documentation

### Local Research
- 已核验项目内开发文档主索引与历史范式，重点参考：
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-C-atomic-plan/01_atomic-task-table-and-sequence.md`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-C-atomic-plan/README.md`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-platformization-first-vectorization/06_backend-db-standardization-vectorization-closure-2026-03-03.md`
- 结论：本次 E 线任务采用“单目录双文档（Task+Dev）+固定输出区块+可复跑验证命令”结构。

## Atomic Plan（依赖/门禁/负责人/产物）
| ID | 原子任务 | 依赖 | 门禁 | 负责人 | 产物 |
|---|---|---|---|---|---|
| E-AT-01 | 收集规范依据（联网+本地） | 无 | 研究来源可追溯 | docs-owner | Research 证据与规范要点 |
| E-AT-02 | 归一任务文档结构（Task Doc） | E-AT-01 | 固定区块齐全 | docs-owner | `01_task_doc.md` |
| E-AT-03 | 归一执行文档结构（Dev Doc） | E-AT-02 | 固定区块齐全 | docs-owner | `02_dev_doc.md` |
| E-AT-04 | Build（文档落盘与路径校验） | E-AT-03 | 仅文档改动 | docs-owner | 可读取、可追踪文档 |
| E-AT-05 | Verify（命令+结果固化） | E-AT-04 | 三类验证命令齐全 | docs-owner | 验证结果写入文档 |

## Build
- Build 类型：文档构建（非代码构建）。
- 执行动作：
  - 创建目标目录（若不存在）。
  - 生成并写入 `01_task_doc.md` 与 `02_dev_doc.md`。
  - 保持改动边界：仅项目区任务文档与开发文档。

## Verification Commands and Results
- 本段最终以 `02_dev_doc.md` 中的 Verify 实际执行结果为准；此处定义必须执行集合：

```bash
git status --short
git diff --name-only
test -f development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-E-doc-normalization/01_task_doc.md && echo "01_task_doc.md exists"
test -f development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-E-doc-normalization/02_dev_doc.md && echo "02_dev_doc.md exists"
```

## Changed Files
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-E-doc-normalization/01_task_doc.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-E-doc-normalization/02_dev_doc.md`

## Risks and Boundaries
- 边界 1：禁止修改任何业务代码/脚本/配置。
- 边界 2：禁止触碰工作区记忆文档。
- 边界 3：禁止写知识池治理动作。
- 风险 1：仓库若存在并行文档改动，`git status` 可能出现额外噪声；本任务仅认领上述两文件。
- 风险 2：目标路径初始不存在时需新建目录，需确保目录命名与日期语义一致。

## Dedup-Diff Statement
- 本轮仅新增 E 线目录下双文档，未复制粘贴历史文档全文。
- 结构去重策略：固定区块统一命名；任务定义与执行记录分离；验证命令集中维护，避免重复散落。
- Diff 范围声明：仅两份文档新增/修改，无代码与脚本差异。

## Next Round Draft
1. 若后续进入 E 线 Round-2，可在同目录新增 `03_round2_actions.md`，只记录增量差异与回归命令。
2. 如需纳入目录索引，可补充 `index.md` 并同步 `CURRENT_DEV/INDEX.md`（保持仅文档改动）。
3. 若需要交付审计版，可补充“命令输出快照”章节并加时间戳。
