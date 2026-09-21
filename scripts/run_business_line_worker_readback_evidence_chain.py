#!/usr/bin/env python3
"""Orchestrate worker-required async task readback evidence chain."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Sequence
from urllib import error, parse, request

try:
    from scripts._automation_runtime import repo_root, utc_now, write_json
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import repo_root, utc_now, write_json


SCHEMA_VERSION = "business_line_worker_readback_evidence_chain.v1"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"

MATRIX_PATH = "/api/v1/business-lines/evidence-matrix"

BATCH75_CANDIDATE_BUILDER = "batch75_candidate_builder"
BATCH74_MANIFEST_CHECKER = "batch74_manifest_checker"
BATCH73_LIVE_SAMPLE_RUNNER = "batch73_live_sample_runner"
BATCH71_ASYNC_TASK_READBACK_BUILDER = "batch71_async_task_readback_builder"
BATCH71_ASYNC_TASK_READBACK_CHECKER = "batch71_async_task_readback_checker"
BATCH82_PROJECT_SCHEMA_PREFLIGHT = "batch82_project_schema_preflight"
BATCH83_TRIGGER_SMOKE = "batch83_trigger_smoke"
TRIGGER_SMOKE_HELPER = "scripts/run_business_line_worker_readback_smoke_triggers.py"

CHAIN_STEP_ORDER = (
    BATCH82_PROJECT_SCHEMA_PREFLIGHT,
    BATCH75_CANDIDATE_BUILDER,
    BATCH74_MANIFEST_CHECKER,
    BATCH73_LIVE_SAMPLE_RUNNER,
    BATCH71_ASYNC_TASK_READBACK_BUILDER,
    BATCH71_ASYNC_TASK_READBACK_CHECKER,
)


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class FetchResult:
    status: str
    payload: Any | None
    http_status: int | None
    error: str | None


def normalize_api_base(api_base: str) -> str:
    return api_base.rstrip("/")


def build_url(api_base: str, path: str) -> Annotated[
    str,
    "kit:prepared-command effect_boundary=evidence_chain_http_read witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{normalize_api_base(api_base)}{normalized_path}"


def append_project_key(path: str, project_key: str | None) -> str:
    if not project_key:
        return path
    parsed = parse.urlsplit(path)
    query_items = parse.parse_qsl(parsed.query, keep_blank_values=True)
    query_items.append(("project_key", project_key))
    return parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parse.urlencode(query_items),
            parsed.fragment,
        )
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", required=True, help="Backend base URL, for example http://127.0.0.1:8000.")
    parser.add_argument("--artifact-dir", required=True, type=Path, help="Directory for chain artifacts.")
    parser.add_argument("--timeout", default=5.0, type=float, help="HTTP/subprocess timeout in seconds.")
    parser.add_argument("--project-key", help="Optional project key to scope runtime readback evidence queries.")
    parser.add_argument(
        "--trigger-smoke",
        action="store_true",
        help=(
            "Run the project-scoped worker-required smoke trigger/wait helper before batch75 evidence collection. "
            "Requires --project-key."
        ),
    )
    parser.add_argument("--allow-blocked", action="store_true", help="Exit zero for blocked environment states.")
    parser.add_argument("--json", action="store_true", help="Print the full chain report as JSON.")
    return parser.parse_args(argv)


def artifact_paths(artifact_dir: Path) -> dict[str, Path]:
    return {
        "chain_report": artifact_dir / "business-line-worker-readback-evidence-chain-report.json",
        "project_schema_preflight": artifact_dir / "business-line-worker-project-schema-preflight.json",
        "trigger_smoke": artifact_dir / "business-line-worker-trigger-smoke-artifact.json",
        "candidate_manifest": artifact_dir / "business-line-task-readback-manifest-candidate.json",
        "manifest_checker_report": artifact_dir / "business-line-task-readback-manifest-check.json",
        "live_samples": artifact_dir / "business-line-async-task-readback-live-samples.json",
        "evidence_matrix": artifact_dir / "business-line-evidence-matrix.json",
        "async_task_readback_artifact": artifact_dir / "business-line-async-task-readback-artifact.json",
        "async_check_report": artifact_dir / "business-line-async-task-readback-check.json",
    }


def load_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, f"could not read JSON file: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON file: {exc}"


def parse_stdout_json(stdout: str) -> tuple[Any | None, str | None]:
    try:
        return json.loads(stdout), None
    except json.JSONDecodeError as exc:
        return None, f"stdout is not valid JSON: {exc}"


def payload_status(payload: Any) -> str | None:
    if isinstance(payload, dict) and isinstance(payload.get("status"), str):
        return payload["status"]
    return None


def normalize_step_status(status: str | None, exit_code: int) -> str:
    if status in {STATUS_PASSED, STATUS_FAILED, STATUS_BLOCKED}:
        return status
    return STATUS_FAILED if exit_code != 0 else STATUS_FAILED


def command_timeout(request_timeout: float) -> float:
    return max(30.0, request_timeout * 20)


def run_command(command: Sequence[str], *, cwd: Path, timeout: float) -> CommandResult:
    try:
        completed = subprocess.run(  # noqa: S603 - fixed repo-local command argv, no shell.
            list(command),
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            exit_code=124,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=f"command timed out after {timeout} seconds",
        )
    return CommandResult(
        exit_code=int(completed.returncode),
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def command_step(
    *,
    step: str,
    command: Sequence[str],
    cwd: Path,
    timeout: float,
    artifact_path: Path | None = None,
    report_path: Path | None = None,
    status_source: str,
) -> tuple[dict[str, Any], Any | None]:
    result = run_command(command, cwd=cwd, timeout=timeout)
    payload: Any | None = None
    load_error: str | None = None

    if status_source == "artifact":
        if artifact_path is None:
            load_error = "artifact_path is required for artifact status source"
        else:
            payload, load_error = load_json(artifact_path)
    elif status_source == "stdout":
        payload, load_error = parse_stdout_json(result.stdout)
        if report_path is not None:
            write_json(
                report_path,
                payload
                if load_error is None
                else {
                    "schema_version": f"{SCHEMA_VERSION}.command_stdout_error",
                    "status": STATUS_FAILED,
                    "error": load_error,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            )
    else:
        load_error = f"unknown status source: {status_source}"

    status = normalize_step_status(payload_status(payload), result.exit_code)
    if load_error is not None:
        status = STATUS_FAILED

    row = {
        "step": step,
        "command": list(command),
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "status": status,
        "artifact_path": str(artifact_path) if artifact_path is not None else None,
        "report_path": str(report_path) if report_path is not None else None,
        "error": load_error,
    }
    return row, payload


def fetch_evidence_matrix(api_base: str, *, timeout: float, project_key: str | None = None) -> FetchResult:
    matrix_path = append_project_key(MATRIX_PATH, project_key)
    req = request.Request(build_url(api_base, matrix_path), headers={"Accept": "application/json"}, method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - explicit backend URL input.
            body = response.read().decode("utf-8", errors="replace")
            payload = json.loads(body)
            return FetchResult(status=STATUS_PASSED, payload=payload, http_status=int(response.status), error=None)
    except error.HTTPError as exc:
        return FetchResult(status=STATUS_FAILED, payload=None, http_status=int(exc.code), error=str(exc))
    except json.JSONDecodeError as exc:
        return FetchResult(status=STATUS_FAILED, payload=None, http_status=None, error=f"invalid JSON: {exc}")
    except (error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        return FetchResult(status=STATUS_BLOCKED, payload=None, http_status=None, error=str(exc))


def build_report(
    *,
    api_base: str,
    artifact_dir: Path,
    timeout: float,
    allow_blocked: bool,
    project_key: str | None,
    trigger_smoke: bool,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=owned_checker_and_live_step_results "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    root = repo_root()
    paths = artifact_paths(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    observed_at = utc_now()
    steps: list[dict[str, Any]] = []
    effective_step_order = (
        list(CHAIN_STEP_ORDER)
        if project_key
        else [step for step in CHAIN_STEP_ORDER if step != BATCH82_PROJECT_SCHEMA_PREFLIGHT]
    )
    if trigger_smoke and project_key:
        effective_step_order.insert(1 if BATCH82_PROJECT_SCHEMA_PREFLIGHT in effective_step_order else 0, BATCH83_TRIGGER_SMOKE)

    def base_report(status: str, stopped_at: str | None, reason: str | None = None) -> dict[str, Any]:
        trigger_step = next((step for step in steps if step.get("step") == BATCH83_TRIGGER_SMOKE), None)
        return {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "observed_at": observed_at,
            "api_base": normalize_api_base(api_base),
            "project_key": project_key,
            "artifact_dir": str(artifact_dir),
            "allow_blocked": allow_blocked,
            "trigger_smoke": trigger_smoke,
            "trigger_smoke_status": trigger_step.get("status") if trigger_step is not None else None,
            "trigger_smoke_artifact_path": str(paths["trigger_smoke"]) if trigger_smoke else None,
            "chain_step_order": effective_step_order,
            "stopped_at": stopped_at,
            "reason": reason,
            "artifacts": {name: str(path) for name, path in paths.items() if name != "chain_report"},
            "steps": steps,
        }

    if trigger_smoke and not project_key:
        steps.append(
            {
                "step": BATCH83_TRIGGER_SMOKE,
                "command": [],
                "exit_code": None,
                "stdout": "",
                "stderr": "--trigger-smoke requires --project-key",
                "status": STATUS_FAILED,
                "artifact_path": str(paths["trigger_smoke"]),
                "report_path": None,
                "error": "trigger_smoke_requires_project_key",
            }
        )
        return base_report(STATUS_FAILED, BATCH83_TRIGGER_SMOKE, "trigger_smoke_requires_project_key")

    if project_key:
        preflight_command = [
            "python3",
            "scripts/check_business_line_worker_project_schema_preflight.py",
            "--api-base",
            normalize_api_base(api_base),
            "--project-key",
            project_key,
            "--output",
            str(paths["project_schema_preflight"]),
            "--timeout",
            str(timeout),
            "--json",
        ]
        preflight_step, _preflight_payload = command_step(
            step=BATCH82_PROJECT_SCHEMA_PREFLIGHT,
            command=preflight_command,
            cwd=root,
            timeout=command_timeout(timeout),
            artifact_path=paths["project_schema_preflight"],
            status_source="artifact",
        )
        steps.append(preflight_step)
        if preflight_step["status"] != STATUS_PASSED:
            return base_report(
                preflight_step["status"],
                BATCH82_PROJECT_SCHEMA_PREFLIGHT,
                "project_schema_preflight_not_passed",
            )

    if trigger_smoke and project_key:
        trigger_command = [
            "python3",
            TRIGGER_SMOKE_HELPER,
            "--api-base",
            normalize_api_base(api_base),
            "--project-key",
            project_key,
            "--output",
            str(paths["trigger_smoke"]),
            "--timeout",
            str(timeout),
            "--json",
        ]
        trigger_step, _trigger_payload = command_step(
            step=BATCH83_TRIGGER_SMOKE,
            command=trigger_command,
            cwd=root,
            timeout=command_timeout(timeout),
            artifact_path=paths["trigger_smoke"],
            status_source="artifact",
        )
        steps.append(trigger_step)
        if trigger_step["status"] != STATUS_PASSED:
            return base_report(trigger_step["status"], BATCH83_TRIGGER_SMOKE, "trigger_smoke_not_passed")

    candidate_command = [
        "python3",
        "scripts/build_business_line_task_readback_manifest_from_runtime.py",
        "--api-base",
        normalize_api_base(api_base),
        "--output",
        str(paths["candidate_manifest"]),
        "--timeout",
        str(timeout),
        "--json",
    ]
    if project_key:
        candidate_command.extend(["--project-key", project_key])
    candidate_step, _candidate_payload = command_step(
        step=BATCH75_CANDIDATE_BUILDER,
        command=candidate_command,
        cwd=root,
        timeout=command_timeout(timeout),
        artifact_path=paths["candidate_manifest"],
        status_source="artifact",
    )
    steps.append(candidate_step)
    if candidate_step["status"] != STATUS_PASSED:
        return base_report(candidate_step["status"], BATCH75_CANDIDATE_BUILDER, "candidate_manifest_not_passed")

    manifest_check_command = [
        "python3",
        "scripts/check_business_line_task_readback_manifest.py",
        str(paths["candidate_manifest"]),
        "--json",
    ]
    manifest_step, _manifest_payload = command_step(
        step=BATCH74_MANIFEST_CHECKER,
        command=manifest_check_command,
        cwd=root,
        timeout=command_timeout(timeout),
        report_path=paths["manifest_checker_report"],
        status_source="stdout",
    )
    steps.append(manifest_step)
    if manifest_step["status"] != STATUS_PASSED:
        status = STATUS_BLOCKED if manifest_step["status"] == STATUS_BLOCKED else STATUS_FAILED
        return base_report(status, BATCH74_MANIFEST_CHECKER, "manifest_checker_not_passed")

    live_command = [
        "python3",
        "scripts/run_business_line_async_task_readback_live_samples.py",
        "--api-base",
        normalize_api_base(api_base),
        "--output",
        str(paths["live_samples"]),
        "--timeout",
        str(timeout),
        "--task-readback-manifest",
        str(paths["candidate_manifest"]),
        "--json",
    ]
    if project_key:
        live_command.extend(["--project-key", project_key])
    live_step, _live_payload = command_step(
        step=BATCH73_LIVE_SAMPLE_RUNNER,
        command=live_command,
        cwd=root,
        timeout=command_timeout(timeout),
        artifact_path=paths["live_samples"],
        status_source="artifact",
    )
    steps.append(live_step)
    if live_step["status"] != STATUS_PASSED:
        return base_report(live_step["status"], BATCH73_LIVE_SAMPLE_RUNNER, "live_sample_runner_not_passed")

    matrix_fetch = fetch_evidence_matrix(normalize_api_base(api_base), timeout=timeout, project_key=project_key)
    if matrix_fetch.status == STATUS_PASSED:
        write_json(paths["evidence_matrix"], matrix_fetch.payload)
    else:
        steps.append(
            {
                "step": "evidence_matrix_fetch",
                "command": [
                    "GET",
                    build_url(normalize_api_base(api_base), append_project_key(MATRIX_PATH, project_key)),
                ],
                "exit_code": None,
                "stdout": "",
                "stderr": matrix_fetch.error,
                "status": matrix_fetch.status,
                "artifact_path": str(paths["evidence_matrix"]),
                "report_path": None,
                "http_status": matrix_fetch.http_status,
                "error": matrix_fetch.error,
            }
        )
        return base_report(matrix_fetch.status, BATCH71_ASYNC_TASK_READBACK_BUILDER, "evidence_matrix_unavailable")

    async_builder_command = [
        "python3",
        "scripts/build_business_line_async_task_readback_artifact.py",
        "--evidence-matrix",
        str(paths["evidence_matrix"]),
        "--task-readback-samples",
        str(paths["live_samples"]),
        "--output",
        str(paths["async_task_readback_artifact"]),
        "--json",
    ]
    async_builder_step, _async_payload = command_step(
        step=BATCH71_ASYNC_TASK_READBACK_BUILDER,
        command=async_builder_command,
        cwd=root,
        timeout=command_timeout(timeout),
        artifact_path=paths["async_task_readback_artifact"],
        status_source="artifact",
    )
    steps.append(async_builder_step)
    if async_builder_step["status"] != STATUS_PASSED:
        return base_report(async_builder_step["status"], BATCH71_ASYNC_TASK_READBACK_BUILDER, "async_task_builder_not_passed")

    async_check_command = [
        "python3",
        "scripts/check_business_line_async_task_readback_artifact.py",
        str(paths["async_task_readback_artifact"]),
        "--task-readback-manifest",
        str(paths["candidate_manifest"]),
        "--json",
    ]
    async_check_step, _async_check_payload = command_step(
        step=BATCH71_ASYNC_TASK_READBACK_CHECKER,
        command=async_check_command,
        cwd=root,
        timeout=command_timeout(timeout),
        report_path=paths["async_check_report"],
        status_source="stdout",
    )
    steps.append(async_check_step)
    if async_check_step["status"] != STATUS_PASSED:
        return base_report(async_check_step["status"], BATCH71_ASYNC_TASK_READBACK_CHECKER, "async_task_checker_not_passed")

    return base_report(STATUS_PASSED, None, None)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        api_base=args.api_base,
        artifact_dir=args.artifact_dir,
        timeout=args.timeout,
        allow_blocked=args.allow_blocked,
        project_key=args.project_key,
        trigger_smoke=args.trigger_smoke,
    )
    report_path = artifact_paths(args.artifact_dir)["chain_report"]
    write_json(report_path, report)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"business_line_worker_readback_evidence_chain={report['status']} report={report_path}")

    if report["status"] == STATUS_PASSED:
        return 0
    if report["status"] == STATUS_BLOCKED and args.allow_blocked:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
