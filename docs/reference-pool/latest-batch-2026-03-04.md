# E 仓 reference-pool 最新批次（2026-03-04）

## 状态
- 仓库内未发现显式 `docs/reference-pool/` 历史批次目录；本批次作为首个落地批次。
- 假设：以 `development/latest-dev-docs` 与 `main/backend/docs` 中最新 E-DB 相关文档作为“参考包代理”。

## 参考包代理（按优先级）
1. `development/latest-dev-docs/backend-docs/E_OPS/DB_BEST_PRACTICES_RESEARCH_2026-03-03.md`
2. `development/latest-dev-docs/backend-docs/E_OPS/DB_ATOMIC_TASKS_E1.md`
3. `development/latest-dev-docs/backend-docs/E_OPS/E_DB_ROUND1_CLOSURE.md`
4. `main/backend/docs/数据库说明文档.md`

## Repo-level 映射
- 配置层：`main/backend/app/settings/config.py`（DB 连接池与超时、重试参数）
- 运行时可靠性：`main/backend/tests/unit/test_db_session_reliability_unittest.py`
- 任务/规范记录：`development/latest-dev-docs/development-plans/CURRENT_DEV/*`

## R5 本批实现范围
- 采用“最小侵入”策略：先做 reference-pool 映射 + 回归验证，避免在 E clean 基线引入额外风险。
- 本批不新增 DB 结构变更，不触发迁移。
