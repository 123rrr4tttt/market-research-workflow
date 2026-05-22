# Wave13 CURRENT_DEV MERGED_OVERVIEW RAG Drift Gate

- date: 2026-05-22
- branch: `codex/devdocs-wave13-merged-overview-drift-gate`
- scope: `development/latest-dev-docs/development-plans/CURRENT_DEV/MERGED_OVERVIEW/` plus a dedicated checker
- status: partial; drift gate advanced
- shared navigation: No top-level MERGED_OVERVIEW.md edits

## Summary

The topic-local Round2 RAG note remains useful as historical intent, but its
repo anchors no longer exist in the current tree. The current repo authority is
the `local_index` service family plus the Wave8, Wave10, and Wave12
vectorization/readiness gates.

This worker does not close the global vectorization foundation or edit
`development/latest-dev-docs/MERGED_OVERVIEW.md`. It records the bounded drift
mapping and adds a checker that fails when old RAG anchors are treated as
current files or when the current local-index/vectorization anchors disappear.

## Legacy Drift

Legacy source: [02_rag-incremental-best-practice-pool-round2.md](./02_rag-incremental-best-practice-pool-round2.md)

| Legacy Round2 mapping | Current repo state | Gate status |
|---|---|---|
| `main/backend/app/services/rag/minimal_rag.py` for metadata filter and stable chunk id | Path is absent. Current retrieval slice lives under [main/backend/app/services/local_index/schema.py](../../../../../main/backend/app/services/local_index/schema.py), [main/backend/app/services/local_index/service.py](../../../../../main/backend/app/services/local_index/service.py), and [main/backend/app/services/local_index/adapters/lancedb_adapter.py](../../../../../main/backend/app/services/local_index/adapters/lancedb_adapter.py). | `missing_current_repo_anchor`; current bounded gate |
| `main/backend/scripts/rag_eval.py` for Recall/MRR/NDCG | Path is absent. Current deterministic quality evidence is captured by [ops/search-lab/scripts/wave10_vectorization_quality_gate.py](../../../../../ops/search-lab/scripts/wave10_vectorization_quality_gate.py) and [development/latest-dev-docs/automation-runs/local-index-lancedb-benchmark/2026-05-22/benchmark_quality_results.json](../../../automation-runs/local-index-lancedb-benchmark/2026-05-22/benchmark_quality_results.json). | `missing_current_repo_anchor`; benchmark gate replaces, but does not prove production semantic quality |
| `main/backend/tests/unit/test_minimal_rag_unittest.py` for minimal RAG tests | Path is absent. Current targeted tests are [main/backend/tests/unit/test_local_index_service_unittest.py](../../../../../main/backend/tests/unit/test_local_index_service_unittest.py), [main/backend/tests/unit/test_wave8_search_vectorization_contract_unittest.py](../../../../../main/backend/tests/unit/test_wave8_search_vectorization_contract_unittest.py), [main/backend/tests/unit/test_wave10_vectorization_quality_gate_unittest.py](../../../../../main/backend/tests/unit/test_wave10_vectorization_quality_gate_unittest.py), and [main/backend/tests/unit/test_wave12_provider_readiness_gate_unittest.py](../../../../../main/backend/tests/unit/test_wave12_provider_readiness_gate_unittest.py). | `missing_current_repo_anchor`; current checker/test anchors recorded |

## Current Anchor Map

