#!/usr/bin/env python3
"""Validate an LLM report token state retention nightly artifact set."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_REPORT_KEYS = {
    "contract_version",
    "status",
    "mode",
    "run_id",
    "script_name",
    "retention_plan",
    "query_window",
    "counts",
    "summary",
}
REQUIRED_COUNT_KEYS = {
    "candidate_count",
    "deleted_count",
    "memory_candidate_count",
    "memory_deleted_count",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return loaded


def _require_string(obj: dict[str, Any], key: str, problems: list[str], *, label: str) -> None:
    if not isinstance(obj.get(key), str) or not obj[key]:
        problems.append(f"{label}.{key} must be a non-empty string")


def _require_int_like(obj: dict[str, Any], key: str, problems: list[str], *, label: str) -> None:
    try:
        int(obj.get(key))
    except (TypeError, ValueError):
        problems.append(f"{label}.{key} must be integer-like")


def validate_report(report: dict[str, Any], problems: list[str]) -> None:
    missing = REQUIRED_REPORT_KEYS - set(report)
    if missing:
        problems.append(f"report missing keys: {', '.join(sorted(missing))}")
    _require_string(report, "contract_version", problems, label="report")
    _require_string(report, "status", problems, label="report")
    _require_string(report, "mode", problems, label="report")
    _require_string(report, "run_id", problems, label="report")
    if report.get("script_name") != "cleanup_llm_report_export_token_state":
        problems.append("report.script_name must be cleanup_llm_report_export_token_state")
    if report.get("mode") not in {"dry_run", "execute"}:
        problems.append("report.mode must be dry_run or execute")
    if report.get("status") not in {"ok", "degraded"}:
        problems.append("report.status must be ok or degraded")

    counts = report.get("counts")
    if not isinstance(counts, dict):
        problems.append("report.counts must be an object")
    else:
        for key in REQUIRED_COUNT_KEYS:
            _require_int_like(counts, key, problems, label="report.counts")

    summary = report.get("summary")
    if not isinstance(summary, dict):
        problems.append("report.summary must be an object")
    else:
        _require_string(summary, "cutoff", problems, label="report.summary")
        if not isinstance(summary.get("token_state_store_degraded"), bool):
            problems.append("report.summary.token_state_store_degraded must be boolean")


def validate_manifest(manifest: dict[str, Any], report: dict[str, Any], problems: list[str]) -> None:
    if manifest.get("schema_version") != "llm_report_token_state_retention_nightly_manifest.v1":
        problems.append("manifest.schema_version mismatch")
    if manifest.get("lane") != "llm_report_token_state_retention_nightly":
        problems.append("manifest.lane mismatch")
    if manifest.get("mode") not in {"dry_run", "execute"}:
        problems.append("manifest.mode must be dry_run or execute")
    if manifest.get("mode") != report.get("mode"):
        problems.append("manifest.mode must match report.mode")
    if manifest.get("current", {}).get("run_id") != report.get("run_id"):
        problems.append("manifest.current.run_id must match report.run_id")
    if not isinstance(manifest.get("counts"), dict):
        problems.append("manifest.counts must be an object")
    if not isinstance(manifest.get("degraded", {}).get("flag"), bool):
        problems.append("manifest.degraded.flag must be boolean")
    if not isinstance(manifest.get("validation", {}).get("cleanup_exit_code"), int):
        problems.append("manifest.validation.cleanup_exit_code must be integer")


def validate_history(path: Path, manifest: dict[str, Any], problems: list[str]) -> None:
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except FileNotFoundError:
        problems.append(f"history missing: {path}")
        return
    if not lines:
        problems.append(f"history is empty: {path}")
        return
    try:
        last = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        problems.append(f"history last row invalid JSON: {exc}")
        return
    if last.get("schema_version") != "llm_report_token_state_retention_trend_history.v1":
        problems.append("history last row schema_version mismatch")
    if last.get("run_date") != manifest.get("run_date"):
        problems.append("history last row run_date must match manifest.run_date")
    if last.get("status") != manifest.get("status"):
        problems.append("history last row status must match manifest.status")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", help="retention-report.json path")
    parser.add_argument("--manifest", default=None, help="nightly-manifest.json path")
    parser.add_argument("--history", default=None, help="trend-history.jsonl path")
    args = parser.parse_args()

    artifact_path = Path(args.artifact)
    manifest_path = Path(args.manifest) if args.manifest else artifact_path.with_name("nightly-manifest.json")
    history_path = (
        Path(args.history)
        if args.history
        else artifact_path.parents[1] / "trend-history.jsonl"
    )

    problems: list[str] = []
    try:
        report = _load_json(artifact_path)
        manifest = _load_json(manifest_path)
    except ValueError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1

    validate_report(report, problems)
    validate_manifest(manifest, report, problems)
    validate_history(history_path, manifest, problems)

    if problems:
        for problem in problems:
            print(f"FAIL {problem}", file=sys.stderr)
        return 1

    print(
        "OK llm_report_token_state_retention_artifact "
        f"artifact={artifact_path} manifest={manifest_path} history={history_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
