#!/usr/bin/env python3
"""Aggregate runtime smoke evidence for the business-line user-flow audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Annotated, Any, Sequence

try:
    from scripts._automation_runtime import utc_now, write_json
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import utc_now, write_json


SCHEMA_VERSION = "mrw.runtime_smoke_evidence_package.v1"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"
STATUS_MISSING = "missing_evidence"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker-preflight", type=Path, help="docker-deploy preflight manifest JSON.")
    parser.add_argument("--local-preflight", type=Path, help="local-deploy preflight manifest JSON.")
    parser.add_argument("--backend-smoke", type=Path, help="business-line user-flow smoke artifact JSON.")
    parser.add_argument("--frontend-browser", type=Path, help="real-backend browser smoke artifact JSON.")
    parser.add_argument("--runtime-health", type=Path, help="passive runtime health matrix JSON.")
    parser.add_argument("--output", type=Path, help="Path to write the aggregate JSON package.")
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Exit 0 when provided evidence is environment-blocked but not failed.",
    )
    parser.add_argument("--json", action="store_true", help="Print the aggregate JSON package.")
    return parser.parse_args(argv)


def load_json(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, "not_provided"
    if not path.exists():
        return None, "file_not_found"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, f"read_error:{exc}"
    except json.JSONDecodeError as exc:
        return None, f"invalid_json:{exc}"
    if not isinstance(payload, dict):
        return None, "json_root_not_object"
    return payload, None


def status_from_payload(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    status = payload.get("status")
    return str(status).strip() if status is not None else None


def normalize_component_status(raw_status: str | None, *, missing_reason: str | None) -> str:
    if missing_reason:
        if missing_reason == "not_provided":
            return STATUS_MISSING
        return STATUS_FAILED
    if raw_status == STATUS_PASSED:
        return STATUS_PASSED
    if raw_status in {STATUS_BLOCKED, "worker_blocked", "passed_with_blocked_modes"}:
        return STATUS_BLOCKED
    return STATUS_FAILED


def preflight_blocker(payload: dict[str, Any] | None) -> Annotated[
    tuple[str | None, str | None],
    "kit:non-authoritative derived_as=preflight "
    "fact_source=runtime_smoke_evidence_payload "
    "witness=test:test_w11_non_authoritative_metadata",
]:
    if not payload:
        return None, None
    if status_from_payload(payload) == STATUS_PASSED:
        return None, None
    fail_fast = payload.get("fail_fast_decision")
    if isinstance(fail_fast, dict):
        reasons = fail_fast.get("reasons")
        if isinstance(reasons, list) and reasons:
            return str(reasons[0]), str(fail_fast.get("recommended_command") or payload.get("recommended_command") or "")
    for check in payload.get("checks") or []:
        if isinstance(check, dict) and check.get("status") == "failed" and check.get("required") is True:
            return str(check.get("name") or "required_check_failed"), str(check.get("recommended_command") or "")
    return None, None


def smoke_blocker(payload: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if not payload:
        return None, None
    if status_from_payload(payload) == STATUS_PASSED:
        return None, None
    summary = payload.get("summary")
    if isinstance(summary, dict):
        reason = summary.get("first_blocker_reason") or summary.get("blocker_classification")
        if reason:
            return str(reason), str(payload.get("recommended_command") or "")
    matrix = payload.get("matrix")
    if isinstance(matrix, dict):
        return str(matrix.get("reason") or ""), str(payload.get("recommended_command") or "")
    return None, str(payload.get("recommended_command") or "")


def browser_blocker(payload: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if not payload:
        return None, None
    if status_from_payload(payload) == STATUS_PASSED:
        return None, None
    summary = payload.get("summary")
    if isinstance(summary, dict):
        for key in ("failed_line_keys", "blocked_line_keys", "missing_line_keys"):
            values = summary.get(key)
            if isinstance(values, list) and values:
                return f"{key}:{values[0]}", ""
    return status_from_payload(payload), ""


def runtime_health_blocker(payload: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if not payload:
        return None, None
    modes = payload.get("runtime_modes")
    if isinstance(modes, list):
        for mode in modes:
            if not isinstance(mode, dict):
                continue
            blocked = mode.get("blocked_by_environment")
            if isinstance(blocked, list) and blocked:
                first = blocked[0]
                if isinstance(first, dict):
                    return str(first.get("reason") or mode.get("mode") or "runtime_blocked"), str(
                        first.get("recommended_command") or ""
                    )
    return status_from_payload(payload), ""


def build_component(
    *,
    name: str,
    path: Path | None,
    blocker_extractor,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view "
    "fact_source=runtime_smoke_component_payload "
    "witness=test:test_w11_non_authoritative_metadata",
]:
    payload, load_error = load_json(path)
    raw_status = status_from_payload(payload)
    status = normalize_component_status(raw_status, missing_reason=load_error)
    first_blocker_reason, recommended_command = blocker_extractor(payload)
    if name == "docker_preflight" and status == STATUS_FAILED and first_blocker_reason:
        if first_blocker_reason.startswith(("service:", "port:")):
            status = STATUS_BLOCKED
    component = {
        "name": name,
        "path": str(path) if path is not None else None,
        "status": status,
        "raw_status": raw_status,
        "load_error": load_error,
        "first_blocker_reason": first_blocker_reason,
        "recommended_command": recommended_command or None,
    }
    if payload and isinstance(payload.get("schema_version"), str):
        component["schema_version"] = payload["schema_version"]
    return component


def summarize_status(components: list[dict[str, Any]]) -> str:
    provided = [component for component in components if component["status"] != STATUS_MISSING]
    if not provided:
        return STATUS_MISSING
    if any(component["status"] == STATUS_FAILED for component in provided):
        return STATUS_FAILED
    if any(component["status"] == STATUS_BLOCKED for component in provided):
        return STATUS_BLOCKED
    if all(component["status"] == STATUS_PASSED for component in provided):
        return STATUS_PASSED
    return STATUS_FAILED


def build_package(args: argparse.Namespace) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=runtime_smoke_component_artifacts "
    "witness=test:test_w11_non_authoritative_metadata",
]:
    components = [
        build_component(
            name="docker_preflight",
            path=args.docker_preflight,
            blocker_extractor=preflight_blocker,
        ),
        build_component(
            name="local_preflight",
            path=args.local_preflight,
            blocker_extractor=preflight_blocker,
        ),
        build_component(
            name="backend_live_smoke",
            path=args.backend_smoke,
            blocker_extractor=smoke_blocker,
        ),
        build_component(
            name="frontend_real_backend_browser",
            path=args.frontend_browser,
            blocker_extractor=browser_blocker,
        ),
        build_component(
            name="runtime_health_matrix",
            path=args.runtime_health,
            blocker_extractor=runtime_health_blocker,
        ),
    ]
    status = summarize_status(components)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "observed_at": utc_now(),
        "summary": {
            "provided_components": [
                component["name"] for component in components if component["status"] != STATUS_MISSING
            ],
            "missing_components": [
                component["name"] for component in components if component["status"] == STATUS_MISSING
            ],
            "blocked_components": [
                component["name"] for component in components if component["status"] == STATUS_BLOCKED
            ],
            "failed_components": [
                component["name"] for component in components if component["status"] == STATUS_FAILED
            ],
            "passed_components": [
                component["name"] for component in components if component["status"] == STATUS_PASSED
            ],
            "first_blocker": next(
                (
                    {
                        "component": component["name"],
                        "reason": component.get("first_blocker_reason"),
                        "recommended_command": component.get("recommended_command"),
                    }
                    for component in components
                    if component["status"] in {STATUS_BLOCKED, STATUS_FAILED}
                ),
                None,
            ),
        },
        "components": components,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    package = build_package(args)
    if args.output:
        write_json(args.output, package)
    if args.json:
        print(json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True))
    elif args.output:
        print(f"runtime_smoke_evidence_package={package['status']} output={args.output}")
    else:
        print(f"runtime_smoke_evidence_package={package['status']}")

    if package["status"] == STATUS_PASSED:
        return 0
    if args.allow_blocked and package["status"] == STATUS_BLOCKED:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
