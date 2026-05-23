# Consumer-Side Modularization Index

更新时间：2026-05-23 PST
状态：`closed` / `wave45_live_api_checked`。本目录已迁入 canonical `ARCHIVE_CLOSED`；仓内 consumer facade/query、admin/dashboard、policy-state 与 prompt-time-density gates 已封住，Wave45 已补齐 live DB/API smoke。目录内早期 `partial`、`external_blocked` 或 repo-local blocker 文案只保留为历史证据，不再是当前目录主状态。

防误读：当前 canonical decision 以本 `INDEX.md` 与 `09_wave45-manual-live-api-closure-2026-05-23.md` 为准。`08_wave27-external-blocked-decision-2026-05-23.md` 只保留为 Wave27 历史快照。

## 文件

- [README.md](./README.md)
  历史目录入口，保留文档列表与主题说明。
- [01_consumer-side-modularization-assessment-and-plan-2026-03-14.md](./01_consumer-side-modularization-assessment-and-plan-2026-03-14.md)
  原始 consumer-side modularization 评估与计划。
- [02_wave9-5-consumer-facade-boundary-contract-2026-05-22.md](./02_wave9-5-consumer-facade-boundary-contract-2026-05-22.md)
  Consumer facade boundary contract。
- [03_wave11-consumer-query-extraction-evidence-2026-05-22.md](./03_wave11-consumer-query-extraction-evidence-2026-05-22.md)
  Consumer query extraction evidence。
- [04_wave13-admin-dashboard-consumer-extraction-evidence-2026-05-22.md](./04_wave13-admin-dashboard-consumer-extraction-evidence-2026-05-22.md)
  Admin dashboard consumer extraction evidence。
- [05_wave15-consumer-sql-predicate-facade-2026-05-22.md](./05_wave15-consumer-sql-predicate-facade-2026-05-22.md)
  Consumer SQL predicate facade。
- [06_wave17-policy-state-consumer-query-boundary-2026-05-22.md](./06_wave17-policy-state-consumer-query-boundary-2026-05-22.md)
  Policy-state consumer query boundary。
- [07_wave20-prompt-time-density-consumer-facade-2026-05-22.md](./07_wave20-prompt-time-density-consumer-facade-2026-05-22.md)
  Prompt-time-density consumer facade。
- [08_wave27-external-blocked-decision-2026-05-23.md](./08_wave27-external-blocked-decision-2026-05-23.md)
  Wave27 historical decision：repo-local consumer gates 通过，剩余 live DB/API smoke。
- [09_wave45-manual-live-api-closure-2026-05-23.md](./09_wave45-manual-live-api-closure-2026-05-23.md)
  当前 canonical closure：live DB/API smoke 已通过，目录 closed。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_CLOSED` | `docs/development/development-plans/ARCHIVE_CLOSED/INDEX.md` |
| Repo-local consumer facade/query gates | sealed | `check_wave27_structured_consumer_closure.py` 与 unit pytest |
| Live DB/API smoke | sealed | Wave45 live evidence pack 与 closure gate |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_wave27_structured_consumer_closure.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_wave27_structured_consumer_closure.py --live-evidence-json development/latest-dev-docs/automation-runs/wave45-manual-structured-consumer-live-api-closure/2026-05-23/live_evidence.json
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave27_structured_consumer_closure_unittest.py
```
