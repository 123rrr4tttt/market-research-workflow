# Global Vectorization General Foundation Plan (2026-05-14)

更新时间：2026-05-22 PST
状态：实效性更新；仍为 partial / doc-aligned，不作封口声明  
范围：全项目数据向量化、chunk/material 标准化、hybrid retrieval、provenance 与下游 Agent / WritingWorkbench / report evidence 共用检索底座。

## 0. 2026-05-14 实效性更新

原 2026-03-02 方案的总方向仍有效：项目需要单一向量基础层，而不是让图谱去重、文档查询、报告证据、采集调度、写作工作台和 Agent 各自维护局部检索语义。

但当前实现事实已经变化：

- local open search provider isolation 已把 SearXNG / YaCy 归为外部搜索 provider 线；这不是本目录的职责。
- `02_local-index-hybrid-retrieval-vectorization-routing-2026-05-14.md` 已把 LanceDB vector / hybrid retrieval 从搜索 provider 解隔离线移入本目录。
- Agent 主题文档 41 已新增 R3 matrix capability requirement；向量检索不能只支持单条 serial query，而必须服务于 intent / keyword / provider-tool / evidence / verification matrix。
- 因此，本目录的当前任务不是“马上全量上线向量库”，而是先冻结一套可复用 contract：向量对象、chunk/material 标准化、混合召回、provenance、版本和矩阵式检索结果结构。

当前优先级：

1. 定义统一向量对象 contract 和 material/chunk contract。
2. 为 LanceDB prototype 扩展 vector / hybrid retrieval 的归属和验收标准。
3. 让 Agent / WritingWorkbench / report evidence 共享同一 retrieval result schema。
4. 为矩阵式检索保留 query group、branch id、evidence class、verification state 和 merge/rank metadata。

### 0.1 当前代码库实现基线（2026-05-14 核查）

本节按当前代码实现更新后续要求，避免文档继续描述一个尚不存在的全新平台。

已落地事实：

1. 主搜索链路已存在：
   - `main/backend/app/services/search/hybrid.py`
   - `main/backend/app/api/search.py`
   - 入口为 `GET /api/v1/search`，支持 `rank=bm25|vector|hybrid`。
   - BM25 使用 `policy_docs_es` 索引。
   - vector 搜索优先尝试 Qdrant，失败后降级 pgvector。
   - hybrid 使用 BM25 + vector 的 RRF 融合。
   - API 已返回 `search_fallback_order` 与 `search_backends_used`，用于诊断 ES/OpenSearch、Qdrant、pgvector fallback。

2. policy indexer 已存在向量 contract 雏形：
   - `main/backend/app/services/indexer/policy.py`
   - chunk 参数为 `_CHUNK_SIZE=800`、`_CHUNK_OVERLAP=120`。
   - 当前必填字段为 `project_key, object_type, object_id, vector_version, clean_text, language, source_domain, effective_time, keep_for_vectorization`。
   - pgvector 表模型为 `main/backend/app/models/entities.py::Embedding`，当前字段为 `object_id, object_type, modality, vector, dim, provider, model, created_at`。
   - Qdrant upsert 是 best-effort，可选依赖与环境配置驱动，不进入主事务。

3. `local_index` 已存在独立材料检索 prototype：
   - `main/backend/app/services/local_index/schema.py`
   - `main/backend/app/services/local_index/service.py`
   - `main/backend/app/services/local_index/adapters/lancedb_adapter.py`
   - `LocalIndexChunk` 已有 `chunk_id, document_id, project_id, source_id, title, content, url, source_type, language, created_at, metadata, vector`。
   - LanceDB adapter 已按 `LocalIndexQuery.mode` 分发 FTS/vector/hybrid，并保持可选依赖边界，不能成为主项目强依赖。
   - Wave3 A 的受控 benchmark 已证明 deterministic-vector 数据集上的 top-k ranking wiring、filters 和 trace；但这不是生产 embedding model 语义相关性质量证明。

4. Agent 矩阵式检索已经部分落地：
   - `main/backend/app/services/agent_core/project_tools.py`
   - `source.discovery.plan` 返回 `agent_core.source_capability_matrix.v1`。
   - `source.web.search` 支持 `matrix_mode, query_variants, providers`，返回 `agent_core.source_web_search_matrix.v1`。
   - 当前 branch 字段包括 `branch_id, query, provider, purpose, status, result_count, accepted_candidate_count, provider_diagnostics`。
   - 候选结果已保留 `matrix_branches, matrix_rank, branch_count`，并按 URL/checksum 去重合并。
   - provider prompt 已要求资料搜集使用 capability matrix，而不是单条 serial query。

