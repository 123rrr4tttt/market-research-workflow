# Wave12 Provider Readiness Gate

- status: `passed`
- readiness_state: `partial`
- contract_version: `wave12-provider-readiness-gate.v1`
- scope: `bounded_repo_controlled_current_probe_no_container_start_no_auto_promotion`

## Gate Semantics

- status passed means: required recorded contracts and report shape are valid
- status passed does not mean: live provider quality, provider=auto promotion, semantic embedding quality, or OSS node SLA closure
- live probe failures are: reported as readiness gaps unless recorded contract evidence is missing or malformed

## Mode Availability

| mode | recorded_runtime | recorded_benchmark | live_probe | live_executed_mode | fallback_from | fallback_reason |
|---|---:|---:|---|---|---|---|
| keyword | true | true | blocked |  |  | missing_optional_dependency |
| vector | true | true | blocked |  |  | missing_optional_dependency |
| hybrid | true | true | blocked |  |  | missing_optional_dependency |

## Provider Availability

| provider | route | auto_included | live_probe | live_result_count | fallback_reason |
|---|---|---:|---|---:|---|
| searxng | explicit:searxng | false | unavailable | 0 | ConnectError |
| yacy | explicit:yacy | false | unavailable | 0 | ConnectError |

## Unsupported Claims

- `provider_auto_quality_not_closed`: SearXNG and YaCy can be promoted into provider=auto. Reason: The accepted contract still keeps local open-search providers explicit-only pending quality, timeout, approval-gate, and operator policy evidence.
- `current_provider_live_quality_not_closed`: Current SearXNG and YaCy live provider quality is proven. Reason: Wave12 only records current probe status without starting containers: {'searxng': 'unavailable', 'yacy': 'unavailable'}.
- `current_local_index_live_quality_not_closed`: Current keyword/vector/hybrid local-index quality is fully proven. Reason: Wave12 mode probes are bounded local readiness checks, not production corpus relevance tests: {'keyword': 'blocked', 'vector': 'blocked', 'hybrid': 'blocked'}.
- `semantic_embedding_quality_not_closed`: Deterministic vector fixtures prove production embedding semantic quality. Reason: Wave8/Wave10 fixtures prove adapter wiring, mode routing, filter behavior, and trace visibility only.
- `oss_node_platform_io_not_closed`: OSS node platform IO can consume search/vector outputs as a live SLA-backed primitive. Reason: Node IO can consume explicit trace fields, but live provider readiness and global vector object provenance remain partial.

## Rerun

```bash
/Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave12_provider_readiness_gate.py --out-dir development/latest-dev-docs/automation-runs/wave12-provider-readiness/2026-05-22
```

Full JSON evidence is in `provider_readiness_summary.json`.
