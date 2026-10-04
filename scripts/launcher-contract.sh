#!/usr/bin/env bash

# Canonical launcher contract shared by shell entrypoints and documentation.
# The macOS app projects these values into its UI; the Docker web launcher
# consumes the same names through the environment when it starts services.
export MRW_LOCAL_BACKEND_URL="${MRW_LOCAL_BACKEND_URL:-http://127.0.0.1:8000}"
export MRW_LOCAL_FRONTEND_URL="${MRW_LOCAL_FRONTEND_URL:-http://127.0.0.1:5173}"
export MRW_DOCKER_BACKEND_URL="${MRW_DOCKER_BACKEND_URL:-http://127.0.0.1:8000}"
export MRW_DOCKER_FRONTEND_URL="${MRW_DOCKER_FRONTEND_URL:-http://127.0.0.1:5174}"
export MRW_DOCKER_LAUNCHER_URL="${MRW_DOCKER_LAUNCHER_URL:-http://127.0.0.1:5176}"
export MRW_DOCKER_PROJECT_NAME="${MRW_DOCKER_PROJECT_NAME:-mrw-app}"
export MRW_LAUNCHER_PROJECT_NAME="${MRW_LAUNCHER_PROJECT_NAME:-mrw-launcher}"

launcher_contract() {
  cat <<EOF
local-process|本地开发模式|${MRW_LOCAL_BACKEND_URL}|${MRW_LOCAL_FRONTEND_URL}|local-deploy.sh
docker-control-ui|Docker 控制台|${MRW_DOCKER_LAUNCHER_URL}|${MRW_DOCKER_LAUNCHER_URL}|docker-launcher-ui.sh
docker-app-stack|Docker 应用栈|${MRW_DOCKER_BACKEND_URL}|${MRW_DOCKER_FRONTEND_URL}|docker-deploy.sh
EOF
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  launcher_contract
fi
