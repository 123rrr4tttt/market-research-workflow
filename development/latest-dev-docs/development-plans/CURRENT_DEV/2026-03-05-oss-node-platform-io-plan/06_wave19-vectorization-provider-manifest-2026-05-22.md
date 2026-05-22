# Wave19 OSS Node Provider Manifest Evidence

- Status: OSS node platform IO partial; deterministic provider manifest readback passed
- Branch: `codex/devdocs-wave19-vectorization-provider-manifest`
- Evidence: [wave19-vectorization-provider-manifest/2026-05-22](../../../automation-runs/wave19-vectorization-provider-manifest/2026-05-22/README.md)
- Checker: `ops/search-lab/scripts/wave19_vectorization_provider_manifest_readback.py`
- Unit gate: `main/backend/tests/unit/test_wave19_vectorization_provider_manifest_readback_unittest.py`

## Node-Consumable Fields

Wave19 fixes a manifest shape that OSS nodes can consume without treating it as a live SLA:

- `provider_id`
- `mode`
- `capabilities.keyword`
- `capabilities.vector`
- `capabilities.hybrid`
- `fallback.fallback_mode`
- `fallback.fallback_reason`
- `trace_quality.required_components`
- `trace_quality.component_coverage`
- `trace_quality.provider_live_verified=false`

The checker also keeps these gap fields mandatory for propagation:

- `closure_claim_allowed=false`
- `live_provider_verified=false`
- `semantic_quality_claim_allowed=false`
- `external_provider_boundary.gap_codes`

## What This Proves

The repo-local provider manifest can be deterministically rebuilt from Wave14 and Wave18 evidence. `keyword`, `vector`, and `hybrid` mode capabilities, fallback mode, and trace quality are now machine-checkable before any OSS node consumes the boundary.

## What Remains Open

This is not an OSS-node live provider closure. It does not prove external provider availability, local open-search service quality, production semantic relevance, live scheduler propagation, or tenant DB/UI runtime behavior.

## Verification

```bash
PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave19_vectorization_provider_manifest_readback.py
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_wave19_vectorization_provider_manifest_readback_unittest.py
python3 scripts/check_current_dev_wave19_plan.py
git diff --check
```
