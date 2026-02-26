#!/usr/bin/env bash
set -euo pipefail
SEED_FILE="${1:-main/backend/seed_data/project_demo_proj_v0.1.5-rc1.sql}"
DB_CONTAINER="${DB_CONTAINER:-ops-db-1}"
DB_NAME="${DB_NAME:-postgres}"
DB_USER="${DB_USER:-postgres}"
TARGET_SCHEMA="${TARGET_SCHEMA:-project_demo_proj}"
STRUCTURE_SCHEMA="${STRUCTURE_SCHEMA:-project_default}"
TABLES=(
  documents
  etl_job_runs
  resource_pool_urls
  resource_pool_site_entries
  source_library_items
  ingest_channels
)
if [[ ! -f "$SEED_FILE" ]]; then
  echo "Seed file not found: $SEED_FILE" >&2
  exit 1
fi
TMP_SQL="$(mktemp)"
trap 'rm -f "$TMP_SQL"' EXIT
if [[ "$TARGET_SCHEMA" != "project_demo_proj" ]]; then
  sed "s/project_demo_proj\./${TARGET_SCHEMA}./g" "$SEED_FILE" > "$TMP_SQL"
else
  cat "$SEED_FILE" > "$TMP_SQL"
fi
# Data-only dumps still include sequence setval statements; these may fail when cloning table structures.
grep -vi "pg_catalog.setval" "$TMP_SQL" > "${TMP_SQL}.filtered"
mv "${TMP_SQL}.filtered" "$TMP_SQL"
USE_SQL="$TMP_SQL"

docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -c "CREATE SCHEMA IF NOT EXISTS ${TARGET_SCHEMA};"
for t in "${TABLES[@]}"; do
  EXISTS_SQL="select exists (select 1 from information_schema.tables where table_schema='${TARGET_SCHEMA}' and table_name='${t}');"
  EXISTS_VAL="$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -At -c "$EXISTS_SQL" | tail -n1)"
  if [[ "$EXISTS_VAL" != "t" ]]; then
    STRUCT_EXISTS_SQL="select exists (select 1 from information_schema.tables where table_schema='${STRUCTURE_SCHEMA}' and table_name='${t}');"
    STRUCT_EXISTS_VAL="$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -At -c "$STRUCT_EXISTS_SQL" | tail -n1)"
    if [[ "$STRUCT_EXISTS_VAL" != "t" ]]; then
      echo "Missing structure table ${STRUCTURE_SCHEMA}.${t}. Initialize a project schema first or set STRUCTURE_SCHEMA=<existing project schema>." >&2
      exit 1
    fi
    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
      -c "CREATE TABLE IF NOT EXISTS ${TARGET_SCHEMA}.${t} (LIKE ${STRUCTURE_SCHEMA}.${t} INCLUDING ALL);"
  fi
done
docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$USE_SQL"
echo "Loaded seed into schema: ${TARGET_SCHEMA}"
