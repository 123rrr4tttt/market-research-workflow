# De-Isolation And Project Coherence Targets

更新时间：2026-05-14 PST  
状态：已执行并收口；前端浏览器/e2e 仍受当前环境阻塞  
范围：在 SearXNG 外部搜索 benchmark、YaCy local baseline、LanceDB FTS PoC 已完成之后，规定并记录“解除隔离并保证全项目融贯性”的开发任务与实测证据。

## 1. 目标

下一轮不再只做 `ops/search-lab/` 隔离实验。目标是把已经验证的能力接入 MRW 的真实工作流，并证明本地 agent、写作工作台、来源候选审查和本地索引检索之间的调用链一致。

核心目标：

1. `SearXNG` 从 search-lab 实验能力升级为项目外部搜索显式 provider 的可用能力。
2. `LanceDB` 从隔离 PoC 升级为本地索引后端候选的项目内 prototype，但仍不得污染 `source_library` 数据库语义。
3. 本地 agent 可以通过 `source.web.search(provider="searxng")` 正常调用外部搜索。
4. 写作工作台可以从 agent / material retrieval 链路拿到搜索候选或已索引材料。
5. 所有入口必须有端到端实测记录，而不是只靠单元测试或脚本 benchmark。

## 2. 边界

必须保持三层分工：

```text
external discovery
  -> Serper / SearXNG / Google / other web providers

source_library database
  -> specific source registry, source config, governance, approval state

local index backend
  -> fetched document/material/chunk retrieval acceleration
```

禁止：

- 把 `source_library` 改成全文索引库。
- 把 LanceDB / YaCy / Qdrant 直接塞进 `source_library` 数据模型。
- 让 `provider="auto"` 未经验证调用 SearXNG。
- 只做后端函数测试而不验证 agent / writing workbench 的真实调用链。

## 3. 解除隔离范围

### 3.1 SearXNG

从隔离实验迁移到项目可用能力：

- 保留 `ops/search-lab/` 作为本地服务启动与 smoke 目录。
- `source.web.search` 明确支持 `provider="searxng"`。
- 本地 agent 的工具调用路径必须能选择并调用 SearXNG。
- 结果必须进入现有 normalized search result / candidate review 结构。
- 出错时 diagnostics 要能显示：
  - `SEARXNG_BASE_URL`
  - provider 是否显式选择
  - timeout / HTTP / parse error
  - result_count

### 3.2 LanceDB

从隔离 PoC 迁移到项目内 prototype：

- 不直接替换数据库。
- 不修改 `source_library` schema。
- 新增本地索引 adapter/prototype 时必须放在检索层，例如：

```text
main/backend/app/services/local_index/
  schema.py
  adapters/lancedb_adapter.py
  service.py
```

或同等边界清晰的位置。

prototype 只索引 fetched document / writing material / chunk，不索引 source_library 的配置记录本身。

### 3.3 YaCy

YaCy 暂时不升级为主项目索引层。它保留为：

- local search baseline。
- push/search smoke 参考。
- 与 LanceDB/Qdrant 对比的传统搜索参照。

## 4. 必须验证的调用链

### Chain A：本地 agent 外部搜索

目标：

```text
AgentChat / local agent
  -> source.web.search(provider="searxng", query=...)
  -> search_sources(provider="searxng")
  -> SearXNG HTTP API
  -> normalized results
  -> agent answer / candidate list
```

验收：

- 后端 agent tool 层能收到 provider=`searxng`。
- SearXNG 结果至少 10 条。
- agent final answer 或 tool event 中可见 search result summary。
- diagnostics 中不把 SearXNG 误判为默认 auto provider。

### Chain B：候选来源审查

目标：

```text
source.web.search(provider="searxng")
  -> URL normalization
  -> source candidate review / trust gate
  -> user approval or rejection state
```

验收：

- 搜索结果可以转成候选来源。
- URL canonicalization / dedup 生效。
- trust/source candidate 逻辑不因为 provider=`searxng` 缺字段而失败。
- 失败状态能显示具体 provider 和 error_type。

### Chain C：写作工作台材料调用

目标：

```text
WritingWorkbench
  -> material/search panel or agent writing assistant
  -> local indexed material retrieval
  -> selected material inserted / referenced in writing context
```

验收：

- 写作工作台能发起材料检索或通过 agent 触发材料检索。
- 检索结果包含 `document_id/chunk_id/source_id/title/content`。
- 结果能映射回原文或材料记录。
- 不把 source_library source config 当成正文材料。

### Chain D：本地索引 prototype

目标：

```text
document/material storage
  -> chunk extraction
  -> local index adapter
  -> keyword / vector / hybrid query
  -> agent / writing workbench retrieval result
```

验收：

- LanceDB prototype 能以项目内统一 schema upsert chunks。
- 支持 `project_id` 与 `source_id` filter。
- 支持 keyword FTS。
- 下一步支持 vector / hybrid。
- benchmark rows 与 `local-index-backend-evaluation/2026-05-14` schema 保持兼容。

## 5. 端到端实测产物

下一轮必须新增：