5. workflow graph 已存在 `vector_search` executor：
   - `main/backend/app/services/workflow_graph/executors/vector_search.py`
   - 正常路径调用 `vector_search`，异常时返回 mock fallback hit 并标记 `degraded=true`。

当前缺口：

1. 还没有独立的 `POST /api/v1/vector/search`。
2. 还没有统一 `retrieval_runs / retrieval_branches / retrieval_hits` 落库。
3. `Embedding` 表还没有 `project_key, chunk_id, source_id, document_id, vector_version, provenance, source_uri, char_start, char_end, token_count, normalization_version, matrix_branch_id` 等字段。
4. policy indexer 目前按 document id 删除/写入 embedding，chunk 级主键仍不充分。
5. Qdrant 与 pgvector 的输出 shape 还不是完整 evidence hit contract；缺少统一 `evidence_class, verification_state, rank_features, provenance`。
6. LanceDB `local_index` runtime 与受控 benchmark 已覆盖 keyword/vector/hybrid，但仍不应被文档描述为生产 embedding quality 已封口。
7. Agent matrix 和主检索链路尚未打通：Agent 外部 source matrix 有 branch diagnostics，但 `/api/v1/search` 的 vector/hybrid 结果尚无 `query_group_id/matrix_branch_id`。

后续要求必须以“扩展现有实现”为原则：

- 第一优先级不是新建另一套检索服务，而是在 `hybrid.py` / `indexer.policy` / `local_index` / Agent matrix contract 之间冻结共享字段。
- Qdrant 作为首选 vector backend，pgvector 作为 fallback；文档中提到 OpenSearch 时要兼容当前 ES client 命名，不要求立即替换。
- LanceDB 只作为 local material index prototype 扩展，不替代主搜索链路。
- 所有新增 contract 必须有对应 unit/contract test，不允许只写文档要求。

## 1. 目标定位

本方案定义为通用基础设施建设，不绑定单一业务功能。  
核心目标：先完成项目级全局向量化，再支撑以下能力统一演进：

1. 图谱去重（实体/关系/事件语义去重）。
2. 文档查询（语义检索 + 关键词检索混合）。
3. 研究报告（证据检索、聚类归纳、观点溯源）。
4. 采集调度（密度评估、低密度窗口优先策略）。
5. Agent 矩阵式资料检索（多关键词、多工具/来源、多证据类型、多验证门禁）。
6. WritingWorkbench / report evidence 的可引用、可回滚证据召回。

---

## 2. 通用定义

1. `全局向量化（Global Vectorization）`
- 对项目内核心对象统一生成向量并可检索：
  - 文档向量
  - 段落向量
  - 名词短语/实体向量
  - 图谱节点文本向量

2. `向量对象统一主键`
- 每个向量对象必须可回溯到业务对象：
  - `object_type`（document/chunk/entity/relation/report_fact）
  - `object_id`
  - `project_key`
  - `vector_version`
- 当前代码兼容要求：
  - `object_type=policy_chunk` 必须继续兼容 `Embedding.object_type` 与 Qdrant payload。
  - 在引入 chunk 级主键前，不得破坏现有 `object_id=document.id` 的 pgvector 查询。
  - 新字段应先进入 ES/Qdrant payload 与 response contract，再评估是否迁移 pgvector 表结构。

3. `通用检索平面`
- 统一提供 TopK 相似检索、阈值过滤、去重聚合、来源追踪能力。

4. `矩阵式检索结果（Matrix Retrieval Result）`
- 一个用户问题可以拆成多个 query branch：
  - intent facet
  - keyword/query variant
  - source/tool route
  - object_type filter
  - verification gate
- 每个 branch 的结果必须可合并、去重、排序，并保留 provenance。

---

## 3. 架构原则

1. 单一向量基础层，多业务复用。  
2. 向量生成与业务流程解耦，通过异步/流水线接入。  
3. 向量版本化，支持灰度切换与回滚。  
4. 检索结果必须可解释（返回相似分、证据来源、版本）。  
5. 检索结果必须可矩阵归并：同一问题下的关键词召回、向量召回、结构化数据召回、图谱召回和来源库/文档召回应能进入统一 merge/rank。
6. 不把本目录和搜索 provider 目录混用：SearXNG / YaCy provider 服务继续归 local open search provider isolation；向量对象、hybrid ranking 和 material retrieval contract 归本目录。

