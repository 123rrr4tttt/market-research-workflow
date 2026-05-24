# Source-Library Ingest Minimal Migration Index

更新时间：2026-05-23 PST
状态：`closed` / `wave55_live_replay_closed`。Wave55 C3 已实现并验证 source-library ingest live article-extraction stack replay 与 live external-project replay；本目录已从 `ARCHIVE_EXTERNAL_BLOCKED` 迁入 `ARCHIVE_CLOSED`，不再计入 external-blocked target set。

防误读：Wave27 文件保留的是 live replay 未完成前的 historical external-blocked decision。当前 canonical closure 以 `19_wave55-c3-live-replay-closure-2026-05-23.md`、live replay artifacts 与 AT-EXT checker `remaining_gaps=[]` 为准。

## 文件

- [01_source-library-ingest-minimal-migration-plan-2026-03-25.md](./01_source-library-ingest-minimal-migration-plan-2026-03-25.md)
  原始 source-library ingest minimal migration plan。
- [02_wave0-freeze-and-acceptance-contract-2026-03-26.md](./02_wave0-freeze-and-acceptance-contract-2026-03-26.md)
  Acceptance contract freeze。
- [03_atomic-tasklist-source-library-ingest-minimal-migration-2026-03-26.md](./03_atomic-tasklist-source-library-ingest-minimal-migration-2026-03-26.md)
  原子任务清单。
- [04_parallel-wave-plan-source-library-ingest-minimal-migration-2026-03-26.md](./04_parallel-wave-plan-source-library-ingest-minimal-migration-2026-03-26.md)
  并行 wave plan。
- [05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md](./05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md)
  初始 validation closure。
- [06_atomic-tasklist-item-layering-migration-2026-03-27.md](./06_atomic-tasklist-item-layering-migration-2026-03-27.md)
  Item layering migration tasks。
- [07_validation-closure-item-layering-migration-2026-03-27.md](./07_validation-closure-item-layering-migration-2026-03-27.md)
  Item layering validation closure。
- [08_atomic-tasklist-external-project-powered-item-2026-03-27.md](./08_atomic-tasklist-external-project-powered-item-2026-03-27.md)
  External-project powered item tasklist。
- [09_lane7-minimal-migration-boundary-status-2026-05-22.md](./09_lane7-minimal-migration-boundary-status-2026-05-22.md)
  Boundary status snapshot。
- [10_wave9-9-at-ext-current-contract-evidence-2026-05-22.md](./10_wave9-9-at-ext-current-contract-evidence-2026-05-22.md)
  AT-EXT current contract evidence。
- [11_wave11-source-library-extraction-runner-evidence-2026-05-22.md](./11_wave11-source-library-extraction-runner-evidence-2026-05-22.md)
  Extraction runner evidence。
- [12_wave12-relevance-review-queue-contract-2026-05-22.md](./12_wave12-relevance-review-queue-contract-2026-05-22.md)
  Relevance review queue contract。
- [13_wave16-review-closure-batch-2026-05-22.md](./13_wave16-review-closure-batch-2026-05-22.md)
  Review closure batch 1。
- [14_wave18-review-closure-batch2-2026-05-22.md](./14_wave18-review-closure-batch2-2026-05-22.md)
  Review closure batch 2。
- [15_wave19-review-closure-batch3-2026-05-22.md](./15_wave19-review-closure-batch3-2026-05-22.md)
  Review closure batch 3。
- [16_wave20-review-closure-batch4-2026-05-22.md](./16_wave20-review-closure-batch4-2026-05-22.md)
  Review closure batch 4。
- [17_wave27-source-library-runner-worker-2026-05-22.md](./17_wave27-source-library-runner-worker-2026-05-22.md)
  Runner worker evidence。
- [18_wave27-external-blocked-decision-2026-05-23.md](./18_wave27-external-blocked-decision-2026-05-23.md)
  Historical external-blocked decision before live replay implementation。
- [19_wave55-c3-live-replay-closure-2026-05-23.md](./19_wave55-c3-live-replay-closure-2026-05-23.md)
  Current canonical live replay closure decision。
- [live-replay-artifacts](./live-replay-artifacts/)
  Public-network live replay JSON/log artifacts。
- [references](./references/INDEX.md)
  Historical references and diagrams。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 目录归属 | `ARCHIVE_CLOSED` | `ARCHIVE_EXTERNAL_BLOCKED/INDEX.md` 不再将本主题计入 external target |
| Article extraction stack live replay | closed | `source_library_ingest_live_replay.py` over `https://peps.python.org/pep-0008/` |
| External-project live replay | closed | `source_library_ingest_live_replay.py` over `https://api.github.com/repos/python/cpython` |
| AT-EXT closure gate | closed | `check_source_library_ingest_external_project_contract.py --require-live-replay` reports `remaining_gaps=[]` |
| Focused tests | closed | Source-library ingest live replay and AT-EXT checker unit tests |

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_source_library_ingest_external_project_contract.py --live-replay-artifact docs/development/development-plans/ARCHIVE_CLOSED/2026-03-25-source-library-ingest-minimal-migration/live-replay-artifacts/2026-05-23-wave55-c3-source-library-ingest-live-replay.json --require-live-replay
```
