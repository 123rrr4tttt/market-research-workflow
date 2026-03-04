# Gap Definitions and Archive References (2026-03-03)

Last Updated: `2026-03-03 15:31 PST`

## 1. 缺口定义（统一口径）

- `GAP-CLOSE-001`：封口证据不足（实现存在，但无可重复验收/实测闭环）。
- `GAP-CONTRACT-002`：接口契约未闭环（字段、错误语义、版本兼容、前后端对齐不足）。
- `GAP-TEST-003`：测试闭环不足（仅单点覆盖，缺端到端/跨链路/失败分支回归）。
- `GAP-OBS-004`：可观测性不足（监控、告警、过程历史字段、SLO 指标缺口）。
- `GAP-ROLLBACK-005`：灰度/回滚/幂等不足（回放、回退、重试一致性缺口）。
- `GAP-DATA-006`：数据模型与迁移缺口（字段/索引/约束/隔离未落地）。
- `GAP-OPS-007`：运维与发布资料缺口（Runbook、压测基线、脚本回归未闭环）。

## 2. CURRENT_DEV 归档引用

| 计划 | 判定 | 缺口标签 | 归档引用 |
|---|---|---|---|
| `2026-03-01-open-source-platform-integration/01_*` | `closed` | `GAP-CLOSE-001` `GAP-TEST-003` `GAP-OBS-004` | [`01_multi-agent-taskboard-open-source-platform-integration-2026-03-01.md`](../../CLOSED_DEV/2026-03-01-open-source-platform-integration-closure/01_multi-agent-taskboard-open-source-platform-integration-2026-03-01.md) |
| `2026-03-02-graph-3d-force-engine-parallel-migration/01_*` | `closed` | `CV02-CLOSE-3D-20260303-01` | [`01_graph-3d-force-engine-parallel-migration-2026-03-02.md`](../../CLOSED_DEV/2026-03-02-graph-3d-force-engine-parallel-migration-closure/01_graph-3d-force-engine-parallel-migration-2026-03-02.md) |
| `2026-03-02-graph-node-standardization-a-then-b-plan/01_*` | `closed` | `GAP-DATA-006` `GAP-ROLLBACK-005` `GAP-TEST-003` | [`01_graph-node-standardization-a-then-b-plan-2026-03-02.md`](../../CLOSED_DEV/2026-03-02-graph-node-standardization-a-then-b-closure/01_graph-node-standardization-a-then-b-plan-2026-03-02.md) |
| `2026-03-02-ingest-chain-full-branch-map/01_*` | `closed` | `GAP-TEST-003` `GAP-CONTRACT-002` | [`01_ingest-chain-full-branch-map-2026-03-02.md`](../../CLOSED_DEV/2026-03-02-ingest-chain-full-branch-map-closure/01_ingest-chain-full-branch-map-2026-03-02.md) |
| `2026-03-02-ingest-platformization-assessment/01_*` | `closed(waived-tail)` | `GAP-CONTRACT-002` `GAP-OBS-004` `GAP-ROLLBACK-005` | [`01_ingest-platformization-assessment-and-roadmap-2026-03-02.md`](../../CLOSED_DEV/2026-03-02-ingest-platformization-assessment-closure/01_ingest-platformization-assessment-and-roadmap-2026-03-02.md) |
| `2026-03-02-meaningful-ingest-guardrails-plan/01_*` | `closed` | `GAP-TEST-003` `GAP-CONTRACT-002` | [`01_meaningful-ingest-guardrails-plan-2026-03-02.md`](../../CLOSED_DEV/2026-03-02-meaningful-ingest-guardrails-plan-closure/01_meaningful-ingest-guardrails-plan-2026-03-02.md) |
| `2026-03-02-single-url-first-ingest-allocation-plan/01_*` | `closed` | `GAP-CONTRACT-002` `GAP-TEST-003` `GAP-OBS-004` | [`01_single-url-first-ingest-allocation-plan-2026-03-02.md`](../../CLOSED_DEV/2026-03-02-single-url-first-ingest-allocation-closure/01_single-url-first-ingest-allocation-plan-2026-03-02.md) |
| `2026-03-02-single-url-first-ingest-allocation-plan/02_*` | `closed` | `GAP-CONTRACT-002` `GAP-TEST-003` `GAP-OBS-004` | [`02_plan-domain-reinvestigation-2026-03-02.md`](../../CLOSED_DEV/2026-03-02-single-url-first-ingest-allocation-closure/02_plan-domain-reinvestigation-2026-03-02.md) |
| `2026-03-02-source-time-window-smart-timestamp-plan/01_*` | `closed` | `GAP-DATA-006` `GAP-CONTRACT-002` `GAP-OBS-004` | [`01_source-time-window-smart-timestamp-plan-2026-03-02.md`](../../CLOSED_DEV/2026-03-02-source-time-window-smart-timestamp-closure/01_source-time-window-smart-timestamp-plan-2026-03-02.md) |
| `2026-03-02-source-time-window-smart-timestamp-plan/02_*` | `closed` | `GAP-DATA-006` `GAP-ROLLBACK-005` `GAP-OPS-007` | [`02_execution-plan-source-time-window-smart-timestamp-2026-03-02.md`](../../CLOSED_DEV/2026-03-02-source-time-window-smart-timestamp-closure/02_execution-plan-source-time-window-smart-timestamp-2026-03-02.md) |
| `2026-03-02-source-time-window-smart-timestamp-plan/03_*` | `closed` | `GAP-DATA-006` `GAP-CONTRACT-002` `GAP-ROLLBACK-005` | [`03_decoupled-implementation-plan-source-time-window-and-noun-density-2026-03-02.md`](../../CLOSED_DEV/2026-03-02-source-time-window-smart-timestamp-closure/03_decoupled-implementation-plan-source-time-window-and-noun-density-2026-03-02.md) |
| `2026-03-03-global-vectorization-general-foundation/01_*` | `closed` | `GAP-DATA-006` `GAP-ROLLBACK-005` `GAP-TEST-003` | [`01_global-vectorization-general-foundation-plan-2026-03-03.md`](../../CLOSED_DEV/2026-03-03-global-vectorization-general-foundation/01_global-vectorization-general-foundation-plan-2026-03-03.md) |
| `2026-03-03-global-vectorization-general-foundation/02_*` | `closed` | `GAP-CLOSE-001` `GAP-TEST-003` `GAP-ROLLBACK-005` | [`02_atomic-vectorization-tasklist-2026-03-03.md`](../../CLOSED_DEV/2026-03-03-global-vectorization-general-foundation/02_atomic-vectorization-tasklist-2026-03-03.md) |
| `2026-03-03-global-vectorization-general-foundation/03_*` | `closed` | `GAP-CLOSE-001` `GAP-TEST-003` `GAP-OPS-007` | [`03_vectorization-atomic-execution-report-2026-03-03.md`](../../CLOSED_DEV/2026-03-03-global-vectorization-general-foundation/03_vectorization-atomic-execution-report-2026-03-03.md) |

