#!/usr/bin/env python3
"""Run the live Agent/knowledge event-model user-flow smoke."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Sequence
from urllib import error, parse, request

try:
    from scripts._automation_runtime import utc_now
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import utc_now


SCHEMA_VERSION = "agent_knowledge_event_model_smoke.v1"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"

TYPED_KNOWLEDGE_LIVE_SAMPLE_PATH = "/api/v1/typed-knowledge/live-sample"
TYPED_KNOWLEDGE_GOVERNANCE_PATH = "/api/v1/typed-knowledge/governance/review-state"
TYPED_KNOWLEDGE_WRITING_CONTEXT_PATH = "/api/v1/typed-knowledge/writing-context"
WRITING_KEYWORD_CARDS_PATH = "/api/v1/writing/keyword-cards"
WORKFLOW_GRAPH_DRAFT_PATH_TEMPLATE = "/api/v1/workflow-graph/curated/{graph_id}/draft"
WORKFLOW_GRAPH_SUBMIT_PATH_TEMPLATE = "/api/v1/workflow-graph/curated/{graph_id}/submit"
WORKFLOW_GRAPH_AUDIT_PATH_TEMPLATE = "/api/v1/workflow-graph/curated/{graph_id}/audit"
WORKFLOW_GRAPH_EVIDENCE_PACK_PATH_TEMPLATE = "/api/v1/workflow-graph/curated/{graph_id}/evidence-pack"
WORKFLOW_GRAPH_WRITING_HANDOFF_PATH_TEMPLATE = "/api/v1/workflow-graph/curated/{graph_id}/handoff/writing"
WORKFLOW_GRAPH_HANDOFF_REPLAY_PATH_TEMPLATE = "/api/v1/workflow-graph/runs/{run_id}/handoff/{handoff_id}/replay"
AGENT_SESSIONS_PATH = "/api/v1/agent-sessions"
AGENT_SESSION_MESSAGES_PATH_TEMPLATE = "/api/v1/agent-sessions/{session_id}/messages"
AGENT_SESSION_EVENTS_PATH_TEMPLATE = "/api/v1/agent-sessions/{session_id}/events"


@dataclass(frozen=True)
class HttpResult:
    status_code: int | None
    body: str
    error: str | None = None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", dest="base_url", help="Backend API base URL.")
    parser.add_argument("--api-base", dest="api_base", help="Backend API base URL alias.")
    parser.add_argument("--project-key", default="demo_proj", help="Project key for live smoke writes.")
    parser.add_argument("--output", required=True, help="Path to write the smoke JSON artifact.")
    parser.add_argument("--json", action="store_true", help="Print the artifact JSON.")
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Exit 0 when the artifact is blocked by environment.",
    )
    parser.add_argument("--timeout", type=float, default=8.0, help="HTTP timeout in seconds.")
    return parser.parse_args(argv)


def normalize_api_base(value: str) -> str:
    return value.rstrip("/")


def build_url(
    api_base: str,
    path: str,
    query: dict[str, Any] | None = None,
) -> Annotated[
    str,
    "kit:prepared-command "
    "effect_boundary=agent_knowledge_event_model_http_request "
    "witness=test:test_w12_runtime_misc_laws",
]:
    normalized_path = path if path.startswith("/") else f"/{path}"
    url = f"{normalize_api_base(api_base)}{normalized_path}"
    if query:
        clean_query = {key: value for key, value in query.items() if value is not None}
        if clean_query:
            url = f"{url}?{parse.urlencode(clean_query, doseq=True)}"
    return url


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None, *, timeout: float) -> HttpResult:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - explicit smoke URL input
            body = response.read().decode("utf-8", errors="replace")
            return HttpResult(status_code=int(response.status), body=body)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return HttpResult(status_code=int(exc.code), body=body, error=str(exc))
    except (error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        return HttpResult(status_code=None, body="", error=str(exc))


def _http_get(url: str, *, timeout: float) -> HttpResult:
    return _http_json("GET", url, timeout=timeout)


def _http_post_json(url: str, payload: dict[str, Any] | None = None, *, timeout: float) -> HttpResult:
    return _http_json("POST", url, payload or {}, timeout=timeout)


def load_json_payload(result: HttpResult) -> tuple[Any | None, str | None]:
    try:
        return json.loads(result.body), None
    except json.JSONDecodeError as exc:
        return None, f"response is not valid JSON: {exc}"


def unwrap_envelope(payload: Any) -> Any:
    if isinstance(payload, dict) and isinstance(payload.get("data"), (dict, list)):
        return payload["data"]
    return payload


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def int_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for key in ("total", "count"):
            if isinstance(value.get(key), int):
                return int(value[key])
        for key in ("items", "events", "cards", "selected_nodes", "handoffs"):
            if isinstance(value.get(key), list):
                return len(value[key])
    if isinstance(value, int):
        return value
    return 0


def get_path(payload: Any, dotted_path: str) -> Any:
    current = payload
    for part in [part for part in dotted_path.replace("/", ".").split(".") if part]:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def list_from_keys(payload: dict[str, Any], keys: Sequence[str]) -> list[Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = list_from_keys(value, keys)
            if nested:
                return nested
    return []


def step_data_or_failure(*, step: dict[str, Any], result: HttpResult, failures: list[str]) -> dict[str, Any] | None:
    step["http_status"] = result.status_code
    step["error"] = result.error
    step.setdefault("evidence", {})
    if result.status_code is None:
        step["status"] = STATUS_BLOCKED
        step["reason"] = "backend_unreachable"
        failures.append(f"{step['name']}:backend_unreachable")
        return None
    if not (200 <= result.status_code < 300):
        step["status"] = STATUS_FAILED
        step["reason"] = "http_error"
        step["response_body_preview"] = result.body[:500]
        failures.append(f"{step['name']}:http_{result.status_code}")
        return None
    payload, json_error = load_json_payload(result)
    if json_error:
        step["status"] = STATUS_FAILED
        step["reason"] = "invalid_json"
        step["response_body_preview"] = result.body[:500]
        failures.append(f"{step['name']}:invalid_json")
        return None
    step["response"] = payload
    data = unwrap_envelope(payload)
    if not isinstance(data, dict):
        step["status"] = STATUS_FAILED
        step["reason"] = "missing_data_object"
        failures.append(f"{step['name']}:missing_data_object")
        return None
    return data


def fail_step(
    *,
    artifact: dict[str, Any],
    step: dict[str, Any],
    failures: list[str],
    reason: str,
    missing: Sequence[str],
) -> dict[str, Any]:
    step["status"] = STATUS_FAILED
    step["reason"] = reason
    failures.extend(f"{step['name']}:{field}" for field in missing)
    artifact["status"] = STATUS_FAILED
    artifact["summary"] = build_summary(artifact)
    return artifact


def blocked_or_failed_return(artifact: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    artifact["status"] = STATUS_BLOCKED if step.get("status") == STATUS_BLOCKED else STATUS_FAILED
    artifact["summary"] = build_summary(artifact)
    return artifact


def build_workflow_graph_dsl(
    smoke_id: str,
) -> Annotated[
    dict[str, Any],
    "kit:prepared-command "
    "effect_boundary=agent_knowledge_event_model_graph_submission "
    "witness=test:test_w12_runtime_misc_laws",
]:
    return {
        "nodes": [
            {
                "node_id": "company-acme",
                "node_type": "Company",
                "title": f"Acme Robotics {smoke_id}",
                "summary": "Acme is expanding robotics supply contracts.",
                "source_uri": "https://example.com/acme-robotics",
                "provenance": {"document_id": "doc-acme"},
            },
            {
                "node_id": "market-robotics",
                "node_type": "Market",
                "title": "Robotics Market",
                "summary": "Robotics demand remains a tracked market signal.",
            },
        ],
        "edges": [
            {
                "from_node_id": "company-acme",
                "to_node_id": "market-robotics",
                "edge_type": "in_market",
                "evidence": "Acme contract backlog maps to robotics demand.",
                "confidence": 0.91,
            }
        ],
    }


def extract_live_sample_evidence(data: dict[str, Any]) -> dict[str, Any]:
    repository = data.get("repository") if isinstance(data.get("repository"), dict) else {}
    writes = data.get("writes") if isinstance(data.get("writes"), list) else []
    records = data.get("records") if isinstance(data.get("records"), list) else []
    return {
        "contract_version": data.get("contract_version"),
        "live_db_write": repository.get("live_db_write") is True or any(
            isinstance(write, dict) and write.get("live_db_write") is True for write in writes
        ),
        "repository_ref": repository.get("repository_ref"),
        "record_count": len(records),
        "write_count": len(writes),
        "knowledge_item_keys": [
            record.get("object_key")
            for record in records
            if isinstance(record, dict) and record.get("object_type") == "knowledge_item"
        ],
    }


def extract_writing_context_evidence(data: dict[str, Any]) -> dict[str, Any]:
    context = data.get("typed_knowledge_context") if isinstance(data.get("typed_knowledge_context"), dict) else {}
    handoffs = context.get("handoffs") if isinstance(context.get("handoffs"), list) else []
    return {
        "live_db_backed": data.get("live_db_backed") is True,
        "context_contract_version": context.get("contract_version"),
        "source": context.get("source"),
        "consumer": context.get("consumer"),
        "handoff_count": len(handoffs),
        "typed_knowledge_context": context,
    }


def extract_keyword_card_evidence(data: dict[str, Any]) -> dict[str, Any]:
    cards = data.get("cards") if isinstance(data.get("cards"), list) else []
    publishers = [
        str(card.get("publisher") or "")
        for card in cards
        if isinstance(card, dict) and str(card.get("publisher") or "").strip()
    ]
    typed_cards = [
        card for card in cards if isinstance(card, dict) and card.get("publisher") == "typed_knowledge"
    ]
    return {
        "card_count": len(cards),
        "typed_knowledge_card_count": len(typed_cards),
        "publishers": publishers,
        "publisher": "typed_knowledge" if "typed_knowledge" in publishers else (publishers[0] if publishers else None),
        "card_ids": [card.get("card_id") for card in typed_cards if isinstance(card, dict)],
        "source_count": data.get("source_count") if isinstance(data.get("source_count"), dict) else {},
    }


def extract_graph_audit_evidence(data: dict[str, Any]) -> dict[str, Any]:
    items = list_from_keys(data, ("items", "audits", "events"))
    return {
        "audit_count": int_count(data) or len(items),
        "event_types": [
            str(item.get("action") or item.get("event_type") or item.get("type") or "")
            for item in items
            if isinstance(item, dict)
        ],
    }


def extract_evidence_pack_evidence(data: dict[str, Any]) -> dict[str, Any]:
    selected_nodes = data.get("selected_nodes") if isinstance(data.get("selected_nodes"), list) else []
    relations = data.get("relations") if isinstance(data.get("relations"), list) else []
    return {
        "contract_version": data.get("contract_version"),
        "selected_node_count": len(selected_nodes),
        "selected_node_ids": [
            node.get("node_id") for node in selected_nodes if isinstance(node, dict) and node.get("node_id")
        ],
        "relation_count": len(relations),
    }


def extract_handoff_evidence(data: dict[str, Any]) -> dict[str, Any]:
    persistence = data.get("persistence") if isinstance(data.get("persistence"), dict) else {}
    return {
        "contract_version": data.get("contract_version"),
        "handoff_id": data.get("handoff_id") or persistence.get("handoff_id"),
        "run_id": data.get("run_id") or persistence.get("run_id"),
        "consumer": data.get("consumer"),
        "producer": data.get("producer") or data.get("owner"),
        "backend_marker": persistence.get("backend_marker"),
        "persistence": persistence,
    }


def extract_replay_evidence(data: dict[str, Any]) -> dict[str, Any]:
    events = data.get("events") if isinstance(data.get("events"), list) else []
    event_types = [
        str(event.get("type") or event.get("event_type") or "")
        for event in events
        if isinstance(event, dict)
    ]
    return {
        "run_id": data.get("run_id"),
        "handoff_id": data.get("handoff_id"),
        "backend_marker": data.get("backend_marker"),
        "event_count": len(events),
        "event_types": event_types,
        "has_persisted_event": "handoff.persisted" in event_types,
        "has_replayed_event": "handoff.replayed" in event_types,
    }


def extract_session_id(data: dict[str, Any]) -> str | None:
    candidates = [
        data.get("session_id"),
        get_path(data, "session.session_id"),
        get_path(data, "session.id"),
    ]
    for candidate in candidates:
        if is_present(candidate):
            return str(candidate)
    return None


def extract_agent_events_evidence(data: dict[str, Any]) -> dict[str, Any]:
    events = data.get("items") if isinstance(data.get("items"), list) else []
    event_types = [
        str(event.get("event_type") or event.get("type") or "")
        for event in events
        if isinstance(event, dict)
    ]
    return {
        "event_count": len(events),
        "event_types": event_types,
        "has_session_or_message_event": any(
            event_type.startswith(("session.", "message.")) for event_type in event_types
        ),
    }


def build_summary(
    artifact: dict[str, Any],
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative "
    "derived_as=view "
    "fact_source=completed_agent_knowledge_event_model_artifact "
    "witness=test:test_w12_runtime_misc_laws",
]:
    steps = artifact.get("steps") if isinstance(artifact.get("steps"), list) else []
    return {
        "step_count": len(steps),
        "passed_step_count": sum(1 for step in steps if isinstance(step, dict) and step.get("status") == STATUS_PASSED),
        "failed_step_count": sum(1 for step in steps if isinstance(step, dict) and step.get("status") == STATUS_FAILED),
        "blocked_step_count": sum(1 for step in steps if isinstance(step, dict) and step.get("status") == STATUS_BLOCKED),
        "failure_count": len(artifact.get("failures") or []),
        "typed_knowledge_live_db_write": artifact.get("evidence", {}).get("typed_knowledge_live_db_write"),
        "writing_context_handoff_count": artifact.get("evidence", {}).get("writing_context_handoff_count"),
        "keyword_card_publisher": artifact.get("evidence", {}).get("keyword_card_publisher"),
        "graph_audit_count": artifact.get("evidence", {}).get("graph_audit_count"),
        "evidence_pack_selected_node_count": artifact.get("evidence", {}).get("evidence_pack_selected_node_count"),
        "handoff_backend_marker": artifact.get("evidence", {}).get("handoff_backend_marker"),
        "handoff_replay_event_count": artifact.get("evidence", {}).get("handoff_replay_event_count"),
        "agent_session_id": artifact.get("evidence", {}).get("agent_session_id"),
        "agent_event_count": artifact.get("evidence", {}).get("agent_event_count"),
    }


def recommended_command(api_base: str, output: Path, project_key: str) -> str:
    return (
        "python3 scripts/run_agent_knowledge_event_model_smoke.py "
        f"--api-base {api_base} --project-key {project_key} --output {output} --allow-blocked --json"
    )


def append_step(artifact: dict[str, Any], *, name: str, path: str, **extra: Any) -> dict[str, Any]:
    step = {
        "name": name,
        "path": path,
        "http_status": None,
        "status": "not_run",
        "evidence": {},
    }
    step.update(extra)
    artifact["steps"].append(step)
    return step


def build_artifact(
    *, api_base: str, project_key: str, output: Path, timeout: float
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative "
    "derived_as=generated_evidence "
    "fact_source=owned_agent_knowledge_event_model_http_step_results "
    "witness=test:test_w12_runtime_misc_laws",
]:
    smoke_id = f"agent-knowledge-event-{uuid.uuid4().hex[:12]}"
    graph_id = f"akem-{uuid.uuid4().hex[:10]}"
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_FAILED,
        "generated_at": utc_now(),
        "api_base": normalize_api_base(api_base),
        "project_key": project_key,
        "smoke_id": smoke_id,
        "graph_id": graph_id,
        "steps": [],
        "failures": [],
        "summary": {},
        "evidence": {},
        "recommended_command": recommended_command(api_base, output, project_key),
    }
    failures: list[str] = artifact["failures"]

    live_step = append_step(
        artifact,
        name="typed_knowledge_live_sample",
        path=TYPED_KNOWLEDGE_LIVE_SAMPLE_PATH,
        query={"project_key": project_key},
    )
    live_result = _http_post_json(
        build_url(api_base, TYPED_KNOWLEDGE_LIVE_SAMPLE_PATH, {"project_key": project_key}),
        {},
        timeout=timeout,
    )
    live_data = step_data_or_failure(step=live_step, result=live_result, failures=failures)
    if live_data is None:
        return blocked_or_failed_return(artifact, live_step)
    live_evidence = extract_live_sample_evidence(live_data)
    live_step["evidence"] = live_evidence
    artifact["evidence"]["typed_knowledge_live_db_write"] = live_evidence["live_db_write"]
    if live_evidence["live_db_write"] is not True:
        return fail_step(
            artifact=artifact,
            step=live_step,
            failures=failures,
            reason="typed_knowledge_live_db_write_missing",
            missing=["live_db_write"],
        )
    live_step["status"] = STATUS_PASSED

    governance_payload = {
        "project_key": project_key,
        "object_type": "knowledge_item",
        "object_key": "ki:robotics-policy",
        "review_state": "human_confirmed",
        "actor_type": "human",
        "actor_id": "codex-live-smoke",
    }
    governance_step = append_step(
        artifact,
        name="governance_review_mutation",
        path=TYPED_KNOWLEDGE_GOVERNANCE_PATH,
        request_payload=governance_payload,
    )
    governance_result = _http_post_json(
        build_url(api_base, TYPED_KNOWLEDGE_GOVERNANCE_PATH),
        governance_payload,
        timeout=timeout,
    )
    governance_data = step_data_or_failure(step=governance_step, result=governance_result, failures=failures)
    if governance_data is None:
        return blocked_or_failed_return(artifact, governance_step)
    governance_evidence = {
        "contract_version": governance_data.get("contract_version"),
        "identity_ref": governance_data.get("identity_ref"),
        "live_db_write": governance_data.get("live_db_write") is True,
        "current_review_state": get_path(governance_data, "current.review_state"),
    }
    governance_step["evidence"] = governance_evidence
    artifact["evidence"]["governance_live_db_write"] = governance_evidence["live_db_write"]
    if governance_evidence["live_db_write"] is not True:
        return fail_step(
            artifact=artifact,
            step=governance_step,
            failures=failures,
            reason="governance_review_mutation_missing_live_write",
            missing=["live_db_write"],
        )
    governance_step["status"] = STATUS_PASSED

    context_step = append_step(
        artifact,
        name="writing_context",
        path=TYPED_KNOWLEDGE_WRITING_CONTEXT_PATH,
        query={"project_key": project_key},
    )
    context_result = _http_get(
        build_url(api_base, TYPED_KNOWLEDGE_WRITING_CONTEXT_PATH, {"project_key": project_key}),
        timeout=timeout,
    )
    context_data = step_data_or_failure(step=context_step, result=context_result, failures=failures)
    if context_data is None:
        return blocked_or_failed_return(artifact, context_step)
    context_evidence = extract_writing_context_evidence(context_data)
    context_step["evidence"] = context_evidence
    artifact["evidence"]["writing_context_handoff_count"] = context_evidence["handoff_count"]
    if context_evidence["handoff_count"] <= 0:
        return fail_step(
            artifact=artifact,
            step=context_step,
            failures=failures,
            reason="writing_context_missing_handoff",
            missing=["handoff_count"],
        )
    context_step["status"] = STATUS_PASSED

    keyword_payload = {
        "project_key": project_key,
        "query": "robotics investment",
        "selection_hash": f"selection-{smoke_id}",
        "limit": 10,
        "sources": ["resource"],
        "context": {"typed_knowledge_context": context_evidence["typed_knowledge_context"]},
    }
    cards_step = append_step(
        artifact,
        name="writing_keyword_cards",
        path=WRITING_KEYWORD_CARDS_PATH,
        request_payload=keyword_payload,
    )
    cards_result = _http_post_json(build_url(api_base, WRITING_KEYWORD_CARDS_PATH), keyword_payload, timeout=timeout)
    cards_data = step_data_or_failure(step=cards_step, result=cards_result, failures=failures)
    if cards_data is None:
        return blocked_or_failed_return(artifact, cards_step)
    cards_evidence = extract_keyword_card_evidence(cards_data)
    cards_step["evidence"] = cards_evidence
    artifact["evidence"]["keyword_card_publisher"] = cards_evidence["publisher"]
    artifact["evidence"]["keyword_card_typed_knowledge_count"] = cards_evidence["typed_knowledge_card_count"]
    if cards_evidence["typed_knowledge_card_count"] <= 0:
        return fail_step(
            artifact=artifact,
            step=cards_step,
            failures=failures,
            reason="writing_keyword_cards_missing_typed_knowledge_publisher",
            missing=["publisher"],
        )
    cards_step["status"] = STATUS_PASSED

    dsl = build_workflow_graph_dsl(smoke_id)
    draft_path = WORKFLOW_GRAPH_DRAFT_PATH_TEMPLATE.format(graph_id=graph_id)
    draft_payload = {"project_key": project_key, "dsl": dsl, "actor_id": "codex-live-smoke"}
    draft_step = append_step(artifact, name="workflow_graph_draft", path=draft_path, request_payload=draft_payload)
    draft_result = _http_post_json(build_url(api_base, draft_path), draft_payload, timeout=timeout)
    draft_data = step_data_or_failure(step=draft_step, result=draft_result, failures=failures)
    if draft_data is None:
        return blocked_or_failed_return(artifact, draft_step)
    draft_step["evidence"] = {
        "sync_status": draft_data.get("sync_status"),
        "revision": draft_data.get("revision"),
        "graph_id": draft_data.get("graph_id") or graph_id,
    }
    draft_step["status"] = STATUS_PASSED

    submit_path = WORKFLOW_GRAPH_SUBMIT_PATH_TEMPLATE.format(graph_id=graph_id)
    submit_payload = {"project_key": project_key, "base_revision": 0, "actor_id": "codex-live-smoke"}
    submit_step = append_step(
        artifact,
        name="workflow_graph_submit",
        path=submit_path,
        request_payload=submit_payload,
    )
    submit_result = _http_post_json(build_url(api_base, submit_path), submit_payload, timeout=timeout)
    submit_data = step_data_or_failure(step=submit_step, result=submit_result, failures=failures)
    if submit_data is None:
        return blocked_or_failed_return(artifact, submit_step)
    submit_step["evidence"] = {
        "submit_status": submit_data.get("submit_status"),
        "revision": submit_data.get("revision"),
        "graph_id": submit_data.get("graph_id") or graph_id,
    }
    submit_step["status"] = STATUS_PASSED

    audit_path = WORKFLOW_GRAPH_AUDIT_PATH_TEMPLATE.format(graph_id=graph_id)
    audit_step = append_step(artifact, name="workflow_graph_audit", path=audit_path, query={"limit": 50})
    audit_result = _http_get(build_url(api_base, audit_path, {"limit": 50}), timeout=timeout)
    audit_data = step_data_or_failure(step=audit_step, result=audit_result, failures=failures)
    if audit_data is None:
        return blocked_or_failed_return(artifact, audit_step)
    audit_evidence = extract_graph_audit_evidence(audit_data)
    audit_step["evidence"] = audit_evidence
    artifact["evidence"]["graph_audit_count"] = audit_evidence["audit_count"]
    if audit_evidence["audit_count"] <= 0:
        return fail_step(
            artifact=artifact,
            step=audit_step,
            failures=failures,
            reason="workflow_graph_audit_empty",
            missing=["audit_count"],
        )
    audit_step["status"] = STATUS_PASSED

    pack_path = WORKFLOW_GRAPH_EVIDENCE_PACK_PATH_TEMPLATE.format(graph_id=graph_id)
    pack_payload = {"project_key": project_key, "selected_node_ids": ["company-acme", "market-robotics"]}
    pack_step = append_step(artifact, name="workflow_graph_evidence_pack", path=pack_path, request_payload=pack_payload)
    pack_result = _http_post_json(build_url(api_base, pack_path), pack_payload, timeout=timeout)
    pack_data = step_data_or_failure(step=pack_step, result=pack_result, failures=failures)
    if pack_data is None:
        return blocked_or_failed_return(artifact, pack_step)
    pack_evidence = extract_evidence_pack_evidence(pack_data)
    pack_step["evidence"] = pack_evidence
    artifact["evidence"]["evidence_pack_selected_node_count"] = pack_evidence["selected_node_count"]
    if pack_evidence["selected_node_count"] <= 0:
        return fail_step(
            artifact=artifact,
            step=pack_step,
            failures=failures,
            reason="workflow_graph_evidence_pack_empty",
            missing=["selected_node_count"],
        )
    pack_step["status"] = STATUS_PASSED

    handoff_path = WORKFLOW_GRAPH_WRITING_HANDOFF_PATH_TEMPLATE.format(graph_id=graph_id)
    handoff_payload = {"project_key": project_key, "query": "robotics", "selected_node_ids": ["company-acme"]}
    handoff_step = append_step(
        artifact,
        name="graph_writing_handoff_persist",
        path=handoff_path,
        request_payload=handoff_payload,
    )
    handoff_result = _http_post_json(build_url(api_base, handoff_path), handoff_payload, timeout=timeout)
    handoff_data = step_data_or_failure(step=handoff_step, result=handoff_result, failures=failures)
    if handoff_data is None:
        return blocked_or_failed_return(artifact, handoff_step)
    handoff_evidence = extract_handoff_evidence(handoff_data)
    handoff_step["evidence"] = handoff_evidence
    artifact["evidence"]["handoff_backend_marker"] = handoff_evidence["backend_marker"]
    artifact["evidence"]["handoff_run_id"] = handoff_evidence["run_id"]
    artifact["evidence"]["handoff_id"] = handoff_evidence["handoff_id"]
    missing_handoff = [
        field
        for field, value in {
            "backend_marker": handoff_evidence["backend_marker"] == "workflow_graph.run_store",
            "run_id": is_present(handoff_evidence["run_id"]),
            "handoff_id": is_present(handoff_evidence["handoff_id"]),
        }.items()
        if not value
    ]
    if missing_handoff:
        return fail_step(
            artifact=artifact,
            step=handoff_step,
            failures=failures,
            reason="graph_writing_handoff_persistence_missing",
            missing=missing_handoff,
        )
    handoff_step["status"] = STATUS_PASSED

    replay_path = WORKFLOW_GRAPH_HANDOFF_REPLAY_PATH_TEMPLATE.format(
        run_id=handoff_evidence["run_id"],
        handoff_id=handoff_evidence["handoff_id"],
    )
    replay_step = append_step(artifact, name="handoff_replay", path=replay_path)
    replay_result = _http_get(build_url(api_base, replay_path), timeout=timeout)
    replay_data = step_data_or_failure(step=replay_step, result=replay_result, failures=failures)
    if replay_data is None:
        return blocked_or_failed_return(artifact, replay_step)
    replay_evidence = extract_replay_evidence(replay_data)
    replay_step["evidence"] = replay_evidence
    artifact["evidence"]["handoff_replay_event_count"] = replay_evidence["event_count"]
    artifact["evidence"]["handoff_replay_event_types"] = replay_evidence["event_types"]
    if not (replay_evidence["has_persisted_event"] and replay_evidence["has_replayed_event"]):
        return fail_step(
            artifact=artifact,
            step=replay_step,
            failures=failures,
            reason="handoff_replay_missing_persisted_or_replayed_event",
            missing=["persisted_replayed_events"],
        )
    replay_step["status"] = STATUS_PASSED

    session_payload = {
        "source": "codex-live-smoke",
        "project_key": project_key,
        "entrypoint_type": "agent_knowledge_event_model_smoke",
        "goal": "Read back Agent/knowledge event model smoke session.",
        "initial_context": {
            "smoke_id": smoke_id,
            "handoff_id": handoff_evidence["handoff_id"],
            "run_id": handoff_evidence["run_id"],
        },
        "metadata": {"schema_version": SCHEMA_VERSION, "smoke_id": smoke_id},
    }
    session_step = append_step(artifact, name="agent_session_create", path=AGENT_SESSIONS_PATH, request_payload=session_payload)
    session_result = _http_post_json(build_url(api_base, AGENT_SESSIONS_PATH), session_payload, timeout=timeout)
    session_data = step_data_or_failure(step=session_step, result=session_result, failures=failures)
    if session_data is None:
        return blocked_or_failed_return(artifact, session_step)
    session_id = extract_session_id(session_data)
    session_step["evidence"] = {"session_id": session_id}
    artifact["evidence"]["agent_session_id"] = session_id
    if not session_id:
        return fail_step(
            artifact=artifact,
            step=session_step,
            failures=failures,
            reason="agent_session_missing_session_id",
            missing=["session_id"],
        )
    session_step["status"] = STATUS_PASSED

    message_path = AGENT_SESSION_MESSAGES_PATH_TEMPLATE.format(session_id=session_id)
    message_payload = {
        "role": "user",
        "actor": "codex-live-smoke",
        "content": f"Replay handoff {handoff_evidence['handoff_id']} for {smoke_id}.",
        "metadata": {"smoke_id": smoke_id, "handoff_id": handoff_evidence["handoff_id"]},
    }
    message_step = append_step(artifact, name="agent_session_message", path=message_path, request_payload=message_payload)
    message_result = _http_post_json(build_url(api_base, message_path), message_payload, timeout=timeout)
    message_data = step_data_or_failure(step=message_step, result=message_result, failures=failures)
    if message_data is None:
        return blocked_or_failed_return(artifact, message_step)
    message_step["evidence"] = {
        "message_id": message_data.get("message_id") or get_path(message_data, "message.message_id"),
        "session_id": session_id,
    }
    message_step["status"] = STATUS_PASSED

    events_path = AGENT_SESSION_EVENTS_PATH_TEMPLATE.format(session_id=session_id)
    events_step = append_step(artifact, name="agent_session_events_readback", path=events_path)
    events_result = _http_get(build_url(api_base, events_path), timeout=timeout)
    events_data = step_data_or_failure(step=events_step, result=events_result, failures=failures)
    if events_data is None:
        return blocked_or_failed_return(artifact, events_step)
    events_evidence = extract_agent_events_evidence(events_data)
    events_step["evidence"] = events_evidence
    artifact["evidence"]["agent_event_count"] = events_evidence["event_count"]
    artifact["evidence"]["agent_event_types"] = events_evidence["event_types"]
    if events_evidence["event_count"] <= 0:
        return fail_step(
            artifact=artifact,
            step=events_step,
            failures=failures,
            reason="agent_session_events_empty",
            missing=["event_count"],
        )
    events_step["status"] = STATUS_PASSED

    artifact["status"] = STATUS_PASSED if not failures else STATUS_FAILED
    artifact["summary"] = build_summary(artifact)
    return artifact


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    api_base = args.api_base or args.base_url or "http://127.0.0.1:8000"
    output = Path(args.output)
    artifact = build_artifact(
        api_base=api_base,
        project_key=args.project_key,
        output=output,
        timeout=args.timeout,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    if artifact["status"] == STATUS_PASSED:
        return 0
    if args.allow_blocked and artifact["status"] == STATUS_BLOCKED:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
