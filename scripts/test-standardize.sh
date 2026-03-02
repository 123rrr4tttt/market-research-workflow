#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/main/backend"
OPS_DIR="${ROOT_DIR}/main/ops"
FRONTEND_DIR="${ROOT_DIR}/main/frontend-modern"
ENV_FILE="${BACKEND_DIR}/.env"
ENV_EXAMPLE_FILE="${BACKEND_DIR}/.env.example"

usage() {
  cat <<USAGE
Usage: $(basename "$0") <profile> [extra pytest args...]

Profiles:
  unit        Run unit tests
  integration Run integration tests
  schema-guard Run tenant schema guard (dashboard stats across projects)
  contract    Run contract tests
  e2e         Run e2e tests
  core-business Run core business suite (tests/core_business)
  external-smoke Run external chain smoke checks in docker compose
  frontend-e2e Run frontend Playwright e2e suite
  coverage    Run split coverage gate (core=100%, other=20%)
  all         Run unit + integration + contract + e2e
  ci-pr       Run CI PR suite (unit + integration)
  ci-main     Run CI main suite (unit + integration + contract + e2e)
  docker      Run test suite through Docker compose backend-test service
USAGE
}

prepare_env() {
  if [[ -f "${ENV_FILE}" ]]; then
    return 0
  fi
  if [[ -f "${ENV_EXAMPLE_FILE}" ]]; then
    cp "${ENV_EXAMPLE_FILE}" "${ENV_FILE}"
    echo "[test-standardize] Created main/backend/.env from .env.example"
    return 0
  fi
  echo "[test-standardize] Missing ${ENV_FILE} and ${ENV_EXAMPLE_FILE}" >&2
  return 1
}

compose() {
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  elif docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  else
    echo "[test-standardize] Missing docker-compose and docker compose" >&2
    return 127
  fi
}

run_pytest_marker() {
  local marker="$1"
  shift
  local py_exec
  py_exec="$(resolve_python_exec)"
  (
    cd "${BACKEND_DIR}"
    "${py_exec}" -m pytest -m "${marker}" "$@"
  )
}

run_pytest_coverage() {
  local py_exec
  local core_paths
  py_exec="$(resolve_python_exec)"
  core_paths="${CORE_COVERAGE_PATHS:-app/api/search.py,app/contracts/api.py,app/contracts/responses.py,app/contracts/tasks.py,app/contracts/errors.py}"
  if ! "${py_exec}" -m pytest --help 2>/dev/null | grep -q -- "--cov"; then
    echo "[test-standardize] Missing pytest-cov plugin in current environment" >&2
    echo "[test-standardize] Install with: ${py_exec} -m pip install pytest-cov" >&2
    return 2
  fi
  (
    cd "${BACKEND_DIR}"
    "${py_exec}" -m pytest -m "(unit or integration) and not external" --cov=app --cov-report=term-missing --cov-report=xml:coverage.xml "$@"
    "${py_exec}" scripts/check_coverage_thresholds.py --coverage-file coverage.xml --core-paths "${core_paths}" --core-threshold 100 --other-threshold 20
  )
}

run_docker_tests() {
  local test_profile="${TEST_PROFILE:-test}"
  (
    cd "${OPS_DIR}"
    cleanup() {
      compose --profile "${test_profile}" down -v || true
    }
    trap cleanup EXIT
    compose --profile "${test_profile}" up --build --abort-on-container-exit --exit-code-from backend-test backend-test
  )
}

run_external_smoke() {
  (
    cd "${OPS_DIR}"
    cleanup() {
      compose down -v || true
    }
    trap cleanup EXIT
    compose up -d db es redis
    compose run --rm backend python -m scripts.test_resource_library_e2e
    compose run --rm backend python -m scripts.test_search_to_document_chain
  )
}

run_frontend_e2e() {
  if ! command -v npm >/dev/null 2>&1; then
    echo "[test-standardize] Missing npm for frontend-e2e profile" >&2
    return 127
  fi
  (
    cd "${FRONTEND_DIR}"
    npm run test:e2e -- "$@"
  )
}

resolve_python_exec() {
  local backend_venv="${BACKEND_DIR}/.venv311/bin/python"
  if [[ -x "${backend_venv}" ]]; then
    echo "${backend_venv}"
    return 0
  fi

  if command -v python >/dev/null 2>&1; then
    echo "python"
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
    return 0
  fi

  echo "[test-standardize] Missing python runtime (.venv311/python, python, python3)" >&2
  return 127
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

profile="$1"
shift

case "${profile}" in
  unit)
    prepare_env
    run_pytest_marker "unit and not external" "$@"
    ;;
  integration)
    prepare_env
    run_pytest_marker "integration and not external" "$@"
    ;;
  schema-guard)
    prepare_env
    run_pytest_marker "integration and not external" tests/integration/test_project_schema_guard_unittest.py -q "$@"
    ;;
  contract)
    prepare_env
    run_pytest_marker "contract and not external" "$@"
    ;;
  e2e)
    prepare_env
    run_pytest_marker "e2e and not external" "$@"
    ;;
  core-business)
    prepare_env
    run_pytest_marker "(unit or integration or contract or e2e) and not external" tests/core_business -q "$@"
    ;;
  external-smoke)
    prepare_env
    run_external_smoke "$@"
    ;;
  frontend-e2e)
    run_frontend_e2e "$@"
    ;;
  coverage)
    prepare_env
    run_pytest_coverage "$@"
    ;;
  all)
    prepare_env
    run_pytest_marker "(unit or integration or contract or e2e) and not external" "$@"
    ;;
  ci-pr)
    prepare_env
    run_pytest_marker "(unit or integration) and not external" "$@"
    ;;
  ci-main)
    prepare_env
    run_pytest_marker "(unit or integration or contract or e2e) and not external" "$@"
    ;;
  docker)
    prepare_env
    run_docker_tests "$@"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "[test-standardize] Unknown profile: ${profile}" >&2
    usage
    exit 2
    ;;
esac
