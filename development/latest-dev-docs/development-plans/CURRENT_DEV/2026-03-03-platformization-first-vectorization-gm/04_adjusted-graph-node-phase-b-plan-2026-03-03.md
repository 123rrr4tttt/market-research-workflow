# Adjusted Graph Node Phase-B Plan (2026-03-03)

## 1. Purpose

在检查 2026-03-03 项目更新（平台化优先、结构化抽取模块化、source-library/resource-pool/crawler 运维能力扩展）后，重排 Graph Node Standardization 的 Phase B（节点投影持久化）方案。

本版本用于替代 2026-03-02 版本中对 B 阶段的过早假设，确保与当前主线一致：

1. 先完成平台化契约冻结（P0）
2. 再实施 B（持久化层）

## 2. Delta vs 2026-03-02 B

### 2.1 Keep

- 目标不变：引入 `graph_nodes` / `graph_node_aliases`，支持稳定节点事实层、回放与可追溯。
- 方向不变：A（读时标准化）先行，B（投影存储）后续接管读取。

### 2.2 Change

1. 顺序调整：B 不再与平台化并行推进，改为 **P0 freeze 后启动**。
2. 租户策略明确：遵循当前 schema 隔离，不新增与 schema 冲突的二次隔离语义。
3. 切换策略明确：强制 feature flag + 双路对比，不允许一次性切读。
4. 写入挂点调整：基于已模块化的结构化抽取结果与最终文档写入链路，先做旁路写，再做主路切换。

## 3. Preconditions (必须满足)

进入 B 之前必须同时满足：

1. P0 平台化冻结完成（single write workflow 语义稳定）。
2. 图谱接口契约稳定（`graph_schema_version/nodes/edges`）且回归通过。
3. A 阶段节点系综与组合析取规则冻结（至少一个版本窗口内不变）。

## 4. Target Architecture (Adjusted)

### 4.1 Data Layer

新增（按现有租户 schema 内建表）：

1. `graph_nodes`
- `id` (bigint pk)
- `node_type` (varchar)
- `canonical_id` (varchar)
- `display_name` (text, optional)
- `properties` (jsonb)
- `source_doc_id` (bigint, optional)
- `node_schema_version` (varchar)
- `quality_flags` (jsonb, optional)
- `created_at` / `updated_at`

唯一约束建议：
- `(node_type, canonical_id)`

2. `graph_node_aliases`
- `id` (bigint pk)
- `node_id` (fk -> graph_nodes.id)
- `alias_text` (text)
- `alias_norm` (text)
- `alias_type` (varchar)
- `created_at`

唯一约束建议：
- `(alias_norm, alias_type)`

### 4.2 Service Layer

新增：

- `app/services/graph/persistence/graph_node_writer.py`
- `app/services/graph/persistence/graph_node_alias_resolver.py`
- `app/services/graph/compat.py`（A/B 双路对比）
- `app/services/graph/backfill_graph_nodes.py`

### 4.3 Read/Write Modes

新增 feature flags（建议放 settings + runtime config）：

- `graph_node_projection_write_mode`:
  - `off` / `shadow` / `on`
- `graph_node_projection_read_mode`:
  - `a_only` / `b_canary` / `b_primary`

规则：

1. 初始：`write=shadow`, `read=a_only`
2. 灰度：`read=b_canary`（仅 `demo_proj`）
3. 全量：`read=b_primary`
4. 回退：任意异常切回 `read=a_only`

## 5. Rollout Plan (4 weeks)

### Week 1: Schema + Shadow Write

1. migration 新增 `graph_nodes` / `graph_node_aliases`
2. writer/alias resolver 接入旁路写（不影响现有读取）
3. 增加幂等/冲突日志

验收：
- 现有 `/admin/*-graph` 输出无变化
- `graph_nodes` 可持续增长且无唯一约束冲突风暴

### Week 2: Backfill + Reconciliation

1. 实施 `backfill_graph_nodes.py`（`--dry-run`、断点续跑）
2. 生成 A/B 差异报表（节点数、类型分布、端点一致性）

验收：
- 单项目全量回填完成
- A/B 差异在阈值内

### Week 3: Canary Read

1. `demo_proj` 启用 `read=b_canary`
2. 观测 `content/market/policy` 图谱接口稳定性
3. 对 `market_deep_entities/topic_scope` 做专项校验

验收：
- canary 窗口内无系统性 5xx/契约漂移
- 节点类型与边端点一致性通过

### Week 4: Full Cut + Harden

1. 扩灰到第二项目后全量切 `b_primary`
2. 保留 `a_only` 回退能力一个发布窗口
3. 补齐运维文档与回滚脚本

验收：
- 线上切换后契约与关键指标稳定
- 回退演练成功

## 6. Validation Matrix (Adjusted)

```bash
# 0) preflight
./scripts/docker-deploy.sh preflight

# 1) health
./scripts/docker-deploy.sh start && ./scripts/docker-deploy.sh health

# 2) api layer import guard
main/backend/.venv311/bin/python main/backend/scripts/check_api_layer_imports.py

# 3) baseline gate
./scripts/test-standardize.sh ci-pr -q

# 4) graph smoke
BASE="http://127.0.0.1:8000/api/v1"
PROJ="demo_proj"
curl -sS "$BASE/admin/content-graph?project_key=$PROJ&limit=50" | jq '{status:.status,nodes:(.data.nodes|length),edges:(.data.edges|length)}'
curl -sS "$BASE/admin/market-graph?project_key=$PROJ&limit=50"  | jq '{status:.status,nodes:(.data.nodes|length),edges:(.data.edges|length)}'
curl -sS "$BASE/admin/policy-graph?project_key=$PROJ&limit=50"  | jq '{status:.status,nodes:(.data.nodes|length),edges:(.data.edges|length)}'

# 5) migration check (when B DDL enabled)
cd main/backend
.venv311/bin/alembic upgrade head
.venv311/bin/alembic current
```

## 7. Rollback

最小回滚顺序：

1. 立刻切 `graph_node_projection_read_mode=a_only`
2. 保留 shadow write 或切 `write=off`
3. 若本次 DDL 引发问题再执行 `alembic downgrade -1`
4. 执行最小复验（健康 + 3 graph API + ci-pr）

## 8. Explicit Non-Goals (当前窗口)

1. 不在本窗口推进 full graph engine migration。
2. 不改动前端图谱交互语义，只保证后端契约与数据稳定。
3. 不与向量化 M1 争抢入口语义，避免上游字段漂移。

## 9. Status

- A 阶段：已收尾（接口冻结 + 系综析取 + 标准化测试）。
- B 阶段：已重排为“平台化冻结后执行”的可落地版本（本文件）。
