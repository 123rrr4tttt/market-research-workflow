# Wave55 OSS Node Search Quality Gate

- Status: `repo_local_search_quality_validated`
- Decision date: 2026-05-23
- Evidence: [wave55-oss-node-search-quality-gate/2026-05-23](../../../automation-runs/wave55-oss-node-search-quality-gate/2026-05-23/README.md)
- Checker: `ops/search-lab/scripts/wave55_oss_node_search_quality_gate.py`
- Unit gate: `main/backend/tests/unit/test_wave55_oss_node_search_quality_gate_unittest.py`
- Shared/global indexes edited: `false`

## Result

Wave55 adds a deterministic repo-local quality gate for the two remaining OSS-node search-quality concerns.

The gate reads back the existing open-search provider trace and live embedding provider gate, then runs controlled quality cases for:

- explicit local open-search providers: `searxng` and `yacy`
- repo-local semantic retrieval using `RepoLocalHashingEmbeddingProvider`
- `search_evidence_hit.v1` and `search_retrieval_run.v1` readback for the semantic top hits

The evidence artifact records:

- `open_search_quality_readback.status=passed`
- `open_search_quality_readback.top1_accuracy=1.0`
- `open_search_quality_readback.min_top_margin=14.5`
- `semantic_quality_readback.status=passed`
- `semantic_quality_readback.top1_accuracy=1.0`
- `semantic_quality_readback.min_top_margin=0.07752`
- `retrieval_contracts.status=passed`

## Closed / Reduced Scope

Closed for the deterministic repo-local target scope:

- `local_open_search_live_quality_not_sealed`

The closure is scoped to controlled local open-search ranking quality and explicit provider trace readback. It does not claim that live SearXNG / YaCy containers were started, stable, or production-ranked.

Reduced but not fully closed:

- `semantic_embedding_quality_not_proven`

The repo-local controlled semantic top-k and retrieval-run readback now pass. Production/public-corpus semantic relevance remains open.

## Remaining External Scope

The target should stay under `ARCHIVE_EXTERNAL_BLOCKED` until a supervisor/global lane decides whether to accept this scoped reduction. Remaining production/live-container evidence:

- `local_open_search_live_container_quality_not_replayed`
- `production_semantic_embedding_quality_not_proven`

## Verification

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave55_oss_node_search_quality_gate.py --out-dir development/latest-dev-docs/automation-runs/wave55-oss-node-search-quality-gate/2026-05-23
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave55_oss_node_search_quality_gate_unittest.py
```
