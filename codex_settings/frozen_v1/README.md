# Frozen v1 Execution Pack

This pack launches Codex main clusters for full 8-chain implementation and forces each cluster to decompose into atomic sub-agent jobs.

## Structure
- `targets.txt`: core paths touched by Frozen v1.
- `prompts/clusters/*.md`: cluster-specific execution prompts.
- `scripts/run_cluster.sh`: run one cluster.
- `scripts/run_all_clusters.sh`: run interface freeze then 8 chains.
- `scripts/collect_results.sh`: summarize outputs.
- `logs/`: per-cluster JSONL + stdout logs.
- `artifacts/`: per-cluster final message files.

## Quick Start
```bash
bash codex_settings/frozen_v1/scripts/run_all_clusters.sh
bash codex_settings/frozen_v1/scripts/collect_results.sh
```

## Notes
- Default model is `gpt-5`; override by `MODEL=...`.
- Each cluster prompt enforces:
  - strict file boundaries
  - atomic task decomposition (`goal/input/output/acceptance`)
  - sub-agent parallelization where possible
  - fixed return format: `结果/改动文件/验证状态/风险`
