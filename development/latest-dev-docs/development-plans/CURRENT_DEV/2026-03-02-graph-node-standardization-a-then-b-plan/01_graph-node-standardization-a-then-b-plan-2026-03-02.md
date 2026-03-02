# Graph Node Standardization A-Then-B Plan (2026-03-02)

## 1. Goal

仅聚焦“图谱节点本身”的入库与存储标准化，采用两阶段策略：

- Phase A: 读时标准化（不新增节点表）
- Phase B: 节点投影存储（新增节点持久化表）

目标是在不阻断现有业务写链路的前提下，先稳定节点定义，再升级为可治理、可回放、可扩展的节点存储体系。

## 2. Current State Baseline

当前节点不是独立数据库实体，而是由文档结构化结果在查询时运行时组装：

- 节点原始来源：`documents.extracted_data`（JSONB）
- 生成位置：`app/services/graph/builder.py`
- 返回位置：`app/services/graph/exporter.py`
- 接口入口：`/api/v1/admin/content-graph|market-graph|policy-graph`

当前未见独立 `graph_nodes` / `graph_edges` 持久化表；图谱接口路径是 `select(Document) -> normalize -> build -> export`。

## 3. Why A Then B

1. 先 A：降低变更风险，快速统一节点口径（type/id/properties）。
2. 再 B：在口径稳定后固化存储，避免反复迁移与回填返工。
3. 分层收益：A 解决“定义一致性”，B 解决“性能与可追溯性”。

## 4. Phase A Definition (Read-Time Standardization)

### 4.1 Scope

保留现有数据库结构，不新增节点表；仅标准化节点生成规则与输出契约。

### 4.2 Standardization Contract

必须统一以下四类规范：

1. `node_type` 枚举
- 明确允许类型集合（如 `Entity/Keyword/Topic/State/Segment/...`）。
- 禁止同义类型并存（例如 `Entity` vs `entity`）。

2. `canonical_id` 生成规则
- 文本标准化：NFKC + 去零宽字符 + 空白归一 + lower + strip。
- 规则稳定：同一输入跨时间、跨运行结果一致。

3. `properties` 白名单
- 每个 `node_type` 允许字段固定化，禁止任意字段透传。
- 对缺失值、空值、NA 设统一策略。

4. `node_schema_version`
- 图返回体显式附带节点版本号（例如 `v1`），用于后续 B 阶段映射。

### 4.3 Implementation Surface

主要影响：

- `main/backend/app/services/graph/builder.py`
- `main/backend/app/services/graph/models.py`
- `main/backend/app/services/graph/exporter.py`
- `main/backend/app/api/admin.py`
- `main/backend/app/services/graph/adapters/*.py`

### 4.4 Deliverables

1. 节点标准规范文档（type/id/properties/version）。
2. A 阶段统一构图实现（保持接口形态兼容）。
3. 回归测试：同输入多次构图节点集合完全一致。

## 5. Phase B Definition (Node Projection Storage)

### 5.1 Scope

在保留 `documents.extracted_data` 原始事实层的基础上，新增节点持久化层，图接口优先读节点表。

### 5.2 Target Data Model

建议新增：

1. `graph_nodes`
- `id` (PK)
- `project_key`
- `node_type`
- `canonical_id`
- `display_name`
- `properties` (JSONB)
- `source_doc_id`
- `schema_version`
- `created_at` / `updated_at`

建议唯一约束：
- `(project_key, node_type, canonical_id)`

2. `graph_node_aliases`（可选）
- 存储原文别名到 canonical 节点的映射。

### 5.3 Write/Read Strategy

写路径：

- 摄取或抽取完成后执行 node upsert。
- 对历史数据执行 backfill（从 `documents.extracted_data` 扫描节点并 upsert）。
- 过渡期双写：旧逻辑继续可用，逐步切流。

读路径：

- 图接口优先查询 `graph_nodes`。
- 当节点表缺失或开关关闭时回退到 A 路径。

### 5.4 Deliverables

1. Alembic migration（新表、索引、约束）。
2. backfill 脚本（支持 dry-run/断点续跑）。
3. 双写与读切换 feature flag。
4. 回滚手册（停双写、读回退、迁移回退策略）。

## 6. Milestones and Exit Criteria

### Milestone A (1-2 weeks)

完成条件：

1. 节点标准契约冻结（v1）。
2. 三类图接口节点输出口径一致。
3. 无 DDL 变更下通过核心回归。

### Milestone B (2-4 weeks)

完成条件：

1. 节点表上线并完成历史回填。
2. 图接口灰度切换到节点表读取。
3. 性能指标优于 A 阶段基线（响应时间与扫描量下降）。

## 7. Minimal Validation Steps

```bash
cd /Users/wangyiliang/market-research-workflow

# A 阶段：基线与接口冒烟
./scripts/test-standardize.sh unit tests/unit/test_raw_import_structuring_unittest.py -q
./scripts/test-standardize.sh unit tests/unit/test_discovery_store_guardrails_unittest.py -q
./scripts/test-standardize.sh integration tests/integration/test_ingest_baseline_matrix_unittest.py -q
./scripts/test-standardize.sh core-business tests/core_business/test_ingest_core_contract.py -q

curl -sS "http://127.0.0.1:8000/api/v1/admin/content-graph?project_key=demo_proj&limit=50" | jq '{status:.status,nodes:(.data.nodes|length)}'
curl -sS "http://127.0.0.1:8000/api/v1/admin/market-graph?project_key=demo_proj&limit=50" | jq '{status:.status,nodes:(.data.nodes|length)}'
curl -sS "http://127.0.0.1:8000/api/v1/admin/policy-graph?project_key=demo_proj&limit=50" | jq '{status:.status,nodes:(.data.nodes|length)}'

# B 阶段：迁移与回填（方案落地时）
cd /Users/wangyiliang/market-research-workflow/main/backend
.venv311/bin/alembic upgrade head
.venv311/bin/alembic current
# backfill_graph_nodes.py --dry-run
```

## 8. Risks and Controls

风险：

1. A 阶段标准化不彻底，导致 B 表结构反复。
2. B 回填与双写期间出现幂等冲突或别名冲突。
3. 灰度切流时前后口径短期不一致。

控制：

1. A 阶段先冻结 `node_schema_version`，未经评审不变更。
2. B 阶段强制幂等 upsert + 冲突日志。
3. 保留读回退开关，先小流量灰度再全量。
