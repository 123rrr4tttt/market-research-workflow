#!/usr/bin/env python3
"""Validate the repo-local performance/capacity automation spec."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any
try:
    from scripts._automation_runtime import repo_root
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import repo_root


try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python < 3.11
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]


EXPECTED_SCHEMA = "performance_capacity_automation_spec.v1"
DEFAULT_SPEC = (
    "development/latest-dev-docs/automation-runs/"
    "performance-capacity-baseline/automation-spec.json"
)
REQUIRED_OUTPUT_KEYS = {"base_dir", "dated_dir", "artifact", "manifest", "history"}
REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "automation_id",
    "schedule",
    "cwd",
    "command",
    "dry_run",
    "outputs",
    "artifact_paths",
    "success_gates",
    "failure_policy",
}
DRY_RUN_REQUIRED_MARKERS = {
    "DRY-RUN repo_root=",
    "DRY-RUN artifact=",
    "DRY-RUN manifest=",
    "DRY-RUN history=",
    "DRY-RUN service_required=",
    "DRY-RUN checker_cmd=",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check the performance/capacity baseline automation spec."
    )
    parser.add_argument(
        "spec",
        nargs="?",
        default=DEFAULT_SPEC,
        help=f"Automation spec path. Defaults to {DEFAULT_SPEC}.",
    )
    parser.add_argument(
        "--run-date",
        default=date.today().isoformat(),
        help="Run date used to resolve {run_date} placeholders.",
    )
    parser.add_argument(
        "--execute-dry-run",
        action="store_true",
        help="Execute the dry_run command and check expected stdout markers.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"spec does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"spec is not valid JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError("spec root must be a JSON object")
    return loaded


def as_string_list(value: Any, label: str, problems: list[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        problems.append(f"{label} must be a non-empty list")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            problems.append(f"{label}[{index}] must be a non-empty string")
            continue
        result.append(item)
    return result


def resolve_spec_path(path: str, run_date: str) -> Path:
    return (repo_root() / path.replace("{run_date}", run_date)).resolve()


def validate_schedule(schedule: Any, problems: list[str]) -> None:
    if not isinstance(schedule, dict):
        problems.append("schedule must be an object")
        return
    for field in ("timezone", "rrule", "cron", "cadence"):
        if not isinstance(schedule.get(field), str) or not schedule[field]:
            problems.append(f"schedule.{field} must be a non-empty string")
    cadence = str(schedule.get("cadence") or "")
    rrule = str(schedule.get("rrule") or "")
    if cadence not in {"daily", "daily_via_24h_interval"}:
        problems.append("schedule.cadence must be daily or daily_via_24h_interval")
    if "FREQ=DAILY" not in rrule and "FREQ=HOURLY;INTERVAL=24" not in rrule:
        problems.append("schedule.rrule must describe a daily recurrence or 24-hour interval")


def validate_codex_app_installation(spec: dict[str, Any], problems: list[str]) -> None:
    install_status = spec.get("install_status")
    if install_status not in {"repo_spec_only_not_installed", "installed_codex_app"}:
        problems.append("install_status must be repo_spec_only_not_installed or installed_codex_app")
        return
    if install_status != "installed_codex_app":
        return

    codex_app = spec.get("codex_app")
    if not isinstance(codex_app, dict):
        problems.append("codex_app must be an object when install_status=installed_codex_app")
        return
    automation_id = codex_app.get("automation_id")
    config_path = codex_app.get("config_path")
    expected_status = codex_app.get("status")
    expected_rrule = codex_app.get("rrule")
    expected_cwd = codex_app.get("cwd")
    for field, value in (
        ("automation_id", automation_id),
        ("config_path", config_path),
        ("status", expected_status),
        ("rrule", expected_rrule),
        ("cwd", expected_cwd),
    ):
        if not isinstance(value, str) or not value:
            problems.append(f"codex_app.{field} must be a non-empty string")
    if not isinstance(config_path, str) or not config_path:
        return

    path = Path(config_path).expanduser()
    if not path.exists():
        problems.append(f"codex_app.config_path does not exist: {config_path}")
        return
    if tomllib is None:
        problems.append("codex_app installed validation requires Python 3.11+ tomllib")
        return
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        problems.append(f"codex_app.config_path is not readable TOML: {exc}")
        return

    if automation_id and config.get("id") != automation_id:
        problems.append(f"codex_app automation id mismatch: {config.get('id')} != {automation_id}")
    if expected_status and config.get("status") != expected_status:
        problems.append(f"codex_app status mismatch: {config.get('status')} != {expected_status}")
    if expected_rrule and config.get("rrule") != expected_rrule:
        problems.append(f"codex_app rrule mismatch: {config.get('rrule')} != {expected_rrule}")
    if expected_cwd:
        cwds = config.get("cwds")
        if expected_cwd not in (cwds if isinstance(cwds, list) else []):
            problems.append(f"codex_app cwd missing from automation config: {expected_cwd}")
    prompt = config.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        problems.append("codex_app prompt must be a non-empty string")
        return
    command = spec.get("command")
    command_args = command.get("args") if isinstance(command, dict) else []
    if isinstance(command_args, list):
        for arg in command_args:
            if isinstance(arg, str) and arg and arg not in prompt:
                problems.append(f"codex_app prompt missing command arg: {arg}")


def validate_command(command: Any, label: str, problems: list[str]) -> list[str]:
    if not isinstance(command, dict):
        problems.append(f"{label} must be an object")
        return []
    shell = command.get("shell")
    if shell not in {"bash", "sh"}:
        problems.append(f"{label}.shell must be bash or sh")
    args = as_string_list(command.get("args"), f"{label}.args", problems)
    if args and not resolve_spec_path(args[0], "{run_date}").exists():
        problems.append(f"{label}.args[0] script does not exist: {args[0]}")
    return [str(shell)] + args if isinstance(shell, str) and args else []


def validate_outputs(outputs: Any, artifact_paths: Any, run_date: str, problems: list[str]) -> None:
    if not isinstance(outputs, dict):
        problems.append("outputs must be an object")
        return
    missing = REQUIRED_OUTPUT_KEYS - set(outputs)
    if missing:
        problems.append(f"outputs missing keys: {', '.join(sorted(missing))}")
    for key in REQUIRED_OUTPUT_KEYS & set(outputs):
        if not isinstance(outputs[key], str) or not outputs[key]:
            problems.append(f"outputs.{key} must be a non-empty string")

    base_dir = outputs.get("base_dir")
    if isinstance(base_dir, str) and not resolve_spec_path(base_dir, run_date).is_dir():
        problems.append(f"outputs.base_dir does not exist: {base_dir}")

    for key in ("dated_dir", "artifact", "manifest"):
        value = outputs.get(key)
        if isinstance(value, str) and "{run_date}" not in value:
            problems.append(f"outputs.{key} must include {{run_date}}")

    history = outputs.get("history")
    if isinstance(history, str):
        history_path = resolve_spec_path(history, run_date)
        if not history_path.exists():
            problems.append(f"outputs.history does not exist: {history}")
        if history_path.suffix != ".jsonl":
            problems.append("outputs.history must point to a .jsonl file")

    paths = as_string_list(artifact_paths, "artifact_paths", problems)
    for required in ("artifact", "manifest", "history"):
        value = outputs.get(required)
        if isinstance(value, str) and value not in paths:
            problems.append(f"artifact_paths must include outputs.{required}")


def validate_success_gates(gates: Any, problems: list[str]) -> None:
    if not isinstance(gates, list) or not gates:
        problems.append("success_gates must be a non-empty list")
        return
    gate_names: set[str] = set()
    gate_commands: list[str] = []
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict):
            problems.append(f"success_gates[{index}] must be an object")
            continue
        name = gate.get("name")
        command = gate.get("command")
        if not isinstance(name, str) or not name:
            problems.append(f"success_gates[{index}].name must be a non-empty string")
        else:
            gate_names.add(name)
        if not isinstance(command, str) or not command:
            problems.append(f"success_gates[{index}].command must be a non-empty string")
        else:
            if "/Users/wangyiliang/.local/bin/python3.11" in command:
                problems.append(
                    f"success_gates[{index}].command must use python3 or PYTHON, not a user-local python path"
                )
            if "/Users/wangyiliang/.codex" in command:
                problems.append(
                    f"success_gates[{index}].command must not depend on a user-local Codex config path"
                )
            gate_commands.append(command)

    required_names = {"wrapper_syntax", "artifact_schema", "automation_spec"}
    missing_names = required_names - gate_names
    if missing_names:
        problems.append(f"success_gates missing names: {', '.join(sorted(missing_names))}")
    joined = "\n".join(gate_commands)
    for path in (
        "scripts/run_performance_capacity_nightly.sh",
        "scripts/check_performance_capacity_baseline_artifact.py",
        "scripts/check_performance_capacity_automation_spec.py",
    ):
        if path not in joined:
            problems.append(f"success_gates must reference {path}")


def validate_failure_policy(policy: Any, problems: list[str]) -> None:
    if not isinstance(policy, dict):
        problems.append("failure_policy must be an object")
        return
    expected = {
        "generation_failure": "fail_run",
        "artifact_schema_failure": "fail_run",
        "degradation_detected": "fail_run_when_fail_on_degradation_is_set",
        "service_probe_unavailable": "record_only",
    }
    for key, value in expected.items():
        if policy.get(key) != value:
            problems.append(f"failure_policy.{key} must be {value}")
    retry = policy.get("retry")
    if not isinstance(retry, dict):
        problems.append("failure_policy.retry must be an object")
    elif retry.get("max_attempts") != 1:
        problems.append("failure_policy.retry.max_attempts must be 1")


def execute_dry_run(command: list[str], expected_markers: set[str], run_date: str) -> list[str]:
    substituted = [part.replace("{run_date}", run_date) for part in command]
    result = subprocess.run(
        substituted,
        cwd=repo_root(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    problems: list[str] = []
    if result.returncode != 0:
        problems.append(
            "dry_run command failed "
            f"rc={result.returncode} stderr={result.stderr.strip() or '<empty>'}"
        )
        return problems
    for marker in expected_markers:
        if marker not in result.stdout:
            problems.append(f"dry_run stdout missing marker: {marker}")
    return problems


def validate(spec: dict[str, Any], run_date: str, *, execute: bool) -> list[str]:
    problems: list[str] = []
    missing_top_level = REQUIRED_TOP_LEVEL_KEYS - set(spec)
    if missing_top_level:
        problems.append(f"spec missing keys: {', '.join(sorted(missing_top_level))}")
    if spec.get("schema_version") != EXPECTED_SCHEMA:
        problems.append(f"schema_version must be {EXPECTED_SCHEMA}")
    validate_codex_app_installation(spec, problems)

    cwd = spec.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        problems.append("cwd must be a non-empty string")
    elif not resolve_spec_path(cwd, run_date).is_dir():
        problems.append(f"cwd does not exist: {cwd}")

    validate_schedule(spec.get("schedule"), problems)
    command_parts = validate_command(spec.get("command"), "command", problems)
    dry_run_command = validate_command(spec.get("dry_run"), "dry_run", problems)
    validate_outputs(spec.get("outputs"), spec.get("artifact_paths"), run_date, problems)
    validate_success_gates(spec.get("success_gates"), problems)
    validate_failure_policy(spec.get("failure_policy"), problems)
    command_text = " ".join(command_parts)
    if "--api-base" not in command_text or "--service-required" not in command_text:
        problems.append("command.args must include --api-base and --service-required for the installed nightly gate")

    dry_run = spec.get("dry_run")
    expected_markers = set()
    if isinstance(dry_run, dict):
        args = dry_run.get("args")
        if isinstance(args, list) and "--dry-run" not in args:
            problems.append("dry_run.args must include --dry-run")
        expected_markers = set(
            as_string_list(dry_run.get("expected_stdout_markers"), "dry_run.expected_stdout_markers", problems)
        )
        missing_markers = DRY_RUN_REQUIRED_MARKERS - expected_markers
        if missing_markers:
            problems.append(
                "dry_run.expected_stdout_markers missing required markers: "
                + ", ".join(sorted(missing_markers))
            )

    if execute and dry_run_command and not problems:
        problems.extend(execute_dry_run(dry_run_command, expected_markers, run_date))

    return problems


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = repo_root() / spec_path
    try:
        spec = load_json(spec_path)
    except ValueError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1

    problems = validate(spec, args.run_date, execute=args.execute_dry_run)
    if problems:
        for problem in problems:
            print(f"FAIL {spec_path}: {problem}", file=sys.stderr)
        return 1

    print(
        "OK performance_capacity_automation_spec "
        f"id={spec['automation_id']} run_date={args.run_date} execute_dry_run={args.execute_dry_run}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
