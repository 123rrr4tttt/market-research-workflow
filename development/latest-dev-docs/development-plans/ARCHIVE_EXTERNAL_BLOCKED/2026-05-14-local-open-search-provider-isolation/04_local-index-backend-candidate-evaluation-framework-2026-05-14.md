# Local Index Backend Candidate Evaluation Framework

更新时间：2026-05-14 PST  
状态：本地索引加速候选评估框架；SQLite FTS5 baseline 与 LanceDB FTS 首轮实测已完成  
范围：为 MRW 的本地 document/material 检索层选择比 YaCy local 更适合 AI agent 的开源后端。

## 1. 边界修正

本文件采用以下定义：

```text
source_library = 特定来源库，内部是数据库
local index backend = 对已抓取 document/material/chunk 做检索加速的索引层
```

因此，本地索引后端不替代 `source_library`，也不直接决定来源可信度。它只服务于：

- 已抓取正文的全文检索。
- chunk 级 semantic retrieval。
- keyword + vector hybrid search。
- 按项目、来源、文档类型、时间过滤。
- agent 写作、研究、证据回查时的低延迟召回。

## 2. 为什么 YaCy local 只做 baseline

YaCy local 的价值：

- 已验证本地 push 可以被 `resource=local` 命中。
- 可以作为本地全文检索 baseline。
- 能隔离运行，不依赖公网 API key。

YaCy local 的限制：

- 更偏传统搜索引擎 / P2P 搜索架构。
- 对 AI agent 常用的 dense vector、sparse vector、hybrid fusion、metadata filter、reranking hook 支持不如现代检索后端直接。
- 当前官方镜像 push servlet 有参数兼容细节，工程上需要额外包一层。
- 不适合作为长期唯一的 agent retrieval backend。

结论：YaCy local 可以保留为 baseline 和备选，但下一轮必须评估更 agent-native 的开源后端。

2026-05-14 首轮执行补记：

- 已生成 `local-index-backend-evaluation/2026-05-14` 数据集：40 documents、232 chunks、30 queries。
- 已跑 SQLite FTS5 baseline：30 queries 全部 ok，p50 0.15ms。
- 已在 `/tmp/mrw-lancedb-024` 隔离安装 LanceDB 0.24.2 并完成 FTS 实测：30 queries 全部 ok，p50 1.83ms。
- LanceDB vector/hybrid 尚未完成，但不再放入本目录下一轮搜索 provider 解隔离任务；已定位到 `../2026-05-14-global-vectorization-general-foundation/02_local-index-hybrid-retrieval-vectorization-routing-2026-05-14.md`。

## 3. 候选短名单

| 候选 | 初始定位 | 是否进入第一轮实测 |
|---|---|---|
| LanceDB | 本地轻量、表格式 document/chunk 存储、full-text + vector + SQL filter | 是 |
| Qdrant | AI-native vector search、dense/sparse/hybrid retrieval、适合 RAG/agent | 是 |
| Meilisearch | 工程简单的全文搜索 + AI/hybrid search | 是 |
| Typesense | 快速文档搜索、vector/hybrid 能力、部署相对轻 | 是 |
| Weaviate | 完整向量数据库、BM25F hybrid、RAG 模块 | 备选实测 |
| YaCy local | 传统 local search baseline | 是 |
| OpenSearch | 大规模 neural sparse / hybrid search | 暂缓 |
| Vespa | 大规模 ranking / hybrid retrieval 平台 | 暂缓 |

## 4. 评估维度

### 4.1 数据模型适配

候选必须能表达以下最小 schema：

```json
{
  "chunk_id": "doc_001_chunk_003",
  "document_id": "doc_001",
  "project_id": "robotics-policy-study",
  "source_id": "source_policy_site_001",
  "source_type": "web|pdf|rss|manual",
  "title": "Document title",
  "url": "https://example.com/report",
  "content": "chunk text",
  "language": "en",
  "created_at": "2026-05-14T00:00:00Z",
  "metadata": {}
}
```

硬要求：

- 支持 `project_id` filter。
- 支持 `source_id` filter。
- 支持 document/chunk 双层 id。
- 支持增量 upsert。
- 支持 delete by document/source/project。

### 4.2 检索模式

每个候选至少跑三种查询：

```text
keyword: exact term / entity / policy name
semantic: natural language question
hybrid: keyword constraints + semantic intent
```

必须记录：

- top_k
- score
- matched fields
- latency_ms
- filter expression
- result chunk id
- parent document id

### 4.3 Agent 适配度

AI agent 不是只要 top 10 结果，而是需要可控检索循环。因此候选要评估：

- 是否支持小工具式 HTTP/Python 调用。
- 是否支持按 metadata 收窄检索。
- 是否支持多阶段检索：keyword recall -> vector recall -> rerank。
- 是否容易返回解释字段，帮助 agent 判断为什么命中。
- 是否容易做 streaming / pagination / cursor。
- 是否容易把检索结果映射回原文和证据位置。

## 5. 实测流程

### Step 1：准备统一测试集

