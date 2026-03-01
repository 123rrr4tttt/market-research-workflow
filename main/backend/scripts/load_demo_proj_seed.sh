#!/usr/bin/env bash
set -euo pipefail
# Supports both Docker (DB_CONTAINER) and local (psql) modes.
# Local: set DB_CONTAINER="" or USE_LOCAL=1, ensure .env or PGHOST/PGUSER/PGPASSWORD/PGDATABASE are set.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SEED_FILE="${1:-$BACKEND_DIR/seed_data/project_demo_proj_v0.1.7-rc1.sql}"
DB_CONTAINER="${DB_CONTAINER:-}"
USE_LOCAL="${USE_LOCAL:-0}"
CLEAN_EXISTING="${CLEAN_EXISTING:-0}"
DB_NAME="${DB_NAME:-postgres}"
DB_USER="${DB_USER:-postgres}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
PGPASSWORD="${PGPASSWORD:-}"
TARGET_SCHEMA="${TARGET_SCHEMA:-project_demo_proj}"
STRUCTURE_SCHEMA="${STRUCTURE_SCHEMA:-}"
PROJECT_KEY="${PROJECT_KEY:-demo_proj}"
PROJECT_NAME="${PROJECT_NAME:-Demo Project}"
ACTIVATE_PROJECT="${ACTIVATE_PROJECT:-true}"
TABLES=(
  sources
  documents
  etl_job_runs
  resource_pool_urls
  resource_pool_site_entries
  source_library_items
  ingest_channels
)

