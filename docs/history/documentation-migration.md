# 文档迁移记录

迁移清单和专题记录维护实际文件位置、兼容路径与历史证据。当前阅读从[文档导航](../README.md)进入。

- [迁移设计](../development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/01_docs-root-restructuring-mapping-2026-03-07.md)
- [开发文档迁移清单](../development/latest-dev-docs-entry-manifest.json)
- [开发内容迁移清单](../development/latest-dev-docs-content-plan.json)
- [架构迁移清单](../architecture/latest-dev-docs-entry-manifest.json)
- [架构内容迁移清单](../architecture/latest-dev-docs-content-plan.json)

## 已完成迁移的核对记录

- [开发主索引迁移](../development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/14_wave25-docs-root-development-main-move-2026-05-23.md)
- [根计划迁移](../development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/15_wave27-worker-b-docs-root-root-plans-main-move-2026-05-23.md)
- [根计划核对](../development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/16_wave27-worker-a-docs-root-root-plans-main-reconciliation-2026-05-23.md)
- [当前主题归属](../development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/17_wave28-docs-root-current-dev-supervisor-owned-2026-05-23.md)
- [归属复核](../development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/17_wave28-docs-root-reviewer-2026-05-23.md)
- [闭合档案分类](../development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/18_wave28-worker-a-docs-root-archive-closed-classification-2026-05-23.md)
- [档案迁移拆分](../development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/19_wave29-worker-a-docs-root-archive-closed-decomposition-2026-05-23.md)
- [导航一致性核对](../development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/19_wave29-worker-b-docs-root-shared-navigation-drift-2026-05-23.md)
- [目标导航读回](../development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/20_wave30-docs-root-navigation-target-readback-2026-05-23.md)
- [共享导航同步](../development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/21_wave31-docs-root-shared-navigation-sync-2026-05-23.md)

上述核对记录集中在此处；当前与兼容入口只引用本索引。[导航检查器](../../scripts/checkers/check_docs_root_navigation_drift.py)验证每个入口到本索引的链接，并核对全部原始记录仍可达。

旧批量生成器 `scripts/docs_only_workflow.sh` 已退役，防止再次跨项目制造旧目录和重复索引；原实现可用 `git show ee10a848:scripts/docs_only_workflow.sh` 查阅。