---

## 4. 能力分层

### 4.1 Embedding Pipeline（生成层）

1. 统一输入标准：
- `raw_text`
- `clean_text`
- `language`
- `source_domain`
- `effective_time`

2. 统一输出标准：
- `embedding`
- `embedding_model`
- `embedding_dim`
- `vector_version`
- `quality_flags`

3. 处理对象：
- 文档全文、段落、标题、名词短语、图谱节点描述、报告证据片段。

4. 2026-05-14 contract 补充：
- `chunk_id`
- `document_id`
- `source_id`
- `provenance`
- `source_uri`
- `char_start` / `char_end`
- `token_count`
- `normalization_version`
- `matrix_branch_id`

5. 当前实现约束：
- `policy.py` 中 `_REQUIRED_VECTOR_FIELDS` 已经形成最小门禁，新增字段必须分阶段进入：
  - M0：文档 contract 和测试覆盖。
  - M1：ES/Qdrant payload 可选字段。
  - M2：API response 字段。
  - M3：pgvector schema migration。
- `keep_for_vectorization=false` 当前会被 contract validator 拒绝；后续若要支持保留但不向量化的材料，必须先改测试与调用方语义。

### 4.2 Vector Store（存储层）

1. 向量表（或向量库集合）最小字段：
- `project_key`
- `object_type`
- `object_id`
- `vector`
- `vector_version`
- `created_at`

2. 索引要求：
- ANN 索引（HNSW/IVF 等）
- `project_key + object_type` 过滤索引
- 版本索引（便于灰度对照）
- full text / keyword index 与 vector index 并存，支持 hybrid retrieval。
- provenance / document / source 过滤可用，避免只返回不可引用的向量命中。

3. 当前 backend 分层要求：
- BM25/keyword：继续兼容当前 ES client 与 `policy_docs_es` 索引；未来可迁移 OpenSearch，但不作为本轮前置条件。
- Vector primary：Qdrant，可选依赖和环境变量驱动，失败必须可降级。
- Vector fallback：pgvector，继续使用 `Embedding` 表。
- Local material prototype：LanceDB，仅限 local_index FTS/vector/hybrid prototype，不进入主搜索 fallback order。
- API 诊断：继续保留并扩展 `search_fallback_order`、`search_backends_used`，不得把 fallback 静默吞掉。

### 4.3 Retrieval API（检索层）

1. 通用接口（建议）：
- `POST /api/v1/vector/search`
- 入参：`project_key, object_type, query_text|query_vector, top_k, min_score, filters`
- 出参：`matches[{object_id, score, vector_version, snippet, provenance}]`

2. 业务适配器：
- 图谱去重适配器
- 文档查询适配器
- 报告证据检索适配器
- 采集密度评估适配器
- Agent matrix retrieval 适配器
- WritingWorkbench citation / rewrite evidence 适配器

3. 2026-05-14 返回结构补充：
- `query_group_id`
- `matrix_branch_id`
- `retrieval_mode`（keyword / vector / hybrid / graph / structured）
- `evidence_class`（internal_existing / generated_artifact / source_catalog / external_candidate）
- `rank_features`
- `verification_state`
- `provenance`

4. 当前 API 兼容要求：
- `GET /api/v1/search` 现有 envelope 和 `results[]` shape 不得破坏。
- 新增字段只能向后兼容追加到 `data` 或 `results[]`。
- `rank=bm25|vector|hybrid` 继续有效；未来 `POST /api/v1/vector/search` 只能作为补充接口，不能替换现有搜索入口。
- `VectorSearchExecutor` 的 degraded fallback 必须保留显式 `degraded` / `degraded_reason`，不得把 mock hit 当成真实 evidence。

---

## 5. 关键业务如何复用

### 5.1 图谱去重

1. 节点候选召回：按节点文本向量召回近邻。  
2. 关系候选召回：按关系三元组描述向量召回。  
3. 合并策略：`score + 规则` 双门禁（语义相似 + 类型一致 + 时间约束）。  

### 5.2 文档查询

1. 语义召回 + 关键词召回混排。  
2. 去重折叠：近重复文档聚类后返回代表文档。  
3. 时间与来源过滤：统一使用 `effective_time`、`source_domain`。  
4. 支持多 query branch 的矩阵式召回：同义词、跨语言、实体名、主题短语和失败症状可并行召回后合并。

### 5.3 研究报告

1. 报告问题拆解为检索子查询。  
2. 每个结论绑定可回溯证据向量命中项。  
3. 输出引用链：`结论 -> 证据片段 -> 原始文档`。  

