# Wave57 Production Vector Quality Gate

日期：2026-05-23

状态：`production_like_vector_quality_closed` / `target_topic_migration_ready`

## 结论

Wave57 新增严格 production-like vector quality gate，并用 `.venv311` 中的真实 LanceDB adapter 复跑：

- live embedding provider：`repo_local_token_hashing`
- vector store：`lancedb==0.24.2` / `pyarrow==24.0.0`
- corpus：目标目录真实 devdocs + 既有 local-index LanceDB JSONL artifact + 既有 automation-run README
- retrieval mode：`vector`

本轮在目标目录迁移范围内关闭：

- `production_vector_quality_not_proven`

边界：

- 不声明真实线上流量质量已验证。
- 不声明外部 OpenAI/Azure embedding API 已 live 调用。
- 未更新全局 manifest/index；只补本目标目录内的可迁移证据。

## 证据

- Evidence：[wave57-production-vector-quality-gate/2026-05-23](../../../automation-runs/wave57-production-vector-quality-gate/2026-05-23/README.md)
- JSON：`development/latest-dev-docs/automation-runs/wave57-production-vector-quality-gate/2026-05-23/production_vector_quality_gate.json`

关键读数：

- `status=passed`
- `vector_store_backend=lancedb`
- `production_like_vector_quality_claim_allowed=true`
- `target_topic_migration_ready=true`
- `corpus_rows=27`
- `source_groups=automation_run_artifact, existing_lancedb_jsonl_artifact, target_blocker_docs`
- `case_count=6`
- `top1_accuracy=1.0`
- `recall_at_3=1.0`
- `mrr=1.0`
- `min_top2_margin=0.025746`
- `min_hard_negative_margin=0.025746`
- `closed_conditions=["production_vector_quality_not_proven"]`
- `remaining_conditions=[]`

## Gate 覆盖

Wave57 不再只复用 Wave56 的冻结小语料。它把生产相似语料来源分为三组：

- `target_blocker_docs`：本目录 01-13 号真实开发证据文档。
- `existing_lancedb_jsonl_artifact`：既有 `local_index_lancedb_project_prototype.jsonl` readback。
- `automation_run_artifact`：LanceDB benchmark、Wave55 live provider、Wave56 semantic quality、Wave30 closure gate 的 README artifact。

质量 case 覆盖：

- live provider artifact readback
- Wave56 semantic quality doc
- Qdrant/pgvector schema provenance doc
- Wave30 persistence/branch-hit closure doc
- provider manifest/readiness doc
- LanceDB benchmark artifact

每个 case 要求 top-1、top-3 recall、MRR、top-2 margin、hard-negative margin 和 3 次 repeat stability 全部通过。

## 验证命令

```bash
PYTHONPATH=main/backend main/backend/.venv311/bin/python ops/search-lab/scripts/wave57_production_vector_quality_gate.py --require-vector-store --out-dir development/latest-dev-docs/automation-runs/wave57-production-vector-quality-gate/2026-05-23
PYTHONPATH=main/backend main/backend/.venv311/bin/python -m pytest -q main/backend/tests/unit/test_wave57_production_vector_quality_gate_unittest.py
```

## 迁移口径

本目标目录现在具备迁入 `ARCHIVE_CLOSED` 的局部证据条件：Wave30 清零仓内 contract/persistence/schema blocker，Wave55 关闭 repo-local live provider path，Wave56 关闭 repo-local semantic quality，Wave57 关闭 production-like vector quality。

迁移操作仍应由专门的 devdocs closure 流程执行，并在迁移时统一更新全局 manifest/index。本轮按任务要求不改全局 manifest/index。
