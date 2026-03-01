#!/usr/bin/env bash
# Fix demo_proj etl_job_runs sequence/PK drift.
# Usage: ./scripts/fix_demo_proj_seq.sh [docker|local]
#   docker: use docker compose exec
#   local:  use psql directly (default)

set -e
MODE="${1:-local}"

run_sql() {
  if [[ "$MODE" == "docker" ]]; then
    docker compose -f main/ops/docker-compose.yml exec -T db psql -U postgres -d postgres -t -A -c "$1"
  else
    psql "postgresql://postgres:postgres@localhost:5432/postgres" -t -A -c "$1"
  fi
}

echo "=== B. Detect ==="
echo "1) column_default:"
run_sql "SELECT column_default FROM information_schema.columns WHERE table_schema='project_demo_proj' AND table_name='etl_job_runs' AND column_name='id';"
echo "2) max_id:"
run_sql "SELECT COALESCE(MAX(id),0) FROM project_demo_proj.etl_job_runs;"
echo "3) sequence last_value, is_called:"
run_sql "SELECT last_value, is_called FROM project_demo_proj.etl_job_runs_id_seq;" 2>/dev/null || echo "(seq may not exist yet)"

echo ""
echo "=== C. Fix ==="
run_sql "
BEGIN;
CREATE SEQUENCE IF NOT EXISTS project_demo_proj.etl_job_runs_id_seq;
ALTER SEQUENCE project_demo_proj.etl_job_runs_id_seq OWNED BY project_demo_proj.etl_job_runs.id;
ALTER TABLE project_demo_proj.etl_job_runs ALTER COLUMN id SET DEFAULT nextval('project_demo_proj.etl_job_runs_id_seq'::regclass);
SELECT setval('project_demo_proj.etl_job_runs_id_seq', COALESCE((SELECT MAX(id) FROM project_demo_proj.etl_job_runs), 0) + 1, false);
COMMIT;
"

echo ""
echo "=== D. Verify ==="
run_sql "SELECT column_default FROM information_schema.columns WHERE table_schema='project_demo_proj' AND table_name='etl_job_runs' AND column_name='id';"
echo "Done. Run ingest to verify: curl -X POST http://localhost:8000/api/v1/ingest/market -H 'Content-Type: application/json' -H 'X-Project-Key: demo_proj' -d '{\"query_terms\":[\"test\"],\"max_items\":1,\"async_mode\":true,\"project_key\":\"demo_proj\"}'"
