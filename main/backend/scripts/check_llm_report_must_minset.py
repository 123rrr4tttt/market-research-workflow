#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    print("[must-minset] running:", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def _check_gate_metrics_visibility(backend_root: Path) -> tuple[int, dict[str, object]]:
    cmd = [
        sys.executable,
        "-c",
        (
            "from app.services.llm_report_generator import build_structured_report, evaluate_report_gate; "
            "report=build_structured_report('must-check', [{'id':'S1','title':'t','url':'https://example.com','publisher':'p','evidence':'ok'}]); "
            "print(__import__('json').dumps(evaluate_report_gate(report), ensure_ascii=False))"
        ),
    ]
    proc = _run(cmd, backend_root)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        return proc.returncode, {"stage": "gate_metrics_visibility", "error": "command_failed"}

    gate = json.loads(proc.stdout.strip())
    missing = [key for key in REQUIRED_GATE_KEYS if key not in gate]
    if missing:
        print(f"[must-minset] missing gate keys: {missing}")
        return 1, {"stage": "gate_metrics_visibility", "missing": missing, "gate": gate}
    print("[must-minset] gate metrics visible:", ", ".join(REQUIRED_GATE_KEYS))
    return 0, {"stage": "gate_metrics_visibility", "gate": gate}


def _check_quality_gate_metrics_export(backend_root: Path) -> tuple[int, dict[str, object]]:
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
    proc = _run(cmd, backend_root)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        return proc.returncode, {"stage": "quality_gate_metrics_export", "error": "command_failed"}

    metrics = json.loads(proc.stdout.strip())
    missing = [key for key in REQUIRED_GATE_METRICS_KEYS if key not in metrics]
    if missing:
        print(f"[must-minset] missing quality_gate_metrics keys: {missing}")
        return 1, {"stage": "quality_gate_metrics_export", "missing": missing, "metrics": metrics}
    print("[must-minset] quality_gate_metrics visible:", ", ".join(REQUIRED_GATE_METRICS_KEYS))
    return 0, {"stage": "quality_gate_metrics_export", "metrics": metrics}


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM report must-check minset with evidence output")
    parser.add_argument(
        "--artifact-dir",
        default="main/backend/artifacts/llm-report-must-check",
        help="Directory to write llm report gate evidence",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    backend_root = Path(__file__).resolve().parents[1]
    artifact_dir = (repo_root / args.artifact_dir).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, object] = {
        "check": "llm-report-must-minset",
        "decision": "fail",
        "required_gate_keys": REQUIRED_GATE_KEYS,
        "required_gate_metrics_keys": REQUIRED_GATE_METRICS_KEYS,
    }

    pytest_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/unit/test_llm_report_generator_unittest.py",
        "tests/unit/test_llm_report_api_unittest.py",
    ]
    pytest_proc = _run(pytest_cmd, backend_root)
    print(pytest_proc.stdout)
    print(pytest_proc.stderr)
    summary["pytest"] = {
        "command": " ".join(pytest_cmd),
        "exit_code": pytest_proc.returncode,
    }
    if pytest_proc.returncode != 0:
        (artifact_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return pytest_proc.returncode

    rc_gate, gate_payload = _check_gate_metrics_visibility(backend_root)
    summary["gate_check"] = gate_payload
    if rc_gate != 0:
        (artifact_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return rc_gate

    rc_metrics, metrics_payload = _check_quality_gate_metrics_export(backend_root)
    summary["metrics_check"] = metrics_payload
    summary["decision"] = "pass" if rc_metrics == 0 else "fail"

    (artifact_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return rc_metrics


if __name__ == "__main__":
    raise SystemExit(main())