### 5.4 采集调度

1. 基于向量相似度评估新采集信息增益。  
2. 高重复窗口降权，低密度窗口升权。  
3. 与 `density/norm_density` 联动形成采集优先级。  

### 5.5 Agent / WritingWorkbench / Report Evidence

1. Agent 不应只调用单条检索链；应把用户问题拆成 query matrix，并用本底座返回可合并的证据集合。
2. WritingWorkbench 需要按当前选区、段落、文档目标生成 retrieval branches，并把返回证据映射到可插入/可引用的文本位置。
3. 报告证据链需要每个结论绑定 retrieval hit、原始文档、chunk 范围、向量版本和验证状态。
4. source catalog / external provider 结果不能直接混作 internal evidence；必须通过 evidence_class 区分。
5. 当前 Agent matrix contract 必须被纳入本底座：
   - `source.discovery.plan` 的 `agent_core.source_capability_matrix.v1` 是规划矩阵。
   - `source.web.search` 的 `agent_core.source_web_search_matrix.v1` 是外部候选矩阵。
   - 主检索链路新增 matrix 字段时，应复用 `branch_id/query/provider/purpose/status/provider_diagnostics/matrix_rank/branch_count` 的语义，而不是另造命名。
   - zero-result branch 只能表示 provider/query uncertainty，不能作为 absence claim。

---

## 6. 数据模型建议

1. `vector_objects`
- `id, project_key, object_type, object_id, vector_version, embedding_model, embedding_dim, created_at`

2. `vector_metadata`
- `vector_object_id, source_domain, effective_time, language, quality_flags, token_count`

3. `vector_links`
- `from_object_type, from_object_id, to_object_type, to_object_id, link_type, score`
- 用于图谱、报告证据链、去重簇映射。

4. `retrieval_runs`
- `id, project_key, query_group_id, user_intent, created_at, consumer`

5. `retrieval_branches`
- `id, retrieval_run_id, matrix_branch_id, query_text, retrieval_mode, filters, provider_or_index, status`

6. `retrieval_hits`
- `branch_id, object_type, object_id, chunk_id, score, rank, evidence_class, verification_state, provenance`

7. 当前代码迁移要求：
- 短期不直接替换 `embeddings` 表；先以兼容字段扩展 ES/Qdrant payload 和 API result。
- `retrieval_*` 三表进入实现前，先用 response-level `query_group_id` / `matrix_branch_id` / `search_branches` 形成无迁移 contract test。
- `LocalIndexChunk` 与 policy chunk contract 要合并字段口径：`project_id` 与 `project_key` 需要明确映射，不能长期并存为两套语义。

---

## 7. 实施里程碑（优先做向量化）

1. `M0`（contract 冻结，当前优先）
- 定义向量对象、chunk/material、retrieval result、retrieval run/branch/hit contract。
- 明确 LanceDB prototype 与主项目依赖边界。
- 明确和 local open search provider isolation 的非重叠边界。
- 以当前实现为基线补齐 contract tests：
  - `test_vectorization_contract_unittest.py`
  - `test_policy_indexer_vector_contract_unittest.py`
  - `test_local_index_service_unittest.py`
  - `test_agent_core_unittest.py` 中 matrix 相关测试。

2026-05-22 lane 9 已完成 M0 的 `local_index` 子项：冻结 `keyword|vector|hybrid` mode contract，补齐 service normalization、LanceDB adapter dispatch、result `retrieval_mode/retrieval_family/trace`，并用 `test_local_index_service_unittest.py` 覆盖 fake-table dispatch 与 optional dependency boundary。Wave2 A/B 已补 [local-index-lancedb-runtime-smoke/2026-05-22](../../../automation-runs/local-index-lancedb-runtime-smoke/2026-05-22/README.md) 与 [local-index-runtime-contract/2026-05-22](../../../automation-runs/local-index-runtime-contract/2026-05-22/README.md) 证据：当前 optional dependency 环境可 import `lancedb`，keyword/vector/hybrid runtime smoke 均通过。Wave3 A 已补 [local-index-lancedb-benchmark/2026-05-22](../../../automation-runs/local-index-lancedb-benchmark/2026-05-22/README.md) 证据：受控 dataset 下三种 mode 的 repeated top-k ranking、project/source filters 和 trace contract 均通过；因此 M0 的 `local_index` runtime/benchmark wiring 已对齐，但真实 embedding model 语义质量、统一 vector object schema 与全项目 evidence contract 仍是后续验证项。

