#!/usr/bin/env bash
set -euo pipefail
TARGET_DIR="${1:-$(pwd)}"
"$TARGET_DIR/scripts/gates/run_r15_c_m1_problem_details_gate.sh" "$TARGET_DIR"
"$TARGET_DIR/scripts/gates/run_r15_c_m2_otel_schema_gate.sh" "$TARGET_DIR"
"$TARGET_DIR/scripts/gates/run_r15_d_m1_provenance_gate.sh" "$TARGET_DIR"
"$TARGET_DIR/scripts/gates/run_r15_d_m2_safety_gate.sh" "$TARGET_DIR"
echo "[r15-cd] passed"
