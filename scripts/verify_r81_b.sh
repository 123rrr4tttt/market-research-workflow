#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 -m unittest main/backend/tests/unit/test_r81_b_contract_faults_unittest.py -v
