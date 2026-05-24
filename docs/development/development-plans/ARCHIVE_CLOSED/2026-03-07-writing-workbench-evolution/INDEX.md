# Writing Workbench Evolution Index

更新时间：2026-05-23 PST
状态：`closed` / `wave54_live_implemented`。本目录已迁入 `ARCHIVE_CLOSED`；Writing Workbench 已接入 live typed-knowledge context fetch、persisted card readback 与治理 mutation control。目录内早期 `external_blocked`、`partial` 或 live-boundary 文案只保留为历史证据，不再是当前目录主状态。

防误读：当前 canonical decision 以本 `INDEX.md` 与 `08_wave54-typed-writing-live-closure-2026-05-23.md` 为准。Wave27 external blocker 已由本轮实现关闭。

## 文件

- [01_writing-workbench-evolution-plan-2026-03-07.md](./01_writing-workbench-evolution-plan-2026-03-07.md)
  原始 Writing Workbench evolution 方案。
- [02_atomic-tasklist-writing-workbench-evolution-2026-03-07.md](./02_atomic-tasklist-writing-workbench-evolution-2026-03-07.md)
  原子任务清单。
- [03_wave6_7_status-evidence-and-minimum-plan-2026-05-22.md](./03_wave6_7_status-evidence-and-minimum-plan-2026-05-22.md)
  Wave6 status evidence 与最小计划。
- [04_wave8_6_typed-knowledge-card-contract-evidence-2026-05-22.md](./04_wave8_6_typed-knowledge-card-contract-evidence-2026-05-22.md)
  Typed-knowledge card contract evidence。
- [05_wave10-worker7-typed-knowledge-context-consumer-evidence-2026-05-22.md](./05_wave10-worker7-typed-knowledge-context-consumer-evidence-2026-05-22.md)
  Typed-knowledge context consumer evidence。
- [06_wave12-worker7-typed-knowledge-persistence-boundary-evidence-2026-05-22.md](./06_wave12-worker7-typed-knowledge-persistence-boundary-evidence-2026-05-22.md)
  Persistence boundary evidence。
- [07_wave15-typed-writing-live-boundary-2026-05-22.md](./07_wave15-typed-writing-live-boundary-2026-05-22.md)
  Typed writing live boundary gate，保留 live gap。
- [08_wave16-worker5-typed-knowledge-fetch-readback-2026-05-22.md](./08_wave16-worker5-typed-knowledge-fetch-readback-2026-05-22.md)
  Typed-knowledge fetch readback。
- [09_wave17-worker6-persisted-typed-card-ui-readback-2026-05-22.md](./09_wave17-worker6-persisted-typed-card-ui-readback-2026-05-22.md)
  Persisted typed-card UI readback。
- [10_wave19-persisted-card-ui-api-boundary-readback-2026-05-22.md](./10_wave19-persisted-card-ui-api-boundary-readback-2026-05-22.md)
  Persisted-card UI/API boundary readback。
- [11_wave27-external-blocked-decision-2026-05-23.md](./11_wave27-external-blocked-decision-2026-05-23.md)
  历史 canonical decision：repo-local Writing Workbench gates 通过，当时剩余 live DB/API/UI/governance/migration 条件。
- [08_wave54-typed-writing-live-closure-2026-05-23.md](./08_wave54-typed-writing-live-closure-2026-05-23.md)
  当前 canonical closure：live context fetch、governance mutation 与 persisted-card live readback 已实现并验证。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_CLOSED` | `CURRENT_DEV/INDEX.md` 不再将本主题计入 `partial` 或 `external_blocked` |
| Repo-local typed-card / keyword-card / preview gates | sealed | `check_typed_writing_live_boundary.py`、focused backend pytest、frontend Playwright e2e |
| Live persisted UI/API/DB | closed | `getTypedKnowledgeWritingContext`、`updateTypedKnowledgeReviewState`、`writing-typed-knowledge-governance`、live persisted-card request/readback |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_typed_writing_live_boundary.py --format text
cd main/backend && /Users/wangyiliang/.local/bin/python3.11 -m alembic upgrade head
/Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_writing_keyword_card_service_unittest.py main/backend/tests/unit/test_typed_writing_live_boundary_checker_unittest.py main/backend/tests/integration/test_typed_knowledge_api_route_unittest.py -q
cd main/frontend-modern && ./node_modules/.bin/playwright test tests/e2e/writing-workbench.spec.ts tests/e2e/agent-chat-writing-crossflow.spec.ts --project=chromium
```
