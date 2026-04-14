#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${1:-$(pwd)}"
ARTIFACT_DIR="$TARGET_DIR/artifacts/quality"
REPORT_JSON="$ARTIFACT_DIR/r9-ef-verification.json"

require_file() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    echo "[r9-ef] missing file: $f" >&2
    return 1
  fi
}

require_json_key() {
  local f="$1"; shift
  local key="$1"
  python3 - "$f" "$key" <<'PY'
import json,sys
f,k=sys.argv[1],sys.argv[2]
with open(f,'r',encoding='utf-8') as fh:
    data=json.load(fh)
if k not in data:
    raise SystemExit(1)
PY
}

mkdir -p "$ARTIFACT_DIR"

DORA_FILE="$TARGET_DIR/docs/ops/dora-metrics.json"
GOLDEN_PATH_FILE="$TARGET_DIR/templates/golden-path/service-default-checklist.md"
DATA_CONTRACT_FILE="$TARGET_DIR/docs/data-contracts/market_event_flow.contract.json"
DATA_CATALOG_FILE="$TARGET_DIR/docs/data-catalog/assets/market_event_flow.asset.json"
AI_RISK_FILE="$TARGET_DIR/docs/ai/release-risk-policy.md"

require_file "$DORA_FILE"
require_file "$GOLDEN_PATH_FILE"
require_file "$DATA_CONTRACT_FILE"
require_file "$DATA_CATALOG_FILE"
require_file "$AI_RISK_FILE"

for k in lead_time_hours deploy_frequency_per_week change_fail_rate mttr_hours collected_at; do
  require_json_key "$DORA_FILE" "$k"
done

for k in schema semantics validation_rules owner consumers; do
  require_json_key "$DATA_CONTRACT_FILE" "$k"
done

for k in asset_id owner lineage_system lineage_ref; do
  require_json_key "$DATA_CATALOG_FILE" "$k"
done

grep -q "Rollback" "$GOLDEN_PATH_FILE"
grep -q "Observability" "$GOLDEN_PATH_FILE"
grep -q "Security Gate" "$GOLDEN_PATH_FILE"
grep -q "人工复核" "$AI_RISK_FILE"

python3 - "$REPORT_JSON" "$DORA_FILE" "$DATA_CONTRACT_FILE" "$DATA_CATALOG_FILE" <<'PY'
import json,sys,datetime
out,dora,contract,catalog=sys.argv[1:5]
with open(dora,'r',encoding='utf-8') as f: d=json.load(f)
with open(contract,'r',encoding='utf-8') as f: c=json.load(f)
with open(catalog,'r',encoding='utf-8') as f: m=json.load(f)
report={
  "gate":"r9_ef_required_check",
  "status":"passed",
  "checked_at":datetime.datetime.utcnow().isoformat()+"Z",
  "dora":{k:d[k] for k in ["lead_time_hours","deploy_frequency_per_week","change_fail_rate","mttr_hours","collected_at"]},
  "data_contract":{"name":c.get("name"),"owner":c.get("owner"),"version":c.get("version")},
  "metadata":{"asset_id":m.get("asset_id"),"lineage_ref":m.get("lineage_ref")}
}
with open(out,'w',encoding='utf-8') as f: json.dump(report,f,ensure_ascii=False,indent=2)
print("[r9-ef] passed")
PY
