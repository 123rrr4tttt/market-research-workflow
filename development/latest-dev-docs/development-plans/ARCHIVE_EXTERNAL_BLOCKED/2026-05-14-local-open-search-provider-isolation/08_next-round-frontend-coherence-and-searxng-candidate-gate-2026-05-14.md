# Next Round: Frontend Coherence And SearXNG Candidate Gate

更新时间：2026-05-14 PST  
状态：已执行并收口  
范围：承接 `07_deisolation-and-project-coherence-targets-2026-05-14.md` 的执行结果，只推进前端融贯性与 SearXNG 候选来源门禁；不在本轮推进 LanceDB vector / hybrid retrieval。

## 1. 本轮目标

本轮只做两件事：

1. 解除前端阻塞，验证本地 agent / 写作工作台对已接入搜索与材料检索能力的真实调用是否正常。
2. 将 SearXNG 接入外部搜索候选池的 approval gate，而不是进入默认 `provider="auto"`。

## 2. 非目标

本轮不做：

- LanceDB vector / hybrid retrieval。
- 全项目 embedding pipeline。
- 向量对象标准化 schema。
- 将 SearXNG 放入默认 auto provider order。
- 将 search result 自动写入 `source_library`。

LanceDB hybrid retrieval 与数据向量化/标准化的后续工作已经单独定位到：

```text
development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-05-14-global-vectorization-general-foundation/02_local-index-hybrid-retrieval-vectorization-routing-2026-05-14.md
```

## 3. 任务 A：WritingWorkbench 前端融贯性验证

目标：

```text
WritingWorkbench UI
  -> material retrieval request
  -> backend local_index / material retrieval contract
  -> result selection
  -> writing context insert/reference
```

必须验证：

- 写作工作台可以从 UI 触发材料检索。
- 前端请求字段与后端 replay 使用的 contract 一致。
- 返回结果包含并展示/使用 `document_id/chunk_id/source_id/title/content`。
- 用户选择材料后可以插入或引用到写作上下文。
- 不把 `source_library` source config 当成正文材料。

验收产物：

```text
development/latest-dev-docs/automation-runs/frontend-coherence-and-searxng-gate/YYYY-MM-DD/
  writing_workbench_material_search.e2e.txt
  writing_workbench_material_search.summary.json
  writing_workbench_material_insert_or_reference.screenshot.png
  frontend_contract_diff.json
```

如果浏览器/e2e 环境仍不可用，必须输出：

```text
frontend_status: blocked_by_env
blocked_reason: <specific reason>
backend_replay_status: passed | failed
```

## 4. 任务 B：本地 Agent 与写作工作台调用一致性

目标：

```text
AgentChat / local agent
  -> material retrieval tool
  -> same backend retrieval contract as WritingWorkbench
  -> result provenance preserved
```

必须验证：

- agent 与 WritingWorkbench 使用同一套 material retrieval contract。
- 两个入口对同一 `project_id/query/source_id` 的字段语义一致。
- agent 返回的片段仍能映射回原始材料。
- UI 插入/引用动作不破坏 provenance。

验收产物：

```text
agent_writing_material_retrieval.summary.json
agent_vs_workbench_contract_alignment.md
```

## 5. 任务 C：SearXNG Candidate Approval Gate

目标：

```text
source.web.search(provider="searxng")
  -> normalized search results
  -> source candidate review
  -> approval / rejection gate
  -> governed ingest candidate only after approval
```

必须验证：

- `provider="searxng"` 搜索结果可以进入候选来源池。
- URL canonicalization / dedup / trust score 正常运行。
- 每个候选都有明确状态：`pending_approval | approved | rejected`。
- 只有 `approved` 的候选可以进入 governed ingest。
- rejected 候选必须保留原因。
- diagnostics 中保留 provider、query、result_count、error_type。

禁止：

- 让 SearXNG 进入 `provider="auto"` 默认链。
- 绕过 approval gate 自动写入 `source_library`。
- 用搜索 provider 的结果数量替代来源质量判断。

