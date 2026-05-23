# Consumer-Side Modularization Index

更新时间：2026-05-23 PST
状态：`external_blocked` / `wave27_checked`。本目录已迁入 `ARCHIVE_EXTERNAL_BLOCKED`；仓内 consumer facade/query、admin/dashboard、policy-state 与 prompt-time-density gates 已封住。目录内早期 `partial` 或 repo-local blocker 文案只保留为历史证据，不再是当前目录主状态。

防误读：当前 canonical decision 以本 `INDEX.md` 与 `08_wave27-external-blocked-decision-2026-05-23.md` 为准。重新进入 `CURRENT_DEV` 前，必须先补齐 live DB/API smoke evidence。

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
  当前 canonical decision：repo-local consumer gates 通过，剩余 live DB/API smoke。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_EXTERNAL_BLOCKED` | `CURRENT_DEV/INDEX.md` 不再将本主题计入 `partial` |
| Repo-local consumer facade/query gates | sealed | `check_wave27_structured_consumer_closure.py` 与 unit pytest |
| Live DB/API smoke | external blocker | `live_db_api_smoke_not_run` |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_wave27_structured_consumer_closure.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave27_structured_consumer_closure_unittest.py
```
