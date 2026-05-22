# Global Vectorization General Foundation Index

更新时间：2026-05-22 PST<br>
状态：全项目数据向量化 / 标准化开发入口；2026-05-22 lane 9 已落地 `local_index` keyword/vector/hybrid mode contract；Wave2 B 已补 runtime artifact/doc closure evidence，真实 hybrid runtime 仍未封口

## 文件

- [01_global-vectorization-general-foundation-plan-2026-05-14.md](./01_global-vectorization-general-foundation-plan-2026-05-14.md)  
  全项目向量化基础层总体方案：已按当前代码实现更新，覆盖 `hybrid.py` 的 ES/BM25 + Qdrant primary + pgvector fallback + RRF、`policy.py` 向量 contract、`local_index` LanceDB FTS prototype，以及 Agent matrix contract 所需的 query branch / evidence / verification / merge-rank 要求。

- [02_local-index-hybrid-retrieval-vectorization-routing-2026-05-14.md](./02_local-index-hybrid-retrieval-vectorization-routing-2026-05-14.md)  
  LanceDB vector / hybrid retrieval 的归属定位文档：明确当前代码只有 optional LanceDB FTS prototype，vector / hybrid 是下一步要求；从 local open search provider isolation 后续工作中移出，归入全项目数据向量化 / 标准化开发线。

## 2026-05-22 lane 9 落地

- 分支：`codex/devdocs-local-index-runtime`
- 证据：[devdocs-lane-9-local-index-runtime-2026-05-22](../../../automation-runs/devdocs-lane-9-local-index-runtime-2026-05-22/README.md)
- 已落地：`LocalIndexQuery.mode` 合法值冻结为 `keyword|vector|hybrid`；service 规范化未知 mode；LanceDB adapter 按 mode 分发 FTS/vector/hybrid；result 返回 `retrieval_mode/retrieval_family/trace`。
- 已验证：`git diff --check`、`py_compile`、`test_local_index_service_unittest.py`。
- 环境边界：lane 9 当时的 Python 环境未安装 `lancedb`，真实 LanceDB runtime smoke 需看后续 optional dependency 环境证据。

## 2026-05-22 Wave2 B evidence

- 分支：`codex/devdocs-local-index-runtime-artifacts`
- 证据：[local-index-runtime-contract/2026-05-22](../../../automation-runs/local-index-runtime-contract/2026-05-22/README.md)
- 文档收口：`mode=keyword|vector|hybrid` 的 schema/service/result/adapter 证据、CURRENT_DEV 状态、复跑命令已集中到证据包。
- Runtime 事实：本 worktree 的 optional dependency 环境 `lancedb_available=True`；keyword runtime smoke 通过，vector runtime path 可达但未验证语义质量，hybrid 当前 fallback 到 keyword 并记录 `fallback_from=hybrid`。
- 状态判定：本目录保持 `partial`，不迁入 `ARCHIVE_CLOSED`。真实 LanceDB hybrid runtime、统一 vector object schema、主搜索 evidence contract 对齐仍是未封口项。

## 当前边界

- 搜索 provider 解隔离继续归 `../2026-05-14-local-open-search-provider-isolation/`。
- 数据向量化、chunk/material 标准化、hybrid retrieval、向量版本化和 provenance 归本目录。
- 本目录已开始落地 runtime contract；lane 9 已完成 `local_index` mode contract，不引入 LanceDB 强依赖。
- 02 号文档本来就是 2026-05-14 文档，文件名和主体保留；仅由本目录索引继续引用。