验收产物：

```text
searxng_candidate_approval_gate.json
searxng_candidate_approval_gate.summary.md
source_library_write_boundary_audit.md
```

## 6. 最小门禁

后端：

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest \
  main/backend/tests/unit/test_search_web_provider_adapters_unittest.py \
  main/backend/tests/unit/test_agent_core_unittest.py \
  main/backend/tests/unit/test_source_candidate_trust_unittest.py \
  -q
```

前端：

```bash
cd main/frontend-modern
AGENT_CORE_REAL_BACKEND_E2E=1 VITE_API_PROXY_TARGET=http://127.0.0.1:8001 npm run test:e2e -- writing-workbench
```

补记：当前 `main/frontend-modern/package.json` 没有 `test` script，因此 `npm run test -- --run` 不作为本轮有效门禁；本轮以前端 e2e 覆盖为准。

项目融贯性 replay：

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  ops/search-lab/scripts/deisolation_project_coherence_replay.py \
  --out-dir development/latest-dev-docs/automation-runs/frontend-coherence-and-searxng-gate/YYYY-MM-DD
```

## 7. 完成定义

本轮完成必须同时满足：

- WritingWorkbench 前端 e2e 通过，或阻塞原因具体且后端 replay 仍通过。
- 本地 agent 与 WritingWorkbench 的材料检索 contract 已对齐。
- SearXNG 搜索结果可进入 candidate approval gate。
- approval / rejection 状态可审计。
- `provider="auto"` 仍不包含 SearXNG。
- `source_library` 只接收 approved/governed ingest，不接收裸搜索结果。
- automation run 证据齐全。

## 8. 执行结果

实测产物已落盘：

```text
development/latest-dev-docs/automation-runs/frontend-coherence-and-searxng-gate/2026-05-14/
  README.md
  writing_workbench_material_search.e2e.txt
  writing_workbench_material_search.summary.json
  writing_workbench_material_insert_or_reference.screenshot.png
  frontend_contract_diff.json
  agent_writing_material_retrieval.summary.json
  agent_vs_workbench_contract_alignment.md
  searxng_candidate_approval_gate.json
  searxng_candidate_approval_gate.summary.md
  source_library_write_boundary_audit.md
  coherence_summary.md
```

本轮执行结论：

| 项 | 状态 | 证据 |
|---|---|---|
| WritingWorkbench 前端 e2e | passed | `AGENT_CORE_REAL_BACKEND_E2E=1 ... npm run test:e2e -- writing-workbench`：6 passed |
| 选区材料检索 | passed | 新增 e2e `searches selected material through the writing agent without writing back`，验证 `project.context.bundle` + `writing.document.list`，且未实际调用 `writing.document.insert_paragraph` |
| Agent / WritingWorkbench contract 对齐 | passed | `frontend_contract_diff.json` 无 diff，`agent_vs_workbench_contract_alignment.md` 记录字段与工具链 |
| SearXNG candidate approval gate | passed | `searxng_candidate_approval_gate.json`：14 candidates，1 approved，1 rejected，12 pending_approval |
| source_library 写边界 | clean | `source_library_write_boundary_audit.md`：裸搜索结果未写入 source_library，仅 approved candidate 产生 URL-pool submit |
| `provider="auto"` 默认链 | unchanged | SearXNG 仍只在 explicit experimental providers，不进入 recommended provider order |

本轮代码修正：

- 修正 `agent_chat.py` 的 E2E scripted provider 匹配条件，避免材料检索请求因为系统提示中的 `replace_range` 文本而误触发写回。
- 新增 WritingWorkbench 选区材料检索 e2e。
- 放宽 WritingWorkbench 文档卡片选择等待，降低真实后端数据刷新时的 e2e 抖动。
- 更新 `agent_core_unittest` 中已过时的 compaction / tool-window 断言，使后端门禁覆盖当前实际工具窗口。
