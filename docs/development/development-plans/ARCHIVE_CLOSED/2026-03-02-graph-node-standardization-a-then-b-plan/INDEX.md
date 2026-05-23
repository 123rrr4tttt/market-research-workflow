# Graph Node Standardization A Then B Plan Index

更新时间：2026-05-23 PST
状态：`closed` / `wave43_live_db_validated`。本目录已迁入 `ARCHIVE_CLOSED`；仓内 canonical-id、backfill readiness、live-DB rollout manifest、readback gates 与 live tenant DB evidence 均已封住。较早 `partial` / `open` / `external_blocked` 文案仅作历史阶段记录，不再是当前目录主状态。

防误读：当前 canonical decision 以本 `INDEX.md` 与 `10_wave43-manual-live-db-closure-2026-05-23.md` 为准。GraphPage/WebGL 视觉 smoke、Graph editing audit/rollback UI 与 live audit durability 不属于本目录闭合范围。

## 文件

- [01_graph-node-standardization-a-then-b-plan-2026-03-02.md](./01_graph-node-standardization-a-then-b-plan-2026-03-02.md)
  原始 Graph Node standardization A/B plan。
- [02_wave7-status-evidence-and-min-plan-2026-05-22.md](./02_wave7-status-evidence-and-min-plan-2026-05-22.md)
  Wave7 status evidence 与最小计划。
- [03_wave8-5-db-backfill-readmode-dry-run-evidence-2026-05-22.md](./03_wave8-5-db-backfill-readmode-dry-run-evidence-2026-05-22.md)
  DB backfill/read-mode dry-run evidence。
- [04_wave10-db-rollout-readiness-contract-2026-05-22.md](./04_wave10-db-rollout-readiness-contract-2026-05-22.md)
  DB rollout readiness contract。
- [05_wave12-live-smoke-readiness-gate-2026-05-22.md](./05_wave12-live-smoke-readiness-gate-2026-05-22.md)
  Live smoke readiness gate。
- [06_wave14-live-db-rollout-gate-2026-05-22.md](./06_wave14-live-db-rollout-gate-2026-05-22.md)
  Live DB rollout gate。
- [07_wave17-rollout-manifest-readback-2026-05-22.md](./07_wave17-rollout-manifest-readback-2026-05-22.md)
  Rollout manifest readback。
- [08_wave19-graph-rollout-readback-gate-2026-05-22.md](./08_wave19-graph-rollout-readback-gate-2026-05-22.md)
  Graph rollout readback gate。
- [09_wave23-closure-decision-2026-05-23.md](./09_wave23-closure-decision-2026-05-23.md)
  历史 decision：仓内 rollout/readback gates 封住，剩余 live tenant DB evidence。
- [10_wave43-manual-live-db-closure-2026-05-23.md](./10_wave43-manual-live-db-closure-2026-05-23.md)
  当前 canonical decision：live tenant DB evidence 已补齐，目录 closed。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_CLOSED` | `CURRENT_DEV/INDEX.md` 不再将本主题计入 `partial` |
| Repo-local graph node gates | sealed | Wave23 decision checker readback |
| Live tenant DB validation | sealed | Wave43 evidence pack |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_node_rollout_manifest.py --format text
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_node_live_db_rollout_gate.py --live-db-evidence-json development/latest-dev-docs/automation-runs/wave43-manual-graph-live-db-closure/2026-05-23/live_db_evidence.json --format text
```
