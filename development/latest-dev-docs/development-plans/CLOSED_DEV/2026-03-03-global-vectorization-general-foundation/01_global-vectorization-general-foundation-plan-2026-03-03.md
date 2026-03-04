# Global Vectorization General Foundation Plan (Revised 2026-03-03)

## 0. 决策与范围（与最新开发基线对齐）

本计划在 2026-03-03 更新后，采用以下固定执行顺序：

1. Platformization first（先平台化，冻结上游契约）
2. Vectorization second（后向量化，在稳定语义上建设通用底座）

对齐依据：

- `development/latest-dev-docs/README.md` 最新补充（2026-03-03）
- `CLOSED_DEV/2026-03-03-platformization-first-vectorization/01_platformization-first-vectorization-2026-03-03.md`
- `development-plans/main/MERGED_DEVELOPMENT_PLANS.md` 依赖规则（标准先行）

本文件定位：

- 定义“全局向量化”通用基础层与执行门禁。
- 不改变既有 ingest 平台化主线；仅在契约冻结后推进 M1/M2。

---

## 1. 目标定位

核心目标：先完成项目级全局向量化，再支撑统一演进：

1. 图谱去重（实体/关系/事件语义去重）
2. 文档查询（语义检索 + 关键词检索混合）
3. 研究报告（证据检索、聚类归纳、观点溯源）
4. 采集调度（信息增益评估、低密度窗口优先）

非目标（本期不做）：

- 前端重设计
- 图引擎迁移
- 非核心业务扩展

---

## 2. 通用定义与对象字典

### 2.1 全局向量化（Global Vectorization）

对核心对象统一生成向量并可检索：

- `document`
- `chunk`
- `entity`
- `relation`
- `report_fact`

### 2.2 向量对象统一业务主键（强制）

每个向量对象必须可回溯：

- `project_key`
- `object_type`
- `object_id`
- `vector_version`

幂等键（强制）：

- `uk_vector_object = (project_key, object_type, object_id, vector_version)`

### 2.3 对象映射规则（补齐歧义）

- 报告证据片段统一映射到 `report_fact`。
- 如后续需要“证据片段”和“结论事实”分离，新增 `report_evidence`，但必须提供向后兼容映射与迁移脚本。

---

## 3. 架构原则（新增执行约束）

1. 单一向量基础层，多业务复用。
2. 向量生成与业务流程解耦，通过异步流水线接入。
3. 向量版本化，支持灰度切换与回滚。
4. 检索结果可解释：返回相似分、证据来源、版本。
5. 强租户隔离：服务端强制 `project_key` 过滤，不信任客户端传参。
6. 不引入第二写入链路：向量化读取平台化后的稳定对象，不反向破坏 ingest 单写规则。

---

## 4. 契约冻结前置条件（Gate-0）

在进入 M1 前，必须完成以下冻结字段校验：

- `project_key`
- `object_type`
- `object_id`
- `vector_version`
- `clean_text`
- `language`
- `source_domain`
- `effective_time`
- `keep_for_vectorization`

Gate-0 最小门禁：

- `pytest tests/core_business/test_ingest_core_contract.py -q`
- `pytest -m "contract and not external" -q`

---

## 5. 能力分层（增强可执行细节）

### 5.1 Embedding Pipeline（生成层）

输入标准：

- `raw_text`
- `clean_text`
- `language`
- `source_domain`
- `effective_time`
- `keep_for_vectorization`

输出标准：

- `embedding`
- `embedding_model`
- `embedding_dim`
- `vector_version`
- `quality_flags`
- `token_count`

处理对象：

- 文档全文、段落、标题、名词短语、图谱节点描述、报告证据片段。

生成策略（新增）：

- 分块策略固定为配置项（`chunk_size/chunk_overlap`），按对象类型可覆盖。
- 失败重试采用指数退避，超过阈值进入死信队列并打 `quality_flags=embedding_failed`。
- 同对象同版本重复请求必须幂等（直接返回已有向量对象 ID）。

### 5.2 Vector Store（存储层）

向量对象最小字段：

- `project_key`
- `object_type`
- `object_id`
- `vector_version`
- `embedding_model`
- `embedding_dim`
- `vector`
- `is_active`
- `created_at`
- `updated_at`

索引要求：

- ANN 索引（HNSW/IVF，按引擎能力选择）
- 过滤索引：`project_key + object_type`
- 版本索引：`vector_version`
- 唯一约束：`(project_key, object_type, object_id, vector_version)`

读取规则（新增）：

