#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
RUN_ONE="$ROOT/codex_settings/frozen_v1/scripts/run_cluster.sh"

# Phase 0 (serial): interface freeze
bash "$RUN_ONE" C0

# Phase 1 (parallel): 8 chains
clusters=(C1 C2 C3 C4 C5 C6 C7 C8)
for c in "${clusters[@]}"; do
  bash "$RUN_ONE" "$c" &
done
wait

echo "All clusters completed."
