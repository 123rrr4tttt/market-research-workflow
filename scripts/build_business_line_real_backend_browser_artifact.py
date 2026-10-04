#!/usr/bin/env python3
"""Build a canonical business-line artifact from a Playwright JSON report."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Annotated, Any, Sequence

try:
    from scripts._automation_runtime import CANONICAL_LINE_KEYS, utc_now, write_json
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import CANONICAL_LINE_KEYS, utc_now, write_json


ARTIFACT_SCHEMA_VERSION = "business_line_real_backend_browser_smoke.v1"
PROOF_LEVEL_REAL_BACKEND_BROWSER = "real_backend_browser_smoke"

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"

LINE_KEY_PATTERN = re.compile(r"\[line_key=([a-z0-9_]+)\]")

REQUIRED_LINE_KEYS = CANONICAL_LINE_KEYS


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("playwright_json", type=Path, help="Playwright JSON reporter output.")
    parser.add_argument("--output", required=True, type=Path, help="Path to write the canonical artifact.")
    parser.add_argument("--json", action="store_true", help="Print the artifact JSON after writing.")
    return parser.parse_args(argv)


def load_json(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                payload, _end = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            return payload
        raise


def iter_specs(suite: dict[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    raw_specs = suite.get("specs")
    if isinstance(raw_specs, list):
        specs.extend(spec for spec in raw_specs if isinstance(spec, dict))
    raw_suites = suite.get("suites")
    if isinstance(raw_suites, list):
        for child in raw_suites:
            if isinstance(child, dict):
                specs.extend(iter_specs(child))
    return specs


def extract_specs(report: Any) -> list[dict[str, Any]]:
    if not isinstance(report, dict):
        return []
    suites = report.get("suites")
    if not isinstance(suites, list):
        return []
    specs: list[dict[str, Any]] = []
    for suite in suites:
        if isinstance(suite, dict):
            specs.extend(iter_specs(suite))
    return specs


def extract_line_key(spec: dict[str, Any]) -> str | None:
    title = str(spec.get("title") or "")
    match = LINE_KEY_PATTERN.search(title)
    return match.group(1) if match else None


def result_rows(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    tests = spec.get("tests")
    if not isinstance(tests, list):
        return rows
    for test in tests:
        if not isinstance(test, dict):
            continue
        project_name = str(test.get("projectName") or test.get("project_name") or "")
        results = test.get("results")
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, dict):
                continue
            row = dict(result)
            row["project_name"] = project_name
            rows.append(row)
    return rows


def classify_spec(spec: dict[str, Any]) -> dict[str, Any]:
    rows = result_rows(spec)
    statuses = [str(row.get("status") or "").strip().lower() for row in rows]
    duration_ms = sum(int(row.get("duration") or 0) for row in rows if isinstance(row.get("duration"), int))
    project_names = sorted({str(row.get("project_name") or "") for row in rows if row.get("project_name")})

    if not rows:
        status = STATUS_FAILED
        skipped = False
        reason = "missing_playwright_results"
    elif any(status in {"failed", "timedout", "interrupted"} for status in statuses):
        status = STATUS_FAILED
        skipped = False
        reason = "playwright_test_failed"
    elif statuses and all(status == "skipped" for status in statuses):
        status = STATUS_BLOCKED
        skipped = True
        reason = "playwright_test_skipped_or_backend_check_bypassed"
    elif any(status == "passed" for status in statuses):
        status = STATUS_PASSED
        skipped = False
        reason = "playwright_test_passed"
    else:
        status = STATUS_FAILED
        skipped = False
        reason = "unknown_playwright_status"

    return {
        "status": status,
        "proof_level": PROOF_LEVEL_REAL_BACKEND_BROWSER,
        "mocked": False,
        "skipped": skipped,
        "reason": reason,
        "test_title": str(spec.get("title") or ""),
        "project_names": project_names,
        "duration_ms": duration_ms,
    }


def build_artifact(
    playwright_report: Any, *, source_path: Path, observed_at: str
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=playwright_json_report_function_input "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    by_line: dict[str, dict[str, Any]] = {}
    duplicate_line_keys: list[str] = []
    unexpected_line_keys: list[str] = []

    for spec in extract_specs(playwright_report):
        line_key = extract_line_key(spec)
        if line_key is None:
            continue
        if line_key not in REQUIRED_LINE_KEYS:
            unexpected_line_keys.append(line_key)
            continue
        if line_key in by_line:
            duplicate_line_keys.append(line_key)
            continue
        by_line[line_key] = classify_spec(spec)

    lines: list[dict[str, Any]] = []
    for line_key in REQUIRED_LINE_KEYS:
        row = by_line.get(line_key)
        if row is None:
            row = {
                "status": STATUS_FAILED,
                "proof_level": PROOF_LEVEL_REAL_BACKEND_BROWSER,
                "mocked": False,
                "skipped": False,
                "reason": "missing_playwright_spec_for_line_key",
                "test_title": None,
                "project_names": [],
                "duration_ms": 0,
            }
        lines.append({"line_key": line_key, **row})

    failed = [line["line_key"] for line in lines if line["status"] == STATUS_FAILED]
    blocked = [line["line_key"] for line in lines if line["status"] == STATUS_BLOCKED]
    passed = [line["line_key"] for line in lines if line["status"] == STATUS_PASSED]

    if failed or duplicate_line_keys or unexpected_line_keys:
        status = STATUS_FAILED
    elif blocked:
        status = STATUS_BLOCKED
    elif len(passed) == len(REQUIRED_LINE_KEYS):
        status = STATUS_PASSED
    else:
        status = STATUS_FAILED

    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "status": status,
        "observed_at": observed_at,
        "source": {
            "kind": "playwright_json_report",
            "path": str(source_path),
        },
        "proof_level": PROOF_LEVEL_REAL_BACKEND_BROWSER,
        "mocked": False,
        "skipped": status == STATUS_BLOCKED,
        "expected_line_keys": list(REQUIRED_LINE_KEYS),
        "summary": {
            "expected_line_count": len(REQUIRED_LINE_KEYS),
            "passed_line_keys": passed,
            "blocked_line_keys": blocked,
            "failed_line_keys": failed,
            "duplicate_line_keys": sorted(set(duplicate_line_keys)),
            "unexpected_line_keys": sorted(set(unexpected_line_keys)),
        },
        "lines": lines,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = load_json(args.playwright_json)
    artifact = build_artifact(report, source_path=args.playwright_json, observed_at=utc_now())
    write_json(args.output, artifact)
    if args.json:
        print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"business_line_real_backend_browser_artifact={artifact['status']} output={args.output}")
    return 0 if artifact["status"] == STATUS_PASSED else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
