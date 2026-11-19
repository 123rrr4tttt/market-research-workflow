#!/usr/bin/env bash
# Run locally with the backend environment, or inside the backend container.
# The application settings (DATABASE_URL / backend .env) select the database.
set -euo pipefail

if [[ $# != 0 || -n ${DB_CONTAINER:-} || -n ${TARGET_SCHEMA:-} || -n ${STRUCTURE_SCHEMA:-} ||
      -n ${PROJECT_KEY:-} && ${PROJECT_KEY:-} != demo_proj || ${CLEAN_EXISTING:-0} != 0 ||
      ${ACTIVATE_PROJECT:-false} == true ]]; then
    echo 'Use the bundled demo_proj seed with DATABASE_URL; alternate schemas, cleanup, and activation are not supported.' >&2
    exit 2
fi
if [[ -z ${DATABASE_URL:-} && -n ${DB_NAME:-}${DB_HOST:-}${DB_PORT:-}${DB_USER:-}${PGDATABASE:-}${PGHOST:-}${PGPORT:-}${PGUSER:-} ]]; then
    echo 'Set DATABASE_URL explicitly instead of passing separate connection fields.' >&2
    exit 2
fi

cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ -x .venv311/bin/python ]]; then
    python=.venv311/bin/python
else
    python=python3
fi
export PYTHONPATH="$PWD:$PWD/../../src${PYTHONPATH:+:$PYTHONPATH}"
exec "$python" -c '
from app.api.projects import _bootstrap_demo_seed_if_needed
_bootstrap_demo_seed_if_needed("demo_proj")
'
