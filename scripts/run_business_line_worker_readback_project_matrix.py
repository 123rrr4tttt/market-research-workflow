#!/usr/bin/env python3
"""Run the worker readback evidence chain for multiple project keys."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from scripts._automation_runtime import repo_root, utc_now, write_json
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import repo_root, utc_now, write_json


SCHEMA_VERSION = "business_line_worker_readback_project_matrix.v1"
CHAIN_REPORT_NAME = "business-line-worker-readback-evidence-chain-report.json"
MATRIX_REPORT_NAME = "business-line-worker-readback-project-matrix-report.json"
CHAIN_SCRIPT = "scripts/run_business_line_worker_readback_evidence_chain.py"

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"

SAFE_DIR_RE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


def normalize_api_base(api_base: str) -> str:
    return api_base.rstrip("/")


def matrix_report_path(artifact_dir: Path) -> Path:
    return artifact_dir / MATRIX_REPORT_NAME


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", required=True, help="Backend base URL, for example http://127.0.0.1:8000.")
    parser.add_argument(
        "--project-key",
        action="append",
        default=[],
        help="Project key to run. May be supplied multiple times.",
    )
    parser.add_argument(
        "--projects-list-json",
        type=Path,
        help="Optional project inventory JSON. Enabled project_key values are appended to the matrix input.",
    )
    parser.add_argument(
        "--projects-api-url",
        help="Optional projects API URL. Enabled project_key values from the response are appended to the matrix input.",
    )
    parser.add_argument("--project-key-regex", help="Optional regex filter applied after merging project sources.")
    parser.add_argument(
        "--exclude-project-key",
        action="append",
        default=[],
        help="Project key to exclude after merging project sources. May be supplied multiple times.",
    )
    parser.add_argument("--max-projects", type=int, help="Maximum projects to keep after filtering.")
    parser.add_argument("--artifact-dir", required=True, type=Path, help="Directory for matrix artifacts.")
    parser.add_argument("--timeout", default=5.0, type=float, help="HTTP/subprocess timeout in seconds.")
    parser.add_argument("--trigger-smoke", action="store_true", help="Pass --trigger-smoke to each project chain.")
    parser.add_argument(
        "--include-child-reports",
        action="store_true",
        help="Embed full child stdout/stderr/chain_report in the top-level matrix report.",
    )
    parser.add_argument("--allow-blocked", action="store_true", help="Exit zero when the matrix is blocked by environment.")
    parser.add_argument("--json", action="store_true", help="Print the full matrix report as JSON.")
    return parser.parse_args(argv)


def load_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, f"could not read JSON file: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON file: {exc}"


def payload_status(payload: Any) -> str | None:
    if isinstance(payload, dict) and isinstance(payload.get("status"), str):
        return payload["status"]
    return None


def project_records_from_payload(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise ValueError("project inventory JSON must be a list or JSON envelope")

    candidates: list[Any] = [payload.get("data"), payload.get("projects"), payload.get("items"), payload.get("results")]
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.extend([data.get("projects"), data.get("items"), data.get("results"), data.get("data")])

    for candidate in candidates:
        if isinstance(candidate, list):
            return candidate
    raise ValueError("project inventory JSON does not contain a project list")


def project_record_selection(record: Any, *, allow_bare_string: bool = True) -> tuple[str | None, str | None]:
    if isinstance(record, str):
        if not allow_bare_string:
            return None, "bare_string_not_allowed"
        project_key = record.strip()
        return (project_key, None) if project_key else (None, "project_key_missing")
    if not isinstance(record, dict):
        return None, "record_not_object"
    if record.get("enabled") is not True:
        return None, "disabled"
    if record.get("archived") is True:
        return None, "archived"
    if record.get("schema_ready") is False:
        return None, "schema_not_ready"
    if record.get("has_worker_fixture") is False:
        return None, "worker_fixture_missing"
    if record.get("nightly_matrix_eligible") is False:
        return None, "nightly_matrix_not_eligible"
    project_key = record.get("project_key")
    if not isinstance(project_key, str):
        return None, "project_key_missing"
    project_key = project_key.strip()
    return (project_key, None) if project_key else (None, "project_key_missing")


def enabled_project_key(record: Any, *, allow_bare_string: bool = True) -> str | None:
    project_key, _ = project_record_selection(record, allow_bare_string=allow_bare_string)
    return project_key


def project_selection_from_records(records: Sequence[Any], *, allow_bare_string: bool) -> tuple[list[str], list[dict[str, Any]]]:
    project_keys: list[str] = []
    excluded: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        project_key, reason = project_record_selection(record, allow_bare_string=allow_bare_string)
        if project_key:
            project_keys.append(project_key)
            continue
        if isinstance(record, dict):
            raw_project_key = record.get("project_key")
        else:
            raw_project_key = record
        excluded.append(
            {
                "index": index,
                "project_key": raw_project_key if isinstance(raw_project_key, str) else None,
                "reason": reason or "excluded",
            }
        )
    return project_keys, excluded


def project_keys_from_inventory(path: Path) -> list[str]:
    payload, error = load_json(path)
    if error is not None:
        raise ValueError(error)
    project_keys, _ = project_selection_from_records(project_records_from_payload(payload), allow_bare_string=True)
    return project_keys


def fetch_json_url(url: str, *, timeout: float) -> Any:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-supplied API URL.
            charset = response.headers.get_content_charset() or "utf-8"
            raw_payload = response.read().decode(charset)
    except HTTPError as exc:
        raise ValueError(f"projects API request failed with HTTP {exc.code}: {url}") from exc
    except URLError as exc:
        raise ValueError(f"projects API request failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ValueError(f"projects API request timed out after {timeout} seconds") from exc

    try:
        return json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"projects API response was not valid JSON: {exc}") from exc


def project_keys_from_api_url(url: str, *, timeout: float) -> list[str]:
    payload = fetch_json_url(url, timeout=timeout)
    project_keys, _ = project_selection_from_records(project_records_from_payload(payload), allow_bare_string=False)
    return project_keys


def project_selection_from_api_url(url: str, *, timeout: float) -> tuple[list[str], list[dict[str, Any]]]:
    payload = fetch_json_url(url, timeout=timeout)
    return project_selection_from_records(project_records_from_payload(payload), allow_bare_string=False)


def unique_project_keys(*groups: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    project_keys: list[str] = []
    for group in groups:
        for raw_project_key in group:
            project_key = raw_project_key.strip()
            if not project_key or project_key in seen:
                continue
            seen.add(project_key)
            project_keys.append(project_key)
    return project_keys


def validate_project_selection_args(args: argparse.Namespace) -> re.Pattern[str] | None:
    if args.max_projects is not None and args.max_projects <= 0:
        raise ValueError("--max-projects must be greater than 0")
    if args.project_key_regex is None:
        return None
    try:
        return re.compile(args.project_key_regex)
    except re.error as exc:
        raise ValueError(f"invalid --project-key-regex: {exc}") from exc


def apply_project_filters(
    project_keys: Sequence[str],
    *,
    project_key_regex: re.Pattern[str] | None,
    exclude_project_keys: Sequence[str],
    max_projects: int | None,
) -> list[str]:
    excluded = {project_key.strip() for project_key in exclude_project_keys if project_key.strip()}
    filtered: list[str] = []
    for project_key in project_keys:
        if project_key_regex is not None and project_key_regex.search(project_key) is None:
            continue
        if project_key in excluded:
            continue
        filtered.append(project_key)
    if max_projects is not None:
        filtered = filtered[:max_projects]
    return filtered


def resolve_project_selection(args: argparse.Namespace) -> dict[str, Any]:
    project_key_regex = validate_project_selection_args(args)
    inventory_keys: list[str] = []
    if args.projects_list_json is not None:
        inventory_keys = project_keys_from_inventory(args.projects_list_json)
    api_keys: list[str] = []
    api_excluded: list[dict[str, Any]] = []
    if args.projects_api_url is not None:
        api_keys, api_excluded = project_selection_from_api_url(args.projects_api_url, timeout=args.timeout)
    merged_keys = unique_project_keys(args.project_key, inventory_keys, api_keys)
    project_keys = apply_project_filters(
        merged_keys,
        project_key_regex=project_key_regex,
        exclude_project_keys=args.exclude_project_key,
        max_projects=args.max_projects,
    )
    return {
        "explicit": {"project_keys": [project_key for project_key in args.project_key if project_key.strip()]},
        "file": {
            "projects_list_json": str(args.projects_list_json) if args.projects_list_json is not None else None,
            "project_keys": inventory_keys,
        },
        "api": {"projects_api_url": args.projects_api_url, "project_keys": api_keys, "excluded": api_excluded},
        "filter": {"project_key_regex": args.project_key_regex},
        "exclude": {"project_keys": [project_key for project_key in args.exclude_project_key if project_key.strip()]},
        "max": {"projects": args.max_projects},
        "explicit_project_keys": [project_key for project_key in args.project_key if project_key.strip()],
        "projects_list_json": str(args.projects_list_json) if args.projects_list_json is not None else None,
        "file_project_keys": inventory_keys,
        "projects_api_url": args.projects_api_url,
        "api_project_keys": api_keys,
        "api_excluded_projects": api_excluded,
        "project_key_regex": args.project_key_regex,
        "exclude_project_keys": [project_key for project_key in args.exclude_project_key if project_key.strip()],
        "max_projects": args.max_projects,
        "merged_project_keys": merged_keys,
        "project_keys": project_keys,
    }


def normalize_status(status: str | None, exit_code: int) -> str:
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
    return CommandResult(exit_code=int(completed.returncode), stdout=completed.stdout, stderr=completed.stderr)


def safe_project_dir_name(project_key: str) -> str:
    stripped = project_key.strip()
    candidate = SAFE_DIR_RE.sub("_", stripped).strip("._-")
    if candidate == stripped and candidate not in {"", ".", ".."}:
        return candidate
    if not candidate:
        candidate = "project"
    digest = hashlib.sha256(project_key.encode("utf-8")).hexdigest()[:12]
    return f"{candidate[:80]}-{digest}"


def project_artifact_dir(artifact_dir: Path, project_key: str) -> Path:
    root = artifact_dir.resolve()
    child = (root / safe_project_dir_name(project_key)).resolve()
    try:
        child.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"unsafe project artifact directory for project_key={project_key!r}") from exc
    return child


def build_chain_command(
    *,
    api_base: str,
    project_key: str,
    artifact_dir: Path,
    timeout: float,
    trigger_smoke: bool,
) -> Annotated[
    list[str],
    "kit:prepared-command effect_boundary=worker_readback_chain_subprocess witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    command = [
        "python3",
        CHAIN_SCRIPT,
        "--api-base",
        normalize_api_base(api_base),
        "--project-key",
        project_key,
        "--artifact-dir",
        str(artifact_dir),
        "--timeout",
        str(timeout),
        "--json",
    ]
    if trigger_smoke:
        command.append("--trigger-smoke")
    return command


def run_project_chain(
    *,
    api_base: str,
    project_key: str,
    root_artifact_dir: Path,
    timeout: float,
    trigger_smoke: bool,
    cwd: Path,
    include_child_reports: bool,
) -> dict[str, Any]:
    artifact_dir = project_artifact_dir(root_artifact_dir, project_key)
    report_path = artifact_dir / CHAIN_REPORT_NAME
    command = build_chain_command(
        api_base=api_base,
        project_key=project_key,
        artifact_dir=artifact_dir,
        timeout=timeout,
        trigger_smoke=trigger_smoke,
    )
    result = run_command(command, cwd=cwd, timeout=command_timeout(timeout))
    payload, load_error = load_json(report_path)
    status = normalize_status(payload_status(payload), result.exit_code)
    if load_error is not None:
        status = STATUS_FAILED

    project_report = {
        "project_key": project_key,
        "status": status,
        "artifact_dir": str(artifact_dir),
        "chain_report_path": str(report_path),
        "command": command,
        "exit_code": result.exit_code,
        "error": load_error,
        "chain_summary": payload.get("summary") if isinstance(payload, dict) else None,
        "trigger_smoke_status": payload.get("trigger_smoke_status") if isinstance(payload, dict) else None,
        "reason": payload.get("reason") if isinstance(payload, dict) else None,
        "stopped_at": payload.get("stopped_at") if isinstance(payload, dict) else None,
    }
    if isinstance(payload, dict) and project_report["trigger_smoke_status"] is None:
        trigger_smoke_payload = payload.get("trigger_smoke")
        if isinstance(trigger_smoke_payload, dict) and isinstance(trigger_smoke_payload.get("status"), str):
            project_report["trigger_smoke_status"] = trigger_smoke_payload["status"]
    if include_child_reports:
        project_report.update(
            {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "chain_report": payload if load_error is None else None,
            }
        )
    return project_report


def summarize_projects(projects: Sequence[dict[str, Any]]) -> dict[str, Any]:
    counts = {STATUS_PASSED: 0, STATUS_FAILED: 0, STATUS_BLOCKED: 0}
    for project in projects:
        status = project.get("status")
        if status in counts:
            counts[status] += 1
    return {
        "total": len(projects),
        "passed": counts[STATUS_PASSED],
        "failed": counts[STATUS_FAILED],
        "blocked_by_environment": counts[STATUS_BLOCKED],
    }


def matrix_status(projects: Sequence[dict[str, Any]]) -> str:
    if not projects:
        return STATUS_FAILED
    statuses = [project.get("status") for project in projects]
    if any(status == STATUS_FAILED for status in statuses):
        return STATUS_FAILED
    if any(status == STATUS_BLOCKED for status in statuses):
        return STATUS_BLOCKED
    return STATUS_PASSED


def recommended_next_commands(
    *,
    api_base: str,
    artifact_dir: Path,
    project_selection: dict[str, Any],
    timeout: float,
    trigger_smoke: bool,
) -> list[str]:
    selection_args: list[str] = []
    if project_selection.get("projects_api_url"):
        selection_args.extend(["--projects-api-url", str(project_selection["projects_api_url"])])
        for project_key in project_selection.get("explicit_project_keys", []):
            selection_args.extend(["--project-key", str(project_key)])
        if project_selection.get("projects_list_json"):
            selection_args.extend(["--projects-list-json", str(project_selection["projects_list_json"])])
    else:
        for project_key in project_selection.get("project_keys", []):
            selection_args.extend(["--project-key", str(project_key)])
    if project_selection.get("project_key_regex"):
        selection_args.extend(["--project-key-regex", str(project_selection["project_key_regex"])])
    for project_key in project_selection.get("exclude_project_keys", []):
        selection_args.extend(["--exclude-project-key", str(project_key)])
    if project_selection.get("max_projects") is not None:
        selection_args.extend(["--max-projects", str(project_selection["max_projects"])])
    project_args = " ".join(shlex.quote(arg) for arg in selection_args)
    trigger_arg = " --trigger-smoke" if trigger_smoke else ""
    return [
        (
            "python3 scripts/run_business_line_worker_readback_project_matrix.py "
            f"--api-base {shlex.quote(normalize_api_base(api_base))} {project_args} "
            f"--artifact-dir {shlex.quote(str(artifact_dir))} "
            f"--timeout {timeout}{trigger_arg} --allow-blocked --json"
        ),
    ]


def build_report(
    *,
    api_base: str,
    project_selection: dict[str, Any],
    artifact_dir: Path,
    timeout: float,
    allow_blocked: bool,
    trigger_smoke: bool,
    include_child_reports: bool,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=project_selection_and_owned_step_results "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    root = repo_root()
    project_keys = project_selection["project_keys"]
    artifact_dir.mkdir(parents=True, exist_ok=True)
    projects = [
        run_project_chain(
            api_base=api_base,
            project_key=project_key,
            root_artifact_dir=artifact_dir,
            timeout=timeout,
            trigger_smoke=trigger_smoke,
            cwd=root,
            include_child_reports=include_child_reports,
        )
        for project_key in project_keys
    ]
    status = matrix_status(projects)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "observed_at": utc_now(),
        "api_base": normalize_api_base(api_base),
        "artifact_dir": str(artifact_dir),
        "allow_blocked": allow_blocked,
        "trigger_smoke": trigger_smoke,
        "include_child_reports": include_child_reports,
        "project_selection": project_selection,
        "projects": projects,
        "summary": summarize_projects(projects),
        "error": None if project_keys else "no project keys were provided",
        "recommended_next_commands": recommended_next_commands(
            api_base=api_base,
            artifact_dir=artifact_dir,
            project_selection=project_selection,
            timeout=timeout,
            trigger_smoke=trigger_smoke,
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        project_selection = resolve_project_selection(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    report = build_report(
        api_base=args.api_base,
        project_selection=project_selection,
        artifact_dir=args.artifact_dir,
        timeout=args.timeout,
        allow_blocked=args.allow_blocked,
        trigger_smoke=args.trigger_smoke,
        include_child_reports=args.include_child_reports,
    )
    report_path = matrix_report_path(args.artifact_dir)
    write_json(report_path, report)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"business_line_worker_readback_project_matrix={report['status']} report={report_path}")

    if report["status"] == STATUS_PASSED:
        return 0
    if report["status"] == STATUS_BLOCKED and args.allow_blocked:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
