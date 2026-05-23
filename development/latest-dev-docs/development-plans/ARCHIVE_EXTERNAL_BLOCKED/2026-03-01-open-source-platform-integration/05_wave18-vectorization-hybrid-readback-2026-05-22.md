# Wave18 Vectorization Hybrid Readback Evidence

- Status: open-source platform integration partial; deterministic local readback slice passed
- Branch: `codex/devdocs-wave18-vectorization-hybrid-readback`
- Evidence: [wave18-vectorization-hybrid-readback/2026-05-22](../../../automation-runs/wave18-vectorization-hybrid-readback/2026-05-22/README.md)
- Checker: `ops/search-lab/scripts/wave18_vectorization_hybrid_readback.py`
- Unit gate: `main/backend/tests/unit/test_wave18_vectorization_hybrid_readback_unittest.py`

## What This Lands

Wave18 adds a repo-local checker that reads Wave8 search/vector contract, Wave10 vectorization quality gate, Wave12 provider readiness, and Wave14 provider capability evidence, then runs a deterministic fixture through `LocalIndexService`.

The fixture proves:

- `keyword`, `vector`, and `hybrid` preserve requested/executed mode identity.
- `trace.quality_trace.score_components` is present for returned rows.
- `trace.readback` mirrors the returned chunk, project, source, and retrieval mode.
- `closure_claim_allowed=false` remains part of the contract.

## Open-Source Platform Impact

The platform integration topic can now rely on a machine-checkable local contract for mode identity and readback. This narrows the platform integration gap from "mode behavior is only described in docs" to "mode identity and readback are covered by a repo-local checker and unit test."

This does not promote local open-search providers into `provider=auto`, and it does not close live provider quality.

## Remaining Gaps

1. `live_provider_quality_not_closed`: no external embedding provider or SearXNG/YaCy live call is made.
2. `semantic_embedding_quality_not_proven`: deterministic vectors prove wiring and trace readback, not production semantic relevance.
3. `oss_node_platform_io_sla_not_closed`: node-level propagation still needs its own live/SLA evidence.

## Verification

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave18_vectorization_hybrid_readback.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave18_vectorization_hybrid_readback_unittest.py
python3 scripts/check_current_dev_wave18_plan.py
git diff --check
```
