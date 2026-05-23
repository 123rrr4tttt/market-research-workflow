# Graph 3D Force Engine Parallel Migration Index

更新时间：2026-05-23 PST
状态：`closed` / `wave44_live_ui_validated`。本目录已迁入 `ARCHIVE_CLOSED`；仓内 Force3D frontend contract、runtime pixel/shape、visual-data smoke、rollback/readback gates 与 live backend-data GraphPage/WebGL evidence 均已封住。历史 `partial` / `open` / `external_blocked` 表述只表示迁档前的推进阶段，不再是当前目录主状态。

防误读：当前 canonical decision 以本 `INDEX.md` 与 `09_wave44-manual-live-ui-closure-2026-05-23.md` 为准。`08_wave24` 是历史 external-blocked decision；Graph editing audit/rollback UI 与 live audit durability 不属于本目录闭合范围。

## 文件

- [01_graph-3d-force-engine-parallel-migration-2026-03-02.md](./01_graph-3d-force-engine-parallel-migration-2026-03-02.md)
  原始 Graph 3D force engine migration 方案。
- [02_wave8-5-backend-rollout-contract-note-2026-05-22.md](./02_wave8-5-backend-rollout-contract-note-2026-05-22.md)
  Backend rollout contract note。
- [03_wave10-frontend-visual-engine-switch-contract-2026-05-22.md](./03_wave10-frontend-visual-engine-switch-contract-2026-05-22.md)
  Frontend visual engine switch contract。
- [04_wave12-live-smoke-readiness-gate-2026-05-22.md](./04_wave12-live-smoke-readiness-gate-2026-05-22.md)
  Live smoke readiness gate。
- [05_wave14-graph-visual-data-smoke-gate-2026-05-22.md](./05_wave14-graph-visual-data-smoke-gate-2026-05-22.md)
  Graph visual data smoke gate。
- [06_wave17-runtime-pixel-shape-gate-2026-05-22.md](./06_wave17-runtime-pixel-shape-gate-2026-05-22.md)
  Runtime pixel/shape gate。
- [07_wave19-graph-rollout-readback-gate-2026-05-22.md](./07_wave19-graph-rollout-readback-gate-2026-05-22.md)
  Graph rollout readback gate。
- [08_wave24-external-blocked-decision-2026-05-23.md](./08_wave24-external-blocked-decision-2026-05-23.md)
  历史 decision：仓内 3D graph gates 封住，剩余 live tenant DB / WebGL evidence。
- [09_wave44-manual-live-ui-closure-2026-05-23.md](./09_wave44-manual-live-ui-closure-2026-05-23.md)
  当前 canonical decision：live backend-data GraphPage/WebGL evidence 已补齐，目录 closed。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_CLOSED` | `CURRENT_DEV/INDEX.md` 不再将本主题计入 `partial` |
| Repo-local graph 3D gates | sealed | backend/frontend graph checker list in Wave24 decision |
| Live tenant DB / WebGL evidence | sealed | Wave43 live DB evidence + Wave44 GraphPage force3d canvas evidence |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_rollout_readback_gate.py --format text
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_visual_data_smoke_gate.py --backend-data-evidence-json development/latest-dev-docs/automation-runs/wave44-manual-graph3d-live-ui-closure/2026-05-23/backend_data_evidence.json --live-ui-evidence-json development/latest-dev-docs/automation-runs/wave44-manual-graph3d-live-ui-closure/2026-05-23/live_ui_evidence.json --format text
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_live_smoke_readiness.py --live-db-evidence-json development/latest-dev-docs/automation-runs/wave43-manual-graph-live-db-closure/2026-05-23/live_db_evidence.json --frontend-backend-evidence-json development/latest-dev-docs/automation-runs/wave44-manual-graph3d-live-ui-closure/2026-05-23/live_ui_evidence.json --format text
```
