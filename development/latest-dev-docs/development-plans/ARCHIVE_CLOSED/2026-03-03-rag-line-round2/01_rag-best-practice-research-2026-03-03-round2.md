# RAG 线第2轮：联网增量最佳实践研究（并入统一知识池）

日期：2026-03-03
范围：仅覆盖 RAG 增量（检索过滤、可追溯 chunk id、评测指标补齐）

## 本轮新增结论（相对 Round1 的增量）

1. **检索必须支持 metadata filter**（尤其 language/source/time）以减少跨域噪声。
2. **Chunk ID 必须稳定可重建**，便于评测、回放、去重和索引更新。
3. **评测不止 Recall/MRR**，应补充 NDCG@k 等排序质量指标。
4. **检索阶段建议保留“粗召回 + 重排”两段式结构**，后续可无缝替换 ANN/交叉编码器。

## 联网来源（本轮）

1. Pinecone Docs - Hybrid Search
   - https://docs.pinecone.io/guides/search/hybrid-search
   - 关键点：推荐语义+词法混合检索，强调检索阶段分层与可扩展性。

2. Pinecone Docs - Filter by metadata
   - https://docs.pinecone.io/guides/search/filter-by-metadata
   - 关键点：metadata 过滤是生产检索中降噪和约束召回域的关键机制。

3. LangChain Docs - Text splitters
   - https://python.langchain.com/docs/concepts/text_splitters/
   - 关键点：chunk/overlap 需要在语义完整性和上下文预算间平衡。

4. RAGAS Metrics 文档
   - https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/
   - 关键点：RAG 评测应覆盖检索与答案两层；排序质量类指标可辅助 Recall/MRR。

## 统一知识池合并说明

已将本轮增量结论合并到：
- `development/latest-dev-docs/development-plans/CURRENT_DEV/MERGED_OVERVIEW/02_rag-incremental-best-practice-pool-round2.md`

合并策略：仅追加“Round2 新增能力”与“可执行落地点”，避免重复 Round1 通用条目。
