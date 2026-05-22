# Global Vectorization General Foundation Index

更新时间：2026-05-22 PST
状态：全项目数据向量化 / 标准化开发入口；2026-05-22 已落地 local-index mode contract 首片，完整 vector / hybrid runtime 证据仍未封口

## 文件

- [01_global-vectorization-general-foundation-plan-2026-05-14.md](./01_global-vectorization-general-foundation-plan-2026-05-14.md)  
  全项目向量化基础层总体方案：已按当前代码实现更新，覆盖 `hybrid.py` 的 ES/BM25 + Qdrant primary + pgvector fallback + RRF、`policy.py` 向量 contract、`local_index` LanceDB FTS prototype，以及 Agent matrix contract 所需的 query branch / evidence / verification / merge-rank 要求。

- [02_local-index-hybrid-retrieval-vectorization-routing-2026-05-14.md](./02_local-index-hybrid-retrieval-vectorization-routing-2026-05-14.md)  
  LanceDB vector / hybrid retrieval 的归属定位文档：明确当前代码只有 optional LanceDB FTS prototype，vector / hybrid 是下一步要求；从 local open search provider isolation 后续工作中移出，归入全项目数据向量化 / 标准化开发线。

## 2026-05-22 落地记录

- `main/backend/app/services/local_index/schema.py` 新增 `keyword` / `vector` / `hybrid` 查询模式归一化，以及 result 侧 `retrieval_mode` / `retrieval_family` / `trace` 合同。
- `main/backend/app/services/local_index/service.py` 在 adapter 边界前归一化未知 mode，避免向下游泄漏未声明模式。
- `main/backend/app/services/local_index/adapters/lancedb_adapter.py` 将 `keyword` 路由到 FTS、`vector` 路由到 vector search、`hybrid` 路由到 hybrid/vector 并保留 keyword fallback。
- `main/backend/tests/unit/test_local_index_service_unittest.py` 已覆盖支持模式保留和未知模式回退。
- 本目录仍不声明封口：真实 LanceDB vector / hybrid runtime benchmark、向量版本化和跨来源 provenance 仍需下一轮验证。

## 当前边界

- 搜索 provider 解隔离继续归 `../2026-05-14-local-open-search-provider-isolation/`。
- 数据向量化、chunk/material 标准化、hybrid retrieval、向量版本化和 provenance 归本目录。
- 本目录当前完成文档实效性更新、归属定位和 local-index mode contract 首片；不新增 schema migration 或强制依赖。
- 02 号文档本来就是 2026-05-14 文档，文件名和主体保留；仅由本目录索引继续引用。