## 3. 封口项目漏项归档引用

- 对象：`CLOSED_DEV/2026-03-03-platformization-first-vectorization`
- 归档结论引用：
  - [`../../CLOSED_DEV/2026-03-03-platformization-first-vectorization/05_graph-node-standardization-overall-completion-2026-03-03.md`](../../CLOSED_DEV/2026-03-03-platformization-first-vectorization/05_graph-node-standardization-overall-completion-2026-03-03.md)
  - [`../../CLOSED_DEV/2026-03-03-platformization-first-vectorization/06_backend-db-standardization-vectorization-closure-2026-03-03.md`](../../CLOSED_DEV/2026-03-03-platformization-first-vectorization/06_backend-db-standardization-vectorization-closure-2026-03-03.md)
  - [`../../main/DEVELOPMENT_STREAMS_CLOSURE_AND_GAPS_2026-03-03.md`](../../main/DEVELOPMENT_STREAMS_CLOSURE_AND_GAPS_2026-03-03.md)

## 4. 过时方案处置映射（已定性）

- “graph projection 作为主路径” -> `confirmed_outdated`（统一改为 `graph_db / db-primary`）。
- “B 异常回退到 A” -> `confirmed_outdated`（按当前实现与封口口径，以 B 路径显式行为为准）。
- `legacy-projection` / `run_item_by_key legacy adapter path` -> `compat_kept`（兼容保留，需补退役条件）。
- `test_graph_projection_unittest.py` 作为主链门禁 -> `confirmed_outdated`（转为历史回归参考，不作为主链封口门禁）。

> 注：本文件只做缺口定义与引用归档，不包含修复方案与执行计划。

## 5. 执行进展快照（2026-03-03）

- 阶段性封口（P0）：`GAP-DATA-006`、`GAP-CONTRACT-002` 的基础任务已落地（`AT-001~AT-004=done`）。
- 图谱运行面：`db-primary` 已回填，`/api/v1/admin/content-graph`、`/api/v1/admin/market-graph`、`/api/v1/admin/policy-graph` 均返回非空。
- 加细视图：`market_deep_entities/topic_scope` 已恢复。
- 后续边界：`AT-005+` 仍按原任务板推进，不在本文件展开。
- 证据引用：[`02_atomic-parallel-closure-taskboard-2026-03-03.md`](./02_atomic-parallel-closure-taskboard-2026-03-03.md)。
