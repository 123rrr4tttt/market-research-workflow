#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_DIR="${GATEPLUS_ARTIFACT_DIR:-.artifacts/gateplus}"
JUNIT_PATH="$ARTIFACT_DIR/junit.xml"
SUMMARY_PATH="$ARTIFACT_DIR/summary.json"
MIN_PASS="${GATEPLUS_MIN_PASS:-1}"
MAX_WARNINGS="${GATEPLUS_MAX_WARNINGS:-9999}"
COMPAT_LEVEL="${GATEPLUS_COMPAT_LEVEL:-BACKWARD}"

mkdir -p "$ARTIFACT_DIR"

declare -a CANDIDATE_TESTS=(
  "tests/unit/test_meaningful_gate_unittest.py"
  "tests/unit/test_single_url_ingest_unittest.py"
  "tests/unit/test_collect_runtime_process_fallback_unittest.py"
)

declare -a SELECTED_TESTS=()
for path in "${CANDIDATE_TESTS[@]}"; do
  if [[ -f "$path" ]]; then
    SELECTED_TESTS+=("$path")
  fi
done

if [[ ${#SELECTED_TESTS[@]} -eq 0 ]]; then
  python3 - <<'PY' "$SUMMARY_PATH" "$COMPAT_LEVEL"
import json
import sys

summary_path, compat_level = sys.argv[1], sys.argv[2]
payload = {
    "tool": "gateplus_ci_guard",
    "status": "missing-tests",
    "summary_line": "no candidate GatePlus test files were found",
    "pytest_exit": 2,
    "compatibility": {"level": compat_level, "source": "env", "enforced": True},
    "counts": {"passed": 0, "skipped": 0, "failed": 0, "warnings": 0},
    "gates": {"min_pass": 1, "max_warnings": 9999, "skip_must_be_zero": True},
    "failure_diagnostics": {
        "root_cause_code": "missing_gateplus_tests",
        "failure_reasons": ["No GatePlus candidate tests were present in the repository."],
        "actionable_hints": [
            "Restore the GatePlus target tests or update the candidate list in gateplus_ci_guard.sh.",
        ],
        "failed_tests": [],
    },
}
with open(summary_path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2, ensure_ascii=False)
PY
  echo "[gateplus][FAIL] no candidate GatePlus test files were found" >&2
  exit 1
fi

set +e
pytest_output="$(python -m pytest -q --junitxml="$JUNIT_PATH" "${SELECTED_TESTS[@]}" 2>&1)"
pytest_exit=$?
set -e

printf '%s\n' "$pytest_output"

selected_tests_json="$(
  python3 - <<'PY' "${SELECTED_TESTS[@]}"
import json
import sys

print(json.dumps(sys.argv[1:], ensure_ascii=False))
PY
)"

python3 - <<'PY' "$JUNIT_PATH" "$SUMMARY_PATH" "$pytest_exit" "$MIN_PASS" "$MAX_WARNINGS" "$COMPAT_LEVEL" "$pytest_output" "$selected_tests_json"
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

junit_path, summary_path, pytest_exit, min_pass, max_warnings, compat_level, pytest_output, selected_tests_json = sys.argv[1:]
pytest_exit = int(pytest_exit)
min_pass = int(min_pass)
max_warnings = int(max_warnings)
selected_tests = json.loads(selected_tests_json)

counts = {"passed": 0, "skipped": 0, "failed": 0, "warnings": 0}
failed_tests = []

junit = Path(junit_path)
if junit.exists():
    root = ET.parse(junit).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    tests = failures = skipped = errors = 0
    for suite in suites:
        tests += int(suite.attrib.get("tests", 0) or 0)
        failures += int(suite.attrib.get("failures", 0) or 0)
        errors += int(suite.attrib.get("errors", 0) or 0)
        skipped += int(suite.attrib.get("skipped", 0) or 0)
        for case in suite.findall("testcase"):
            issue = case.find("failure") or case.find("error")
            if issue is not None:
                failed_tests.append(
                    {
                        "nodeid": "::".join(filter(None, [case.attrib.get("classname"), case.attrib.get("name")])),
                        "message": (issue.attrib.get("message") or (issue.text or "")).strip()[:300],
                    }
                )
    counts["failed"] = failures + errors
    counts["skipped"] = skipped
    counts["passed"] = max(tests - counts["failed"] - skipped, 0)

warn_match = re.search(r"(?P<count>\d+)\s+warnings?\s+in\s", pytest_output)
if warn_match:
    counts["warnings"] = int(warn_match.group("count"))

summary_line = ""
for line in reversed([line.strip() for line in pytest_output.splitlines() if line.strip()]):
    if "passed" in line or "failed" in line or "skipped" in line or "warnings" in line:
        summary_line = line
        break

failure_reasons = []
actionable_hints = []
status = "pass"
root_cause_code = "none"

if pytest_exit != 0 or counts["failed"] > 0:
    status = "fail"
    root_cause_code = "pytest_failures"
    failure_reasons.append("GatePlus target tests returned failures.")
    actionable_hints.append("Open junit.xml or pytest output to inspect the first failing test.")
elif counts["skipped"] != 0:
    status = "fail"
    root_cause_code = "skip_detected"
    failure_reasons.append("GatePlus guard requires skip==0, but skipped tests were detected.")
    actionable_hints.append("Remove skip conditions or move unstable coverage out of the GatePlus guard lane.")
elif counts["passed"] < min_pass:
    status = "fail"
    root_cause_code = "insufficient_pass_count"
    failure_reasons.append(f"Passed tests ({counts['passed']}) are below the required minimum ({min_pass}).")
    actionable_hints.append("Restore the missing target tests or lower GATEPLUS_MIN_PASS only with explicit approval.")
elif counts["warnings"] > max_warnings:
    status = "fail"
    root_cause_code = "warnings_budget_exceeded"
    failure_reasons.append(f"Warnings budget exceeded: {counts['warnings']} > {max_warnings}.")
    actionable_hints.append("Reduce warning-producing imports/usages or raise GATEPLUS_MAX_WARNINGS intentionally.")

payload = {
    "tool": "gateplus_ci_guard",
    "status": status,
    "summary_line": summary_line,
    "pytest_exit": pytest_exit,
    "compatibility": {"level": compat_level, "source": "env", "enforced": True},
    "counts": counts,
    "gates": {"min_pass": min_pass, "max_warnings": max_warnings, "skip_must_be_zero": True},
    "selected_tests": selected_tests,
    "failure_diagnostics": {
        "root_cause_code": root_cause_code,
        "failure_reasons": failure_reasons,
        "actionable_hints": actionable_hints,
        "failed_tests": failed_tests[:10],
    },
}

with open(summary_path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2, ensure_ascii=False)

if status != "pass":
    sys.exit(1)
PY
