#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REQUIRED_GATE_KEYS = [
    "gate_version",
    "decision",
    "hard_failures",
    "soft_failures",
    "missing_items",
    "observability",
]
REQUIRED_GATE_METRICS_KEYS = [
    "gate_version",
    "decision",
    "pass",
    "hard_failure_count",
    "soft_failure_count",
    "citation_coverage",
    "evidence_coverage",
    "source_count",
    "unique_citations",
    "rules_count",
    "gate_duration_ms",
]


def _check_gate_metrics_visibility(backend_root: Path) -> int:
    cmd = [
        sys.executable,
        "-c",
        (
            "from app.services.llm_report_generator import build_structured_report, evaluate_report_gate; "
            "report=build_structured_report('must-check', [{'id':'S1','title':'t','url':'https://example.com','publisher':'p','evidence':'ok'}]); "
            "print(__import__('json').dumps(evaluate_report_gate(report), ensure_ascii=False))"
        ),
    ]
    print("[must-minset] running:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=backend_root, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        return proc.returncode

    gate = json.loads(proc.stdout.strip())
    missing = [key for key in REQUIRED_GATE_KEYS if key not in gate]
    if missing:
        print(f"[must-minset] missing gate keys: {missing}")
        return 1
    print("[must-minset] gate metrics visible:", ", ".join(REQUIRED_GATE_KEYS))
    return 0


def _check_quality_gate_metrics_export(backend_root: Path) -> int:
    cmd = [
        sys.executable,
        "-c",
        (
            "from app.services.llm_report_generator import "
            "build_structured_report,evaluate_report_gate,export_quality_gate_metrics; "
            "report=build_structured_report('must-check', [{'id':'S1','title':'t','url':'https://example.com','publisher':'p','evidence':'ok'}]); "
            "print(__import__('json').dumps(export_quality_gate_metrics(evaluate_report_gate(report)), ensure_ascii=False))"
        ),
    ]
    print("[must-minset] running:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=backend_root, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        return proc.returncode

    metrics = json.loads(proc.stdout.strip())
    missing = [key for key in REQUIRED_GATE_METRICS_KEYS if key not in metrics]
    if missing:
        print(f"[must-minset] missing quality_gate_metrics keys: {missing}")
        return 1
    print("[must-minset] quality_gate_metrics visible:", ", ".join(REQUIRED_GATE_METRICS_KEYS))
    return 0


def main() -> int:
    backend_root = Path(__file__).resolve().parents[1]
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/unit/test_llm_report_generator_unittest.py",
        "tests/unit/test_llm_report_api_unittest.py",
    ]
    print("[must-minset] running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=backend_root)
    if result.returncode != 0:
        return result.returncode

    rc = _check_gate_metrics_visibility(backend_root)
    if rc != 0:
        return rc
    return _check_quality_gate_metrics_export(backend_root)


if __name__ == "__main__":
    raise SystemExit(main())
