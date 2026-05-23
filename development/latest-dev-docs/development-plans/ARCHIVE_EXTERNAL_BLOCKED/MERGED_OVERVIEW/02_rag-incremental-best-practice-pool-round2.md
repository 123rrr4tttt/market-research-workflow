# Unified Knowledge Pool（RAG 增量 Round2）

## 可复用结论

- 检索层应支持 metadata filter（lang/source/time/tenant），先约束召回域再做相似度排序。
- Chunk ID 需要稳定（可重建）并可追溯到 doc_id + chunk_index。
- 排序质量评估建议至少包含 Recall@k + MRR@k + NDCG@k。
- 结构上保留“粗召回 + 重排”，便于后续替换为 ANN + cross-encoder。

## 本仓落地映射

- metadata filter：`main/backend/app/services/rag/minimal_rag.py`
- stable chunk id：`main/backend/app/services/rag/minimal_rag.py`
- ndcg 指标：`main/backend/scripts/rag_eval.py`
- 覆盖测试：`main/backend/tests/unit/test_minimal_rag_unittest.py`

## 去重声明

本文件仅保留 Round2 新增能力，不复制 Round1 已沉淀的通用 RAG 认知。