从 MRW 当前已有 document/material 里抽取一批材料：

```text
dataset/
  documents.jsonl
  chunks.jsonl
  queries.jsonl
  judgments.jsonl
```

`queries.jsonl` 示例：

```json
{"query_id":"q001","query":"robotics policy national commission","type":"keyword","project_id":"robotics-policy-study"}
{"query_id":"q002","query":"which documents discuss embodied AI industrial policy?","type":"semantic","project_id":"robotics-policy-study"}
{"query_id":"q003","query":"具身智能 政策 标准","type":"hybrid","project_id":"robotics-policy-study"}
```

### Step 2：为每个候选建立索引

每个候选必须使用同一批 chunk 和 metadata。

输出：

```text
candidate_index_report.json
```

字段：

- candidate
- document_count
- chunk_count
- index_size_mb
- build_time_ms
- upsert_time_ms
- delete_test_ok

### Step 3：运行查询 benchmark

输出：

```text
benchmark_results.jsonl
```

字段：

- candidate
- query_id
- query
- query_type
- filter_used
- ok
- top_k
- latency_ms
- hit_document_ids
- score_summary
- error_type

### Step 4：人工抽查相关性

至少抽查每个候选 30 条 top results，记录：

- relevant
- partially_relevant
- irrelevant
- wrong_project
- duplicate_chunk
- missing_source_metadata

### Step 5：产出推荐

推荐文档必须明确：

- 第一选择。
- 第二选择。
- 不建议选择的候选及原因。
- 是否继续保留 YaCy local。
- 如何与 `source_library` 数据库边界连接。

## 6. 初始推荐假设

在实测前，先按官方能力和 MRW 需求建立以下假设：

### 6.1 LanceDB

适合：

- 本地轻量部署。
- document/chunk 与 metadata 放在同一表式结构里。
- agent 工具直接用 Python 调用。
- full-text + vector + SQL filter 的本地检索。

风险：

- 多用户/大规模服务化能力需要后续验证。
- hybrid ranking 质量要靠测试集实测。

### 6.2 Qdrant

适合：

- AI-native retrieval。
- dense + sparse hybrid。
- metadata filter。
- RAG / agent 标准化检索后端。

风险：

- 需要额外 embedding / sparse model 管线。
- 原文存储和数据库事务仍要由 MRW 自己管理。

### 6.3 Meilisearch

适合：

- 快速全文搜索。
- 工程接入简单。
- 有 hybrid / AI-powered search 路线。

风险：

- 对复杂 agent retrieval loop 的可控性可能不如 LanceDB/Qdrant。
- 向量和 embedder 配置需要实测稳定性。

### 6.4 Typesense

适合：

- 快速文档搜索。
- keyword + vector hybrid。
- 产品化搜索体验。

风险：

- 对复杂 RAG/agent 的多阶段检索能力需要二次封装。

### 6.5 Weaviate

适合：

- 完整向量数据库。
- BM25F + vector hybrid。
- 长期知识库服务。

风险：

- 部署与运行比 LanceDB/Qdrant 更重。
- 当前阶段可能超出“本地索引加速”最小需求。

## 7. 第一轮推荐排序

第一轮实测优先级：

```text
1. LanceDB
2. Qdrant
3. Meilisearch
4. Typesense
5. YaCy local baseline
6. Weaviate optional
```

暂缓：

```text
OpenSearch
Vespa
```

原因：OpenSearch / Vespa 很强，但部署、schema、ranking profile 和运维复杂度更高；当前目标是找到适合 MRW 本地 agent 管线的轻量索引加速层。

## 8. 通过标准

候选进入下一阶段必须满足：

- 单机本地可启动。
- 能索引同一批 MRW chunks。
- 支持 `project_id` 和 `source_id` filter。
- 支持 keyword 或 full-text。
- 至少支持 vector 或 hybrid 检索。
- 30 条查询 benchmark 可跑完。
- p50 latency 不超过 300ms，本地小数据集 p95 不超过 1500ms。
- top 10 人工相关性明显优于 YaCy local baseline，或在工程复杂度上明显更低。

## 9. 官方文档依据

- Qdrant Hybrid Queries: https://qdrant.tech/documentation/concepts/hybrid-queries/
- Qdrant Search: https://qdrant.tech/documentation/search/
- LanceDB Full-Text Search: https://docs.lancedb.com/search/full-text-search
- LanceDB Hybrid Search: https://lancedb.github.io/lancedb/hybrid_search/hybrid_search/
- Meilisearch Hybrid Search: https://www.meilisearch.com/docs/learn/ai_powered_search/difference_full_text_ai_search
- Typesense Vector / Hybrid Search: https://typesense.org/docs/28.0/api/vector-search.html
- Weaviate Hybrid Search: https://weaviate.io/developers/weaviate/search/hybrid
- OpenSearch Neural Sparse Search: https://docs.opensearch.org/latest/vector-search/ai-search/neural-sparse-search/
- Vespa Nearest Neighbor / Hybrid Retrieval: https://docs.vespa.ai/en/querying/nearest-neighbor-search.html
