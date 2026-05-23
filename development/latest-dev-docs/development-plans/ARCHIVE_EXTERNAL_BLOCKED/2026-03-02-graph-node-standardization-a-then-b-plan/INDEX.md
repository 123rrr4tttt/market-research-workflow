# Graph Node Standardization A Then B Plan Index

更新时间：2026-05-23 PST
状态：`external_blocked` / `wave23_checked`。本目录已迁入 `ARCHIVE_EXTERNAL_BLOCKED`；仓内 canonical-id、backfill readiness、live-DB rollout manifest 与 readback gates 已封住。较早 `partial` / `open` 文案仅作历史阶段记录，不再是当前目录主状态。

防误读：当前 canonical decision 以本 `INDEX.md` 与 `09_wave23-closure-decision-2026-05-23.md` 为准。重新进入 `CURRENT_DEV` 前，必须先补齐 configured tenant schema、live backfill dry-run、nonempty tenant graph endpoint smoke 与 read-mode parity evidence。

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
  当前 canonical decision：仓内 rollout/readback gates 封住，剩余 live tenant DB evidence。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_EXTERNAL_BLOCKED` | `CURRENT_DEV/INDEX.md` 不再将本主题计入 `partial` |
| Repo-local graph node gates | sealed | Wave23 decision checker readback |
| Live tenant DB validation | external blocker | configured tenant schema and live endpoint evidence still required |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_node_rollout_manifest.py --format text
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_node_live_db_rollout_gate.py --format text
```
