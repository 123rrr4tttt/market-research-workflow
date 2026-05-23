#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def build_summary(*, junit_glob: str, threshold: float, top_n: int) -> dict:
    files = [Path(path) for path in glob.glob(junit_glob)]
    totals: Counter[str] = Counter()
    failures: Counter[str] = Counter()

    for path in files:
        if not path.exists():
            continue
        root = ET.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
        for suite in suites:
            for case in suite.findall("testcase"):
                nodeid = "::".join(filter(None, [case.attrib.get("classname"), case.attrib.get("name")]))
                if not nodeid:
                    continue
                totals[nodeid] += 1
                if case.find("failure") is not None or case.find("error") is not None:
                    failures[nodeid] += 1

    tests = []
    for nodeid, total in totals.items():
        flaky_count = failures[nodeid]
        rate = flaky_count / total if total else 0.0
        tests.append(
            {
                "nodeid": nodeid,
                "runs": total,
                "failures": flaky_count,
                "failure_rate": round(rate, 4),
                "above_threshold": rate > threshold,
            }
        )
    tests.sort(key=lambda item: (item["failure_rate"], item["failures"], item["runs"]), reverse=True)

    return {
        "history_files": len(files),
        "threshold": threshold,
        "top_n": top_n,
        "totals": {
            "tests": len(tests),
            "runs": sum(item["runs"] for item in tests),
            "failures": sum(item["failures"] for item in tests),
        },
        "items": tests[:top_n],
        "tests": tests,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit-glob", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--output-json")
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--threshold", type=float, default=0.30)
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_summary(junit_glob=args.junit_glob, threshold=args.threshold, top_n=args.top_n)

    lines = [
        "## Flaky Trend Report",
        "",
        f"- history_files: `{payload['history_files']}`",
        f"- threshold: `{args.threshold:.2f}`",
    ]
    if payload["tests"]:
        lines.extend(["", "### Top flaky tests"])
        for item in payload["items"]:
            lines.append(
                f"- `{item['nodeid']}`: failure_rate={item['failure_rate']:.2f} failures={item['failures']} runs={item['runs']}"
            )
    else:
        lines.append("- status: no-history")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if args.output_json:
        output_json_path = Path(args.output_json)
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        output_json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
