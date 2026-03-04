#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
POLICY="$ROOT/docs/governance/api_versioning_policy.md"
REGISTRY="$ROOT/docs/governance/feature_flag_killswitch_registry.yaml"

[[ -f "$POLICY" ]] && [[ -f "$REGISTRY" ]]

grep -q "Compatibility window" "$POLICY"
grep -q "Deprecation policy" "$POLICY"
grep -q "Migration announcement template" "$POLICY"
grep -q "kill switch" "$POLICY"

grep -q "kill_switch: true" "$REGISTRY"
grep -q "service_owner:" "$REGISTRY"
grep -q "data_owner:" "$REGISTRY"
grep -q "alert_owner:" "$REGISTRY"

echo "R8.1-A verify: PASS"
