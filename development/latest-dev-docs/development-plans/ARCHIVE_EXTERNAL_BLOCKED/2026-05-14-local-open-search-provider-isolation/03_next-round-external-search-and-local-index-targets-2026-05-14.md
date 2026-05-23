# Next Round Targets: External Search Pipeline And Local Index Backend

更新时间：2026-05-14 PST  
状态：下一轮目标规定稿  
范围：在已完成 SearXNG / YaCy 隔离验证之后，规定下一轮工程目标、边界、产物和验收。

## 1. 总目标

下一轮只处理两条线：

1. 将 `SearXNG` 接入 MRW 的外部搜索管线，作为显式公网搜索 provider。
2. 调研并实测更适合 AI agent 的本地索引加速后端，重新评估 YaCy local、LanceDB、Qdrant、Meilisearch 等候选。

两条线必须保持边界清晰：

```text
SearXNG = external web discovery provider
source_library = specific source registry / source config database
local index backend = fetched document / material full-text and hybrid retrieval layer
```

禁止把 `source_library` 说成全文材料库。`source_library` 是特定来源库，内部是数据库；本地索引后端只能作为其下游检索加速层或 document/material storage 的检索层。

## 2. 目标 A：SearXNG 接入外部搜索管线

### 2.1 定位

`SearXNG` 只承担外部公网发现，不承担本地数据库索引，不替代 `source_library`。

推荐管线：

```text
agent / research task
  -> external search tool
  -> provider=serper | searxng | google | ...
  -> candidate URL normalization
  -> source candidate review
  -> ingest / fetch / document processing
```

### 2.2 工程要求

- `searxng` 必须是显式 provider。
- `provider="auto"` 默认链继续保持 `serper -> google -> serpstack -> serpapi -> ddg`，不自动调用 SearXNG。
- 支持扩量检索：`max_results=30/50` 时通过官方 `/search` API 的 `pageno` 翻页。
- 默认 `SEARXNG_MAX_PAGES=5`，硬上限 10 页。
- 对每一条结果保留：
  - `title`
  - `link`
  - `snippet`
  - `source="searxng"`
  - `rank`
  - `raw.engine`
  - `raw.engines`
  - `raw.category`
  - `raw.pageno`
- 复用现有 URL canonicalization 与 dedup，不在 adapter 内另写去重规则。
- 失败必须返回可诊断错误，不允许把 search tool 挂死。

### 2.3 Benchmark 要求

新增一组外部搜索 benchmark，输入 20-50 个真实研究关键词，至少覆盖：

- 技术产业关键词，例如 `embodied ai supply chain`
- 政策关键词，例如 `robotics policy`
- 公司/市场关键词，例如 `humanoid robot market size`
- 学术/论文关键词，例如 `robot foundation model survey`
- 中文关键词，例如 `具身智能 政策`

输出路径：

```text
development/latest-dev-docs/automation-runs/search-provider-benchmark/YYYY-MM-DD/
```

每行 JSONL 至少包含：

```json
{
  "provider": "searxng",
  "keyword": "robotics policy",
  "ok": true,
  "requested_limit": 50,
  "result_count": 43,
  "unique_domain_count": 31,
  "usable_url_count": 40,
  "duplicate_url_count": 3,
  "latency_ms": 8123.4,
  "error_type": null,
  "results": []
}
```

### 2.4 质量指标

下一轮不只看“有没有结果”，还要看搜索效能：

| 指标 | 说明 | 最低可接受 |
|---|---|---|
| `result_count` | 单关键词实际返回数量 | 30 条目标下不少于 20 条 |
| `usable_url_count` | 有 title/link 且 URL 可解析的结果数 | 不低于返回数 85% |
| `unique_domain_count` | 域名多样性 | 30 条结果不少于 10 个域名 |
| `duplicate_url_count` | 去重前重复 URL 数 | 不超过返回数 20% |
| `latency_p50` | 中位延迟 | 10 秒以内 |
| `latency_p95` | 高位延迟 | 20 秒以内 |
| `precision@10` | 人工抽查前 10 条相关性 | 不低于 0.6 |
| `empty_rate` | 空结果率 | 不高于 15% |

### 2.5 验收

完成条件：

- SearXNG 显式 provider 能在外部搜索工具链中稳定调用。
- `max_results=30/50` 真实请求可跑通并落盘。
- benchmark summary 明确：是否建议继续只做显式 provider，是否可以进入受控 fallback。
- 不修改 `source_library` 数据库语义。
- 不把 SearXNG 放入默认 `auto` 链。

## 3. 目标 B：本地索引加速后端选型

### 3.1 定位

