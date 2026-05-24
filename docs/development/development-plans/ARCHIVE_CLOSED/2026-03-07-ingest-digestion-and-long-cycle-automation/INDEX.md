# Ingest Digestion and Long-Cycle Automation Index

更新时间：2026-05-23 PST
状态：`closed` / `wave55_live_implemented`。Wave55 已实现并验证 live scheduler -> queue -> worker -> tenant DB write/readback -> downstream handoff run；本目录已从 `ARCHIVE_EXTERNAL_BLOCKED` 迁入 `ARCHIVE_CLOSED`，不再计入 external-blocked target set。

防误读：Wave7-Wave23 文件保留的是仓内 deterministic / contract-only 分期证据，其中 Wave20 仍刻意声明 `live_dispatch=false`。当前 canonical closure 以 `11_wave55-live-scheduler-closure-2026-05-23.md` 和 live checker artifact 为准。

## 文件

- [01_ingest-digestion-and-long-cycle-automation-plan-2026-03-07.md](./01_ingest-digestion-and-long-cycle-automation-plan-2026-03-07.md)
  原始 ingest digestion / long-cycle automation plan。
- [02_atomic-tasklist-ingest-digestion-and-long-cycle-automation-2026-03-07.md](./02_atomic-tasklist-ingest-digestion-and-long-cycle-automation-2026-03-07.md)
  原子任务清单。
- [03_wave7-7-ingest-digestion-long-cycle-automation-evidence-2026-05-22.md](./03_wave7-7-ingest-digestion-long-cycle-automation-evidence-2026-05-22.md)
  Digestion + long-cycle status contract evidence。
- [04_wave9-6-ingest-long-cycle-lifecycle-contract-evidence-2026-05-22.md](./04_wave9-6-ingest-long-cycle-lifecycle-contract-evidence-2026-05-22.md)
  Lifecycle contract evidence。
- [05_wave11-long-cycle-scheduler-e2e-evidence-2026-05-22.md](./05_wave11-long-cycle-scheduler-e2e-evidence-2026-05-22.md)
  Contract-only scheduler E2E evidence。
- [06_wave13-long-cycle-scheduler-readiness-2026-05-22.md](./06_wave13-long-cycle-scheduler-readiness-2026-05-22.md)
  Scheduler readiness boundary evidence。
- [07_wave16-long-cycle-durable-repository-readback-2026-05-22.md](./07_wave16-long-cycle-durable-repository-readback-2026-05-22.md)
  Durable repository readback evidence。
- [08_wave18-long-cycle-scheduler-handoff-trace-2026-05-22.md](./08_wave18-long-cycle-scheduler-handoff-trace-2026-05-22.md)
  Scheduler handoff trace evidence。
- [09_wave20-long-cycle-scheduler-queue-handoff-replay-2026-05-22.md](./09_wave20-long-cycle-scheduler-queue-handoff-replay-2026-05-22.md)
  Queue handoff and repository replay evidence。
- [10_wave23-closure-decision-2026-05-23.md](./10_wave23-closure-decision-2026-05-23.md)
  Historical external-blocked decision before live implementation。
- [11_wave55-live-scheduler-closure-2026-05-23.md](./11_wave55-live-scheduler-closure-2026-05-23.md)
  Current canonical SQLAlchemy tenant live closure decision。
- [12_wave55-repo-local-live-scheduler-queue-handoff-closure-2026-05-23.md](./12_wave55-repo-local-live-scheduler-queue-handoff-closure-2026-05-23.md)
  Repo-local scheduler queue / worker / SQLite live replay gate。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_CLOSED` | `ARCHIVE_EXTERNAL_BLOCKED/INDEX.md` 不再将本主题计入 external target |
| Tenant live task table | closed | `long_cycle_live_tasks` migration `20260402_000004` |
| Live scheduler enqueue / worker consumption | closed | `check_ingest_long_cycle_live_scheduler_closure.py` and `check_ingest_long_cycle_scheduler_queue_handoff_replay_contract.py` |
| Live DB write/readback | closed | `live_scheduler_closure.json` fresh-session readback |
| Downstream handoff observation | closed | `downstream_handoffs` in live closure artifact |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_long_cycle_live_scheduler_closure.py --format text --output development/latest-dev-docs/automation-runs/wave55-long-cycle-live-scheduler-closure/2026-05-23/live_scheduler_closure.json
```
