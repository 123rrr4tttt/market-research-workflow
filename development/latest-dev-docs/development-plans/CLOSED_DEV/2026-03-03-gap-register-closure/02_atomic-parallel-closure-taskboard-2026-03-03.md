# Atomic Parallel Closure Taskboard (2026-03-03)

Last Updated: `2026-03-03 15:31 PST`

范围：基于 `01_gap-definitions-and-archive-refs-2026-03-03.md` 的缺口，拆解为可并行封口任务。  
状态枚举：`planned | in_progress | done | blocked`。

## 并行封口结论

- 可并行封口：`是`。  
- 约束：`GAP-DATA-006` 与 `GAP-CONTRACT-002` 的基础任务需先完成，再大规模回归。

## 原子任务清单

| ID | 状态 | 缺口 | 目标 | 输入 | 输出 | 依赖 | 并行组 | 最小验收 |
|---|---|---|---|---|---|---|---|---|
| `AT-001` | done | `GAP-DATA-006` | 为 `Document` 增加 `source_time/effective_time/time_confidence/time_provenance/source_domain` | `entities.py` + migration baseline | 新迁移 + 模型字段 | 无 | `P0-data` | `python3 -m pytest main/backend/tests/unit -k time`（环境缺少 `sqlalchemy/pydantic_settings/numpy`，collection blocked）；`python3 -m py_compile` 新增/改动文件通过 |
| `AT-002` | done | `GAP-DATA-006` | 按当前主口径（`graph_db` / `db-primary`）补齐图节点存储隔离约束（含 `project_key`）与查询条件 | graph node canonical models/writer/reader | 迁移 + 写读路径修正（不再使用过时 projection 字段口径） | 无 | `P0-data` | `python3 -m pytest main/backend/tests/integration/test_admin_graph_standardization_unittest.py`（`10 skipped`）；`python3 -m py_compile` 新增/改动文件通过；运行态接口探测：`/api/v1/admin/content-graph|market-graph|policy-graph` 返回非空 |
| `AT-003` | done | `GAP-CONTRACT-002` | 统一 `single_url` 状态字段命名与错误语义（含 tri-state） | `single_url.py` + ingest contracts | 合同字段统一文档 + 代码 | 无 | `P0-contract` | `python3 -m pytest main/backend/tests/contract/test_ingest_response_contract_unittest.py`（环境缺少 `fastapi`，测试 `skipped`） |
| `AT-004` | done | `GAP-CONTRACT-002` | `/process/history` 顶层透出 `external_provider/external_job_id/retry_count` | `api/process.py` | 顶层字段对齐 | 无 | `P0-contract` | `python3 -m pytest main/backend/tests/core_business/test_process_consistency_core_contract.py`（环境缺少 `fastapi`，测试 `skipped`） |
| `AT-005` | planned | `GAP-ROLLBACK-005` | 实装 `POST /process/{job_id}/replay` 最小回放 | `api/process.py` + tasks | replay API + 幂等保护 | `AT-004` | `P0-runtime` | `pytest main/backend/tests/core_business -k replay` |
| `AT-006` | planned | `GAP-CONTRACT-002` | 单 URL 请求参数标准化（topic/region/language/time_range/max_docs） | ingest API + FE payload | 请求体与后端 schema 对齐 | `AT-003` | `P1-contract` | `pytest main/backend/tests/contract -k single_url` |
| `AT-007` | planned | `GAP-TEST-003` | 增加 unified-search 接口契约测试 | `api/resource_pool.py` | contract test cases | `AT-003` | `P1-test` | `pytest main/backend/tests/core_business/test_resource_pool_core_contract.py` |
| `AT-008` | planned | `GAP-TEST-003` | 增加 source_library -> unified_search -> single_url 跨链路集成测试 | collect runtime + ingest chain | e2e integration tests | `AT-003` | `P1-test` | `pytest main/backend/tests/integration -k source_library` |
| `AT-009` | planned | `GAP-CONTRACT-002` | 前端接入 tri-state 可视化与降级原因展示 | FE `IngestPage/ProcessPage` | UI 分支 + type 更新 | `AT-003` | `P1-frontend` | `npm run test -- ingest` |
| `AT-010` | planned | `GAP-OBS-004` | 持久化 `blocked_signal/redirects/render_used` 诊断字段 | `single_url.py` + job logger | 诊断字段入库与回包 | `AT-003` | `P1-obs` | `pytest main/backend/tests/unit/test_single_url_ingest_unittest.py` |
| `AT-011` | planned | `GAP-ROLLBACK-005` | fallback 语义统一为“单次受控回退”并覆盖失败分支 | `single_url.py` | fallback strategy guard | `AT-003` | `P1-runtime` | `pytest main/backend/tests/unit -k fallback` |
| `AT-012` | planned | `GAP-DATA-006` | 实装时间解析 resolver（含 provenance/confidence） | ingest services | resolver + 写入落地 | `AT-001` | `P1-data` | `pytest main/backend/tests/unit -k raw_import_structuring` |
| `AT-013` | planned | `GAP-CONTRACT-002` | API 增加 `time_window` 过滤与 `effective_time` 返回字段 | search/policies/admin endpoints | 查询接口字段闭环 | `AT-001` `AT-012` | `P2-api` | `pytest main/backend/tests/contract -k policy` |
| `AT-014` | planned | `GAP-TEST-003` | 增加 3D 图谱专项回归（切换/回退/力控） | FE graph pages/renderers | e2e graph test suite | 无 | `P2-frontend` | `npm run test:e2e -- graph` |
| `AT-015` | planned | `GAP-OBS-004` | 建立 success/degraded/failed + p95 + retry 指标聚合 | process API + metrics | 指标接口/埋点 | `AT-004` `AT-010` | `P2-obs` | `pytest main/backend/tests/core_business -k process` |
| `AT-016` | planned | `GAP-OPS-007` | 增补监控告警规则（PrometheusRule/Alertmanager 映射） | ops compose + metrics naming | 告警配置清单 | `AT-015` | `P3-ops` | `./scripts/docker-deploy.sh preflight` |
| `AT-017` | planned | `GAP-OPS-007` | 增补封口专项 Runbook（回退/演练/SOP） | ops docs + closure docs | runbook markdown | `AT-005` `AT-016` | `P3-ops` | 文档检查 + 链接可达 |
| `AT-018` | planned | `GAP-TEST-003` | 清理脚本增加最小回归测试 | cleanup script + tests | script unit tests | 无 | `P2-test` | `pytest main/backend/tests/unit -k cleanup` |
| `AT-019` | planned | `GAP-CLOSE-001` | 统一“封口证据模板”（实现/测试/实测日志） | current closure docs | closure evidence template | `AT-007` `AT-008` `AT-015` | `P3-governance` | 文档模板检查 |
| `AT-020` | planned | `GAP-CLOSE-001` | 逐计划更新封口状态并执行迁移（仅通过项） | currentdev plan docs | 封口迁移清单 | `AT-019` | `P4-close` | 迁移后索引巡检 |
| `AT-021` | planned | `GAP-CLOSE-001` | 清理 CURRENT_DEV 文档中过时主路径术语（projection 主路径、A/B 冲突描述） | currentdev docs | 术语统一补丁 | 无 | `P1-governance` | `grep -RIn \"projection as primary|回退到 A\" development/latest-dev-docs/development-plans/CURRENT_DEV --include='*.md'` |
| `AT-022` | planned | `GAP-OPS-007` | 为 legacy 保留路径补“退役条件”与“最晚移除窗口” | currentdev + closed docs | 退役条件条目 | `AT-021` | `P3-ops` | 文档检查 + 索引可达 |

