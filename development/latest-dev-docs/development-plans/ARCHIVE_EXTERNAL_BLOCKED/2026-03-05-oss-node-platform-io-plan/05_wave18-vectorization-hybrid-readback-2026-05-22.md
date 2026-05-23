# Wave18 OSS Node Vectorization Readback Evidence

- Status: OSS node platform IO partial; deterministic local readback slice passed
- Branch: `codex/devdocs-wave18-vectorization-hybrid-readback`
- Evidence: [wave18-vectorization-hybrid-readback/2026-05-22](../../../automation-runs/wave18-vectorization-hybrid-readback/2026-05-22/README.md)
- Checker: `ops/search-lab/scripts/wave18_vectorization_hybrid_readback.py`
- Unit gate: `main/backend/tests/unit/test_wave18_vectorization_hybrid_readback_unittest.py`

## Node IO Contract

Wave18 fixes the node-facing local readback fields that OSS node IO can consume:

- `retrieval_mode`
- `retrieval_family`
- `trace.requested_mode`
- `trace.executed_mode`
- `trace.quality_trace.score_components`
- `trace.readback.chunk_id`
- `trace.readback.project_id`
- `trace.readback.source_id`

The checker also fixes the fields that must keep propagating as gaps:

- `provider_live_verified=false`
- `semantic_quality_claim_allowed=false`
- `closure_claim_allowed=false`

## What This Proves

The repo-local fixture returns stable top-k identity for `keyword`, `vector`, and `hybrid`, with mode-specific quality trace and readback metadata. This is enough for node IO to assert that local vectorization fields survive a deterministic readback path.

## What Remains Open

This is not an OSS node live SLA closure. It does not prove:

- external embedding provider availability;
- SearXNG/YaCy live quality or `provider=auto` promotion;
- production semantic relevance;
- graph/node runtime propagation under live scheduler or tenant DB conditions.

## Verification

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave18_vectorization_hybrid_readback.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave18_vectorization_hybrid_readback_unittest.py
python3 scripts/check_current_dev_wave18_plan.py
git diff --check
```
