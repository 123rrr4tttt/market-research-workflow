# 链路 02：Search & Indexing 平台化开源参考池

> 范围：基于 `main/backend/app/api/search.py`、`main/backend/app/services/search/*`、`main/backend/app/services/indexer/*`、`README.md` 归纳与平台化设计。

## 1) 现状（ES + DB 混合）简图

```text
[Client]
   |
   | GET /api/v1/search?q&state&rank&top_k
   v
[api/search.py::search]
   |
   v
[services/search/hybrid.py::hybrid_search]
   |------------------------------|
   |                              |
   v                              v
[bm25_search]                 [vector_search]
   |                              |
   | ES index: policy_docs_es     | PostgreSQL + pgvector
   |                              | tables: embeddings + documents
   |                              | order_by l2_distance(query_vec)
   |                              |
   |---------------> [RRF 融合 reciprocal_rank_fusion] <--------------|
                               |
                               v
                      标准化 results[] 返回
```

```text
[services/indexer/policy.py::index_policy_documents]
   -> 文本切分 (chunk)
   -> 生成 embedding
   -> 写入 Embedding 表 (DB)
   -> bulk 写入 ES policy_docs_es
```

现状要点：
- 查询面：BM25（ES）+ 向量检索（pgvector）+ RRF 融合，属于“双引擎混合检索”。
- 索引面：`indexer` 同时落 ES 与 DB，已具备“双写”基础能力。
- 运维面：`/search/_init` 可幂等初始化 ES 索引；向量检索依赖 embedding 服务可用性。

## 2) 3-5 个上位替代方案（平台化候选）

| 候选 | 类型 | 适配定位 | 优势 | 主要代价 |
|---|---|---|---|---|
| OpenSearch | 搜索+向量一体 | 替代 ES + 部分向量链路 | 与现有 ES 心智接近；支持 BM25/向量/混合与流水线 | 集群资源与调优复杂度较高 |
| Meilisearch | 轻量全文+语义/混合 | 中小规模低运维成本检索 | 上手快、API 简洁、低延迟体验好 | 生态与深度可定制能力弱于 OpenSearch |
| Qdrant | 向量数据库（可做混合） | 向量检索主引擎，文本检索可外接 | 向量能力强，过滤与 ANN 性能成熟 | 需补齐关键词检索和统一排序策略 |
| Weaviate | 向量数据库（内建 BM25/Hybrid） | 一体化语义+关键词检索 | 混合检索开箱能力强，Schema/检索接口完整 | 学习成本与运行形态相对更重 |

官方资料（优先官方文档/仓库）：
- OpenSearch: 文档 https://docs.opensearch.org/latest/ ，仓库 https://github.com/opensearch-project/OpenSearch
- Meilisearch: 文档 https://www.meilisearch.com/docs ，仓库 https://github.com/meilisearch/meilisearch
- Qdrant: 文档 https://qdrant.tech/documentation/ ，仓库 https://github.com/qdrant/qdrant
- Weaviate: 文档 https://docs.weaviate.io/weaviate ，仓库 https://github.com/weaviate/weaviate

## 3) 查询协议与 IO 映射（query/request -> retrieval -> rank -> response）

建议先冻结统一检索协议（与底层引擎解耦）：

```json
{
  "query": "market trend",
  "filters": {"state": "CA"},
  "top_k": 10,
  "retrieval": {
    "lexical": {"enabled": true, "engine": "es", "index": "policy_docs_es"},
    "vector": {"enabled": true, "engine": "pgvector", "embedding_model": "text-embedding-*"}
  },
  "rank": {"strategy": "rrf", "params": {"k": 60}},
  "debug": {"return_subscores": true}
}
```

阶段映射：

| 阶段 | 输入 | 当前实现映射 | 目标平台化映射 | 输出 |
|---|---|---|---|---|
| Request | `q/state/rank/top_k` | `api/search.py` Query 参数 | 统一 JSON 协议（可兼容 Query 参数） | `SearchRequest` |
| Retrieval | 查询请求 | `bm25_search`(ES) + `vector_search`(DB) | `RetrieverAdapter`（OpenSearch/Meili/Qdrant/Weaviate） | `CandidateSet[]` |
| Rank | 候选集合 | `reciprocal_rank_fusion` | 统一 `Ranker`（RRF/weighted/hybrid-native） | `RankedResult[]` |
| Response | 排序结果 | `ok({query,...,results})` | 保持现有 envelope，追加 `trace/engine/meta` | 标准响应 |

