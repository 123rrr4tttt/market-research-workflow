# Data Structured Service Modularization Index

更新时间：2026-05-23 PST
状态：`closed` / `wave45_live_api_checked`。本目录已迁入 canonical `ARCHIVE_CLOSED`；仓内 `document_queries.v1`、structured endpoint projection、SQL helper、generic `DocumentQuery -> SQLAlchemy statement` builder 均已封住，Wave45 已补齐 live DB/API smoke。目录内早期 `partial` 或 `external_blocked` 文案只保留为历史证据，不再是当前目录主状态。

防误读：当前 canonical decision 以本 `INDEX.md` 与 `15_wave45-manual-live-api-closure-2026-05-23.md` 为准。`12_wave27` 与 `14_wave28` 只保留为历史 closure progression 证据。

## 文件

- [README.md](./README.md)
  历史目录入口，保留文档列表与主题说明。
- [14_wave28-structured-document-query-statement-builder-2026-05-23.md](./14_wave28-structured-document-query-statement-builder-2026-05-23.md)
  Wave28 repo-local statement-builder closure。
- [15_wave45-manual-live-api-closure-2026-05-23.md](./15_wave45-manual-live-api-closure-2026-05-23.md)
  当前 canonical closure：live DB/API smoke 已通过，目录 closed。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_CLOSED` | `docs/development/development-plans/ARCHIVE_CLOSED/INDEX.md` |
| Repo-local structured gates | sealed | `check_wave27_structured_consumer_closure.py` 与 unit pytest |
| Live DB/API smoke | sealed | Wave45 live evidence pack 与 closure gate |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_wave27_structured_consumer_closure.py --live-evidence-json development/latest-dev-docs/automation-runs/wave45-manual-structured-consumer-live-api-closure/2026-05-23/live_evidence.json
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave27_structured_consumer_closure_unittest.py
```
