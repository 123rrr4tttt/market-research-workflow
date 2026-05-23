# 2026-03-12 Data Structured Service Modularization

## 文档列表

1. [01_terminal-structured-ingest-output-standardization-plan-2026-03-12.md](./01_terminal-structured-ingest-output-standardization-plan-2026-03-12.md)
2. [02_source-library-terminal-output-unification-and-boundary-2026-03-12.md](./02_source-library-terminal-output-unification-and-boundary-2026-03-12.md)
3. [03_discrete-retained-modules-and-preprocess-frontdoor-plan-2026-03-12.md](./03_discrete-retained-modules-and-preprocess-frontdoor-plan-2026-03-12.md)
4. [05_runtime-validation-source-library-write-through-and-structured-path-2026-03-14.md](./05_runtime-validation-source-library-write-through-and-structured-path-2026-03-14.md)
5. [06_atomic-tasklist-quality-frontdoor-source-library-first-2026-03-14.md](./06_atomic-tasklist-quality-frontdoor-source-library-first-2026-03-14.md)
6. [07_wave9-worker4-document-queries-contract-2026-05-22.md](./07_wave9-worker4-document-queries-contract-2026-05-22.md)
7. [08_wave11-structured-consumer-query-extraction-evidence-2026-05-22.md](./08_wave11-structured-consumer-query-extraction-evidence-2026-05-22.md)
8. [09_wave13-structured-search-endpoint-contract-2026-05-22.md](./09_wave13-structured-search-endpoint-contract-2026-05-22.md)
9. [10_wave17-policy-state-query-boundary-2026-05-22.md](./10_wave17-policy-state-query-boundary-2026-05-22.md)
10. [11_wave20-document-query-endpoint-slice-2026-05-22.md](./11_wave20-document-query-endpoint-slice-2026-05-22.md)
11. [12_wave27-structured-consumer-closure-decision-2026-05-23.md](./12_wave27-structured-consumer-closure-decision-2026-05-23.md)
12. [13_wave28-structured-reviewer-evidence-2026-05-23.md](./13_wave28-structured-reviewer-evidence-2026-05-23.md)
13. [14_wave28-structured-document-query-statement-builder-2026-05-23.md](./14_wave28-structured-document-query-statement-builder-2026-05-23.md)

## 使用顺序

1. 先读 `02`：明确来源库末端边界与统一输出格式。
2. 再读 `03`：按离散模块与后处理前门计划推进实施。
3. 再读 `05`：看当前过渡期实测状态，确认 clean boundary 与兼容 write-through 并存。
4. 再读 `06`：按“统一质检前门、来源库先行”的原子任务清单推进。
5. 再读 `07`：确认 Wave9 worker 4 已落地的 `document_queries.v1` 消费侧查询契约。
6. `01` 作为扩展背景与细化参考。

## 2026-03-14 状态补充

- `02` 所定义的来源库 clean terminal output 已进入代码主链。
- 对外契约主语义已切换到 `results.records/results.stats/errors/meta/raw_snapshot`。
- `legacy_result` 仍保留兼容，但不再代表来源库正式边界。
- 2026-03-14 实测确认：部分来源项仍可继续下沉到 `single_url` 写入链，且新增文档已产出 `terminal.ingest.v1.1` 结构化结果。
- 2026-03-14 架构修正：`single_url` 仅视为历史遗留实现；统一标准化质检应前移为前门层能力，并优先在来源库采集链落地。
- 2026-03-14 已补充来源库优先的统一质检前门原子任务清单，作为下一阶段实施主入口。
- 2026-05-22 Wave9 worker 4 已补齐 `document_queries.v1` 最小契约层：稳定 query/filter/sort/result envelope，并保留 writing keyword-card 与 `document_views` 旧消费 row 兼容。
- 2026-05-22 Wave17 worker 8 已将 `/policies/state/{state}` 的状态 predicate 与时间表达式收口到 `document_queries.policy_filters`，作为非 admin/dashboard query boundary 的增量迁移证据。
- 2026-05-22 Wave20 worker 6 已将 `project.structured_data.search` 成功响应增加 `document_queries.v1` 投影，作为低风险 query-service endpoint slice；更多 endpoint 与 DB statement builder 仍保留为后续边界。
- 2026-05-23 Wave27 已补组合 endpoint/consumer closure gate：endpoint/query/facade gates 均通过；paired consumer topic 迁入 `ARCHIVE_EXTERNAL_BLOCKED`，本目录因 generic `DocumentQuery -> SQLAlchemy statement` builder 仍未导出而保留 `CURRENT_DEV`。
- 2026-05-23 Wave28 structured worker A 已导出 generic `DocumentQuery -> SQLAlchemy statement` builder，并更新 closure checker；本目录 repo-local blocker 归零，只剩 `live_db_api_smoke_not_run` 外部运行时验证。
- 2026-05-23 Wave28 reviewer 复核当前 `document_queries` 服务、checker 与 `CURRENT_DEV` evidence：当前可执行封口范围原本只剩 generic `DocumentQuery -> SQLAlchemy statement` builder；本轮 builder 变更合并后 focused gates 显示 repo-local blocker 清零，目录已迁入 `ARCHIVE_EXTERNAL_BLOCKED` 而非 `ARCHIVE_CLOSED`。
