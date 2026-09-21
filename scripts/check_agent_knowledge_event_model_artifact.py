#!/usr/bin/env python3
"""Check Agent/knowledge event-model smoke JSON artifacts."""

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


ARTIFACT_SCHEMA_VERSION = "agent_knowledge_event_model_smoke.v1"
CHECK_SCHEMA_VERSION = "agent_knowledge_event_model_smoke_check.v1"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"

REQUIRED_STEP_NAMES = (
    "typed_knowledge_live_sample",
    "governance_review_mutation",
    "writing_context",
    "writing_keyword_cards",
    "workflow_graph_draft",
    "workflow_graph_submit",
    "workflow_graph_audit",
    "workflow_graph_evidence_pack",
    "graph_writing_handoff_persist",
    "handoff_replay",
    "agent_session_create",
    "agent_session_message",
    "agent_session_events_readback",
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", help="Agent/knowledge event-model smoke JSON artifact path.")
    parser.add_argument("--output", type=Path, help="Path to write the checker JSON artifact.")
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Exit 0 when the smoke artifact is blocked by environment.",
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
    if isinstance(value, bool):
        return value
    return True


def as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for key in ("count", "total", "event_count", "handoff_count", "selected_node_count"):
            if isinstance(value.get(key), int):
                return int(value[key])
    return 0


def load_artifact(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, f"artifact could not be read: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"artifact is not valid JSON: {exc}"


def step_by_name(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    return {
        str(step.get("name")): step
        for step in steps
        if isinstance(step, dict) and is_present(step.get("name"))
    }


def step_evidence(steps: dict[str, dict[str, Any]], name: str) -> dict[str, Any]:
    evidence = steps.get(name, {}).get("evidence")
    return evidence if isinstance(evidence, dict) else {}


def event_types_from(value: Any) -> list[str]:
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, dict):
                event_type = item.get("type") or item.get("event_type")
            else:
                event_type = item
            if is_present(event_type):
                out.append(str(event_type))
        return out
    return []


def check_condition(name: str, passed: bool, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": STATUS_PASSED if passed else STATUS_FAILED,
        "details": details or {},
    }


def validate_required_step_shape(steps: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for name in REQUIRED_STEP_NAMES:
        step = steps.get(name)
        missing_fields: list[str] = []
        if not isinstance(step, dict):
            checks.append(check_condition(f"step.{name}", False, {"missing_fields": ["step"]}))
            continue
        for field in ("name", "path", "http_status", "status", "evidence"):
            if field not in step:
                missing_fields.append(field)
        if step.get("status") != STATUS_PASSED:
            missing_fields.append("status:passed")
        checks.append(check_condition(f"step.{name}", not missing_fields, {"missing_fields": missing_fields}))
    return checks


def build_check(path: Path, *, allow_blocked: bool = False) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=agent_knowledge_event_model_smoke_artifact "
    "witness=test:test_w11_non_authoritative_metadata",
]:
    payload, load_error = load_artifact(path)
    if load_error or not isinstance(payload, dict):
        return {
            "schema_version": CHECK_SCHEMA_VERSION,
            "status": STATUS_FAILED,
            "checked_at": utc_now(),
            "artifact_path": str(path),
            "artifact_status": None,
            "checks": [],
            "failures": [load_error or "artifact root is not an object"],
        }

    artifact_status = str(payload.get("status") or "")
    if artifact_status == STATUS_BLOCKED:
        status = STATUS_BLOCKED if allow_blocked else STATUS_FAILED
        return {
            "schema_version": CHECK_SCHEMA_VERSION,
            "status": status,
            "checked_at": utc_now(),
            "artifact_path": str(path),
            "artifact_schema_version": payload.get("schema_version"),
            "artifact_status": artifact_status,
            "checks": [
                check_condition(
                    "artifact.blocked_by_environment",
                    allow_blocked,
                    {"allow_blocked": allow_blocked, "failures": payload.get("failures") or []},
                )
            ],
            "failures": [] if allow_blocked else ["artifact_status_blocked_by_environment"],
        }

    steps = step_by_name(payload)
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    checks: list[dict[str, Any]] = [
        check_condition(
            "artifact.schema_version",
            payload.get("schema_version") == ARTIFACT_SCHEMA_VERSION,
            {"expected": ARTIFACT_SCHEMA_VERSION, "actual": payload.get("schema_version")},
        ),
        check_condition(
            "artifact.status",
            artifact_status == STATUS_PASSED,
            {"expected": STATUS_PASSED, "actual": artifact_status},
        ),
    ]
    checks.extend(validate_required_step_shape(steps))

    typed_live = step_evidence(steps, "typed_knowledge_live_sample")
    checks.append(
        check_condition(
            "typed_knowledge.live_db_write",
            typed_live.get("live_db_write") is True or evidence.get("typed_knowledge_live_db_write") is True,
            {"step_value": typed_live.get("live_db_write"), "artifact_value": evidence.get("typed_knowledge_live_db_write")},
        )
    )

    writing_context = step_evidence(steps, "writing_context")
    handoff_count = as_int(writing_context.get("handoff_count") or evidence.get("writing_context_handoff_count"))
    checks.append(
        check_condition(
            "writing_context.handoff_count",
            handoff_count > 0,
            {"handoff_count": handoff_count},
        )
    )

    cards = step_evidence(steps, "writing_keyword_cards")
    publishers = cards.get("publishers") if isinstance(cards.get("publishers"), list) else []
    publisher = cards.get("publisher") or evidence.get("keyword_card_publisher")
    typed_card_count = as_int(cards.get("typed_knowledge_card_count") or evidence.get("keyword_card_typed_knowledge_count"))
    checks.append(
        check_condition(
            "keyword_card.publisher",
            publisher == "typed_knowledge" or "typed_knowledge" in publishers or typed_card_count > 0,
            {"publisher": publisher, "publishers": publishers, "typed_knowledge_card_count": typed_card_count},
        )
    )

    audit = step_evidence(steps, "workflow_graph_audit")
    audit_count = as_int(audit.get("audit_count") or evidence.get("graph_audit_count"))
    checks.append(check_condition("workflow_graph.audit_count", audit_count > 0, {"audit_count": audit_count}))

    pack = step_evidence(steps, "workflow_graph_evidence_pack")
    selected_node_count = as_int(pack.get("selected_node_count") or evidence.get("evidence_pack_selected_node_count"))
    checks.append(
        check_condition(
            "workflow_graph.evidence_pack_selected_nodes",
            selected_node_count > 0,
            {"selected_node_count": selected_node_count},
        )
    )

    handoff = step_evidence(steps, "graph_writing_handoff_persist")
    backend_marker = handoff.get("backend_marker") or evidence.get("handoff_backend_marker")
    checks.append(
        check_condition(
            "handoff.persistence_backend_marker",
            backend_marker == "workflow_graph.run_store",
            {"backend_marker": backend_marker},
        )
    )

    replay = step_evidence(steps, "handoff_replay")
    replay_event_types = event_types_from(replay.get("events")) or [
        str(item)
        for item in (replay.get("event_types") if isinstance(replay.get("event_types"), list) else [])
        if is_present(item)
    ]
    if not replay_event_types and isinstance(evidence.get("handoff_replay_event_types"), list):
        replay_event_types = [str(item) for item in evidence["handoff_replay_event_types"] if is_present(item)]
    replay_event_count = as_int(replay.get("event_count") or evidence.get("handoff_replay_event_count"))
    checks.append(
        check_condition(
            "handoff.replay_persisted_and_replayed",
            "handoff.persisted" in replay_event_types and "handoff.replayed" in replay_event_types,
            {"event_count": replay_event_count, "event_types": replay_event_types},
        )
    )

    session_create = step_evidence(steps, "agent_session_create")
    session_id = session_create.get("session_id") or evidence.get("agent_session_id")
    checks.append(check_condition("agent_session.session_id", is_present(session_id), {"session_id": session_id}))

    agent_events = step_evidence(steps, "agent_session_events_readback")
    agent_event_types = [
        str(item)
        for item in (agent_events.get("event_types") if isinstance(agent_events.get("event_types"), list) else [])
        if is_present(item)
    ]
    agent_event_count = as_int(agent_events.get("event_count") or evidence.get("agent_event_count"))
    checks.append(
        check_condition(
            "agent_session.events_readback",
            any(event_type.startswith(("session.", "message.")) for event_type in agent_event_types)
            or agent_event_count > 0,
            {"event_count": agent_event_count, "event_types": agent_event_types},
        )
    )

    failures = [check["name"] for check in checks if check["status"] != STATUS_PASSED]
    return {
        "schema_version": CHECK_SCHEMA_VERSION,
        "status": STATUS_PASSED if not failures else STATUS_FAILED,
        "checked_at": utc_now(),
        "artifact_path": str(path),
        "artifact_schema_version": payload.get("schema_version"),
        "artifact_status": artifact_status,
        "checks": checks,
        "failures": failures,
        "summary": {
            "check_count": len(checks),
            "passed_check_count": sum(1 for check in checks if check["status"] == STATUS_PASSED),
            "failed_check_count": len(failures),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_check(Path(args.artifact), allow_blocked=args.allow_blocked)
    if args.output:
        write_json(args.output, result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"agent_knowledge_event_model_smoke_check={result['status']} artifact={args.artifact}")
    if result["status"] == STATUS_PASSED:
        return 0
    if args.allow_blocked and result["status"] == STATUS_BLOCKED:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
