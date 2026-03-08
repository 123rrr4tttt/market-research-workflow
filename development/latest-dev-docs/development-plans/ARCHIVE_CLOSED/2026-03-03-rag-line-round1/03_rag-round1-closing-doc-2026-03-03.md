# RAG Line Round1 — Closing Doc

## Scope Closed
- 已完成独立副本开发：`market-research-workflow-parallel-20260303-215619-D-rag`
- 已完成RAG最佳实践联网检索与沉淀
- 已交付最小可运行 RAG 模块（索引+检索+重排+回答）
- 已交付评测脚本（Recall@3 / MRR@3）
- 已补充单元测试并执行验证

## Code Delivered
- `main/backend/app/services/rag/minimal_rag.py`
- `main/backend/app/services/rag/__init__.py`
- `main/backend/scripts/rag_eval.py`
- `main/backend/tests/unit/test_minimal_rag_unittest.py`

## Validation Snapshot
- `python3 scripts/rag_eval.py` -> 输出 recall_at_3, mrr_at_3
- `python3 -m pytest tests/unit/test_minimal_rag_unittest.py` -> 通过

## Rollback Point
- 仅新增文件，无侵入性修改现有核心链路；可直接回滚新增文件提交。

## Remaining Risks
- 非生产级 embedding / reranker。
- 未接入在线向量库与真实语料回归集。

## 差异化声明（去重清单 + 独特点）

### 与 A/B/C/E/F/G 线去重清单
- A/B/C 线已有的 ingest/gate/streamplus 改造：本线不重复实现，只引用其产物作为上游语料输入。
- E 线（数据库方向）已有存储层扩展：本线不重复做数据库schema扩展，当前采用最小本地索引验证；后续仅对接其能力。
- F/G 线（报告/研究或其他方向）已有分析文档：本线不重复写通用平台报告，仅沉淀 RAG 专项可执行文档。

### 本线独特点（至少两项）
1. **目标差异**：以“检索增强问答链路闭环”作为主目标，而非 ingest 吞吐或数据库扩容。
2. **架构差异**：新增 `services/rag/minimal_rag.py`，形成 split->vector retrieve->rerank->answer 的独立链路。
3. **验证指标差异**：采用 Retrieval 专项指标 `Recall@3`、`MRR@3` 作为硬验证（与其他线非同类指标）。
4. **模块差异**：新增 `scripts/rag_eval.py` 与 RAG 专项单测，不改动既有 streamplus 业务模块。

## Handoff for Round2
1. 接入真实 embedding + 向量库（pgvector 或 ES dense retrieval）。
2. 加入 cross-encoder rerank。
3. 扩展评测到真实业务query集，纳入CI门禁。
