# Typed Knowledge Organization Index

更新时间：2026-05-23 PST
状态：`external_blocked` / `wave27_checked`。本目录已迁入 `ARCHIVE_EXTERNAL_BLOCKED`；仓内 typed-knowledge JSONL durable readback、public API route contract、persisted-card request/response readback 与 overclaim guards 已封住。目录内早期 `partial`、`not_closed` 或 live-boundary 文案只保留为历史证据，不再是当前目录主状态。

防误读：当前 canonical decision 以本 `INDEX.md` 与 `10_wave27-external-blocked-decision-2026-05-23.md` 为准。重新进入 `CURRENT_DEV` 前，必须先补齐 live DB/API/UI、governance UI 与 migration/backfill evidence。

## 文件

- [01_typed-knowledge-organization-plan-2026-03-07.md](./01_typed-knowledge-organization-plan-2026-03-07.md)
  原始 typed knowledge organization 方案。
- [02_atomic-tasklist-typed-knowledge-organization-2026-03-07.md](./02_atomic-tasklist-typed-knowledge-organization-2026-03-07.md)
  原子任务清单。
- [03_wave6-6-status-evidence-and-minimal-plan-2026-05-22.md](./03_wave6-6-status-evidence-and-minimal-plan-2026-05-22.md)
  Wave6 status evidence 与最小计划。
- [03_wave8_6_writing-handoff-contract-evidence-2026-05-22.md](./03_wave8_6_writing-handoff-contract-evidence-2026-05-22.md)
  Writing handoff contract evidence。
- [04_wave10-worker7-writing-context-envelope-evidence-2026-05-22.md](./04_wave10-worker7-writing-context-envelope-evidence-2026-05-22.md)
  Writing context envelope evidence。
- [05_wave12-worker7-persistence-api-boundary-evidence-2026-05-22.md](./05_wave12-worker7-persistence-api-boundary-evidence-2026-05-22.md)
  Persistence API boundary evidence。
- [06_wave15-typed-writing-live-boundary-2026-05-22.md](./06_wave15-typed-writing-live-boundary-2026-05-22.md)
  Typed writing live boundary gate，保留 live gap。
- [07_wave16-typed-knowledge-api-route-contract-2026-05-22.md](./07_wave16-typed-knowledge-api-route-contract-2026-05-22.md)
  API route contract。
- [08_wave17-typed-knowledge-durable-readback-2026-05-22.md](./08_wave17-typed-knowledge-durable-readback-2026-05-22.md)
  Durable repository readback。
- [09_wave19-persisted-card-api-boundary-readback-2026-05-22.md](./09_wave19-persisted-card-api-boundary-readback-2026-05-22.md)
  Persisted-card API boundary readback。
- [10_wave27-external-blocked-decision-2026-05-23.md](./10_wave27-external-blocked-decision-2026-05-23.md)
  当前 canonical decision：repo-local typed-knowledge gates 通过，剩余 live DB/API/UI/governance/migration 条件。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_EXTERNAL_BLOCKED` | `CURRENT_DEV/INDEX.md` 不再将本主题计入 `partial` |
| Repo-local persistence / API / readback gates | sealed | `check_typed_writing_live_boundary.py`、`check_typed_knowledge_durable_repository_readback.py` 与 focused backend pytest |
| Live typed-knowledge DB/API/UI | external blocker | 需要 live DB write/readback、browser UI readback、governance mutation、migration/backfill |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_typed_writing_live_boundary.py --format text
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_typed_knowledge_durable_repository_readback.py
/Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_typed_knowledge_persistence_boundary_unittest.py main/backend/tests/unit/test_writing_keyword_card_service_unittest.py main/backend/tests/unit/test_typed_writing_live_boundary_checker_unittest.py main/backend/tests/integration/test_typed_knowledge_api_route_unittest.py -q
```
