# ARCHIVE_EXTERNAL_BLOCKED - 外部条件阻塞开发计划

更新时间：2026-05-22（PST）

本目录用于存放已经完成仓内确定性门禁、但剩余验收依赖外部运行时、公网 replay、生产数据、真实租户环境或人工 review 的开发计划。它们不继续占用 `CURRENT_DEV` 的 `partial` 指标；重新进入当前开发前，必须先补齐对应外部条件或开新主题。

## 迁入标准

- 仓内代码、fixture、manifest、readback 或 checker 已能重复验证当前边界
- 剩余 blocker 不可在当前仓库内用确定性测试闭合
- 目录继续留在 `CURRENT_DEV` 会让 `partial` 数虚高，并误导后续 agent 继续补小 gate
- 迁入记录必须写明外部条件、仓内已封证据、恢复条件和验证命令

## 外部阻塞目录

本索引由 Wave21 封口优先波次填充。

## 返回

- [CURRENT_DEV](../CURRENT_DEV/INDEX.md) - 当前仍可作为现行入口的未封口开发计划
- [ARCHIVE_CLOSED](../ARCHIVE_CLOSED/INDEX.md) - 已收口开发计划
- [ARCHIVE_RETIRED](../ARCHIVE_RETIRED/INDEX.md) - 已退场 / 过时开发计划
