<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-rag-line-round1/01_rag-best-practice-research-2026-03-03.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-rag-line-round1/01_rag-best-practice-research-2026-03-03.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# RAG Line Round1 — Best Practice Research (2026-03-03)

## Scope
- 索引构建（index build）
- 切分策略（chunking）
- 向量检索（vector retrieval）
- 重排（rerank）
- 评测（evaluation）

## Web References (联网检索)
1. LlamaIndex: Basic RAG strategies
   https://docs.llamaindex.ai/en/stable/optimizing/basic_strategies/basic_strategies/
2. LangChain: RAG concept docs
   https://python.langchain.com/docs/concepts/rag/
3. Weaviate: Chunking strategies for RAG
   https://weaviate.io/blog/chunking-strategies-for-rag
4. Pinecone: Rerankers in RAG pipeline
   https://www.pinecone.io/learn/series/rag/rerankers/
5. Qdrant: Search concepts and filtering
   https://qdrant.tech/documentation/concepts/search/
6. Ragas docs (RAG evaluation)
   https://docs.ragas.io/en/latest/

## Distilled Practices

### 1) Index Build
- 入库前做文档清洗（去噪、去模板、去导航垃圾文本）。
- 使用稳定文档ID与chunk ID，方便增量更新与回滚。
- 索引元数据至少包含：source、time、language、domain_tag。
- 索引构建与线上检索解耦：支持离线重建 + 在线热更新。

### 2) Chunking
- chunk 大小优先语义完整，不盲目按固定字符。
- 常见重叠区间 10%-20%，用于跨段语义衔接。
- 对结构化内容（标题/小节）优先结构感知切分。
- 以召回指标驱动 chunk 参数，而不是拍脑袋。

### 3) Vector Retrieval
- 先高召回向量检索，再叠加 metadata filter 缩小噪声。
- top_k 不宜过小（先保证 recall），后续由 reranker 压 precision。
- 线上建议保留检索日志：query、topk、命中源、得分。

### 4) Rerank
- rerank 是 RAG 质量关键层，建议作为标准链路而非可选项。
- 典型策略：dense score + lexical overlap/cross-encoder score 融合。
- rerank 只处理候选集合，控制延迟与成本。

### 5) Evaluation
- Retrieval层：Recall@k、MRR、nDCG。
- Generation层：groundedness/faithfulness、answer relevancy。
- 评测集需要覆盖真实查询分布与难例（同义、长尾、噪声）。
- 每轮迭代必须输出可复现实验脚本和结果快照。

## Round1 Design Decision
- 先实现“最小可运行RAG模块”：
  - 本地切分 + TF向量检索 + 轻量重排 + 基于证据片段的回答拼装。
- 先打通“检索-回答-评测”全链路，再在后续轮次替换为生产级 embedding/reranker。
