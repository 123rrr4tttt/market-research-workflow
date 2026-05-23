# Wave10 Worker6 Search / Vector Node Quality Evidence

- 状态：node IO 输入边界 evidence partial；不作封口声明
- 分支：`codex/devdocs-wave10-vectorization-quality`
- Evidence：[wave10-vectorization-quality-gate/2026-05-22](../../../automation-runs/wave10-vectorization-quality-gate/2026-05-22/README.md)
- Checker：`ops/search-lab/scripts/wave10_vectorization_quality_gate.py`

## 对 OSS node platform 的约束

- `vector_search` / external-search 类节点后续只能消费带 `retrieval_mode`、provider trace、fallback reason 和 benchmark threshold 的 evidence；不能把 fixture benchmark 当作真实 embedding 质量证明。
- open-source search provider trace 继续区分 explicit provider route 与 `provider=auto` route，避免 SearXNG / YaCy 在未验收时混入默认平台能力。
- `local_index` search result contract 继续以 `keyword|vector|hybrid` 为唯一 mode 集合，fallback 必须保留 `fallback_from` / `fallback_reason`，便于节点 trace artifact 解释降级路径。

## 本次 deterministic gate 覆盖

- provider trace：`searxng`、`yacy` explicit-only，`provider=auto` 未调用 local open-search provider。
- runtime smoke：已复核既有 LanceDB captured artifact 中 `keyword` / `vector` / `hybrid` 均无 fallback。
- benchmark threshold：3 个 ranking cases、3 个 filter cases、每个 ranking case 至少 3 次 repeat。
- fallback fixture：fake LanceDB table 触发 `vector` / `hybrid` runtime exception，结果 fallback 到 keyword，trace 写入 `fallback_reason=RuntimeError`。

## 保留缺口

- 不声明 live containers 当前可用。
- 不声明生产 embedding 语义质量达标。
- 不关闭统一 vector object schema、embedding version/provenance 与主搜索 evidence contract。
