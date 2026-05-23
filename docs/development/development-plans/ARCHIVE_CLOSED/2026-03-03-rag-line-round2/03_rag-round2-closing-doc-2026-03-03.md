<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-rag-line-round2/03_rag-round2-closing-doc-2026-03-03.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-rag-line-round2/03_rag-round2-closing-doc-2026-03-03.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# RAG 线第2轮 Closing Doc

## 1) 完成项

- 已完成联网检索并沉淀增量最佳实践。
- 已输出原子任务表并按顺序执行。
- 已完成 RAG 线增量实现（metadata filter + stable chunk id + ndcg 评测）。
- 已完成验证（eval 脚本 + 单测）。
- 已完成统一知识池与索引更新。

## 2) 代码变更（仅 RAG 线）

1. `main/backend/app/services/rag/minimal_rag.py`
   - `retrieve()` 新增 `metadata_filter` 参数
   - `answer()` 新增 `metadata_filter` 透传
   - 新增稳定 chunk id 生成：`_stable_chunk_id()`
   - 新增 `_metadata_match()`

2. `main/backend/scripts/rag_eval.py`
   - 引入 metadata 过滤测试集
   - 指标扩展为 `recall_at_3` / `mrr_at_3` / `ndcg_at_3`

3. `main/backend/tests/unit/test_minimal_rag_unittest.py`
   - 新增“metadata filter 生效”测试
   - 新增“chunk_id 稳定性”测试

## 3) 验证结果

- `python3 scripts/rag_eval.py`
  - recall_at_3 = 1.0
  - mrr_at_3 = 1.0
  - ndcg_at_3 = 1.0

- `python3 -m pytest tests/unit/test_minimal_rag_unittest.py -q`
  - 2 passed

## 4) 差异化声明（Round2 vs Round1）

- Round1：建立最小可运行 RAG 主流程。
- Round2：补齐生产化增量能力（过滤、可追溯、排序指标），不改主流程骨架。

## 5) 去重清单

本轮刻意未重复实现/输出：

- 不重复实现新的向量库接入
- 不重复实现外部 LLM 生成链
- 不重复编写 Round1 已存在的通用 RAG 概述
- 不重复新增非 RAG 线代码（API/前端/ingest）

## 6) 索引更新

- 已新增目录：`CURRENT_DEV/2026-03-03-rag-line-round2/`
- 已更新：
  - `CURRENT_DEV/INDEX.md`
  - `CURRENT_DEV/MERGED_OVERVIEW/index.md`
