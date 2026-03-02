# Global Vectorization General Foundation Plan (2026-03-02)

## 1. 目标定位

本方案定义为通用基础设施建设，不绑定单一业务功能。  
核心目标：先完成项目级全局向量化，再支撑以下能力统一演进：

1. 图谱去重（实体/关系/事件语义去重）。
2. 文档查询（语义检索 + 关键词检索混合）。
3. 研究报告（证据检索、聚类归纳、观点溯源）。
4. 采集调度（密度评估、低密度窗口优先策略）。

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

3. `通用检索平面`
- 统一提供 TopK 相似检索、阈值过滤、去重聚合、来源追踪能力。

---

## 3. 架构原则

1. 单一向量基础层，多业务复用。  
2. 向量生成与业务流程解耦，通过异步/流水线接入。  
3. 向量版本化，支持灰度切换与回滚。  
4. 检索结果必须可解释（返回相似分、证据来源、版本）。  

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

### 5.3 研究报告

1. 报告问题拆解为检索子查询。  
2. 每个结论绑定可回溯证据向量命中项。  
3. 输出引用链：`结论 -> 证据片段 -> 原始文档`。  

### 5.4 采集调度

1. 基于向量相似度评估新采集信息增益。  
2. 高重复窗口降权，低密度窗口升权。  
3. 与 `density/norm_density` 联动形成采集优先级。  

---

## 6. 数据模型建议

1. `vector_objects`
- `id, project_key, object_type, object_id, vector_version, embedding_model, embedding_dim, created_at`

2. `vector_metadata`
- `vector_object_id, source_domain, effective_time, language, quality_flags, token_count`

3. `vector_links`
- `from_object_type, from_object_id, to_object_type, to_object_id, link_type, score`
- 用于图谱、报告证据链、去重簇映射。

---

## 7. 实施里程碑（优先做向量化）

1. `M1`（基础落库）
- 建立向量对象 schema 与索引。
- 接入文档/段落向量生产任务。

2. `M2`（统一检索接口）
- 上线通用向量检索 API。
- 支持过滤、分数阈值、版本选择。

3. `M3`（三能力接入）
- 图谱去重接入。
- 文档查询接入。
- 研究报告证据检索接入。

4. `M4`（调度接入）
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

---

## 9. 风险与控制

1. 风险：向量漂移导致结果不稳定。  
- 控制：版本冻结、A/B 对照、分批切换。  

2. 风险：检索延迟上升。  
- 控制：索引调参、缓存热点查询、分层召回。  

3. 风险：去重误合并。  
- 控制：语义+规则双门禁，人工抽样复核。  

---

## 10. 完成定义（DoD）

1. 已具备项目级全局向量化基础层。  
2. 图谱去重、文档查询、研究报告三能力均接入同一向量底座。  
3. 采集调度可使用向量密度与重复信号。  
4. 能力可版本化发布、可解释、可回滚。  