| Current anchor | What it proves | Limit |
|---|---|---|
| [main/backend/app/services/local_index/schema.py](../../../../../main/backend/app/services/local_index/schema.py) | `LocalIndexQuery.mode` is bounded to `keyword`, `vector`, `hybrid`; chunks/results carry `chunk_id`, `document_id`, `project_id`, `source_id`, `metadata`, `retrieval_mode`, `retrieval_family`, and `trace`. | `chunk_id` is a required caller-supplied field, not the retired `_stable_chunk_id()` generator. |
| [main/backend/app/services/local_index/service.py](../../../../../main/backend/app/services/local_index/service.py) | Empty query/project input short-circuits and query mode is normalized before adapter dispatch. | The service remains a thin retrieval layer, not a full RAG orchestration service. |
| [main/backend/app/services/local_index/adapters/lancedb_adapter.py](../../../../../main/backend/app/services/local_index/adapters/lancedb_adapter.py) | LanceDB adapter dispatches FTS/vector/hybrid, applies `project_id` and optional `source_id` predicates, and reports fallback metadata for non-keyword runtime errors. | It uses deterministic vectors for local proof; it does not prove production embedding relevance. |
| [ops/search-lab/scripts/wave8_search_vectorization_contract.py](../../../../../ops/search-lab/scripts/wave8_search_vectorization_contract.py) | Reuses recorded provider/local-index evidence without claiming live containers. | Keeps `current_container_availability_not_replayed`, `semantic_embedding_quality_not_proven`, and `global_vector_contract_not_closed` open. |
| [ops/search-lab/scripts/wave10_vectorization_quality_gate.py](../../../../../ops/search-lab/scripts/wave10_vectorization_quality_gate.py) | Checks provider trace fields, local-index runtime smoke, benchmark thresholds, and fallback reason visibility. | Still deterministic fixture scope; not a global vector closure. |
| [ops/search-lab/scripts/wave12_provider_readiness_gate.py](../../../../../ops/search-lab/scripts/wave12_provider_readiness_gate.py) | Separates recorded evidence from current live readiness and unsupported claims. | Current live probes may remain blocked by optional dependency availability; `semantic_embedding_quality_not_closed` remains open. |
| [development/latest-dev-docs/automation-runs/local-index-lancedb-runtime-smoke/2026-05-22/runtime_smoke_results.json](../../../automation-runs/local-index-lancedb-runtime-smoke/2026-05-22/runtime_smoke_results.json) | Captured `keyword`, `vector`, and `hybrid` modes passed without fallback in that evidence run. | Captured artifact only; does not prove every current runtime has optional dependencies. |
| [development/latest-dev-docs/automation-runs/local-index-lancedb-benchmark/2026-05-22/benchmark_quality_results.json](../../../automation-runs/local-index-lancedb-benchmark/2026-05-22/benchmark_quality_results.json) | Captured deterministic ranking/filter benchmark passed for all three modes. | Explicitly retains `semantic_embedding_quality_not_proven` and `global_vector_contract_not_closed`. |
| [development/latest-dev-docs/automation-runs/wave10-vectorization-quality-gate/2026-05-22/contract_summary.json](../../../automation-runs/wave10-vectorization-quality-gate/2026-05-22/contract_summary.json) | Current Wave10 quality-gate summary is `passed` and includes `local_index_fallback_contract`. | Reads bounded evidence and fake fallback fixtures. |
| [development/latest-dev-docs/automation-runs/wave12-provider-readiness/2026-05-22/provider_readiness_summary.json](../../../automation-runs/wave12-provider-readiness/2026-05-22/provider_readiness_summary.json) | Readiness state remains `partial` and unsupported claims are explicit. | Not a closure signal for the global vectorization foundation. |

## Gate Decision

The current `MERGED_OVERVIEW` topic can now distinguish three states:

- historical Round2 RAG anchors: absent from the current repo and therefore not valid as current mapping evidence;
- current bounded local-index/vectorization anchors: present and checker-backed;
- remaining closure blockers: global vector object/schema alignment, production semantic relevance, and live optional-provider/runtime readiness.

This reduces the `doc_drift` risk for the topic-local row because a later
integration worker can update shared navigation from this evidence without
guessing which old RAG paths still exist. It does not remove the `partial`
status by itself.

## Focused Checker

Checker: [scripts/check_current_dev_merged_overview_drift_gate.py](../../../../../scripts/check_current_dev_merged_overview_drift_gate.py)

The checker enforces:

- old RAG anchors are still recorded in the legacy topic doc but are absent from the current repo;
- current local-index/vectorization files, tests, and JSON evidence exist;
- current anchors contain the key symbols or contract markers listed above;
- this evidence document cites each current anchor and keeps the bounded partial status text.

## Minimum Validation

```bash
python3 scripts/check_current_dev_merged_overview_drift_gate.py
python3 scripts/check_latest_dev_docs_structure.py --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/MERGED_OVERVIEW
python3 scripts/check_current_dev_wave13_plan.py
git diff --check
```

## Validation In This Branch

- `python3 scripts/check_current_dev_merged_overview_drift_gate.py`: `OK current_dev_merged_overview_drift_gate=passed old_missing=3 current_anchors=14`
- `python3 scripts/check_latest_dev_docs_structure.py --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/MERGED_OVERVIEW`: `OK latest_dev_docs_structure=passed markdown_link_files=3 markdown_links=25`
- `python3 scripts/check_current_dev_wave13_plan.py`: `OK wave13_current_dev_plan=passed mode=codex/devdocs-wave13-merged-overview-drift-gate branches=9 changed_files=3 worker_boundary_enforced=true`
- `git diff --check`: passed
- `python3 -m py_compile scripts/check_current_dev_merged_overview_drift_gate.py`: passed

## Remaining Risk

- Shared indexes are intentionally untouched in this worker branch; supervisor integration owns the final `CURRENT_DEV` and top-level `MERGED_OVERVIEW.md` wording.
- The retired RAG note still contains old paths for historical traceability; consumers must use this Wave13 gate as the current mapping.
- `semantic_embedding_quality_not_proven`, `semantic_embedding_quality_not_closed`, and `global_vector_contract_not_closed` remain real blockers, not documentation wording issues.
