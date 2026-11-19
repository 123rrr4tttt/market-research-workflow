#!/bin/bash
# Stop the current checkout. Docker dependencies require explicit opt-in.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
USE_DOCKER_DEPS=0
WITH_LOCAL_WORKER=1

for arg in "$@"; do
    case "$arg" in
        --with-docker-deps) USE_DOCKER_DEPS=1 ;;
        --local-only) USE_DOCKER_DEPS=0 ;;
        --with-local-worker) WITH_LOCAL_WORKER=1 ;;
        --no-local-worker) WITH_LOCAL_WORKER=0 ;;
    esac
done

CONTROL="$ROOT_DIR/scripts/local-service-control.sh"
if [ "$WITH_LOCAL_WORKER" = "1" ]; then
    "$CONTROL" worker-stop
fi
"$CONTROL" frontend-stop
"$CONTROL" backend-stop

if [ "$USE_DOCKER_DEPS" = "1" ]; then
    cd "$ROOT_DIR/main/ops"
    docker compose stop db es redis
fi
