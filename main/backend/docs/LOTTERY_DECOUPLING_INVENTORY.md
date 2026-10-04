# 彩票能力退役指针

> 最后更新：2026-10-03

彩票专用项目、数据采集、MarketStat 写入/查询产品接口已整体退役。通用市场搜索、市场文档、指标点和图谱功能继续保留。MarketStat ORM/schema 仅保留 persistence-only 用途：支持既有数据随项目 schema 迁移和读取保全，不清理或删除数据库中的现有记录。

当前架构退役说明见 [docs/architecture/backend-docs/A_ARCHITECTURE/LOTTERY_DECOUPLING_INVENTORY.md](../../../docs/architecture/backend-docs/A_ARCHITECTURE/LOTTERY_DECOUPLING_INVENTORY.md)。历史 Stage 4–6 evidence、冻结快照和 `ARCHIVE_CLOSED` 文档保持原样。
