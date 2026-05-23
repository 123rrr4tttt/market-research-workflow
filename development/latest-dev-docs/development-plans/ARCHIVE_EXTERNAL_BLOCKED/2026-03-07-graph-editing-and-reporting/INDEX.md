# Graph Editing And Reporting Index

更新时间：2026-05-23 PST
状态：`external_blocked` / `wave27_checked`。本目录已迁入 `ARCHIVE_EXTERNAL_BLOCKED`；仓内 backend audit/readback、tenant-like fixture、conflict/rollback readback 与 GraphPage audit/rollback/handoff replay UI gate 已封住。目录内早期 `partial`、`not_closed`、`live smoke readiness` 表述只表示迁档前推进阶段，不再是当前目录主状态。

防误读：当前 canonical decision 以本 `INDEX.md` 与 `11_wave27-external-blocked-decision-2026-05-23.md` 为准。重新进入 `CURRENT_DEV` 前，必须先补齐 live tenant DB audit durability、persistent handoff replay readback 与 tenant/project scoping 证据。

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
  当前 canonical decision：repo-local gates 通过，剩余 live tenant DB audit durability。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_EXTERNAL_BLOCKED` | `CURRENT_DEV/INDEX.md` 不再将本主题计入 `partial` |
| Repo-local audit / rollback / UI gates | sealed | `check_graph_editing_audit_durability.py`、unit pytest、GraphPage focused e2e |
| Live tenant DB audit durability | external blocker | 需要 configured tenant DB、fresh-session audit readback、persistent handoff replay |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_editing_audit_durability.py --format text
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_graph_editing_audit_durability_unittest.py
npm --prefix main/frontend-modern run test:e2e -- tests/e2e/graphpage.spec.ts -g "graph builder (submits|surfaces)" --reporter=line
```
