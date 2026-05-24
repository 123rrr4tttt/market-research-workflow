# Wave56 Semantic Vector Quality Gate

日期：2026-05-23

状态：`repo_local_semantic_quality_closed` / `production_vector_quality_reduced`

## 结论

Wave56 新增可复跑的 repo-local semantic/vector quality gate，不再只用 Wave55 的三条受控 top-1 smoke case 作为质量证据。

本轮可关闭的范围：

- `semantic_embedding_quality_not_proven`：在 repo-local provider path 和冻结 production-like evaluation set 范围内关闭。Gate 覆盖 5 个 domain、8 个 paraphrase/hard-negative case、3 次 repeat stability，并要求 `top1_accuracy=1.0`、`recall_at_3=1.0`、`mrr=1.0`、hard-negative margin 达标。

本轮只能降低但不迁 closed 的范围：

- `production_vector_quality_not_proven`：已补 production-like corpus 质量证据，但仍缺真实生产流量或生产语料 replay；因此本目标仍不应迁入 `ARCHIVE_CLOSED`。

## 落地

- `main/backend/app/services/local_index/embedding_provider.py` 将 repo-local provider 版本提升到 `2026-05-23.wave56` / `repo-local-live-v2`，默认 embedding dim 从 64 提升到 512，并补充 robotics / policy / agriculture / energy / safety / event-ops 语义别名，降低 hash collision 对排名的影响。
- `ops/search-lab/scripts/wave56_semantic_vector_quality_gate.py` 新增 semantic/vector quality gate，输出 provider readback、query case metrics、hard-negative margin、repeat stability 与 `search_evidence_hit.v1` / `search_retrieval_run.v1` readback。
- `main/backend/tests/unit/test_wave56_semantic_vector_quality_gate_unittest.py` 覆盖 closure claim、质量阈值、provider metadata 与 retrieval-run readback。

## 证据

- Evidence：[wave56-semantic-vector-quality-gate/2026-05-23](../../../automation-runs/wave56-semantic-vector-quality-gate/2026-05-23/README.md)
- JSON：`development/latest-dev-docs/automation-runs/wave56-semantic-vector-quality-gate/2026-05-23/semantic_vector_quality_gate.json`

关键读数：

- `status=passed`
- `domain_count=5`
- `case_count=8`
- `top1_accuracy=1.0`
- `recall_at_3=1.0`
- `mrr=1.0`
- `min_top2_margin=0.170647`
- `min_hard_negative_margin=0.170647`
- `closed_conditions=["semantic_embedding_quality_not_proven"]`
- `reduced_conditions=["production_vector_quality_not_proven"]`

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave56_semantic_vector_quality_gate.py --out-dir development/latest-dev-docs/automation-runs/wave56-semantic-vector-quality-gate/2026-05-23
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_local_index_service_unittest.py \
  main/backend/tests/unit/test_wave55_live_embedding_provider_gate_unittest.py \
  main/backend/tests/unit/test_wave56_semantic_vector_quality_gate_unittest.py
```

## 边界

本文件只记录本目标内部的 semantic/vector quality 进展，不更新全局 manifest / CURRENT_DEV。若要把 `production_vector_quality_not_proven` 从全局 blocker 移除，仍需真实生产流量或生产语料 replay 的证据。
