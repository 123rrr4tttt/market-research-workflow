# Outdated Schemes Inventory (2026-03-03)

Last Updated: `2026-03-03 15:31 PST`

## 口径说明
- `confirmed_outdated`：已确认与当前主口径冲突，应淘汰/替换。
- `compat_kept`：历史兼容保留，短期可存在但需标注。
- 本次状态：`to_confirm=0`（已全部定性）。
- 术语说明：`b_primary` 仅作为历史映射名，运行口径统一以 `graph_db/db-primary` 为准。

## 清单

| 状态 | 方案/术语 | 文件引用 | 说明 |
|---|---|---|---|
| `confirmed_outdated` | “graph projection 作为主路径”表述 | [`02_atomic-parallel-closure-taskboard-2026-03-03.md`](./02_atomic-parallel-closure-taskboard-2026-03-03.md)（已修正） | 已改为 `graph_db / db-primary` 主口径。 |
| `compat_kept` | `b_primary` 配置字面量 | [`05_graph-node-standardization-overall-completion-2026-03-03.md`](../../CLOSED_DEV/2026-03-03-platformization-first-vectorization/05_graph-node-standardization-overall-completion-2026-03-03.md) | 文档已注明仅兼容映射，语义主路径是 `db-primary`。 |
| `compat_kept` | `graph_node_projection_*` 历史配置项 | [`06_backend-db-standardization-vectorization-closure-2026-03-03.md`](../../CLOSED_DEV/2026-03-03-platformization-first-vectorization/06_backend-db-standardization-vectorization-closure-2026-03-03.md) | 文档已标注“兼容期保留”。 |
| `confirmed_outdated` | “B 异常回退到 A”方案 | [`01_graph-node-standardization-a-then-b-plan-2026-03-02.md`](../../CLOSED_DEV/2026-03-02-graph-node-standardization-a-then-b-closure/01_graph-node-standardization-a-then-b-plan-2026-03-02.md) | 与当前实现/封口口径冲突，按当前实现口径收敛，不再作为主路径策略。 |
| `compat_kept` | “legacy-projection 并行保留”长期策略 | [`01_graph-3d-force-engine-parallel-migration-2026-03-02.md`](../../CLOSED_DEV/2026-03-02-graph-3d-force-engine-parallel-migration-closure/01_graph-3d-force-engine-parallel-migration-2026-03-02.md) | 兼容保留，但必须补退役条件与最晚移除窗口。 |
| `compat_kept` | `run_item_by_key legacy adapter path` | [`01_ingest-chain-full-branch-map-2026-03-02.md`](../../CLOSED_DEV/2026-03-02-ingest-chain-full-branch-map-closure/01_ingest-chain-full-branch-map-2026-03-02.md) | 作为兼容路径保留，需在 collect_runtime 完整替代后退役。 |
| `confirmed_outdated` | `test_graph_projection_unittest.py` 作为主链门禁 | [`02_atomic-vectorization-tasklist-2026-03-03.md`](../2026-03-03-global-vectorization-general-foundation/02_atomic-vectorization-tasklist-2026-03-03.md) | 可作为历史回归参考，不再作为主链封口门禁。 |

## 建议处理顺序（仅归档，不展开方案）
1. 先统一图主路径术语：`graph_db / db-primary`。
2. 明确 legacy 退役条件：触发条件、最晚移除时间、替代路径。
3. 对冲突描述打补丁：A/B 回退策略在 plan 与 closure 文档保持一致。

## 本次执行验证覆盖（2026-03-03）

- 覆盖项 1：`graph projection 作为主路径`（`confirmed_outdated`）
  - validated_on: `2026-03-03`
  - evidence_ref: [`02_atomic-parallel-closure-taskboard-2026-03-03.md`](./02_atomic-parallel-closure-taskboard-2026-03-03.md)
- 覆盖项 2：`B 异常回退到 A`（`confirmed_outdated`）
  - validated_on: `2026-03-03`
  - evidence_ref: [`02_atomic-parallel-closure-taskboard-2026-03-03.md`](./02_atomic-parallel-closure-taskboard-2026-03-03.md)
