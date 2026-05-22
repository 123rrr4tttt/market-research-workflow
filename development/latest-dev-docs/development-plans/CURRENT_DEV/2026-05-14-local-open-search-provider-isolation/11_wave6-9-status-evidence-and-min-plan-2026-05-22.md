# Wave6-9 Status Evidence And Minimum Plan

日期：2026-05-22 PST
状态：topic-local status evidence；共享总索引待集成更新

## 1. no_closure_claim / 需更新检查

`development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md` 仍把本目录列为：

```text
[no_closure_claim][planned_ready] 2026-05-14 SearXNG / YaCy Isolated Deployment And Search Provider Integration Plan
```

该共享索引状态已落后于本目录内证据，但本轮按 Wave6-9 约束不编辑共享总索引。当前 topic-local 判定如下：

| 范围 | 判定 | 证据 |
|---|---|---|
| 隔离部署与 smoke | 已有完成证据 | `01_...integration-plan...md`、`02_...checklist...md`、`automation-runs/search-provider-lab/2026-05-14/` |
| 显式 provider adapter | 已有完成证据 | `main/backend/app/services/search/web.py` 已支持 `provider="searxng"` / `provider="yacy"`；`provider="auto"` 不进入本地开源 provider |
| provider trace contract | 已有完成证据 | `10_search-provider-trace-contract-closure-replay-2026-05-22.md`、`automation-runs/search-provider-trace-artifacts/2026-05-22/` |
| 真实容器 replay | 已有完成证据 | `automation-runs/search-provider-container-replay/2026-05-22/`：2 rows / 2 passed，trace_failure_count=0 |
| agent provider 暴露与诊断 | 本轮补最小护栏测试 | `test_source_web_search_diagnostics_keep_local_open_search_explicit_only` 固定 SearXNG / YaCy 仅为显式实验 provider，不进入 recommended auto order |

结论：本目录不再是单纯 `planned_ready` / `no_closure_claim` 状态；更准确的 topic-local 状态是 `implementation_evidence_present / shared_index_stale`。是否从 CURRENT_DEV 移动到 archive 不在本轮范围内，且需要最终集成 lane 同步共享索引后再做。

## 2. 最小开发计划

本轮只落三项确定工作：

1. 新增本状态证据文件，记录共享索引滞后原因与本目录证据矩阵。
2. 增加 agent 层配置护栏单测，防止 SearXNG / YaCy 被误纳入推荐 auto provider 顺序。
3. 复跑 adapter trace contract、agent core 相关单测和 markdown link 检查。

本轮不做：

- 不把 `searxng` / `yacy` 加入 `provider="auto"`。
- 不编辑 `development/latest-dev-docs/README.md`、`MERGED_OVERVIEW.md`、`development-plans/INDEX.md` 或 `CURRENT_DEV/INDEX.md`。
- 不启动或保留长期运行的 SearXNG / YaCy 容器；真实容器 replay 证据复用 `automation-runs/search-provider-container-replay/2026-05-22/`。
- 不推进 LanceDB vector / hybrid retrieval；该后续线已转到 global vectorization / local index runtime 相关目录。

## 3. 本轮新增护栏

新增单测：

```text
main/backend/tests/unit/test_agent_core_unittest.py::AgentCoreUnitTest::test_source_web_search_diagnostics_keep_local_open_search_explicit_only
```

护栏断言：

- `explicit_experimental_providers == ["searxng", "yacy"]`。
- `recommended_provider_order == ["serper", "google", "serpstack", "serpapi", "ddg"]`。
- `searxng` / `yacy` 不出现在 recommended auto order 中。
- SearXNG / YaCy base URL 只作为显式 provider readiness 信息暴露。

## 4. 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_search_web_provider_adapters_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_agent_core_unittest.py -k 'source_web_search'
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/search_provider_trace_contract.py --out development/latest-dev-docs/automation-runs/search-provider-trace-artifacts/2026-05-22/search_provider_trace_contract.json
git diff --check
```

结果：

- adapter provider 单测：5 passed。
- agent core `source_web_search` 单测：5 passed，70 deselected。
- offline trace artifact 复跑：`ok=true`，`contract_version=search-provider-trace-artifacts.v1`。
- `git diff --check`：通过。
- topic-local Markdown path-existence check：12 个 Markdown 文件通过。

本工作树没有 `main/backend/.venv311/bin/python` 和 `development/latest-dev-docs/scripts/check_markdown_links.py`，因此验证使用 `/Users/wangyiliang/.local/bin/python3.11` 和等价的 topic-local Python 相对链接检查。