```text
development/latest-dev-docs/automation-runs/deisolation-project-coherence/YYYY-MM-DD/
  README.md
  agent_searxng_search.sse.txt
  agent_searxng_search.summary.json
  source_candidate_review_from_searxng.json
  writing_workbench_material_retrieval.json
  local_index_lancedb_project_prototype.jsonl
  coherence_summary.md
```

如果前端无法在当前环境完整启动，也必须输出后端 replay 证据，并明确阻塞：

```text
frontend_status: blocked_by_env | passed
backend_replay_status: passed | failed
```

## 6. 最小测试门禁

后端：

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest \
  main/backend/tests/unit/test_search_web_provider_adapters_unittest.py -q

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest \
  main/backend/tests/unit/test_agent_core_unittest.py -q -k "source_web_search"
```

本地索引 prototype：

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest \
  main/backend/tests/unit/test_local_index_* -q
```

前端 / 工作台：

```bash
cd main/frontend-modern
npm run test -- --run
npm run test:e2e -- writing-workbench
```

若前端测试命令不可用，必须写入 `coherence_summary.md` 的阻塞原因。

## 7. 完成判定

下一轮完成不能只看一个点通过。必须同时满足：

- SearXNG 真实 agent tool 调用通过。
- SearXNG 搜索结果能进入候选来源审查链。
- 写作工作台能正常调用材料检索链，或有明确后端 replay 与前端阻塞证据。
- LanceDB prototype 在项目内边界清晰，不污染 source_library。
- 本地索引结果能按 `project_id/source_id` filter。
- `provider="auto"` 仍不调用 SearXNG。
- automation run 下有完整证据文件。
- 所有新增文档仍在本目录维护索引。

## 8. 执行结果

实测产物已落盘：

```text
development/latest-dev-docs/automation-runs/deisolation-project-coherence/2026-05-14/
  README.md
  agent_searxng_search.sse.txt
  agent_searxng_search.summary.json
  source_candidate_review_from_searxng.json
  writing_workbench_material_retrieval.json
  local_index_lancedb_project_prototype.jsonl
  coherence_summary.md
```

本轮已完成的解除隔离链路：

| 链路 | 状态 | 证据 |
|---|---|---|
| Chain A：本地 agent 调用 SearXNG | passed | `agent_searxng_search.summary.json`：provider=`searxng`，candidate_count=14，accepted_candidate_count=14 |
| Chain B：候选来源审查 | passed | `source_candidate_review_from_searxng.json`：14 个 candidate URLs，0 个 rejected URLs，进入 approval/governed ingest 下一门 |
| Chain C：写作工作台材料调用 | backend replay passed；frontend blocked_by_env | `writing_workbench_material_retrieval.json`：result_count=10，包含 `document_id/chunk_id/source_id/title/content` 边界字段 |
| Chain D：本地索引 prototype | passed | `local_index_lancedb_project_prototype.jsonl`：LanceDB FTS prototype 可按项目材料 chunk 检索 |
| `provider="auto"` 默认链 | unchanged | agent summary 保持 SearXNG 为显式 experimental provider，不进入 recommended provider order |
| `source_library` 边界 | clean | 本地索引只处理 fetched document/material chunks，未修改 `source_library` schema |

本轮代码边界：

- `SearXNG` 已进入真实 agent tool 调用路径，但仍只作为显式 provider 使用。
- `LanceDB` 已进入项目内 `local_index` prototype service/adapters 边界，但没有作为主项目强依赖写入依赖表。
- `YaCy` 保留为 local search baseline，不升级为主项目本地索引层。

剩余阻塞：

- 当前环境未完成浏览器级 WritingWorkbench e2e，因此前端状态记为 `frontend_status: blocked_by_env`。
- LanceDB 目前验证的是 FTS prototype；在正式作为本地索引后端前，还需要补 vector/hybrid 检索与真实写作工作台 UI 触发证据。
- 下一轮前端融贯性与 SearXNG candidate approval gate 已单独写入 `08_next-round-frontend-coherence-and-searxng-candidate-gate-2026-05-14.md`。
- LanceDB vector / hybrid retrieval 不放入下一轮搜索 provider 解隔离任务，已定位到 `../2026-05-14-global-vectorization-general-foundation/02_local-index-hybrid-retrieval-vectorization-routing-2026-05-14.md`，本次不实施。

## 9. 风险

| 风险 | 控制 |
|---|---|
| 解除隔离后污染默认搜索链 | SearXNG 继续显式 provider，auto 链保持不变 |
| source_library 边界再次混淆 | 文档、schema、adapter 命名统一使用 local index / material retrieval |
| 写作工作台只接 UI 不接真实数据 | 必须有 backend replay 或 e2e 证据 |
| LanceDB 依赖污染主项目 | 先 prototype，依赖变更必须单独评估 |
| 搜索结果质量未经人工审查 | 不进入 auto，不进入默认推荐，只做显式可用 |

## 10. 下一轮建议顺序

1. 在前端栈可用时补跑 WritingWorkbench 浏览器/e2e 证据。
2. 将材料检索入口与本地 agent / 写作工作台 UI 的调用参数对齐，避免后端 replay 与前端请求形态分叉。
3. 在候选来源进入 source_library 前补 SearXNG candidate approval / rejection gate 证据。
