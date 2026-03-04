# E-DB R5（E线）执行记录：Reference-Pool 代理映射 + Deep Health Pool Gate

Date: 2026-03-04 (PST)

## 1) 最新参考包消费与 repo-level 映射

### 1.1 检查结果

- `docs/reference-pool`：未找到（目录不存在）。

### 1.2 代理映射（按“最新 + DB/E_OPS/门禁相关”）

- `development/latest-dev-docs/backend-docs/E_OPS/DB_BEST_PRACTICES_RESEARCH_2026-03-03.md`
- `development/latest-dev-docs/backend-docs/E_OPS/E_DB_ROUND1_CLOSURE.md`
- `development/latest-dev-docs/backend-core/main/TEST_AUTOMATION_STANDARDIZATION.md`
- `development/latest-dev-docs/backend-core/main/TEST_SCENARIO_MATRIX.md`
- `main/backend/docs/INGEST_CHAIN_EVIDENCE_MATRIX_2026-03-01.md`

### 1.3 明确假设

- 以文件名内日期为第一优先时间线索。
- 对无日期文件，使用仓库内文件修改时间作为“最新”近似信号。
- 相关性优先级：`DB/E_OPS` > `测试门禁` > `通用摄取证据`。

## 2) 最小真实 E-DB 改进

- 改造点：`main/backend/app/main.py` 的 `/api/v1/health/deep`。
- 改动：增加连接池耗尽门禁（`database_pool`），在连接池达到阈值时返回 `error: pool_exhausted` 并将整体状态置为 `degraded`。
- 侵入性：低（只读检查，不改 schema，不改写路径）。
- 可回滚：高（单文件小范围逻辑变更）。

## 3) 验证计划（定向）

- Integration: `tests/integration/test_deep_health_db_degraded_unittest.py`
- Unit: `tests/unit/test_db_session_reliability_unittest.py`

## 4) 风险

- 瞬时流量波动可能造成短时 `degraded` 告警（误报风险）。
- 若运维将 deep health 直接联动摘流，需要先确认告警策略。

