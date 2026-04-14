#!/bin/bash
# Run market info ingest workflow via API.
# Usage: ./run_market_ingest.sh [query_terms...]
# Example: ./run_market_ingest.sh "lottery market" "California lottery sales"
#          ./run_market_ingest.sh "Powerball jackpot" --max 5 --provider serper

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Defaults
PROJECT_KEY="${PROJECT_KEY:-demo_proj}"
MAX_ITEMS="${MAX_ITEMS:-5}"
PROVIDER="${PROVIDER:-serper}"
ENABLE_EXTRACTION="${ENABLE_EXTRACTION:-false}"
API_URL="${API_URL:-http://localhost:8000}"

# Parse optional args
QUERY_TERMS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --max) MAX_ITEMS="$2"; shift 2 ;;
    --provider) PROVIDER="$2"; shift 2 ;;
    --project) PROJECT_KEY="$2"; shift 2 ;;
    --extract) ENABLE_EXTRACTION="true"; shift ;;
    *) QUERY_TERMS+=("$1"); shift ;;
  esac
done

if [[ ${#QUERY_TERMS[@]} -eq 0 ]]; then
  QUERY_TERMS=("lottery market report" "California lottery sales")
fi

# Build JSON array for query_terms
TERMS_JSON="["
for i in "${!QUERY_TERMS[@]}"; do
  [[ $i -gt 0 ]] && TERMS_JSON+=","
  TERMS_JSON+="\"${QUERY_TERMS[$i]}\""
done
TERMS_JSON+="]"

echo "🔍 市场信息采集: project=$PROJECT_KEY max_items=$MAX_ITEMS provider=$PROVIDER"
echo "   query_terms: ${QUERY_TERMS[*]}"
echo ""

curl -s -X POST "${API_URL}/api/v1/ingest/market" \
  -H "Content-Type: application/json" \
  -H "X-Project-Key: ${PROJECT_KEY}" \
  -d "{
    \"query_terms\": ${TERMS_JSON},
    \"max_items\": ${MAX_ITEMS},
    \"provider\": \"${PROVIDER}\",
    \"enable_extraction\": ${ENABLE_EXTRACTION},
    \"project_key\": \"${PROJECT_KEY}\"
  }" | python3 -m json.tool
