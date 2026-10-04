# 历史资料

这里查找已完成方案、旧决策和原始证据。日常使用见[使用说明](../usage.md)，开发见[开发指南](../development/README.md)。

## 最近完成的工作

| 工作 | 原记录与结果 |
| --- | --- |
| 平台实现精简 | [设计与事实归属](../development/MRW实现清简方案.md)、[实施结果](../development/MRW清简分阶段实施分发包.md#73-整组最终收口2026-10-03当前结果入口) |
| 整链修复与宿主认证 | [修复记录](../development/MRW全量核查修复分发包.md) |
| 结构整理与维护收敛 | [整理记录](../development/MRW结构整理方案与分发包.md#8-实际实施进度)，最新一轮结果在该文第 10.11 节 |

这些方案已完成对应实施批次，原分发说明只用于追溯。历史执行次数、局部测试和运行记录保持各自日期与验证边界；后续维护沿开发指南进行。

2026-10-05 复筛后，五条未合入的旧本地开发分支退出维护。旧参考托盘与节点方案已有主线等价内容；早期迁移实验内核、旧启动脚本和历史报告保留为恢复材料，不加入运行主线。业务回归分支中仍适用的统计接口 fixture 与 DNS 隔离修补已吸收到当前测试。原分支提交保存在本地 Git 恢复包，历史工作树停留在原提交；仍被桥接服务使用的目录继续保留。远端分支未删除。

## 发布与原始证据

[本地发布验证记录](../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/06_production-deployment-stage-progress.v1.md)的顶部记载本地验收、清理完成和停止执行；正式发布延后，生产发布授权未建立。下方旧状态只说明当时情况。

冻结快照、候选身份、日志和散列保留原路径、原字节。旧生产合同目录与仓库根的 `stage1-successor-evidence/`、`stage3-evidence/`、`stage5-evidence/`、`stage6-evidence/` 是历史证据位置。旧编号不参与日常使用导航。

## 专题档案

| 内容 | 入口 |
| --- | --- |
| 已完成开发主题 | [已关闭档案](../development/development-plans/ARCHIVE_CLOSED/INDEX.md) |
| 已退出实施的主题 | [退役档案](../../development/latest-dev-docs/development-plans/ARCHIVE_RETIRED/INDEX.md) |
| 保留外部条件的主题 | [外部依赖档案](../../development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/INDEX.md) |
| 前端和根计划 | [前端历史](../development/frontend-modern/README.md)、[根计划历史](../development/root-plans/README.md) |
| 后端排查与调研 | [后端专题档案](../../main/backend/docs/archive/) |
| 历史架构目录 | [后端](../architecture/backend-core/README.md)、[运行与界面](../architecture/ops-frontend/README.md)、[开发计划](../architecture/development-plans/README.md)、[根计划](../architecture/root-plans/README.md)、[后端专题](../architecture/backend-docs/README.md) |
| 旧版本说明 | 仓库根 `RELEASE_NOTES_*.md`，按文件日期与版本读取 |
| 文档迁移 | [迁移记录索引](documentation-migration.md) |

旧 `development/latest-dev-docs` 目录保留必要兼容链接与证据，内容位置由既有迁移清单确定。原入口全文可从 Git 历史查询，重复总览不再继续累加更新。
