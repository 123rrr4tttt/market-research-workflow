# Global Vectorization General Foundation Index

更新时间：2026-05-23 PST<br>
状态：`external_blocked` / `wave30_checked`。全项目数据向量化 / 标准化 repo-local blocker 已由 Wave30 清零；目录已从 `CURRENT_DEV` 迁入 `ARCHIVE_EXTERNAL_BLOCKED`。剩余条件是真实 live embedding provider、`semantic_embedding_quality_not_proven` 与 production vector quality，不再作为当前仓内 `partial` 入口。

防误读：下方 Wave2/Wave3/Wave8/Wave10 段落中的 `partial` 是历史快照；当前 canonical readback 以本 `INDEX.md` 和 `11_wave30-vector-closure-external-blocked-decision-2026-05-23.md` 为准。

## 文件

- [01_global-vectorization-general-foundation-plan-2026-05-14.md](./01_global-vectorization-general-foundation-plan-2026-05-14.md)  
  全项目向量化基础层总体方案：已按当前代码实现更新，覆盖 `hybrid.py` 的 ES/BM25 + Qdrant primary + pgvector fallback + RRF、`policy.py` 向量 contract、`local_index` LanceDB FTS prototype，以及 Agent matrix contract 所需的 query branch / evidence / verification / merge-rank 要求。

- [02_local-index-hybrid-retrieval-vectorization-routing-2026-05-14.md](./02_local-index-hybrid-retrieval-vectorization-routing-2026-05-14.md)  
  LanceDB vector / hybrid retrieval 的归属定位文档：2026-05-22 已补 `local_index` optional runtime smoke 与受控 benchmark-quality evidence，但真实 embedding model 语义质量和全项目 evidence contract 仍归本开发线继续推进。

- [03_wave10-vectorization-quality-gate-2026-05-22.md](./03_wave10-vectorization-quality-gate-2026-05-22.md)
  Wave10 worker6 deterministic quality gate：复核 provider trace、`keyword|vector|hybrid` runtime/benchmark evidence、benchmark threshold 与 vector/hybrid fallback reason；继续保留真实 embedding semantic quality 与全局 vector contract 缺口。

- [04_wave12-provider-readiness-gate-2026-05-22.md](./04_wave12-provider-readiness-gate-2026-05-22.md)
  Wave12 provider readiness gate。

- [05_wave14-vectorization-provider-capability-2026-05-22.md](./05_wave14-vectorization-provider-capability-2026-05-22.md)
  Wave14 provider capability gate。

- [06_wave18-vectorization-hybrid-readback-2026-05-22.md](./06_wave18-vectorization-hybrid-readback-2026-05-22.md)
  Wave18 hybrid readback gate。

- [07_wave19-vectorization-provider-manifest-2026-05-22.md](./07_wave19-vectorization-provider-manifest-2026-05-22.md)
  Wave19 provider manifest readback。

- [08_wave22-vectorization-provider-external-blocked-decision-2026-05-22.md](./08_wave22-vectorization-provider-external-blocked-decision-2026-05-22.md)
  Wave22 provider external-blocked decision。

- [09_wave27-vectorization-closure-decision-2026-05-23.md](./09_wave27-vectorization-closure-decision-2026-05-23.md)
  Wave27 closure decision showing repo-local blockers still existed before Wave30。

- [10_wave29-vector-schema-alignment-2026-05-23.md](./10_wave29-vector-schema-alignment-2026-05-23.md)
  Wave29 repo-local schema gate：新增 `search_evidence_hit.v1` / `global_vector_object.v1` builder 与 validator，并让 `/api/v1/search` 在保持 legacy `results` 不变的同时返回并行 `evidence_hits`，关闭 `unified_vector_object_contract_not_frozen` 与 `main_search_evidence_hit_contract_not_aligned` 两个 blocker。

- [11_wave30-vector-closure-external-blocked-decision-2026-05-23.md](./11_wave30-vector-closure-external-blocked-decision-2026-05-23.md)
  Wave30 external-blocked decision：关闭 retrieval run JSONL persistence/readback、qdrant/pgvector payload provenance 统一、Agent matrix/main search schema join 三个 repo-local blocker；剩余条件均为外部 provider / production quality evidence。

## 2026-05-22 lane 9 落地

- 分支：`codex/devdocs-local-index-runtime`
- 证据：[devdocs-lane-9-local-index-runtime-2026-05-22](../../../automation-runs/devdocs-lane-9-local-index-runtime-2026-05-22/README.md)
- 已落地：`LocalIndexQuery.mode` 合法值冻结为 `keyword|vector|hybrid`；service 规范化未知 mode；LanceDB adapter 按 mode 分发 FTS/vector/hybrid；result 返回 `retrieval_mode/retrieval_family/trace`。
- 已验证：`git diff --check`、`py_compile`、`test_local_index_service_unittest.py`。
- 环境边界：lane 9 当时的 Python 环境未安装 `lancedb`，真实 LanceDB runtime smoke 需看后续 optional dependency 环境证据。

