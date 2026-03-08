# RAG 线第2轮：原子任务表（仅增量）

## 目标
在不改动主流程形态（split -> retrieve -> rerank -> answer）的前提下，完成 RAG 线可生产化增量。

## 原子任务表

| ID | 原子任务 | 输入 | 输出 | 验收标准 |
|---|---|---|---|---|
| R2-A1 | 为检索增加 metadata_filter | MinimalRAG.retrieve | 过滤后的候选集 | 指定 lang=zh 时不返回 en chunk |
| R2-A2 | 为 answer 透传 metadata_filter | MinimalRAG.answer | 过滤条件可见且生效 | answer 返回包含 metadata_filter 字段 |
| R2-A3 | 引入稳定 chunk_id 生成 | doc_id/chunk_index/chunk_text | 可重建 chunk_id | 同数据重复 build_index 后 chunk_id 一致 |
| R2-A4 | 扩展评测指标到 NDCG@3 | rag_eval.py | recall/mrr/ndcg 三指标 | 输出含 ndcg_at_3 且可运行 |
| R2-A5 | 增量单测覆盖 | unittest | 2 条通过用例 | `pytest` 全绿 |
| R2-A6 | 文档与索引更新 | CURRENT_DEV docs | round2 三件套 + index 更新 | 可在 INDEX.md 导航到 round2 |

## 执行顺序
R2-A1 -> R2-A2 -> R2-A3 -> R2-A4 -> R2-A5 -> R2-A6

## 风险控制
- 不引入新依赖，不改公共接口主语义。
- 增量字段默认可选，保持向后兼容。
