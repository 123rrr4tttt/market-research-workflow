# Global Vectorization General Foundation Index

更新时间：2026-05-22 PST<br>
状态：全项目数据向量化 / 标准化开发入口；2026-05-22 lane 9 已落地 `local_index` keyword/vector/hybrid mode contract；Wave2 A 已补真实 LanceDB keyword/vector/hybrid runtime smoke；仍未封口的是 embedding/ranking benchmark、统一 vector object schema 和主搜索 evidence contract 对齐

## 文件

- [01_global-vectorization-general-foundation-plan-2026-05-14.md](./01_global-vectorization-general-foundation-plan-2026-05-14.md)  
  全项目向量化基础层总体方案：已按当前代码实现更新，覆盖 `hybrid.py` 的 ES/BM25 + Qdrant primary + pgvector fallback + RRF、`policy.py` 向量 contract、`local_index` LanceDB FTS prototype，以及 Agent matrix contract 所需的 query branch / evidence / verification / merge-rank 要求。

- [02_local-index-hybrid-retrieval-vectorization-routing-2026-05-14.md](./02_local-index-hybrid-retrieval-vectorization-routing-2026-05-14.md)  
  LanceDB vector / hybrid retrieval 的归属定位文档：2026-05-22 已补 `local_index` optional runtime smoke，但 embedding/ranking 质量、benchmark 和全项目 evidence contract 仍归本开发线继续推进。

## 2026-05-22 lane 9 落地

- 分支：`codex/devdocs-local-index-runtime`
- 证据：[devdocs-lane-9-local-index-runtime-2026-05-22](../../../automation-runs/devdocs-lane-9-local-index-runtime-2026-05-22/README.md)
- 已落地：`LocalIndexQuery.mode` 合法值冻结为 `keyword|vector|hybrid`；service 规范化未知 mode；LanceDB adapter 按 mode 分发 FTS/vector/hybrid；result 返回 `retrieval_mode/retrieval_family/trace`。
- 已验证：`git diff --check`、`py_compile`、`test_local_index_service_unittest.py`。
- 环境边界：lane 9 当时的 Python 环境未安装 `lancedb`，真实 LanceDB runtime smoke 需看后续 optional dependency 环境证据。

## 2026-05-22 Wave2 A/B evidence

- 分支：`codex/devdocs-lancedb-runtime-smoke`、`codex/devdocs-local-index-runtime-artifacts`
- Runtime 证据：[local-index-lancedb-runtime-smoke/2026-05-22](../../../automation-runs/local-index-lancedb-runtime-smoke/2026-05-22/README.md)
- Contract 证据：[local-index-runtime-contract/2026-05-22](../../../automation-runs/local-index-runtime-contract/2026-05-22/README.md)
- 文档收口：`mode=keyword|vector|hybrid` 的 schema/service/result/adapter 证据、CURRENT_DEV 状态、复跑命令已集中到证据包。
- Runtime 事实：`lancedb==0.24.2` / `pyarrow==24.0.0` 环境中，`keyword`、`vector`、`hybrid` 均在真实 LanceDB table 上返回预期 top row，未触发 fallback。
- 状态判定：本目录保持 `partial`，不迁入 `ARCHIVE_CLOSED`。下一步未封口项是 embedding/ranking benchmark、统一 vector object schema、主搜索 evidence contract 和 Agent/WritingWorkbench 对齐。

## 当前边界

- 搜索 provider 解隔离继续归 `../2026-05-14-local-open-search-provider-isolation/`。
- 数据向量化、chunk/material 标准化、hybrid retrieval、向量版本化和 provenance 归本目录。
- 本目录已开始落地 runtime contract；lane 9 已完成 `local_index` mode contract，不引入 LanceDB 强依赖。
- 02 号文档本来就是 2026-05-14 文档，文件名和主体保留；仅由本目录索引继续引用。