本地索引后端只处理“抓回来之后怎么搜”，不处理“来源从哪里来”。

正确边界：

```text
source_library database
  -> 管来源、来源配置、启停状态、可信度、抓取策略

ingest / crawler
  -> 抓取正文、PDF、网页快照、metadata

document / material storage
  -> 存正文、chunk、文件、证据、版本

local index backend
  -> 对 document/material 做全文、向量、hybrid、metadata filter 检索
```

### 3.2 候选范围

下一轮先比较以下候选：

- YaCy local
- LanceDB
- Qdrant
- Meilisearch
- Typesense
- Weaviate

OpenSearch 与 Vespa 只作为后期规模化候选，不作为第一批本地轻量实验优先项。

### 3.3 实测数据集

必须用同一批 MRW 真实材料做评估，不只看 demo：

- 20-100 篇已抓取网页正文或 Markdown 材料。
- 至少包含 title、url、source_id、project_id、content、created_at。
- 每篇材料切 chunk，保留 parent document id。
- 查询集至少 30 条，包含：
  - 精确实体名
  - 术语组合
  - 语义改写问题
  - 中文查询
  - 需要 metadata filter 的查询

### 3.4 检索能力矩阵

每个候选都要回答：

| 能力 | 必测问题 |
|---|---|
| Full-text | 是否有 BM25 / FTS / keyword ranking |
| Vector | 是否原生支持 dense vector |
| Hybrid | 是否能融合 keyword + vector |
| Metadata filter | 是否能按 `project_id/source_id/document_type/date` 过滤 |
| Incremental update | 新文档/更新/删除是否方便 |
| Local deployment | 是否适合本机和 Docker 隔离部署 |
| Agent ergonomics | Python/HTTP API 是否便于工具调用 |
| Explainability | 能否解释命中原因或返回 score 组成 |
| Reranking hook | 是否容易接 reranker |
| Ops cost | 依赖、资源、维护复杂度 |

### 3.5 推荐判断口径

初始判断：

- `LanceDB`：优先作为本地轻量 agent retrieval 实验候选，适合嵌入式、本地文件/材料索引、SQL filter、hybrid search。
- `Qdrant`：优先作为 AI-native dense+sparse hybrid retrieval 候选，适合标准 RAG / agent retrieval backend。
- `Meilisearch`：适合作为更现代的全文搜索 + hybrid search 候选，工程简单，但 agent 检索组合能力需要实测。
- `Typesense`：适合快速全文/向量/hybrid 文档搜索，适合轻量产品化搜索。
- `Weaviate`：功能完整，适合长期知识库和 RAG，但比 LanceDB/Qdrant 更重。
- `YaCy local`：可作为 baseline；优点是本地 push/search 已跑通，缺点是 AI agent 友好的 hybrid / metadata / reranking 能力不如现代向量检索后端。

## 4. 下一轮文档产物

下一轮必须新增以下产物：

```text
development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-05-14-local-open-search-provider-isolation/
  05_searxng-external-search-pipeline-implementation-plan-YYYY-MM-DD.md
  06_local-index-agent-backend-evaluation-plan-YYYY-MM-DD.md

development/latest-dev-docs/automation-runs/search-provider-benchmark/YYYY-MM-DD/
  README.md
  searxng_benchmark.jsonl
  searxng_benchmark_summary.md

development/latest-dev-docs/automation-runs/local-index-backend-evaluation/YYYY-MM-DD/
  README.md
  dataset_manifest.json
  candidate_matrix.md
  benchmark_results.jsonl
  recommendation.md
```

## 5. 官方文档依据

- SearXNG Search API: https://docs.searxng.org/dev/search_api
- Qdrant Hybrid Queries: https://qdrant.tech/documentation/concepts/hybrid-queries/
- Qdrant Search: https://qdrant.tech/documentation/search/
- LanceDB Full-Text Search: https://docs.lancedb.com/search/full-text-search
- LanceDB Hybrid Search: https://lancedb.github.io/lancedb/hybrid_search/hybrid_search/
- Meilisearch Hybrid Search: https://www.meilisearch.com/docs/learn/ai_powered_search/difference_full_text_ai_search
- Typesense Vector / Hybrid Search: https://typesense.org/docs/28.0/api/vector-search.html
- Weaviate Hybrid Search: https://weaviate.io/developers/weaviate/search/hybrid
- OpenSearch Neural Sparse Search: https://docs.opensearch.org/latest/vector-search/ai-search/neural-sparse-search/
- Vespa Nearest Neighbor / Hybrid Retrieval: https://docs.vespa.ai/en/querying/nearest-neighbor-search.html
