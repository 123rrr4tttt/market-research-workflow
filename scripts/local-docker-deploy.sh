#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/main/ops/docker-compose.yml"
OVERLAY_FILE="$ROOT_DIR/main/ops/docker-compose.local-user.yml"
ENV_FILE="$ROOT_DIR/main/ops/.env.local-user"
PROJECT="${MRW_DOCKER_PROJECT:-mrw-local-user}"
export HOST_PROJECT_ROOT="${HOST_PROJECT_ROOT:-$ROOT_DIR}"
COMPOSE=(docker compose --project-name "$PROJECT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -f "$OVERLAY_FILE")
SERVICES=(db es redis backend celery-worker codex-webui frontend-modern)

usage() {
    cat <<'USAGE'
Usage: scripts/local-docker-deploy.sh <command>

Commands:
  up       Build/start the complete local Docker workbench and wait for health
  status   Show the Compose services and published ports
  health   Check the business API and WebUI health endpoints
  logs     Follow backend, worker, WebUI and gateway logs
  down     Stop this project and preserve all data volumes
  reset    Delete this project's containers and data volumes (destructive)
  config   Render Compose configuration without starting anything

Set MRW_DOCKER_PROJECT to use a different Compose project. The default configuration
file is main/ops/.env.local-user; it is private and is never read from the host app.
USAGE
}

need_docker() {
    command -v docker >/dev/null 2>&1 || {
        echo "Docker CLI is required." >&2
        exit 1
    }
    docker info >/dev/null 2>&1 || {
        echo "Docker Engine is not running or is unreachable." >&2
        exit 1
    }
    docker compose version >/dev/null
}

need_env() {
    if [[ ! -f "$ENV_FILE" ]]; then
        echo "Missing $ENV_FILE; copy main/ops/.env.local-user.example there and set two different random keys." >&2
        exit 1
    fi
    local server_key webui_key
    server_key="$(sed -n 's/^MRW_SERVER_API_KEY=//p' "$ENV_FILE" | tail -n 1)"
    webui_key="$(sed -n 's/^MRW_WEBUI_API_KEY=//p' "$ENV_FILE" | tail -n 1)"
    if [[ -z "$server_key" || -z "$webui_key" || "$server_key" == replace-* || "$webui_key" == replace-* || "$server_key" == "$webui_key" ]]; then
        echo "Set two different non-placeholder keys in $ENV_FILE." >&2
        exit 1
    fi
    if [[ ! "$server_key" =~ ^[A-Za-z0-9_-]+$ || ! "$webui_key" =~ ^[A-Za-z0-9_-]+$ ]]; then
        echo "Docker keys may contain only letters, digits, underscore or hyphen." >&2
        exit 1
    fi
}

frontend_port() {
    sed -n 's/^MRW_DOCKER_PORT=//p' "$ENV_FILE" | tail -n 1 | grep -E '^[0-9]+$' || printf '15132'
}

api_port() {
    sed -n 's/^MRW_DOCKER_API_PORT=//p' "$ENV_FILE" | tail -n 1 | grep -E '^[0-9]+$' || printf '18132'
}

command="${1:-}"
case "$command" in
    up)
        need_docker
        need_env
        "${COMPOSE[@]}" up -d --build --pull missing --wait --wait-timeout 180 "${SERVICES[@]}"
        printf 'MRW: http://127.0.0.1:%s\nAPI: http://127.0.0.1:%s/docs\n' "$(frontend_port)" "$(api_port)"
        ;;
    status)
        need_docker
        need_env
        "${COMPOSE[@]}" ps
        ;;
    health)
        need_docker
        need_env
        for service in "${SERVICES[@]}"; do
            container_id="$("${COMPOSE[@]}" ps -q "$service")"
            if [[ -z "$container_id" ]]; then
                echo "Missing $service container." >&2
                exit 1
            fi
            state="$(docker inspect --format '{{.State.Status}}' "$container_id")"
            health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")"
            if [[ "$state" != "running" || ( "$health" != "healthy" && "$health" != "none" ) ]]; then
                echo "$service is not ready (state=$state health=$health)." >&2
                exit 1
            fi
        done
        curl -fsS "http://127.0.0.1:$(api_port)/api/v1/health" >/dev/null
        curl -fsS "http://127.0.0.1:$(frontend_port)/" >/dev/null
        "${COMPOSE[@]}" exec -T codex-webui \
            node -e "fetch('http://127.0.0.1:8172/api/status',{headers:{authorization:'Bearer '+process.env.WEBUI_API_KEY}}).then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"
        echo "MRW services, business API and gateway health checks passed."
        ;;
    logs)
        need_docker
        need_env
        "${COMPOSE[@]}" logs -f backend celery-worker codex-webui frontend-modern
        ;;
    down)
        need_docker
        need_env
        "${COMPOSE[@]}" down
        ;;
    reset)
        need_docker
        need_env
        printf 'This deletes the %s containers and all of its data volumes. Type the project name to continue: ' "$PROJECT" >&2
        read -r answer
        [[ "$answer" == "$PROJECT" ]] || exit 1
        "${COMPOSE[@]}" down --volumes --remove-orphans
        ;;
    config)
        need_env
        "${COMPOSE[@]}" config --quiet
        echo "Compose configuration is valid."
        ;;
    *)
        usage
        [[ -z "$command" ]] || exit 1
        ;;
esac
