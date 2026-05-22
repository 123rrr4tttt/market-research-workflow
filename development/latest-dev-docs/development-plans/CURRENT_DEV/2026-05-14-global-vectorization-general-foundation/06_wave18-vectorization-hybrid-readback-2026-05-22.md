# Wave18 Vectorization Hybrid Readback Gate

- Status: global vectorization foundation partial; deterministic local readback slice passed
- Branch: `codex/devdocs-wave18-vectorization-hybrid-readback`
- Evidence: [wave18-vectorization-hybrid-readback/2026-05-22](../../../automation-runs/wave18-vectorization-hybrid-readback/2026-05-22/README.md)
- Checker: `ops/search-lab/scripts/wave18_vectorization_hybrid_readback.py`
- Unit gate: `main/backend/tests/unit/test_wave18_vectorization_hybrid_readback_unittest.py`

## Contract Summary

`wave18-vectorization-hybrid-readback.v1` is a deterministic repo-local contract. It does not start containers, does not access the network, and does not assert live provider closure.

Mode readback results:

| mode | expected top order | result |
|---|---|---|
| `keyword` | `kw-primary`, `kw-secondary` | passed |
| `vector` | `vec-primary`, `vec-secondary` | passed |
| `hybrid` | `hybrid-primary`, `hybrid-secondary` | passed |

Each row includes:

- `retrieval_mode=keyword|vector|hybrid`
- `trace.requested_mode`
- `trace.executed_mode`
- `trace.quality_trace.score_components`
- `trace.readback.chunk_id`
- `trace.readback.project_id`
- `trace.readback.source_id`

## Foundation Impact

This closes the narrow local readback gap left after Wave10/Wave12/Wave14: local vectorization mode identity can now be checked without optional LanceDB runtime dependencies or live provider availability.

The topic remains `partial` because production semantic embedding quality, external provider probes, provider auto-promotion, and OSS node SLA are still explicitly outside this gate.

## Non-Closure Boundary

- `closure_claim_allowed=false`
- `provider_live_closure_claim_allowed=false`
- `semantic_quality_claim_allowed=false`

## Verification

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave18_vectorization_hybrid_readback.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave18_vectorization_hybrid_readback_unittest.py
python3 scripts/check_current_dev_wave18_plan.py
git diff --check
```