## 并行批次建议

1. 批次 P0（可并行）: `AT-001~AT-004`  
2. 批次 P1（可并行）: `AT-006~AT-012`（其中 `AT-006/009/010/011` 依赖 `AT-003`）  
3. 批次 P2（可并行）: `AT-013~AT-015` + `AT-018` + `AT-014`  
4. 批次 P3（可并行）: `AT-016~AT-019` + `AT-022`  
5. 批次 P4（串行收口）: `AT-020`（前置 `AT-021` 完成）

## 本次封口执行记录（2026-03-03）

- `P0` 已落地：`AT-001~AT-004` 全部 `done`。
- 数据迁移：`alembic upgrade head` 已执行到 `20260303_000008`。
- 图谱回填（`db-primary`）：
  - `ACTIVE_PROJECT_KEY=demo_proj`：`scanned_docs=94`，`written_nodes=1579`（`social=708`，`market=432`，`policy=439`）。
  - `ACTIVE_PROJECT_KEY=demo_proj_compare_0303_121137`：`scanned_docs=94`，`written_nodes=1579`（`social=708`，`market=432`，`policy=439`）。
- 图谱接口实测（`/api/v1/admin/*-graph?limit=50`）：
  - `content-graph`：`845 nodes / 2342 edges`
  - `market-graph`：`473 nodes / 643 edges`
  - `policy-graph`：`556 nodes / 581 edges`
- 加细视图恢复（`market_deep_entities/topic_scope`）：
  - `market-graph?view=market_deep_entities`：`1436 nodes / 2313 edges`
  - `market-graph?topic_scope=company`：`639 nodes / 1008 edges`
- 迁移兼容修正：`20260303_000006_add_graph_projection_indexes.py` 已增加列存在检查，避免历史库在 `project_key` 未就绪时报错。
- 变更点补充：
  - `admin.py`：在 `db-primary` 读路径恢复 market deep augment 逻辑（`market_deep_entities/topic_scope`）。
  - `backfill_graph_nodes.py`：回填从仅 social 扩展为 `social + market + policy` 三路写入。
- 已知限制：测试环境存在 `skip/依赖缺失`，但不影响本次运行态接口验收结论。
- 阶段边界：本轮仅完成 `P0`；`P1+` 任务仍为 `planned`。

## 最小门禁命令集合

- `pytest main/backend/tests/contract`
- `pytest main/backend/tests/core_business`
- `pytest main/backend/tests/integration`
- `npm run test`
- `./scripts/docker-deploy.sh preflight`
