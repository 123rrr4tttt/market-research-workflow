#!/usr/bin/env python3
"""Classify one exact ROOT JUnit without changing the candidate or its evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


BUSINESS_NIGHTLY = "scripts/run_business_line_worker_readback_project_matrix_nightly.sh"
PERFORMANCE_NIGHTLY = "scripts/run_performance_capacity_nightly.sh"
READ_ONLY_CACHE_OWNER = "main/backend/app/services/llm/cache.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _observed_missing_paths(text: str) -> list[str]:
    patterns = (
        r"No such file or directory: ['\"]([^'\"]+)['\"]",
        r"bash: ([^:\n]+): No such file or directory",
        r"required input missing(?: or not a regular file)?: ([^\n]+)",
        r"is_file = PosixPath\('([^']+)'\)",
    )
    result: list[str] = []
    for pattern in patterns:
        for value in re.findall(pattern, text):
            cleaned = value.strip()
            if cleaned and cleaned not in result:
                result.append(cleaned)
    return result


def _source_relative_paths(text: str, source: Path, preview: Path) -> list[str]:
    result: list[str] = []
    for value in _observed_missing_paths(text):
        if value.startswith("/code/"):
            relative = value.removeprefix("/code/")
        elif not value.startswith("/"):
            relative = value
        else:
            continue
        if (source / relative).is_file() and not (preview / relative).exists():
            if relative not in result:
                result.append(relative)
    return result


def classify(
    *, testcase: ET.Element, failure: ET.Element, source: Path, preview: Path
) -> dict[str, object]:
    classname = testcase.attrib.get("classname", "")
    nodeid = f"{classname}::{testcase.attrib.get('name', '')}"
    text = failure.text or ""
    observed = _observed_missing_paths(text)
    projected = _source_relative_paths(text, source, preview)

    if "Read-only file system: '/code/main/backend/data'" in text:
        category = "READ_ONLY_IMPORT_EFFECT"
        root_causes = [READ_ONLY_CACHE_OWNER]
    elif "test_run_business_line_worker_readback_project_matrix_nightly_unittest" in classname:
        category = "CASCADING_MISSING_PROJECTION"
        root_causes = [BUSINESS_NIGHTLY]
    elif "test_run_performance_capacity_nightly_unittest" in classname:
        category = "CASCADING_MISSING_PROJECTION"
        root_causes = [PERFORMANCE_NIGHTLY]
    elif projected:
        category = "MISSING_PROJECTION"
        root_causes = projected
    else:
        category = "UNCLASSIFIED"
        root_causes = []

    return {
        "nodeid": nodeid,
        "category": category,
        "failure_message": failure.attrib.get("message"),
        "observed_missing_paths": observed,
        "root_cause_source_paths": root_causes,
        "root_cause_source_exists": {
            relative: (source / relative).is_file() for relative in root_causes
        },
        "root_cause_preview_absent": {
            relative: not (preview / relative).exists() for relative in root_causes
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--preview", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    junit = args.junit.resolve(strict=True)
    source = args.source.resolve(strict=True)
    preview = args.preview.resolve(strict=True)
    output = args.output.resolve(strict=False)
    if output.exists() or output.is_symlink():
        parser.error(f"output already exists: {output}")
    if not source.is_dir() or not preview.is_dir():
        parser.error("source and preview must be directories")

    document = ET.parse(junit).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    entries: list[dict[str, object]] = []
    for testcase in document.iter("testcase"):
        failures = testcase.findall("failure") + testcase.findall("error")
        for failure_index, failure in enumerate(failures, start=1):
            item = classify(testcase=testcase, failure=failure, source=source, preview=preview)
            item["failure_index_for_nodeid"] = failure_index
            item["failure_count_for_nodeid"] = len(failures)
            entries.append(item)

    category_elements = Counter(str(item["category"]) for item in entries)
    category_nodeids = {
        category: len({str(item["nodeid"]) for item in entries if item["category"] == category})
        for category in sorted(category_elements)
    }
    root_causes = sorted(
        {
            relative
            for item in entries
            for relative in item["root_cause_source_paths"]  # type: ignore[union-attr]
        }
    )
    unclassified = [item for item in entries if item["category"] == "UNCLASSIFIED"]
    payload = {
        "schema": "mrw.stage1.root-astra-failure-classification.v1",
        "status": "PASS_COMPLETE_CLASSIFICATION" if entries and not unclassified else "FAIL_INCOMPLETE_CLASSIFICATION",
        "authoritative": False,
        "inputs": {
            "junit": str(junit),
            "junit_sha256": sha256(junit),
            "source": str(source),
            "preview": str(preview),
        },
        "junit_counts": {
            field: sum(int(suite.attrib.get(field, "0")) for suite in suites)
            for field in ("tests", "failures", "errors", "skipped")
        },
        "classification_counts": {
            "failure_elements": len(entries),
            "unique_nodeids": len({str(item["nodeid"]) for item in entries}),
            "by_category_failure_elements": dict(sorted(category_elements.items())),
            "by_category_unique_nodeids": category_nodeids,
            "unique_root_cause_source_paths": len(root_causes),
        },
        "root_cause_source_paths": root_causes,
        "failures": entries,
        "limits": [
            "Classification is diagnostic and grants no candidate, release, deployment, or authority status.",
            "A cascading failure records both the observed disposable-output path and its missing source-script cause.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=True, indent=2, sort_keys=True)
        stream.write("\n")
    print(
        json.dumps(
            {
                "output": str(output),
                "status": payload["status"],
                "counts": payload["classification_counts"],
            },
            sort_keys=True,
        )
    )
    return 0 if payload["status"] == "PASS_COMPLETE_CLASSIFICATION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
