# Wave14 Vectorization Provider Capability Gate

- status: `passed`
- capability_state: `partial`
- closure_claim_allowed: `false`
- contract_version: `wave14-vectorization-provider-capability.v1`
- scope: `deterministic_repo_contract_no_network_no_container_start_no_external_provider_seal`

## Gate Semantics

- status passed means: repo-controlled local capability contract, recorded evidence, and external gap reporting are valid
- status passed does not mean: external embedding providers, SearXNG/YaCy live quality, provider=auto promotion, semantic quality, or OSS node SLA are sealed

## Local Capability

| mode | recorded_runtime | recorded_benchmark | fallback_visible | current_live_probe | current_live_gap |
|---|---:|---:|---:|---|---|
| keyword | true | true | true | blocked | missing_optional_dependency |
| vector | true | true | true | blocked | missing_optional_dependency |
| hybrid | true | true | true | blocked | missing_optional_dependency |

## External Provider Gap

| provider | route | auto_included | current_live_probe | current_live_gap | claim_allowed |
|---|---|---:|---|---|---:|
| searxng | explicit:searxng | false | unavailable | ConnectError | false |
| yacy | explicit:yacy | false | unavailable | ConnectError | false |

## Embedding Provider Branches

| provider | required config | live_verified_by_gate |
|---|---|---:|
| openai | OPENAI_API_KEY | false |
| azure | AZURE_API_BASE, AZURE_API_KEY, AZURE_API_VERSION, AZURE_EMBEDDING_DEPLOYMENT | false |
| ollama | OLLAMA_BASE_URL | false |
| litellm | LITELLM_API_BASE, LITELLM_API_KEY | false |

## Gap Codes

- `external_embedding_provider_live_not_verified`
- `provider_auto_promotion_not_allowed`
- `local_open_search_live_quality_not_sealed`
- `semantic_embedding_quality_not_proven`
- `oss_node_platform_io_sla_not_closed`

## Rerun

```bash
PYTHONPATH=main/backend python3 main/backend/scripts/check_wave14_vectorization_provider_capability.py --out-dir development/latest-dev-docs/automation-runs/wave14-vectorization-provider-capability/2026-05-22
```

Full deterministic output is in `provider_capability_summary.json`.