最小接口建议：
- `retrieve(request) -> List[Candidate]`
- `rank(candidates, request.rank) -> List[Candidate]`
- `format_response(request, ranked) -> dict`

## 4) 迁移分阶段（shadow read、A/B、cutover）

### Phase 0：基线冻结
- 冻结当前基线（ES+pgvector）的 P95、召回、成本。
- 建立固定评测集（查询集 + 标注相关文档集）。

### Phase 1：Shadow Read（只读对比，不影响用户）
- 线上仍走主链路返回；旁路调用候选新引擎并记录结果。
- 采集指标：TopK 重叠率、NDCG/Recall、延迟差、失败率。
- 退出条件：连续 7 天无严重回归，P95 不劣于基线 10% 以上。

### Phase 2：A/B（小流量真实验证）
- 按 `project_key` 或请求哈希分流（例如 10% -> 30% -> 50%）。
- 实时监控：P95、错误率、业务点击率/停留时长（若有）。
- 保留一键回滚：流量权重归零即回退旧链路。

### Phase 3：Cutover（正式切换）
- 新引擎升为主读路径；旧链路保留只读回滚窗口（建议 1-2 周）。
- 完成文档与运维项切换（告警、备份、索引生命周期、容量预算）。

## 5) 最小 PoC 命令与评估指标（P95、召回、成本）

### 5.1 最小 PoC 命令

当前链路基线：
```bash
# 1) 初始化索引
curl -sS -X POST 'http://localhost:8000/api/v1/search/_init'

# 2) 基线查询
curl -sS 'http://localhost:8000/api/v1/search?q=market%20trend&state=CA&rank=hybrid&top_k=10' | jq '.data.results | length'
```

候选引擎（本地单节点快速拉起示例）：
```bash
# OpenSearch
docker run -d --name os -p 9200:9200 -p 9600:9600 \
  -e discovery.type=single-node -e plugins.security.disabled=true \
  opensearchproject/opensearch:latest

# Meilisearch
docker run -d --name meili -p 7700:7700 getmeili/meilisearch:latest

# Qdrant
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant:latest

# Weaviate
docker run -d --name weaviate -p 8080:8080 \
  -e QUERY_DEFAULTS_LIMIT=20 -e AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true \
  -e PERSISTENCE_DATA_PATH=/var/lib/weaviate -e DEFAULT_VECTORIZER_MODULE=none \
  -e ENABLE_MODULES= \
  semitechnologies/weaviate:latest
```

压测（P95）最小命令（示例使用 `vegeta`）：
```bash
echo "GET http://localhost:8000/api/v1/search?q=market%20trend&rank=hybrid&top_k=10" \
  | vegeta attack -duration=30s -rate=20 | vegeta report
```

### 5.2 评估指标（验收口径）

- P95 延迟：`search API` 端到端 P95（ms）。
- 召回：`Recall@10`（基于标注集）。
- 排序质量：`NDCG@10`（建议与 Recall 一起看）。
- 成本：
  - 基础设施成本：`$/day`（CPU/内存/存储/网络）。
  - 单请求成本：`$/1k queries`。
  - 索引成本：`分钟/百万文档` 与 `GB/百万文档`。

建议最小通过线（PoC 阶段）：
- `P95_new <= 1.10 * P95_baseline`
- `Recall@10_new >= Recall@10_baseline - 0.02`
- `$/1k queries_new <= 1.15 * baseline`

---

结论（链路 2 平台化方向）：
- 先做“协议层标准化 + 适配器化”再替换底层引擎，避免被单一技术栈绑定。
- 迁移路径采用 `Shadow Read -> A/B -> Cutover`，优先保证可回滚与可观测性。
- 候选优先级可按现有团队经验分层：`OpenSearch（平滑）`、`Qdrant/Weaviate（语义优先）`、`Meilisearch（轻量低运维）`。