- 默认仅读 `is_active=true`。
- 指定 `vector_version` 时按版本读取。
- 回滚通过“批量切换 is_active + 灰度比例”实现，不做全量删除。

### 5.3 Retrieval API（检索层）

通用接口：

- `POST /api/v1/vector/search`

请求：

- `project_key`（必填，且需与鉴权上下文匹配）
- `object_type`
- `query_text | query_vector`
- `top_k`
- `min_score`
- `filters`
- `vector_version`（可选）

响应（统一 envelope）：

- `status/data/error/meta`
- `data.matches[{object_id, object_type, score, vector_version, snippet, provenance}]`

安全约束（新增）：

- 服务端强制 tenant 过滤。
- 未授权 `project_key` 返回 `403`。
- 缺失关键字段返回 `400` + 稳定错误码。

业务适配器：

- 图谱去重适配器
- 文档查询适配器
- 报告证据检索适配器
- 采集密度评估适配器

---

## 6. 数据模型建议（可迁移、可回放）

1. `vector_objects`

- `id`
- `project_key`
- `object_type`
- `object_id`
- `vector_version`
- `embedding_model`
- `embedding_dim`
- `vector`
- `is_active`
- `created_at`
- `updated_at`
- `UNIQUE(project_key, object_type, object_id, vector_version)`

1. `vector_metadata`

- `vector_object_id`
- `source_domain`
- `effective_time`
- `language`
- `quality_flags`
- `token_count`
- `source_ref`

1. `vector_links`

- `from_object_type`
- `from_object_id`
- `to_object_type`
- `to_object_id`
- `link_type`
- `score`
- `created_at`

1. `vector_jobs`（新增，保障可运维）

- `job_id`
- `project_key`
- `object_scope`
- `vector_version`
- `status`
- `error_code`
- `processed_count`
- `failed_count`
- `started_at`
- `finished_at`

---

## 7. 关键业务复用（补充量化门禁）

### 7.1 图谱去重

1. 节点候选召回：按节点文本向量召回近邻。
2. 关系候选召回：按关系描述向量召回。
3. 合并策略：`semantic_score >= T1` 且 `type/time rule pass`。
4. 风险控制：`T1~T2` 区间进入人工抽样复核。

### 7.2 文档查询

1. 语义召回 + 关键词召回混排。
2. 去重折叠：近重复文档聚类后返回代表文档。
3. 统一过滤：`effective_time/source_domain/project_key`。

### 7.3 研究报告

1. 报告问题拆解为检索子查询。
2. 每个结论绑定证据命中。
3. 输出引用链：`结论 -> 证据片段(report_fact) -> 原始文档`。

### 7.4 采集调度

1. 以向量相似度评估信息增益。
2. 高重复窗口降权，低密度窗口升权。
3. 增加稳态保护：任意 24h/72h 高价值窗口覆盖率不得低于阈值底线。

---

## 8. 里程碑（重排为可执行链路）

### P0（平台化前置，必须先完成）

- 完成 ingest 契约冻结与 `single_url` 单写链路治理。
- 通过既有合同测试与平台任务清单（T1-T8）。

退出标准：

- 平台化核心链路稳定，契约可冻结签字。

### M1（向量基础落库）

- 建立向量对象 schema、唯一约束、索引。
- 接入 `document/chunk` 向量生成。
- 新增 `vectorization_contract` 测试。

退出标准：

- 重复写入幂等通过；同对象多版本并存可控；回滚开关可用。

### M2（统一检索接口）

- 上线统一检索 API（含 tenant 强隔离、错误码、版本选择）。
- 与现有 envelope 契约一致。

退出标准：

- 安全用例通过（跨租户阻断、缺参拒绝、权限拦截）。

### M3（三能力接入）

- 图谱去重接入。
- 文档查询接入。
- 报告证据检索接入。

退出标准：

- 三能力共享同一向量底座且 provenance 完整。

---

## 9. 当前进行状况（2026-03-03，仅按已执行事实）

### 9.1 已完成

- 向量召回 + 分组 + 并行 LLM 建议链路已可运行。
- 自动成团流程已支持主阈值 + 补充阈值（fallback）并组。
- 合并建议可写回数据库（节点合并 + 关系重映射）并输出对比报告。
- compare 项目已完成一次全量执行与写库验证。

### 9.2 当前可量化状态（latest compare run）

- compare 输出（`demo_proj_compare_0303_121137`）：
  - `candidate_count=2240`
  - `group_count=1121`
  - `llm_called_groups=500`
  - `merge_count=32`
