# Local Index Hybrid Retrieval Vectorization Routing

更新时间：2026-05-14 PST  
状态：归属定位文档；本次不实施  
范围：把 LanceDB vector / hybrid retrieval 从 local open search provider isolation 后续工作中移出，归入全项目数据向量化 / 标准化开发线。

## 1. 定位

`LanceDB` 已在 local open search provider isolation 工作中完成 FTS prototype 验证，但下一步的 vector / hybrid retrieval 不应继续作为搜索 provider 隔离任务推进。

原因：

- vector / hybrid retrieval 依赖全项目 embedding pipeline。
- chunk / document / material 的向量对象需要统一主键、版本、provenance 和质量字段。
- 写作工作台、agent、报告证据链、图谱去重都应复用同一套向量化与检索标准。
- 如果只在 `local_index` prototype 内局部推进，容易形成第二套不可复用的材料检索语义。

因此，后续工作归入本目录：

```text
development/latest-dev-docs/development-plans/CURRENT_DEV/2026-05-14-global-vectorization-general-foundation/
```

当前代码基线：

- `main/backend/app/services/local_index/schema.py` 已定义 `LocalIndexChunk / LocalIndexQuery / LocalIndexSearchResult`。
- `main/backend/app/services/local_index/service.py` 已提供薄 service，过滤无效 chunk 并委托 adapter。
- `main/backend/app/services/local_index/adapters/lancedb_adapter.py` 已实现可选 LanceDB adapter。
- 当前 LanceDB adapter 的 `search()` 使用 `query_type="fts"`；`vector` 字段只在缺失时用 deterministic vector 填充，尚未用于真实 vector similarity。
- 因此，本文中的 LanceDB vector / hybrid retrieval 是下一步要求，不是已完成事实。

## 2. 与搜索 provider 线的边界

local open search provider isolation 线继续负责：

- SearXNG / YaCy 的本地服务、provider adapter、benchmark 和 smoke。
- SearXNG 显式外部搜索。
- source candidate review / approval gate。
- 写作工作台与本地 agent 对现有 material retrieval 的调用融贯性。

本向量化线负责：

- embedding pipeline。
- vector object schema。
- chunk / document / material 标准化。
- vector versioning。
- keyword + vector hybrid ranking。
- 向量检索结果的 provenance 与引用链。
- 与当前主搜索链路对齐：Qdrant 为 vector primary，pgvector 为 fallback，ES/OpenSearch 兼容 BM25，LanceDB 仅作为 local material prototype。

## 3. 后续目标草案

下一轮向量化/标准化任务应单独定义，不与 SearXNG provider 解隔离混在一个迭代内。

候选目标：

1. 定义统一向量对象 contract：
   - `project_key`
   - `object_type`
   - `object_id`
   - `chunk_id`
   - `source_id`
   - `document_id`
   - `embedding_model`
   - `embedding_dim`
   - `vector_version`
   - `provenance`
2. 定义 material/chunk 标准化 contract：
   - 原文位置
   - 清洗文本
   - token count
   - language
   - source/domain metadata
   - quality flags
3. 为 LanceDB prototype 增加 vector / hybrid retrieval：
   - keyword FTS
   - vector similarity
   - hybrid score
   - project/source/document filters
   - result provenance
   - `mode=keyword|vector|hybrid` 的查询语义
   - 与主检索 `search_backends_used` / evidence hit contract 对齐的 adapter diagnostics
4. 建立 agent / WritingWorkbench / report evidence 共用 retrieval schema。

实现前置门禁：

- 不把 LanceDB 加入主项目强依赖。
- 不把 LanceDB 加入 `/api/v1/search` 的主 fallback order。
- 不把 FTS prototype 宣称为 vector/hybrid 已完成。
- 新增 vector/hybrid 前，先补 `test_local_index_service_unittest.py` 或新增 contract test 覆盖 optional dependency、keyword/vector/hybrid mode、project/source/document filters。

## 2026-05-22 lane 9 落地状态

- 已落地 `local_index` mode contract：`keyword|vector|hybrid` 合法值、service 规范化、LanceDB adapter mode dispatch。
- 已补 `test_local_index_service_unittest.py` 覆盖 optional dependency boundary、service mode normalization、adapter keyword/vector/hybrid dispatch 和 vector fallback。
- 已为 result contract 增加 `retrieval_mode/retrieval_family/trace`，避免只在 metadata 中隐式表达检索语义。
- 当前 lane 环境 `lancedb_available=False`，真实 LanceDB optional runtime smoke 未执行；这仍是后续验证项，不应把 fake-table dispatch 单测等同于真实 LanceDB runtime 完成。

## 2026-05-22 Wave2 A/B 文档证据状态

- Runtime 证据包：[local-index-lancedb-runtime-smoke/2026-05-22](../../../automation-runs/local-index-lancedb-runtime-smoke/2026-05-22/README.md)。
- Contract 证据包：[local-index-runtime-contract/2026-05-22](../../../automation-runs/local-index-runtime-contract/2026-05-22/README.md)。
- Wave2 A/B 合并后，optional dependency 环境 `lancedb_available=True`，已用 `LanceDBLocalIndexAdapter` 执行真实 upsert/search smoke。
- 结果口径：
  - `keyword`：可执行 FTS runtime path，并返回 `retrieval_mode=keyword` 与 trace。
  - `vector`：可执行 runtime path，并返回 `retrieval_mode=vector`；但 score/ranking 质量、embedding 语义和 benchmark 未验证。
  - `hybrid`：可执行 true hybrid runtime path，并返回 `retrieval_mode=hybrid`；A 线修复后未触发 keyword fallback。
- 因此，本文件状态从“只剩未安装依赖环境补跑”更新为“依赖可用时 keyword/vector/hybrid runtime smoke 已通过，但 embedding/ranking 质量与全项目 evidence contract 仍未封口”。
- 本目录仍保留在 `CURRENT_DEV`，不迁入 `ARCHIVE_CLOSED`。

## 4. 本次不做

本文件只完成归属定位，不实施：

- 不新增 embedding 任务。
- 不修改数据库 schema。
- 不引入 LanceDB 为主项目强依赖。
- 不接入前端。
- 不改 `source_library`。

## 5. 与现有文档关系

上游基础文档：

- `01_global-vectorization-general-foundation-plan-2026-05-14.md`

下游待拆分文档：

- 全项目 embedding pipeline 实施计划。
- material/chunk 标准化 schema。
- LanceDB hybrid retrieval prototype。
- agent / WritingWorkbench / report evidence retrieval contract 对齐。
