# reference-pool 最新批次（2026-03-04）

## 状态
- 仓内此前无显式 `docs/reference-pool` 批次文件；本批次作为首个合并落地批次。
- 本文件同时记录 E 线（DB reliability）与 F 线（llm-report must-gate）的参考包代理与 repo-level 映射。

## E 线参考包代理（按优先级）
1. `development/latest-dev-docs/backend-docs/E_OPS/DB_BEST_PRACTICES_RESEARCH_2026-03-03.md`
2. `development/latest-dev-docs/backend-docs/E_OPS/DB_ATOMIC_TASKS_E1.md`
3. `development/latest-dev-docs/backend-docs/E_OPS/E_DB_ROUND1_CLOSURE.md`
4. `main/backend/docs/数据库说明文档.md`

## E 线 Repo-level 映射
- 配置层：`main/backend/app/settings/config.py`
- 运行时可靠性：`main/backend/tests/unit/test_db_session_reliability_unittest.py`
- 任务/规范记录：`development/latest-dev-docs/development-plans/CURRENT_DEV/*`

## E 线 R5 本批实现范围
- 采用最小侵入策略：先做 reference-pool 映射 + 回归验证，避免在 E clean 基线引入额外风险。
- 本批不新增 DB 结构变更，不触发迁移。

## F 线参考包代理（按优先级）
1. `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-04-sa3-r3-f-llm-report-must-minset/01_sa3-r3-f-implementation-2026-03-04.md`
2. `development/latest-dev-docs/root-plans/F_PLAN/llm-report-best-practices-2026-03-03.md`
3. `main/backend/docs/version-F-llm-report-delivery-2026-03-03.md`
4. `main/backend/docs/AI_GOVERNANCE_MIN_BASELINE.md`

## F 线 Repo-level 映射
- API: `main/backend/app/api/llm_report.py`
- Service: `main/backend/app/services/llm_report_generator.py`
- Config: `main/backend/app/settings/config.py`
- Tests: `main/backend/tests/unit/test_llm_report_*`
- Must-check 脚本: `main/backend/scripts/check_llm_report_must_minset.py`

## F 线 R5 本批实现范围
- 复用 R3 已落地代码与门禁，补齐 reference-pool 映射与回归验证记录。