- 写库 apply：
  - `input_merge_items=32`
  - `applied_merge_items=32`
  - `deleted_source_nodes=37`

### 9.3 当前未收口项（legacy merge 语义下）

- 同名节点残留仍可能存在（示例：`AI`），原因包括：
  - 同名节点未同时进入同一候选组；
  - LLM 输出未覆盖全部同名候选；
  - 后续流程新增节点进入池子。
- 若需要“同名强收敛”，需额外 deterministic fallback（按白名单类型执行强制同名并）。

### M4（调度接入与稳态）

- 密度/重复评估接入采集调度。
- 启用“低密度优先 + 覆盖率底线”策略。

退出标准：

- 调度增益与覆盖率同时达标。

---

## 9. 验收指标（补充可复现口径）

1. 覆盖率：核心文档向量覆盖率 `>= 98%`。
2. 质量：`Recall@10 / nDCG@10` 达到基线（固定评测集、固定时间窗）。
3. 去重：重复节点率较上线前下降，误合并率不高于阈值。
4. 溯源：报告结论证据链覆盖率 `>= 95%`。
5. 调度：低密度窗口采集占比达标，同时高价值窗口覆盖率不低于底线。
6. 稳定性：版本切换 + 回退演练通过（至少一次完整演练记录）。

---

## 10. 测试与门禁（最小集合）

P0/P1：

- `pytest -m "unit and not external" -q`
- `pytest -m "integration and not external" -q`
- `pytest tests/core_business/test_ingest_core_contract.py -q`

M1/M2：

- `pytest -m "contract and not external" -q`
- `pytest tests/core_business/test_search_core_contract.py -q`
- `pytest tests/contract/test_vectorization_contract_unittest.py -q`

M3/M4：

- 图谱去重回归测试
- 报告证据链回归测试
- 调度稳态覆盖率回归测试

---

## 11. 风险与控制（补充操作级策略）

1. 向量漂移导致质量波动

- 控制：版本冻结、A/B 对照、灰度发布、可观测告警。

1. 检索延迟升高

- 控制：ANN 参数调优、分层召回、热点缓存、限流。

1. 去重误合并

- 控制：语义 + 规则双门禁；灰区人工抽样复核。

1. 跨租户数据风险

- 控制：服务端 tenant 强过滤 + 鉴权绑定 + 审计日志。

1. 调度偏置

- 控制：探索/利用双策略与覆盖率底线回补。

---

## 12. 完成定义（DoD）

1. 具备项目级全局向量化基础层（含版本与幂等语义）。
2. 图谱去重、文档查询、研究报告接入统一向量底座。
3. 采集调度可使用向量密度与重复信号，且具覆盖率兜底。
4. 能力可版本化发布、可解释、可回滚。
5. 合同测试、回归测试、回滚演练证据齐全。

---

## 13. 外部最佳实践映射（2026-03-03）

说明：以下为对官方文档/论文的工程化映射，不是逐字照搬。

1. Embedding 模型与维度

- 参考 OpenAI Embeddings（模型与向量维度策略）。
- 映射：将 `embedding_model/embedding_dim` 写入每条向量对象，禁止隐式推断。

1. 向量索引

- 参考 pgvector、OpenSearch k-NN、Elasticsearch dense_vector/HNSW。
- 映射：在文档层面固定“过滤优先 + ANN 检索 + 版本索引”三件套。

1. ANN 理论与参数意识

- 参考 HNSW 原始论文。
- 映射：将召回-延迟权衡纳入验收（非只看单点质量）。

1. 检索质量评测

- 参考 BEIR 基准。
- 映射：验收引入 `Recall@k/nDCG@k`，并固定评测集与时间窗。

---

## 14. 参考链接

- OpenAI Embeddings Guide: [https://platform.openai.com/docs/guides/embeddings](https://platform.openai.com/docs/guides/embeddings)
- pgvector documentation: [https://github.com/pgvector/pgvector](https://github.com/pgvector/pgvector)
- OpenSearch k-NN: [https://docs.opensearch.org/docs/latest/vector-search/](https://docs.opensearch.org/docs/latest/vector-search/)
- Elasticsearch vector search / dense_vector: [https://www.elastic.co/docs/solutions/search/vector](https://www.elastic.co/docs/solutions/search/vector)
- HNSW paper (arXiv): [https://arxiv.org/abs/1603.09320](https://arxiv.org/abs/1603.09320)
- BEIR benchmark (arXiv): [https://arxiv.org/abs/2104.08663](https://arxiv.org/abs/2104.08663)
