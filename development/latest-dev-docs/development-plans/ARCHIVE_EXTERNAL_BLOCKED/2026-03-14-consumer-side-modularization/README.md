# 2026-03-14 Consumer Side Modularization

## 文档列表

1. [01_consumer-side-modularization-assessment-and-plan-2026-03-14.md](./01_consumer-side-modularization-assessment-and-plan-2026-03-14.md)
2. [02_wave9-5-consumer-facade-boundary-contract-2026-05-22.md](./02_wave9-5-consumer-facade-boundary-contract-2026-05-22.md)
3. [03_wave11-consumer-query-extraction-evidence-2026-05-22.md](./03_wave11-consumer-query-extraction-evidence-2026-05-22.md)
4. [04_wave13-admin-dashboard-consumer-extraction-evidence-2026-05-22.md](./04_wave13-admin-dashboard-consumer-extraction-evidence-2026-05-22.md)
5. [05_wave15-consumer-sql-predicate-facade-2026-05-22.md](./05_wave15-consumer-sql-predicate-facade-2026-05-22.md)
6. [06_wave17-policy-state-consumer-query-boundary-2026-05-22.md](./06_wave17-policy-state-consumer-query-boundary-2026-05-22.md)
7. [07_wave20-prompt-time-density-consumer-facade-2026-05-22.md](./07_wave20-prompt-time-density-consumer-facade-2026-05-22.md)
8. [08_wave27-external-blocked-decision-2026-05-23.md](./08_wave27-external-blocked-decision-2026-05-23.md)

## 使用说明

1. 本目录单独覆盖消费侧读取模块化。
2. 重点区分 `document_views` 读取层与 `document_queries` 查询层。
3. 与 `2026-03-12-data-structured-service-modularization/` 目录形成“写入侧主线 / 消费侧主线”分工。
4. Wave17 worker 8 将 `/policies/state/{state}` 作为非 admin/dashboard consumer query boundary 增量迁移到 `document_queries` helper。
5. Wave27 已将本目录迁入 `ARCHIVE_EXTERNAL_BLOCKED`：repo-local consumer facade/query gates 均通过，剩余条件为 live DB/API smoke。