# Resolve seed file path when given relative path
if [[ "$SEED_FILE" != /* ]] && [[ "$SEED_FILE" != ./* ]]; then
  SEED_FILE="$BACKEND_DIR/../$SEED_FILE"
fi
if [[ ! -f "$SEED_FILE" ]]; then
  echo "Seed file not found: $SEED_FILE" >&2
  exit 1
fi

# Load .env for local mode
if [[ -f "$BACKEND_DIR/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$BACKEND_DIR/.env"
  set +a
  # Parse DATABASE_URL if set: postgresql+psycopg2://user:pass@host:port/dbname
  if [[ -n "${DATABASE_URL:-}" ]]; then
    if [[ "$DATABASE_URL" =~ postgresql[^:]*://([^:]+):([^@]*)@([^:]+):([0-9]+)/([^?]*) ]]; then
      DB_USER="${BASH_REMATCH[1]}"
      PGPASSWORD="${BASH_REMATCH[2]}"
      DB_HOST="${BASH_REMATCH[3]}"
      DB_PORT="${BASH_REMATCH[4]}"
      DB_NAME="${BASH_REMATCH[5]}"
    fi
  fi
fi

# Detect mode: local when DB_CONTAINER empty or USE_LOCAL=1
if [[ -z "$DB_CONTAINER" ]] || [[ "$USE_LOCAL" == "1" ]]; then
  USE_LOCAL=1
  if command -v psql >/dev/null 2>&1; then
    PSQL_CMD="psql"
  elif [[ -x /opt/homebrew/opt/postgresql/bin/psql ]]; then
    PSQL_CMD="/opt/homebrew/opt/postgresql/bin/psql"
  elif [[ -x /usr/local/opt/postgresql/bin/psql ]]; then
    PSQL_CMD="/usr/local/opt/postgresql/bin/psql"
  else
    PSQL_CMD="psql"
  fi
  PSQL_OPTS=(-h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1)
  export PGPASSWORD
  run_psql() {
    "$PSQL_CMD" "${PSQL_OPTS[@]}" "$@"
  }
  run_psql_in() {
    "$PSQL_CMD" "${PSQL_OPTS[@]}" -f -
  }
else
  run_psql() {
    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 "$@"
  }
  run_psql_in() {
    docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 "$@"
  }
fi

# Auto-detect STRUCTURE_SCHEMA: use first project schema from public.projects, else public (tables from alembic)
if [[ -z "$STRUCTURE_SCHEMA" ]]; then
  STRUCTURE_SCHEMA="$(run_psql -At -c "SELECT schema_name FROM public.projects WHERE enabled = true LIMIT 1" 2>/dev/null | head -1 || true)"
  STRUCTURE_SCHEMA="${STRUCTURE_SCHEMA:-public}"
fi

TMP_SQL="$(mktemp)"
trap 'rm -f "$TMP_SQL"' EXIT
if [[ "$TARGET_SCHEMA" != "project_demo_proj" ]]; then
  sed "s/project_demo_proj\./${TARGET_SCHEMA}./g" "$SEED_FILE" > "$TMP_SQL"
else
  cat "$SEED_FILE" > "$TMP_SQL"
fi
grep -vi "pg_catalog.setval" "$TMP_SQL" > "${TMP_SQL}.filtered"
mv "${TMP_SQL}.filtered" "$TMP_SQL"
USE_SQL="$TMP_SQL"

run_psql -c "CREATE SCHEMA IF NOT EXISTS ${TARGET_SCHEMA};"

if [[ "$CLEAN_EXISTING" == "1" ]]; then
  TRUNCATE_LIST=""
  for t in "${TABLES[@]}"; do
    EXISTS_VAL="$(run_psql -At -c "SELECT exists (SELECT 1 FROM information_schema.tables WHERE table_schema='${TARGET_SCHEMA}' AND table_name='${t}')" 2>/dev/null | tail -n1 || echo "f")"
    if [[ "$EXISTS_VAL" == "t" ]]; then
      TRUNCATE_LIST="${TRUNCATE_LIST}${TARGET_SCHEMA}.${t},"
    fi
  done
  if [[ -n "$TRUNCATE_LIST" ]]; then
    TRUNCATE_LIST="${TRUNCATE_LIST%,}"
    run_psql -c "TRUNCATE TABLE ${TRUNCATE_LIST} CASCADE;"
    echo "Cleaned existing data in ${TARGET_SCHEMA}"
  fi
fi

for t in "${TABLES[@]}"; do
  EXISTS_SQL="select exists (select 1 from information_schema.tables where table_schema='${TARGET_SCHEMA}' and table_name='${t}');"
  EXISTS_VAL="$(run_psql -At -c "$EXISTS_SQL" 2>/dev/null | tail -n1 || echo "f")"
  if [[ "$EXISTS_VAL" != "t" ]]; then
    STRUCT_EXISTS_SQL="select exists (select 1 from information_schema.tables where table_schema='${STRUCTURE_SCHEMA}' and table_name='${t}');"
    STRUCT_EXISTS_VAL="$(run_psql -At -c "$STRUCT_EXISTS_SQL" 2>/dev/null | tail -n1 || echo "f")"
    if [[ "$STRUCT_EXISTS_VAL" != "t" ]]; then
      echo "Missing structure table ${STRUCTURE_SCHEMA}.${t}. Run alembic upgrade head and backend bootstrap first, or set STRUCTURE_SCHEMA=<existing project schema>." >&2
      exit 1
    fi
    run_psql -c "CREATE TABLE IF NOT EXISTS ${TARGET_SCHEMA}.${t} (LIKE ${STRUCTURE_SCHEMA}.${t} INCLUDING ALL);"
  fi
done
run_psql_in < "$USE_SQL"

run_psql_in <<SQL
CREATE SCHEMA IF NOT EXISTS public;
INSERT INTO public.projects (project_key, name, schema_name, enabled, is_active)
VALUES ('${PROJECT_KEY}', '${PROJECT_NAME}', '${TARGET_SCHEMA}', true, false)
ON CONFLICT (project_key) DO UPDATE
SET name = EXCLUDED.name,
    schema_name = EXCLUDED.schema_name,
    enabled = true;
SQL

if [[ "${ACTIVATE_PROJECT}" == "true" ]]; then
  run_psql_in <<SQL
UPDATE public.projects SET is_active = false;
UPDATE public.projects SET is_active = true WHERE project_key = '${PROJECT_KEY}';
SQL
fi

echo "Loaded seed into schema: ${TARGET_SCHEMA}"
echo "Registered project in public.projects: ${PROJECT_KEY} (${TARGET_SCHEMA})"
