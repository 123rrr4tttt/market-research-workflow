#!/usr/bin/env python3
"""Validate performance/capacity baseline JSON artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_SCHEMA = "performance_capacity_baseline.v1"
EXPECTED_FIXTURES = {"small", "medium", "large"}
REQUIRED_BUDGET_FIELDS = {"max_total_ms", "max_records", "max_fixture_bytes"}
REQUIRED_DIAGNOSTIC_KEYS = {
    "schema_version",
    "lane",
    "generated_at",
    "summary",
    "fixture_budget_summary",
    "budget_breach_summary",
    "trend_summary",
    "service_probe_summary",
    "recommended_commands",
}
REQUIRED_RECOMMENDED_COMMANDS = {
    "minimal_gate",
    "self_test",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check the performance/capacity baseline artifact schema."
    )
    parser.add_argument("artifact", help="Path to performance-baseline JSON artifact.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"artifact does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"artifact is not valid JSON: {exc}") from exc


def validate_diagnostic_package(artifact: dict[str, Any], problems: list[str]) -> None:
    diagnostic = artifact.get("diagnostic_package")
    if not isinstance(diagnostic, dict):
        problems.append("diagnostic_package must be an object")
        return

    missing = REQUIRED_DIAGNOSTIC_KEYS - set(diagnostic)
    if missing:
        problems.append(f"diagnostic_package missing keys: {', '.join(sorted(missing))}")
    if diagnostic.get("schema_version") != artifact.get("schema_version"):
        problems.append("diagnostic_package.schema_version must match artifact schema_version")
    if diagnostic.get("lane") != artifact.get("lane"):
        problems.append("diagnostic_package.lane must match artifact lane")
    if diagnostic.get("generated_at") != artifact.get("generated_at"):
        problems.append("diagnostic_package.generated_at must match artifact generated_at")

    summary = diagnostic.get("summary")
    if not isinstance(summary, dict):
        problems.append("diagnostic_package.summary must be an object")
    elif "status" not in summary or "degradation_flag" not in summary:
        problems.append("diagnostic_package.summary.status/degradation_flag missing")

    fixture_summary = diagnostic.get("fixture_budget_summary")
    if not isinstance(fixture_summary, list) or len(fixture_summary) != 3:
        problems.append("diagnostic_package.fixture_budget_summary must contain three fixtures")
        fixture_summary = []
    fixture_names = {
        item.get("fixture")
        for item in fixture_summary
        if isinstance(item, dict)
    }
    if fixture_names != EXPECTED_FIXTURES:
        problems.append("diagnostic_package.fixture_budget_summary must cover small, medium, large")
    for item in fixture_summary:
        if not isinstance(item, dict):
            problems.append("diagnostic_package.fixture_budget_summary items must be objects")
            continue
        for field in ("fixture", "status", "total_ms", "max_total_ms", "budget_checks"):
            if field not in item:
                problems.append(f"diagnostic_package.fixture_budget_summary.{field} missing")

    breach_summary = diagnostic.get("budget_breach_summary")
    if not isinstance(breach_summary, dict):
        problems.append("diagnostic_package.budget_breach_summary must be an object")
    elif "count" not in breach_summary or "breaches" not in breach_summary:
        problems.append("diagnostic_package.budget_breach_summary.count/breaches missing")
    elif not isinstance(breach_summary.get("breaches"), list):
        problems.append("diagnostic_package.budget_breach_summary.breaches must be a list")

    trend_summary = diagnostic.get("trend_summary")
    if not isinstance(trend_summary, dict):
        problems.append("diagnostic_package.trend_summary must be an object")
    elif "status" not in trend_summary or "current_total_ms_by_fixture" not in trend_summary:
        problems.append("diagnostic_package.trend_summary.status/current_total_ms_by_fixture missing")

    service_summary = diagnostic.get("service_probe_summary")
    if not isinstance(service_summary, dict):
        problems.append("diagnostic_package.service_probe_summary must be an object")
    elif "enabled" not in service_summary or "status" not in service_summary:
        problems.append("diagnostic_package.service_probe_summary.enabled/status missing")
    else:
        for field in (
            "runtime_mode",
            "latency",
            "service_ping",
            "service_ready",
            "port",
            "secret",
            "dependency",
            "recommended_command",
            "fail_fast_decision",
            "degradation",
        ):
            if field not in service_summary:
                problems.append(f"diagnostic_package.service_probe_summary.{field} missing")
        latency = service_summary.get("latency")
        if not isinstance(latency, dict):
            problems.append("diagnostic_package.service_probe_summary.latency must be an object")
        elif "status" not in latency or "total_elapsed_ms" not in latency:
            problems.append("diagnostic_package.service_probe_summary.latency.status/total_elapsed_ms missing")
        fail_fast = service_summary.get("fail_fast_decision")
        if not isinstance(fail_fast, dict):
            problems.append("diagnostic_package.service_probe_summary.fail_fast_decision must be an object")
        elif any(
            field not in fail_fast
            for field in ("should_fail", "recommended_command", "effective_exit_code", "allow_service_failure")
        ):
            problems.append(
                "diagnostic_package.service_probe_summary.fail_fast_decision."
                "should_fail/recommended_command/effective_exit_code/allow_service_failure missing"
            )
        degradation = service_summary.get("degradation")
        if not isinstance(degradation, dict):
            problems.append("diagnostic_package.service_probe_summary.degradation must be an object")
        elif "flag" not in degradation or "decision" not in degradation:
            problems.append("diagnostic_package.service_probe_summary.degradation.flag/decision missing")

    commands = diagnostic.get("recommended_commands")
    if not isinstance(commands, dict):
        problems.append("diagnostic_package.recommended_commands must be an object")
        return
    missing_commands = REQUIRED_RECOMMENDED_COMMANDS - set(commands)
    if missing_commands:
        problems.append(
            "diagnostic_package.recommended_commands missing keys: "
            + ", ".join(sorted(missing_commands))
        )
    minimal_gate = commands.get("minimal_gate")
    if not isinstance(minimal_gate, str) or "check_performance_capacity_baseline_artifact.py" not in minimal_gate:
        problems.append("diagnostic_package.recommended_commands.minimal_gate invalid")


def validate(artifact: dict[str, Any]) -> list[str]:
    problems: list[str] = []

    if artifact.get("schema_version") != EXPECTED_SCHEMA:
        problems.append(f"schema_version must be {EXPECTED_SCHEMA}")
    if artifact.get("lane") != "performance_capacity_baseline_smoke":
        problems.append("lane must be performance_capacity_baseline_smoke")

    budgets = artifact.get("budgets")
    if not isinstance(budgets, dict):
        problems.append("budgets must be an object")
        budgets = {}
    if set(budgets) != EXPECTED_FIXTURES:
        problems.append("budgets must contain exactly small, medium, large")
    for fixture, budget in budgets.items():
        if not isinstance(budget, dict):
            problems.append(f"budget for {fixture} must be an object")
            continue
        missing = REQUIRED_BUDGET_FIELDS - set(budget)
        if missing:
            problems.append(f"budget for {fixture} missing fields: {', '.join(sorted(missing))}")

    observations = artifact.get("observations")
    if not isinstance(observations, list) or len(observations) != 3:
        problems.append("observations must contain exactly three fixture results")
        observations = []

    observed_fixtures: set[str] = set()
    for item in observations:
        fixture = item.get("fixture", {})
        name = fixture.get("name")
        observed_fixtures.add(name)
        if name not in EXPECTED_FIXTURES:
            problems.append(f"unexpected fixture name: {name}")
        if "record_count" not in fixture:
            problems.append(f"{name} fixture.record_count missing")
        if "budget" not in item:
            problems.append(f"{name} budget missing in observation")
        observed = item.get("observed", {})
        timings = observed.get("timings_ms", {})
        capacity = observed.get("capacity", {})
        if observed.get("status") not in {"passed", "budget_exceeded"}:
            problems.append(f"{name} observed.status invalid")
        if "total_ms" not in timings:
            problems.append(f"{name} observed.timings_ms.total_ms missing")
        if "fixture_bytes" not in capacity:
            problems.append(f"{name} observed.capacity.fixture_bytes missing")
        checks = item.get("budget_checks", {})
        if not isinstance(checks, dict) or not checks:
            problems.append(f"{name} budget_checks missing")

    if observed_fixtures != EXPECTED_FIXTURES:
        problems.append("observations must cover small, medium, large")

    trend = artifact.get("trend_record")
    if not isinstance(trend, dict):
        problems.append("trend_record must be an object")
    elif "status" not in trend or "current_total_ms_by_fixture" not in trend:
        problems.append("trend_record.status/current_total_ms_by_fixture missing")

    degradation = artifact.get("degradation")
    if not isinstance(degradation, dict):
        problems.append("degradation must be an object")
    elif "flag" not in degradation or "reasons" not in degradation:
        problems.append("degradation.flag/reasons missing")

    service_probe = artifact.get("service_probe")
    if not isinstance(service_probe, dict) or "status" not in service_probe:
        problems.append("service_probe.status missing")
    else:
        for field in (
            "runtime_mode",
            "latency",
            "service_ping",
            "service_ready",
            "port",
            "secret",
            "dependency",
            "recommended_command",
            "fail_fast_decision",
            "degradation",
        ):
            if field not in service_probe:
                problems.append(f"service_probe.{field} missing")
        for field in (
            "latency",
            "service_ping",
            "service_ready",
            "port",
            "secret",
            "dependency",
            "fail_fast_decision",
            "degradation",
        ):
            if field in service_probe and not isinstance(service_probe.get(field), dict):
                problems.append(f"service_probe.{field} must be an object")
        fail_fast = service_probe.get("fail_fast_decision")
        service_ready = service_probe.get("service_ready")
        degradation_record = service_probe.get("degradation")
        latency = service_probe.get("latency")
        if isinstance(latency, dict):
            if latency.get("status") not in {"measured", "skipped"}:
                problems.append("service_probe.latency.status invalid")
            if not isinstance(latency.get("total_elapsed_ms"), (int, float)):
                problems.append("service_probe.latency.total_elapsed_ms must be numeric")
        if isinstance(fail_fast, dict):
            if not isinstance(fail_fast.get("should_fail"), bool):
                problems.append("service_probe.fail_fast_decision.should_fail must be a boolean")
            for field in (
                "status",
                "exit_code",
                "effective_exit_code",
                "allow_service_failure",
                "service_required",
                "service_ready_status",
                "recommended_command",
            ):
                if field not in fail_fast:
                    problems.append(f"service_probe.fail_fast_decision.{field} missing")
        if isinstance(degradation_record, dict):
            if not isinstance(degradation_record.get("flag"), bool):
                problems.append("service_probe.degradation.flag must be a boolean")
            if "decision" not in degradation_record:
                problems.append("service_probe.degradation.decision missing")
        requires_service = artifact.get("scope", {}).get("requires_service") is True
        if (
            requires_service
            and isinstance(service_ready, dict)
            and isinstance(fail_fast, dict)
            and isinstance(degradation_record, dict)
        ):
            ready_passed = service_ready.get("status") == "passed"
            if ready_passed and fail_fast.get("should_fail"):
                problems.append("service_probe.fail_fast_decision should not fail when service_ready passed")
            if not ready_passed:
                if fail_fast.get("should_fail") is not True:
                    problems.append("service_probe.fail_fast_decision.should_fail must be true when required service_ready fails")
                if degradation_record.get("flag") is not True:
                    problems.append("service_probe.degradation.flag must be true when required service_ready fails")
                if artifact.get("status") != "degraded":
                    problems.append("artifact.status must be degraded when required service_ready fails")

    validate_diagnostic_package(artifact, problems)

    return problems


def main() -> int:
    args = parse_args()
    path = Path(args.artifact)
    try:
        artifact = load_json(path)
    except ValueError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1

    problems = validate(artifact)
    if problems:
        for problem in problems:
            print(f"FAIL {path}: {problem}", file=sys.stderr)
        return 1

    print(
        "OK performance_capacity_baseline_artifact "
        f"fixtures={','.join(sorted(EXPECTED_FIXTURES))} degradation={artifact['degradation']['flag']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
