# Graph 3D Force Engine Parallel Migration Index

更新时间：2026-05-23 PST
状态：`external_blocked` / `wave24_checked`。本目录已迁入 `ARCHIVE_EXTERNAL_BLOCKED`；仓内 Force3D frontend contract、runtime pixel/shape、visual-data smoke、rollback/readback gates 已封住。历史 `partial` / `open` 表述只表示迁档前的推进阶段，不再是当前目录主状态。

防误读：当前 canonical decision 以本 `INDEX.md` 与 `08_wave24-external-blocked-decision-2026-05-23.md` 为准。重新进入 `CURRENT_DEV` 前，必须先补齐 live tenant DB GraphPage run、backend graph endpoint data、nonblank WebGL canvas 和 `window.__graph3dDebug` evidence。

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
  当前 canonical decision：仓内 3D graph gates 封住，剩余 live tenant DB / WebGL evidence。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_EXTERNAL_BLOCKED` | `CURRENT_DEV/INDEX.md` 不再将本主题计入 `partial` |
| Repo-local graph 3D gates | sealed | backend/frontend graph checker list in Wave24 decision |
| Live tenant DB / WebGL evidence | external blocker | requires configured live tenant data and browser capture |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_rollout_readback_gate.py --format text
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_visual_data_smoke_gate.py --format text
```
