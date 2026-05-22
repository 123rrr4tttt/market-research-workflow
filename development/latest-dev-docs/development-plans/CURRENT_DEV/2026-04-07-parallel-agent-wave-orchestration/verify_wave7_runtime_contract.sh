#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

TOPIC="development/latest-dev-docs/development-plans/CURRENT_DEV/2026-04-07-parallel-agent-wave-orchestration"
AGENTS="codex_settings/AGENTS.md"
BOOTSTRAP="codex_settings/scripts/swarm_file_bootstrap.sh"
SWARM="codex_settings/scripts/swarm.sh"
WAVE7="$TOPIC/05_wave7-runtime-closure-evidence-2026-05-22.md"

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

require_file() {
  [[ -f "$1" ]] || fail "missing file: $1"
}

require_contains() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  grep -q -- "$pattern" "$file" || fail "$label not found in $file"
}

for file in \
  "$TOPIC/README.md" \
  "$TOPIC/01_parallel-agent-wave-orchestration-plan-2026-04-07.md" \
  "$TOPIC/02_subagent-task-contract-template-2026-04-07.md" \
  "$TOPIC/03_wave0-baseline-freeze-task-pool-2026-04-07.md" \
  "$TOPIC/04_wave6-evidence-closure-gap-2026-05-22.md" \
  "$WAVE7" \
  "$AGENTS" \
  "$BOOTSTRAP" \
  "$SWARM"; do
  require_file "$file"
done

require_contains "$AGENTS" "multi_agent_v1.spawn_agent" "multi-agent runtime name"
require_contains "$AGENTS" "tool_search" "tool discovery fallback"
require_contains "$AGENTS" "不要伪造子 Agent 能力" "no-fabrication fallback"
require_contains "$AGENTS" "swarm_file_bootstrap.sh" "swarm bootstrap command"
require_contains "$AGENTS" "swarm.sh" "swarm batch command"

CONTRACT="$TOPIC/02_subagent-task-contract-template-2026-04-07.md"
for field in \
  "任务 ID" \
  "任务标题" \
  "所属主题路径" \
  "所属波次" \
  "子 Agent" \
  "目标" \
  "边界" \
  "禁止项" \
  "推荐入口" \
  "验收" \
  "结果" \
  "改动文件" \
  "验证状态" \
  "风险" \
  "下一阻塞"; do
  require_contains "$CONTRACT" "$field" "required contract field $field"
done

require_contains "$BOOTSTRAP" "SWARM FILE BOOTSTRAP" "bootstrap marker"
require_contains "$BOOTSTRAP" "inbound_references_top20" "inbound references section"
require_contains "$BOOTSTRAP" "same_stem_files_top20" "same-stem section"
require_contains "$SWARM" "JOBS=4" "default bounded concurrency"
require_contains "$SWARM" "RETRIES=1" "default retry count"
require_contains "$SWARM" "swarm summary" "batch summary"
require_contains "$SWARM" "swarm_file_bootstrap.sh" "batch bootstrap delegation"
require_contains "$WAVE7" 'Status: `partial`' "Wave7 partial status"

check_topic_links() {
  local md="$1"
  local dir link clean target
  dir="$(dirname "$md")"
  while IFS= read -r link; do
    [[ -z "$link" ]] && continue
    case "$link" in
      http://*|https://*|mailto:*|\#*|/*)
        continue
        ;;
    esac
    clean="${link%%#*}"
    [[ -z "$clean" ]] && continue
    target="$dir/$clean"
    [[ -e "$target" ]] || fail "broken markdown link in $md: $link"
  done < <(grep -oE '\]\([^ )]+' "$md" | sed 's/^](//')
}

for md in "$TOPIC"/*.md; do
  check_topic_links "$md"
done

bootstrap_output="$(bash "$BOOTSTRAP" "$WAVE7")"
grep -q "=== SWARM FILE BOOTSTRAP ===" <<<"$bootstrap_output" \
  || fail "bootstrap output missing header"
grep -q "target: $WAVE7" <<<"$bootstrap_output" \
  || fail "bootstrap output missing Wave7 target"

echo "WAVE7_RUNTIME_CONTRACT_OK"
