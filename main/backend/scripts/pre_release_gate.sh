#!/usr/bin/env bash
set -euo pipefail

# Minimal pre-release gate for local developer verification.
# Default behavior is non-invasive: enforce syntax + targeted tests,
# run API import guard in warn-only mode unless --strict is provided.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="quick"
STRICT="false"

for arg in "$@"; do
  case "$arg" in
    --full)
      MODE="full"
      ;;
    --strict)
      STRICT="true"
      ;;
    *)
      echo "[gate] unknown arg: $arg" >&2
      echo "usage: $0 [--full] [--strict]" >&2
      exit 2
      ;;
  esac
done

echo "[gate] root=$ROOT_DIR mode=$MODE strict=$STRICT"

if [[ -x "$ROOT_DIR/.venv311/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv311/bin/python"
else
  PYTHON_BIN="python3"
fi

# Ensure pytest is available; fallback to system python when needed.
if ! "$PYTHON_BIN" -c "import pytest" >/dev/null 2>&1; then
  if python3 -c "import pytest" >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "[gate] ERROR: pytest not found in selected interpreter or system python3" >&2
    exit 2
  fi
fi

echo "[gate] python=$PYTHON_BIN"

echo "[gate] step 1/4: python syntax smoke (compileall app/)"
"$PYTHON_BIN" -m compileall -q app

echo "[gate] step 2/4: targeted contract/unit tests"
if [[ "$MODE" == "quick" ]]; then
  "$PYTHON_BIN" -m pytest -q \
    tests/unit/test_streamplus_contracts_unittest.py \
    tests/unit/test_collect_runtime_process_fallback_unittest.py \
    tests/unit/test_agent_control_tools_unittest.py \
    tests/unit/test_agent_run_loop_unittest.py \
    tests/unit/test_agent_session_memory_unittest.py \
    tests/unit/test_interactive_agent_runtime_unittest.py \
    tests/unit/test_local_index_service_unittest.py \
    tests/unit/test_material_ontology_unittest.py \
    tests/unit/test_search_web_provider_adapters_unittest.py \
    tests/unit/test_source_candidate_trust_unittest.py \
    tests/unit/test_source_library_url_pool_adapter_unittest.py \
    tests/unit/test_structured_data_search_unittest.py \
    tests/unit/test_time_semantics_release_gate_unittest.py \
    tests/unit/test_time_semantics_sample_provenance_readback_unittest.py \
    tests/integration/test_agent_chat_api_unittest.py \
    tests/integration/test_agent_runtime_artifact_idle_replay_unittest.py \
    tests/integration/test_agent_runtime_scenario_replay_unittest.py \
    tests/integration/test_writing_api_unittest.py
else
  "$PYTHON_BIN" -m pytest -q \
    tests/unit \
    tests/contract/test_contracts_unittest.py \
    tests/integration/test_api_exception_envelope_unittest.py
fi

echo "[gate] step 3/4: time semantics release gate"
"$PYTHON_BIN" scripts/check_time_semantics_release_gate.py

echo "[gate] step 4/4: api import guard"
if [[ "$STRICT" == "true" ]]; then
  "$PYTHON_BIN" scripts/check_api_layer_imports.py
else
  if ! "$PYTHON_BIN" scripts/check_api_layer_imports.py; then
    echo "[gate] WARN: api import guard reported issues (non-blocking in default mode)"
  fi
fi

echo "[gate] PASS"
