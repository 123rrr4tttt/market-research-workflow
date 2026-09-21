#!/usr/bin/env python3
"""Check resource source lifecycle smoke JSON artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Annotated, Any, Sequence

try:
    from scripts._automation_runtime import repo_root, utc_now
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import repo_root, utc_now


ARTIFACT_SCHEMA_VERSION = "resource_source_lifecycle_smoke.v1"
CHECK_SCHEMA_VERSION = "resource_source_lifecycle_smoke_check.v1"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"

REQUIRED_STEPS = (
    "create_site_entry",
    "readback_site_entry",
    "accept_lifecycle",
    "source_library_run",
    "reject_lifecycle",
)
REQUIRED_TOP_LEVEL_FIELDS = (
    "schema_version",
    "status",
    "generated_at",
    "api_base",
    "project_key",
    "site_entry_url",
    "steps",
    "failures",
    "summary",
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", help="Resource source lifecycle smoke JSON artifact path.")
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Exit 0 when the artifact is blocked by environment, while still failing failed states.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args(argv)


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def relative_artifact_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def load_artifact(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, f"artifact could not be read: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"artifact is not valid JSON: {exc}"


def normalize_status(value: Any) -> str | None:
    if not is_present(value):
        return None
    return str(value).strip().lower()


def step_by_name(steps: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for step in steps:
        name = str(step.get("name") or "").strip()
        if name and name not in by_name:
            by_name[name] = step
    return by_name


def collect_step_names(steps: Sequence[dict[str, Any]]) -> list[str]:
    return [str(step.get("name") or "").strip() for step in steps if str(step.get("name") or "").strip()]


def check_accepted_guard(step: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    evidence = step.get("evidence") if isinstance(step, dict) and isinstance(step.get("evidence"), dict) else {}
    guard = evidence.get("single_source_guard") if isinstance(evidence.get("single_source_guard"), dict) else {}
    if not step:
        return {"guard_status": None}, ["accept_lifecycle"]
    if step.get("status") != STATUS_PASSED:
        failures.append("accept_lifecycle.status")
    if evidence.get("lifecycle_state") != "accepted":
        failures.append("accept_lifecycle.lifecycle_state")
    if evidence.get("review_closure_status") != "ready_to_collect":
        failures.append("accept_lifecycle.review_closure_status")
    if evidence.get("next_action") != "collect_source_library_run":
        failures.append("accept_lifecycle.next_action")
    if evidence.get("next_action_enabled") is not True:
        failures.append("accept_lifecycle.next_action_enabled")
    if guard.get("status") != "passed":
        failures.append("accept_lifecycle.single_source_guard.status")
    if guard.get("strict_source") is not True:
        failures.append("accept_lifecycle.single_source_guard.strict_source")
    if guard.get("guarantee") is not True:
        failures.append("accept_lifecycle.single_source_guard.guarantee")
    if not is_present(guard.get("report_source_ref")) and not is_present(evidence.get("report_source_ref")):
        failures.append("accept_lifecycle.report_source_ref")
    return {
        "guard_status": guard.get("status"),
        "strict_source": guard.get("strict_source"),
        "guarantee": guard.get("guarantee"),
        "report_source_ref": guard.get("report_source_ref") or evidence.get("report_source_ref"),
    }, failures


def check_blocked_review(step: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    evidence = step.get("evidence") if isinstance(step, dict) and isinstance(step.get("evidence"), dict) else {}
    guard = evidence.get("single_source_guard") if isinstance(evidence.get("single_source_guard"), dict) else {}
    if not step:
        return {"review_closure_status": None}, ["reject_lifecycle"]
    if step.get("status") != STATUS_PASSED:
        failures.append("reject_lifecycle.status")
    if evidence.get("lifecycle_state") not in {"rejected", "needs_review"}:
        failures.append("reject_lifecycle.lifecycle_state")
    if evidence.get("review_closure_status") != "blocked":
        failures.append("reject_lifecycle.review_closure_status")
    if evidence.get("next_action") != "collect_source_library_run":
        failures.append("reject_lifecycle.next_action")
    if evidence.get("next_action_enabled") is not False or evidence.get("next_action_blocked") is not True:
        failures.append("reject_lifecycle.next_action_blocked")
    if guard.get("status") != "blocked":
        failures.append("reject_lifecycle.single_source_guard.status")
    if guard.get("strict_source") is not True:
        failures.append("reject_lifecycle.single_source_guard.strict_source")
    if guard.get("guarantee") is not False:
        failures.append("reject_lifecycle.single_source_guard.guarantee")
    return {
        "review_closure_status": evidence.get("review_closure_status"),
        "next_action_blocked": evidence.get("next_action_blocked"),
        "guard_status": guard.get("status"),
        "guarantee": guard.get("guarantee"),
        "block_reason": evidence.get("block_reason"),
    }, failures


def check_run_evidence(step: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    if not step:
        return {}, ["source_library_run"]
    evidence = step.get("evidence") if isinstance(step.get("evidence"), dict) else {}
    task_id = evidence.get("task_id")
    terminal_status = evidence.get("terminal_status")
    trace_id = evidence.get("trace_id")
    failures: list[str] = []
    if step.get("status") != STATUS_PASSED:
        failures.append("source_library_run.status")
    if not (is_present(task_id) or is_present(terminal_status) or is_present(trace_id)):
        failures.append("source_library_run.task_or_terminal_or_trace")
    return {
        "task_id": task_id,
        "terminal_status": terminal_status,
        "trace_id": trace_id,
        "submission_id": evidence.get("submission_id"),
    }, failures


def inspect_artifact(path: Path, root: Path, observed_at: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "artifact_path": relative_artifact_path(path, root),
        "absolute_path": str(path.resolve()),
        "observed_at": observed_at,
    }
    if not path.exists():
        row.update({"status": STATUS_FAILED, "structural_failures": ["artifact_file"], "steps": []})
        return row

    payload, error = load_artifact(path)
    if error is not None:
        row.update(
            {
                "status": STATUS_FAILED,
                "reason": error,
                "structural_failures": ["valid_json"],
                "steps": [],
            }
        )
        return row
    if not isinstance(payload, dict):
        row.update({"status": STATUS_FAILED, "structural_failures": ["artifact_object"], "steps": []})
        return row

    artifact_status = normalize_status(payload.get("status"))
    steps = [step for step in payload.get("steps", []) if isinstance(step, dict)] if isinstance(payload.get("steps"), list) else []
    names = collect_step_names(steps)
    by_name = step_by_name(steps)
    missing_top_level_fields = [field for field in REQUIRED_TOP_LEVEL_FIELDS if field not in payload]
    missing_steps = [name for name in REQUIRED_STEPS if name not in by_name]
    duplicate_steps = sorted({name for name in names if names.count(name) > 1})
    failed_steps = [name for name, step in by_name.items() if step.get("status") == STATUS_FAILED]
    blocked_steps = [name for name, step in by_name.items() if step.get("status") == STATUS_BLOCKED]

    accepted_guard, accepted_failures = check_accepted_guard(by_name.get("accept_lifecycle"))
    blocked_review, blocked_failures = check_blocked_review(by_name.get("reject_lifecycle"))
    run_evidence, run_failures = check_run_evidence(by_name.get("source_library_run"))

    structural_failures: list[str] = []
    if payload.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        structural_failures.append("schema_version")
    if artifact_status not in {STATUS_PASSED, STATUS_FAILED, STATUS_BLOCKED}:
        structural_failures.append("artifact_status")
    if missing_top_level_fields:
        structural_failures.append("top_level_fields")
    if missing_steps and artifact_status != STATUS_BLOCKED:
        structural_failures.append("missing_steps")
    if duplicate_steps:
        structural_failures.append("duplicate_steps")

    semantic_failures: list[str] = []
    if artifact_status == STATUS_PASSED:
        if failed_steps or blocked_steps:
            semantic_failures.append("step_statuses")
        semantic_failures.extend(accepted_failures)
        semantic_failures.extend(blocked_failures)
        semantic_failures.extend(run_failures)
        if payload.get("failures"):
            semantic_failures.append("artifact_failures_empty")
    elif artifact_status == STATUS_BLOCKED:
        blocked_environment_evidence = any(
            step.get("status") == STATUS_BLOCKED
            and (step.get("http_status") is None or step.get("reason") == "backend_unreachable")
            for step in steps
        )
        if not blocked_steps:
            semantic_failures.append("blocked_without_blocked_step")
        if not blocked_environment_evidence:
            semantic_failures.append("blocked_without_environment_evidence")
        non_blocked_terminal_failures = [name for name in failed_steps if name not in blocked_steps]
        if non_blocked_terminal_failures:
            semantic_failures.append("blocked_artifact_has_failed_step")
    elif artifact_status == STATUS_FAILED:
        if not (payload.get("failures") or failed_steps or semantic_failures):
            semantic_failures.append("failed_artifact_without_failure_evidence")

    status = STATUS_FAILED if structural_failures or semantic_failures else artifact_status
    row.update(
        {
            "status": status,
            "artifact_status": artifact_status,
            "schema_version": payload.get("schema_version"),
            "expected_schema_version": ARTIFACT_SCHEMA_VERSION,
            "structural_failures": structural_failures,
            "semantic_failures": semantic_failures,
            "summary": {
                "required_steps": list(REQUIRED_STEPS),
                "observed_steps": names,
                "missing_steps": missing_steps,
                "duplicate_steps": duplicate_steps,
                "failed_steps": failed_steps,
                "blocked_steps": blocked_steps,
                "missing_top_level_fields": missing_top_level_fields,
                "artifact_failure_count": len(payload.get("failures") or []),
                "accepted_guard_status": accepted_guard.get("guard_status"),
                "blocked_review_status": blocked_review.get("review_closure_status"),
                "run_task_id": run_evidence.get("task_id"),
                "run_terminal_status": run_evidence.get("terminal_status"),
                "run_trace_id": run_evidence.get("trace_id"),
            },
            "accepted_guard": accepted_guard,
            "blocked_review": blocked_review,
            "run_evidence": run_evidence,
            "steps": steps,
            "artifact_failures": payload.get("failures") if isinstance(payload.get("failures"), list) else [],
        }
    )
    return row


def build_report(
    artifact_path: str | Path, root: Path | None = None
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=resource_source_lifecycle_artifact "
    "witness=test:test_w11_non_authoritative_metadata",
]:
    resolved_root = root.resolve() if root else repo_root()
    observed_at = utc_now()
    artifact = inspect_artifact(Path(artifact_path), resolved_root, observed_at)
    failures = list(artifact.get("structural_failures") or []) + list(artifact.get("semantic_failures") or [])
    return {
        "schema_version": CHECK_SCHEMA_VERSION,
        "status": artifact["status"],
        "observed_at": observed_at,
        "failures": failures,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact": artifact,
        "evidence": {
            "accepted_guard_status": (artifact.get("accepted_guard") or {}).get("guard_status"),
            "accepted_report_source_ref": (artifact.get("accepted_guard") or {}).get("report_source_ref"),
            "blocked_review_status": (artifact.get("blocked_review") or {}).get("review_closure_status"),
            "blocked_guard_status": (artifact.get("blocked_review") or {}).get("guard_status"),
            "task_id": (artifact.get("run_evidence") or {}).get("task_id"),
            "terminal_status": (artifact.get("run_evidence") or {}).get("terminal_status"),
            "trace_id": (artifact.get("run_evidence") or {}).get("trace_id"),
        },
        "recommended_command": (
            "python3 scripts/check_resource_source_lifecycle_artifact.py "
            "<artifact.json> [--allow-blocked] [--json]"
        ),
    }


def print_human(report: dict[str, Any]) -> None:
    if report["status"] == STATUS_PASSED:
        print("OK resource source lifecycle smoke artifact passed")
        return
    if report["status"] == STATUS_BLOCKED:
        print("BLOCKED resource source lifecycle smoke artifact is environment-blocked")
        return
    artifact = report["artifact"]
    print("FAILED resource source lifecycle smoke artifact")
    failures = report.get("failures") or ["unknown"]
    print(f"- {artifact['artifact_path']}: failures={', '.join(failures)}")
    summary = artifact.get("summary") or {}
    for key in ("missing_steps", "failed_steps", "blocked_steps", "missing_top_level_fields"):
        values = summary.get(key) or []
        if values:
            print(f"- {key}: {', '.join(values)}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args.artifact)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human(report)
    if report["status"] == STATUS_PASSED:
        return 0
    if args.allow_blocked and report["status"] == STATUS_BLOCKED:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
