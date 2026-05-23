#!/usr/bin/env python3
from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    junit_path = Path(args.junit)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["## Flaky Observation Report", ""]
    if not junit_path.exists():
        lines.extend(["- status: missing-junit", f"- junit: `{junit_path}`"])
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0

    root = ET.parse(junit_path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    tests = failures = skipped = errors = 0
    failed_cases = []
    for suite in suites:
        tests += int(suite.attrib.get("tests", 0) or 0)
        failures += int(suite.attrib.get("failures", 0) or 0)
        errors += int(suite.attrib.get("errors", 0) or 0)
        skipped += int(suite.attrib.get("skipped", 0) or 0)
        for case in suite.findall("testcase"):
            failure = case.find("failure")
            error = case.find("error")
            issue = failure if failure is not None else error
            if issue is not None:
                failed_cases.append(
                    (
                        "::".join(filter(None, [case.attrib.get("classname"), case.attrib.get("name")])),
                        (issue.attrib.get("message") or (issue.text or "")).strip()[:240],
                    )
                )

    lines.extend(
        [
            f"- tests: `{tests}`",
            f"- failures: `{failures + errors}`",
            f"- skipped: `{skipped}`",
            f"- status: `{'fail' if failures + errors else 'pass'}`",
        ]
    )
    if failed_cases:
        lines.extend(["", "### Failed cases"])
        lines.extend([f"- `{name}`: {message}" for name, message in failed_cases[:20]])

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
