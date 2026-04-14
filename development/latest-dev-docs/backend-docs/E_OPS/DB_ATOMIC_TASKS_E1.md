# E-db 第1轮原子任务表

| ID | 原子任务 | 输入 | 输出 | 状态 |
|---|---|---|---|---|
| E1-T1 | 创建独立工作副本/worktree（含 -E-db） | 主仓库 + 分支策略`feature/version-C-streamplus` | `...-E-db` 工作副本 + `feature/version-E-db` | ✅ |
| E1-T2 | 联网检索 DB 最佳实践 | 官方文档源 | 可复用结论清单 | ✅ |
| E1-T3 | 知识池沉淀 | 检索结论 | `DB_BEST_PRACTICES_RESEARCH_2026-03-03.md` | ✅ |
| E1-T4 | 最小工程化增强：连接池配置模板化 | 现有 settings/base | 可调参数（Settings + .env.example） | ✅ |
| E1-T5 | 最小工程化增强：索引迁移 | 现有表结构 + 查询模式 | revision `20260303_000006` | ✅ |
| E1-T6 | 最小工程化增强：健康检查增强 | health/deep 现状 | 增加 pool 状态与延迟字段 | ✅ |
| E1-T7 | 验证与封口文档 + 索引更新 | 代码改动 | 验证记录 + 文档入口更新 | ✅ |
