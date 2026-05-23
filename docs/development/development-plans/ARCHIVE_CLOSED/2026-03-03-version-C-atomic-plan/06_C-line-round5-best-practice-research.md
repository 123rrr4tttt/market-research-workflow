<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-C-atomic-plan/06_C-line-round5-best-practice-research.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-C-atomic-plan/06_C-line-round5-best-practice-research.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# C线第5轮 Stage-1：最佳实践检索与知识池沉淀

- 分支：`feature/version-C-streamplus`
- 知识池主文档：`信息源库/global/research/2026-03-03-C-line-round5-best-practices.md`

## 本轮采用的三条实践基线
1. 工件 manifest + checksum（发布产物可验证）
2. gate/report/verify 分层（定位快、可并行）
3. strict 观测性收敛（默认连续性 + 严格兜底）

## 对后续开发的强约束
- 无 `artifact-manifest.json` 视为 pre-release 不完整。
- verify 失败直接判定本轮失败（不进入 publish）。
- strict 模式下 observability 不能为 warn。