2026-05-22 Wave8-8 补充 [wave8-search-vectorization-contract/2026-05-22](../../../automation-runs/wave8-search-vectorization-contract/2026-05-22/README.md)：新增 `ops/search-lab/scripts/wave8_search_vectorization_contract.py`，只读取既有 provider trace、container replay summary、LanceDB runtime smoke 和 benchmark JSON，不启动容器、不访问外网。该 gate 固定了 `local_index` runtime/benchmark 与 search provider trace 的交叉证据，同时显式保留 `current_container_availability_not_replayed`、`semantic_embedding_quality_not_proven`、`global_vector_contract_not_closed`。

2. `M1`（基础落库）
- 在不破坏 `Embedding` 表现有 contract 的前提下，扩展 ES/Qdrant payload 字段。
- 明确 `chunk_id` 生成规则，并让 policy indexer 输出稳定 chunk 级标识。
- 保持 Qdrant upsert best-effort，不影响主事务。

3. `M2`（统一检索接口）
- 先扩展 `GET /api/v1/search` 的 response contract，再评估新增 `POST /api/v1/vector/search`。
- 支持 keyword/vector/hybrid 三种 retrieval_mode，并保留 `search_backends_used`。
- 让 Qdrant/pgvector/ES 命中的返回字段对齐 evidence hit contract。

4. `M3`（三能力接入）
- 图谱去重接入。
- 文档查询接入。
- 研究报告证据检索接入。
- `VectorSearchExecutor` 接入真实 evidence metadata，mock fallback 只能用于 degraded 场景。

5. `M4`（矩阵式 Agent / WritingWorkbench 接入）
- Agent query matrix 接入。
- WritingWorkbench selection/range evidence retrieval 接入。
- 报告 evidence citation retrieval 接入。
- 将 Agent 已有 `source_capability_matrix` / `source_web_search_matrix` 字段映射到 retrieval run/branch/hit contract。

6. `M5`（调度接入）
- 密度/重复评估接入采集调度。
- 默认启用低密度窗口优先策略。

---

## 8. 验收指标

1. 向量覆盖率：
- 核心文档向量覆盖率 >= 98%。

2. 检索质量：
- Top10 语义召回命中率达到既定基线（由评测集定义）。

3. 图谱去重效果：
- 重复节点率下降（上线前后对比）。

4. 报告可溯源性：
- 报告结论具备证据链覆盖率 >= 95%。

5. 调度有效性：
- 低密度窗口采集占比持续高于默认阈值。

6. 矩阵检索质量：
- broad research/material request 至少保留 query_group、branch、retrieval_mode、evidence_class 和 merge/rank 记录。
- 单条 query/provider 不得产生 source absence 结论。

7. 当前实现回归门禁：
- `python -m pytest main/backend/tests/contract/test_vectorization_contract_unittest.py`
- `python -m pytest main/backend/tests/unit/test_policy_indexer_vector_contract_unittest.py`
- `python -m pytest main/backend/tests/unit/test_local_index_service_unittest.py`
- `python -m pytest main/backend/tests/unit/test_agent_core_unittest.py -k "source_discovery_plan_returns_capability_matrix or source_web_search_matrix_merges_ranks"`
- 无可用 Qdrant/LanceDB 时，测试必须验证 optional dependency / fallback boundary，而不是要求本机强装依赖。

---

## 9. 风险与控制

1. 风险：向量漂移导致结果不稳定。  
- 控制：版本冻结、A/B 对照、分批切换。  

2. 风险：检索延迟上升。  
- 控制：索引调参、缓存热点查询、分层召回。  

3. 风险：去重误合并。  
- 控制：语义+规则双门禁，人工抽样复核。  

4. 风险：局部 prototype 形成第二套检索语义。  
- 控制：LanceDB / local_index 只作为实现候选，contract 以本目录统一对象和 retrieval schema 为准。

5. 风险：Agent 仍然用单条串行检索。  
- 控制：按 41 号 R3 要求，把 query matrix / branch / merge-rank / diagnostics 纳入验收。

---

## 10. 完成定义（DoD）

1. 已具备项目级全局向量化基础层。  
2. 图谱去重、文档查询、研究报告三能力均接入同一向量底座。  
3. 采集调度可使用向量密度与重复信号。  
4. 能力可版本化发布、可解释、可回滚。
5. Agent / WritingWorkbench / report evidence 能通过同一 hybrid retrieval contract 返回矩阵式、可引用、可验证的证据。
