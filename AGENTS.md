# MRW 项目 Agent 工作约定

## 强制必读：流程缩减与当前进度

开始或恢复本项目的开发、测试、CI、证据维护、监督或自动化任务前，必须读取：

1. [流程缩减强制规则](development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/19_direct-testing-batch-freeze-amendment.v1.md)，包括 2026-09-13 补充。
2. [阶段进度](development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/06_production-deployment-stage-progress.v1.md)顶部当前执行入口，以及入口指向的本阶段合同和实际相关结果。Stage 4 读取 20 号合同；18 号 Stage 3 合同仅在核对上游要求时按需读取，不要求逐条重读历代候选记录。

本文件是入口，19 号文档是流程缩减规则的统一维护位置，不另建平行规则副本。旧合同、旧回传或过期索引中的逐小修冻结、逐项报审、无差别全量重跑要求，不得恢复为默认流程。实际执行状态须核对当前文件，不能照搬历史 PASS。

强制执行：直接修复 → 最小相关验证 → 批次稳定后仅按真实交付需要统一封存。不得为普通调试先生成 successor；不得因回传进度停止等待重新发放；不得为无变化的同一失败重复跑整套测试。已有阶段退出条件、安全阈值、冻结历史和发布权限边界仍须遵守。

保留用户和其他任务的改动；共享写冲突按具体文件或资源协调，不扩大成整个项目暂停。维护进度和文档本身不触发新候选、rebind、全量测试或新审核循环。

重试复用、日志归属及 CI/冻结影响范围按 19 号文档执行；文档规则生效不等于相关脚本已经修复。监督集中审核整阶段结果，同阶段返工留在原任务，不转发每个普通修复形成审批往返。
