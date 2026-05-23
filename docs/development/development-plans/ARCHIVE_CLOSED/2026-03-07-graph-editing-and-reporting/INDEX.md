# Graph Editing And Reporting Index

更新时间：2026-05-23 PST
状态：`closed` / `wave46_live_audit_closed`。本目录已迁入 `ARCHIVE_CLOSED`；仓内 backend audit/readback、tenant-like fixture、conflict/rollback readback、GraphPage audit/rollback/handoff replay UI gate，以及 Wave46 live tenant DB audit durability / persistent handoff replay / tenant-project scope 证据均已封住。目录内早期 `partial`、`not_closed`、`live smoke readiness`、`external_blocked` 表述只表示迁档前推进阶段，不再是当前目录主状态。

防误读：当前 canonical decision 以本 `INDEX.md` 与 `12_wave46-manual-live-audit-closure-2026-05-23.md` 为准。`11_wave27-external-blocked-decision-2026-05-23.md` 保留为历史外部阻塞判定，不再代表当前目录状态。

## 文件

- [01_graph-editing-and-reporting-plan-2026-03-07.md](./01_graph-editing-and-reporting-plan-2026-03-07.md)
  原始 graph editing/reporting 方案。
- [02_atomic-tasklist-graph-editing-and-reporting-2026-03-07.md](./02_atomic-tasklist-graph-editing-and-reporting-2026-03-07.md)
  原子任务清单，历史未封口语义仅作追溯。
- [03_wave6-reporting-handoff-evidence-closure-gap-2026-05-22.md](./03_wave6-reporting-handoff-evidence-closure-gap-2026-05-22.md)
  Reporting handoff evidence 与 closure gap。
- [04_wave8-5-projection-rollout-contract-note-2026-05-22.md](./04_wave8-5-projection-rollout-contract-note-2026-05-22.md)
  Projection rollout contract note。
- [05_wave11-graph-editing-audit-rollback-evidence-2026-05-22.md](./05_wave11-graph-editing-audit-rollback-evidence-2026-05-22.md)
  Audit / rollback repo-local evidence。
- [06_wave12-live-smoke-readiness-gate-2026-05-22.md](./06_wave12-live-smoke-readiness-gate-2026-05-22.md)
  Live smoke readiness gate，保留外部环境条件。
- [07_wave15-graph-editing-audit-durability-2026-05-22.md](./07_wave15-graph-editing-audit-durability-2026-05-22.md)
  Audit durability repo-local gate。
- [08_wave16-graph-editing-ui-audit-controls-2026-05-22.md](./08_wave16-graph-editing-ui-audit-controls-2026-05-22.md)
  GraphPage UI audit controls。
- [09_wave18-graph-editing-audit-readback-2026-05-22.md](./09_wave18-graph-editing-audit-readback-2026-05-22.md)
  Audit readback evidence。
- [10_wave20-graph-editing-audit-conflict-readback-2026-05-22.md](./10_wave20-graph-editing-audit-conflict-readback-2026-05-22.md)
  Conflict / rollback readback evidence。
- [11_wave27-external-blocked-decision-2026-05-23.md](./11_wave27-external-blocked-decision-2026-05-23.md)
  Wave27 historical decision：repo-local gates 通过，当时剩余 live tenant DB audit durability。
- [12_wave46-manual-live-audit-closure-2026-05-23.md](./12_wave46-manual-live-audit-closure-2026-05-23.md)
  当前 canonical closure：live tenant DB audit durability、persistent handoff replay readback 与 tenant/project scoping 已通过。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_CLOSED` | `CURRENT_DEV/INDEX.md` 不再将本主题计入 `partial` 或 `external_blocked` |
| Repo-local audit / rollback / UI gates | sealed | `check_graph_editing_audit_durability.py`、unit pytest、GraphPage focused e2e |
| Live tenant DB audit durability | sealed | Wave46 live API + PostgreSQL readback evidence |
| Persistent handoff replay readback | sealed | `workflow_graph_runs` / `workflow_graph_events` fresh DB readback |
| Tenant/project scoping | sealed | `demo_proj` readback + `default` project `NOT_FOUND` / DB row count `0` |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_editing_audit_durability.py --format text --live-db-audit-evidence-json development/latest-dev-docs/automation-runs/wave46-manual-graph-editing-live-audit-closure/2026-05-23/live_evidence.json --allow-live-closure-claim
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_graph_editing_audit_durability_unittest.py
npm --prefix main/frontend-modern run test:e2e -- tests/e2e/graphpage.spec.ts -g "graph builder (submits|surfaces)" --reporter=line
```
