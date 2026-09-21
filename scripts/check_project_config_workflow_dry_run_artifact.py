#!/usr/bin/env python3
"""Check project config workflow dry-run smoke JSON artifacts."""

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


ARTIFACT_SCHEMA_VERSION = "project_config_workflow_dry_run_smoke.v1"
CHECK_SCHEMA_VERSION = "project_config_workflow_dry_run_smoke_check.v1"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"

REQUIRED_STEPS = (
    "config_readback",
    "template_diff_preview",
    "stage_draft",
    "versions_after_draft",
    "promote_to_staging",
    "promote_to_active",
    "workflow_dry_run",
    "rollback_preview",
)
READBACK_STEP_ALIASES = ("config_readback", "project_readback")
REQUIRED_TOP_LEVEL_FIELDS = (
    "schema_version",
    "status",
    "generated_at",
    "api_base",
    "project_key",
    "workflow",
    "steps",
    "failures",
    "summary",
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", help="Project config workflow dry-run smoke JSON artifact path.")
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


def evidence(step: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(step, dict) and isinstance(step.get("evidence"), dict):
        return step["evidence"]
    return {}


def check_step_contracts(steps: Sequence[dict[str, Any]], *, artifact_status: str | None) -> list[str]:
    failures: list[str] = []
    for step in steps:
        name = str(step.get("name") or "").strip() or "<unknown>"
        if "http_status" not in step:
            failures.append(f"{name}.http_status")
        if artifact_status == STATUS_PASSED and not isinstance(step.get("evidence"), dict):
            failures.append(f"{name}.evidence")
    return failures


def expect_values(step_name: str, step: dict[str, Any] | None, checks: dict[str, Any]) -> list[str]:
    data = evidence(step)
    failures: list[str] = []
    if not step:
        return [step_name]
    if step.get("status") != STATUS_PASSED:
        failures.append(f"{step_name}.status")
    for field, expected in checks.items():
        if data.get(field) != expected:
            failures.append(f"{step_name}.{field}")
    return failures


def check_readback(step: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    data = evidence(step)
    failures: list[str] = []
    if not step:
        return {}, ["config_readback"]
    if step.get("status") != STATUS_PASSED:
        failures.append("config_readback.status")
    if step.get("name") == "project_readback":
        if data.get("project_present") is not True:
            failures.append("project_readback.project_present")
    elif data.get("workflow_present") is not True:
        failures.append("config_readback.workflow_present")
    if not is_present(data.get("project_key")):
        failures.append("config_readback.project_key")
    return data, failures


def check_versions(by_name: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    draft = evidence(by_name.get("stage_draft")).get("next_version")
    staging = evidence(by_name.get("promote_to_staging")).get("next_version")
    active = evidence(by_name.get("promote_to_active")).get("next_version")
    versions_after_draft = evidence(by_name.get("versions_after_draft"))
    failures: list[str] = []
    if not isinstance(draft, int):
        failures.append("stage_draft.next_version")
    if not isinstance(staging, int):
        failures.append("promote_to_staging.next_version")
    if not isinstance(active, int):
        failures.append("promote_to_active.next_version")
    if isinstance(draft, int) and isinstance(staging, int) and not draft < staging:
        failures.append("version_progression.draft_to_staging")
    if isinstance(staging, int) and isinstance(active, int) and not staging < active:
        failures.append("version_progression.staging_to_active")
    if versions_after_draft.get("has_draft") is not True:
        failures.append("versions_after_draft.has_draft")
    if isinstance(draft, int) and versions_after_draft.get("draft_version") != draft:
        failures.append("versions_after_draft.draft_version")
    return {"draft_version": draft, "staging_version": staging, "active_version": active}, failures


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
    has_readback = any(name in by_name for name in READBACK_STEP_ALIASES)
    missing_steps = [name for name in REQUIRED_STEPS if name not in by_name]
    if has_readback and "config_readback" in missing_steps:
        missing_steps.remove("config_readback")
    duplicate_steps = sorted({name for name in names if names.count(name) > 1})
    failed_steps = [name for name, step in by_name.items() if step.get("status") == STATUS_FAILED]
    blocked_steps = [name for name, step in by_name.items() if step.get("status") == STATUS_BLOCKED]

    readback_step = by_name.get("config_readback") or by_name.get("project_readback")
    readback, readback_failures = check_readback(readback_step)
    version_evidence, version_failures = check_versions(by_name)

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
    structural_failures.extend(check_step_contracts(steps, artifact_status=artifact_status))

    semantic_failures: list[str] = []
    if artifact_status == STATUS_PASSED:
        if failed_steps or blocked_steps:
            semantic_failures.append("step_statuses")
        semantic_failures.extend(readback_failures)
        semantic_failures.extend(
            expect_values(
                "template_diff_preview",
                by_name.get("template_diff_preview"),
                {
                    "governance_dry_run": True,
                    "governance_will_mutate": False,
                    "governance_requires_publish": True,
                    "version_summary_requires_publish": True,
                },
            )
        )
        semantic_failures.extend(
            expect_values(
                "stage_draft",
                by_name.get("stage_draft"),
                {
                    "stage": "draft",
                    "governance_will_mutate": True,
                    "governance_requires_publish": True,
                    "version_summary_requires_publish": True,
                },
            )
        )
        semantic_failures.extend(
            expect_values(
                "versions_after_draft",
                by_name.get("versions_after_draft"),
                {"governance_dry_run": True, "governance_will_mutate": False},
            )
        )
        semantic_failures.extend(
            expect_values(
                "promote_to_staging",
                by_name.get("promote_to_staging"),
                {
                    "from_stage": "draft",
                    "to_stage": "staging",
                    "governance_will_mutate": True,
                    "governance_requires_publish": True,
                    "version_summary_requires_publish": True,
                },
            )
        )
        semantic_failures.extend(
            expect_values(
                "promote_to_active",
                by_name.get("promote_to_active"),
                {
                    "from_stage": "staging",
                    "to_stage": "active",
                    "governance_will_mutate": True,
                    "governance_requires_publish": False,
                    "version_summary_requires_publish": False,
                },
            )
        )
        semantic_failures.extend(version_failures)
        semantic_failures.extend(
            expect_values(
                "workflow_dry_run",
                by_name.get("workflow_dry_run"),
                {
                    "dry_run": True,
                    "governance_dry_run": True,
                    "governance_will_mutate": False,
                    "governance_requires_publish": False,
                    "writes_blocked": True,
                    "runtime_tasks_blocked": True,
                    "policy_requires_publish": False,
                },
            )
        )
        semantic_failures.extend(
            expect_values(
                "rollback_preview",
                by_name.get("rollback_preview"),
                {
                    "rollback_preview": True,
                    "governance_dry_run": True,
                    "governance_will_mutate": False,
                    "rollback_plan_will_mutate": False,
                    "version_summary_will_mutate": False,
                },
            )
        )
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
                "draft_version": version_evidence.get("draft_version"),
                "staging_version": version_evidence.get("staging_version"),
                "active_version": version_evidence.get("active_version"),
                "workflow_dry_run_writes_blocked": evidence(by_name.get("workflow_dry_run")).get("writes_blocked"),
                "workflow_dry_run_runtime_tasks_blocked": evidence(by_name.get("workflow_dry_run")).get(
                    "runtime_tasks_blocked"
                ),
                "rollback_preview_will_mutate": evidence(by_name.get("rollback_preview")).get(
                    "rollback_plan_will_mutate"
                ),
            },
            "readback": readback,
            "version_evidence": version_evidence,
            "workflow_dry_run": evidence(by_name.get("workflow_dry_run")),
            "rollback_preview": evidence(by_name.get("rollback_preview")),
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
    "fact_source=project_config_workflow_dry_run_artifact "
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
            "draft_version": (artifact.get("version_evidence") or {}).get("draft_version"),
            "staging_version": (artifact.get("version_evidence") or {}).get("staging_version"),
            "active_version": (artifact.get("version_evidence") or {}).get("active_version"),
            "workflow_dry_run_writes_blocked": (artifact.get("workflow_dry_run") or {}).get("writes_blocked"),
            "workflow_dry_run_runtime_tasks_blocked": (artifact.get("workflow_dry_run") or {}).get(
                "runtime_tasks_blocked"
            ),
            "rollback_preview_will_mutate": (artifact.get("rollback_preview") or {}).get("rollback_plan_will_mutate"),
        },
        "recommended_command": (
            "python3 scripts/check_project_config_workflow_dry_run_artifact.py "
            "<artifact.json> [--allow-blocked] [--json]"
        ),
    }


def print_human(report: dict[str, Any]) -> None:
    if report["status"] == STATUS_PASSED:
        print("OK project config workflow dry-run smoke artifact passed")
        return
    if report["status"] == STATUS_BLOCKED:
        print("BLOCKED project config workflow dry-run smoke artifact is environment-blocked")
        return
    artifact = report["artifact"]
    print("FAILED project config workflow dry-run smoke artifact")
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