## 2026-05-22 Wave2 A/B evidence

- 分支：`codex/devdocs-lancedb-runtime-smoke`、`codex/devdocs-local-index-runtime-artifacts`
- Runtime 证据：[local-index-lancedb-runtime-smoke/2026-05-22](../../../automation-runs/local-index-lancedb-runtime-smoke/2026-05-22/README.md)
- Contract 证据：[local-index-runtime-contract/2026-05-22](../../../automation-runs/local-index-runtime-contract/2026-05-22/README.md)
- 文档收口：`mode=keyword|vector|hybrid` 的 schema/service/result/adapter 证据、CURRENT_DEV 状态、复跑命令已集中到证据包。
- Runtime 事实：`lancedb==0.24.2` / `pyarrow==24.0.0` 环境中，`keyword`、`vector`、`hybrid` 均在真实 LanceDB table 上返回预期 top row，未触发 fallback。
- 状态判定：本目录保持 `partial`，不迁入 `ARCHIVE_CLOSED`。下一步未封口项是 embedding/ranking benchmark、统一 vector object schema、主搜索 evidence contract 和 Agent/WritingWorkbench 对齐。

## 2026-05-22 Wave3 A benchmark evidence

- 分支：`codex/devdocs-wave3-lancedb-benchmark`
- Benchmark 证据：[local-index-lancedb-benchmark/2026-05-22](../../../automation-runs/local-index-lancedb-benchmark/2026-05-22/README.md)
- 已落地：`ops/search-lab/scripts/local_index_lancedb_benchmark_quality.py`，用受控数据集重复验证 `keyword`、`vector`、`hybrid` 的 top-2 排名稳定性、`project_id/source_id` filter 隔离和 result `trace` 字段。
- Runtime 事实：`lancedb==0.24.2` / `pyarrow==24.0.0` 环境中，三种 mode 的受控 benchmark 均通过，且 vector/hybrid 未触发 keyword fallback。
- 状态判定：受控 adapter ranking benchmark 已推进；本目录仍保持 `partial`，因为真实 embedding model 的语义相关性、embedding version/provenance 和主搜索 evidence contract 尚未封口。

## 2026-05-22 Wave8-8 deterministic closure slice

- 分支：`codex/devdocs-wave8-search-vectorization`
- Evidence：[wave8-search-vectorization-contract/2026-05-22](../../../automation-runs/wave8-search-vectorization-contract/2026-05-22/README.md)
- 已落地：`ops/search-lab/scripts/wave8_search_vectorization_contract.py` 将 search provider trace、SearXNG/YaCy container replay 摘要、LanceDB runtime smoke、LanceDB benchmark 串成一个无外网、无容器启动的 deterministic gate。
- 已验证：`local_index` 的 `keyword|vector|hybrid` runtime smoke 与 benchmark evidence 均为 `passed`，且 checker 继续保留真实 embedding 语义质量、全局 vector contract、当前容器可用性未复跑三个缺口。
- 状态判定：本 slice 关闭的是 evidence 漂移与 contract 复核缺口，不改变本目录 `partial` 状态。

## 2026-05-22 Wave10 worker6 quality gate

- 分支：`codex/devdocs-wave10-vectorization-quality`
- Evidence：[wave10-vectorization-quality-gate/2026-05-22](../../../automation-runs/wave10-vectorization-quality-gate/2026-05-22/README.md)
- 已落地：`ops/search-lab/scripts/wave10_vectorization_quality_gate.py` 对 provider trace、runtime smoke、benchmark fixture threshold 与 fallback reason 做统一 deterministic 检查；新增 unit gate 覆盖 contract 输出。
- 已验证：`quality_thresholds.required_modes=keyword, vector, hybrid`；ranking/filter case 数与 repeat 数达标；`vector` / `hybrid` runtime exception fallback 到 keyword 时保留 `fallback_from` 与 `fallback_reason=RuntimeError`。
- 状态判定：这是质量门槛与 trace 可解释性推进，不把受控 fixture benchmark 宣称为生产 embedding 语义质量封口。

## 当前边界

- 搜索 provider 解隔离继续归 `../2026-05-14-local-open-search-provider-isolation/`。
- 数据向量化、chunk/material 标准化、hybrid retrieval、向量版本化和 provenance 归本目录。
- 本目录已开始落地 runtime contract 与受控 benchmark evidence；lane 9/Wave3 A 均保持 `local_index` optional boundary，不引入 LanceDB 强依赖。
- Wave30 已关闭仓内 retrieval persistence、stored payload provenance、Agent matrix join blocker，但不声明 live embedding provider 或生产语义质量已封口。
- 02 号文档本来就是 2026-05-14 文档，文件名和主体保留；仅由本目录索引继续引用。
