from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..contracts import ApiEnvelope, ErrorCode, error_response, map_exception_to_error, success_response
from ..services.ingest_config import get_config, upsert_config
from ..project_customization import get_project_customization
from ..services.graph.doc_types import (
    resolve_graph_doc_types,
    resolve_graph_edge_style_bindings,
    resolve_graph_edge_types,
    resolve_graph_field_labels,
    resolve_graph_node_labels,
    resolve_graph_node_types,
    resolve_graph_projections,
    resolve_graph_relation_labels,
    resolve_graph_topic_scope_entities,
    resolve_graph_type_labels,
)
from ..services.projects.workflow import (
    WORKFLOW_PLATFORM_CONFIG_KEY,
    _WORKFLOW_HANDLERS,
    dump_workflow_definition,
    execute_project_workflow,
    load_custom_workflow_board_layout,
    load_custom_workflow_definition,
)
from ..services.request_identity import resolve_request_actor_context

router = APIRouter(prefix="/project-customization", tags=["project-customization"])
ProjectCustomizationDictEnvelope = ApiEnvelope[dict[str, Any]]


def _raise_invalid_input(message: str, *, details: dict | None = None) -> None:
    raise HTTPException(
        status_code=400,
        detail=error_response(ErrorCode.INVALID_INPUT, message, details=details),
    )


def _raise_project_key_required(message: str = "project_key is required. Please select a project first.") -> None:
    raise HTTPException(
        status_code=400,
        detail=error_response(ErrorCode.PROJECT_KEY_REQUIRED, message),
    )


def _raise_not_found(message: str, *, details: dict | None = None) -> None:
    raise HTTPException(
        status_code=404,
        detail=error_response(ErrorCode.NOT_FOUND, message, details=details),
    )


def _status_code_for_error_code(code: ErrorCode) -> int:
    if code == ErrorCode.INVALID_INPUT:
        return 400
    if code == ErrorCode.NOT_FOUND:
        return 404
    if code == ErrorCode.RATE_LIMITED:
        return 429
    if code in {ErrorCode.UPSTREAM_ERROR, ErrorCode.PARSE_ERROR}:
        return 502
    if code == ErrorCode.CONFIG_ERROR:
        return 500
    return 500


class WorkflowRunPayload(BaseModel):
    project_key: str | None = None
    params: dict = Field(default_factory=dict)
    dry_run: bool = Field(default=False)


class WorkflowStepPayload(BaseModel):
    handler: str
    params: dict = Field(default_factory=dict)
    enabled: bool = Field(default=True)
    name: str | None = Field(default=None)


class WorkflowTemplatePayload(BaseModel):
    project_key: str | None = None
    steps: list[WorkflowStepPayload] = Field(default_factory=list)
    board_layout: dict = Field(default_factory=dict)


class WorkflowTemplateStagePayload(WorkflowTemplatePayload):
    stage: Literal["draft", "staging", "active"] = Field(default="draft")
    actor: str | None = None
    requested_by: str | None = None
    trace_id: str | None = None


class WorkflowTemplatePromotePayload(BaseModel):
    project_key: str | None = None
    from_stage: Literal["draft", "staging"] = Field(default="draft")
    to_stage: Literal["staging", "active"] = Field(default="staging")
    actor: str | None = None
    requested_by: str | None = None
    trace_id: str | None = None


class WorkflowTemplateRollbackPreviewPayload(BaseModel):
    project_key: str | None = None
    target_stage: Literal["staging", "active"] = Field(default="staging")
    target_version: int | None = None
    reason: str | None = None
    actor: str | None = None
    requested_by: str | None = None
    trace_id: str | None = None


WORKFLOW_GOVERNANCE_CONTRACT_VERSION = "cross_object.publish_governance.v1"
WORKFLOW_GOVERNANCE_OBJECT_TYPE = "workflow_template"
WORKFLOW_GOVERNANCE_COMPATIBLE_OBJECT_TYPES = ("workflow_template", "dashboard", "report", "project")
WORKFLOW_GOVERNANCE_OPERATIONS = ("stage", "publish", "rollback", "snapshot", "history", "dry_run")


def _coerce_workflow_payload(raw_payload: dict | None) -> tuple[dict[str, dict], dict[str, dict], int]:
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    workflows = payload.get("workflows")
    boards = payload.get("boards")
    version_raw = payload.get("version", 0)
    try:
        version = int(version_raw) if version_raw is not None else 0
    except (TypeError, ValueError):
        version = 0
    return (
        workflows if isinstance(workflows, dict) else {},
        boards if isinstance(boards, dict) else {},
        version if version >= 0 else 0,
    )


def _coerce_workflow_stages(raw_payload: dict | None) -> dict[str, dict[str, dict[str, Any]]]:
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    stages = payload.get("workflow_stages")
    if not isinstance(stages, dict):
        return {}
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for workflow_name, stage_map in stages.items():
        if not isinstance(stage_map, dict):
            continue
        normalized_stage_map: dict[str, dict[str, Any]] = {}
        for stage_name, stage_payload in stage_map.items():
            if stage_name not in {"draft", "staging", "active"} or not isinstance(stage_payload, dict):
                continue
            steps = stage_payload.get("steps") if isinstance(stage_payload.get("steps"), list) else []
            board_layout = stage_payload.get("board_layout") if isinstance(stage_payload.get("board_layout"), dict) else {}
            normalized_stage_map[stage_name] = {
                **stage_payload,
                "steps": steps,
                "board_layout": board_layout,
            }
        if normalized_stage_map:
            out[str(workflow_name)] = normalized_stage_map
    return out


def _coerce_workflow_stage_history(raw_payload: dict | None) -> dict[str, list[dict[str, Any]]]:
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    raw_history = payload.get("workflow_stage_history")
    if not isinstance(raw_history, dict):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for workflow_name, items in raw_history.items():
        if not isinstance(items, list):
            continue
        normalized_items = [item for item in items if isinstance(item, dict)]
        if normalized_items:
            out[str(workflow_name)] = normalized_items
    return out


def _validate_workflow_template_payload(workflow_name: str, payload: WorkflowTemplatePayload) -> tuple[str, str]:
    effective_project_key = (payload.project_key or "").strip()
    if not effective_project_key:
        _raise_project_key_required()

    normalized_workflow_name = workflow_name.strip()
    if not normalized_workflow_name:
        _raise_invalid_input(
            "workflow_name is required.",
            details={"field": "workflow_name", "value": workflow_name},
        )

    if not isinstance(payload.steps, list) or not payload.steps:
        _raise_invalid_input(
            "steps is required and must be a non-empty array.",
            details={"field": "steps"},
        )
    for idx, step in enumerate(payload.steps, start=1):
        if not step.handler or not str(step.handler).strip():
            _raise_invalid_input(
                f"steps[{idx}].handler is required.",
                details={"field": f"steps[{idx}].handler", "index": idx},
            )
    return effective_project_key, normalized_workflow_name


def _read_workflow_platform_payload(
    project_key: str,
) -> tuple[
    dict[str, Any],
    dict[str, dict],
    dict[str, dict],
    int,
    dict[str, dict[str, dict[str, Any]]],
    dict[str, list[dict[str, Any]]],
]:
    existing_record = get_config(project_key, WORKFLOW_PLATFORM_CONFIG_KEY) or {}
    existing_payload = existing_record.get("payload") if isinstance(existing_record.get("payload"), dict) else {}
    workflows, boards, version = _coerce_workflow_payload(existing_payload)
    stages = _coerce_workflow_stages(existing_payload)
    history = _coerce_workflow_stage_history(existing_payload)
    return existing_payload, workflows, boards, version, stages, history


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_audit_actor(actor: str | None, requested_by: str | None) -> str:
    return (requested_by or actor or "system").strip() or "system"


def _workflow_governance_object_id(project_key: str, workflow_name: str) -> str:
    return f"{project_key}:{workflow_name}"


def _governance_operator_from_audit(audit: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(audit, dict):
        return {"actor": "system", "requested_by": "system", "applied_by": "system", "identity_source": "system"}
    return {
        "actor": audit.get("actor") or "system",
        "requested_by": audit.get("requested_by") or audit.get("actor") or "system",
        "applied_by": audit.get("applied_by") or audit.get("actor") or "system",
        "identity_source": audit.get("identity_source") or "system",
        "actor_trusted": bool(audit.get("actor_trusted", False)),
        "actor_auth_mode": audit.get("actor_auth_mode") or audit.get("identity_source") or "system",
        "legacy_actor_id": audit.get("legacy_actor_id"),
        "trace_id": audit.get("trace_id"),
    }


def _build_workflow_governance(
    *,
    project_key: str,
    workflow_name: str,
    operation: str,
    stage: str,
    dry_run: bool,
    will_mutate: bool,
    requires_publish: bool,
    current_version: int | None = None,
    next_version: int | None = None,
    target_stage: str | None = None,
    target_version: int | None = None,
    reason: str | None = None,
    audit: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_operation = operation if operation in WORKFLOW_GOVERNANCE_OPERATIONS else "snapshot"
    object_id = _workflow_governance_object_id(project_key, workflow_name)
    target = {
        "object_type": WORKFLOW_GOVERNANCE_OBJECT_TYPE,
        "object_id": object_id,
        "stage": target_stage or stage,
        "version": target_version,
    }
    snapshot_payload = snapshot if isinstance(snapshot, dict) else {}
    history_items = history if isinstance(history, list) else []
    resolved_reason = str(reason or "").strip() or None
    return {
        "contract_version": WORKFLOW_GOVERNANCE_CONTRACT_VERSION,
        "object_type": WORKFLOW_GOVERNANCE_OBJECT_TYPE,
        "object_id": object_id,
        "project_key": project_key,
        "operation": resolved_operation,
        "stage": stage,
        "dry_run": bool(dry_run),
        "will_mutate": bool(will_mutate),
        "requires_publish": bool(requires_publish),
        "version": {
            "current": current_version,
            "next": next_version,
            "target": target_version,
        },
        "operator": _governance_operator_from_audit(audit),
        "target": target,
        "snapshot": snapshot_payload,
        "history": {
            "included": bool(history_items),
            "count": len(history_items),
            "items": history_items,
        },
        "reason": resolved_reason,
        "compatible_object_types": list(WORKFLOW_GOVERNANCE_COMPATIBLE_OBJECT_TYPES),
        "schema": {
            "operations": list(WORKFLOW_GOVERNANCE_OPERATIONS),
            "object_type_field": "object_type",
            "object_id_field": "object_id",
            "extension_rule": "dashboard/report/project may reuse this governance shape with their own object_type/object_id",
        },
    }


def _resolve_audit_identity(
    request: Request,
    *,
    actor: str | None = None,
    requested_by: str | None = None,
) -> dict[str, Any]:
    actor_context = resolve_request_actor_context(request)
    if (actor or "").strip() or (requested_by or "").strip():
        payload_actor = actor or requested_by
        return {
            "actor": actor,
            "requested_by": requested_by,
            "applied_by": payload_actor,
            "identity_source": "payload",
            "actor_trusted": False,
            "actor_auth_mode": "payload",
            "legacy_actor_id": actor_context.legacy_actor_id,
        }
    if actor_context.actor_source != "anonymous" and actor_context.actor_id != "anonymous":
        return {
            "actor": actor_context.actor_id,
            "requested_by": actor_context.actor_id,
            "applied_by": actor_context.actor_id,
            "identity_source": actor_context.actor_source,
            "actor_trusted": actor_context.actor_trusted,
            "actor_auth_mode": actor_context.actor_auth_mode,
            "legacy_actor_id": actor_context.legacy_actor_id,
        }
    return {
        "actor": "system",
        "requested_by": "system",
        "applied_by": "system",
        "identity_source": "system",
        "actor_trusted": False,
        "actor_auth_mode": "system",
        "legacy_actor_id": actor_context.legacy_actor_id,
    }


def _build_stage_audit_event(
    *,
    action: str,
    version: int,
    actor: str | None = None,
    requested_by: str | None = None,
    applied_by: str | None = None,
    from_stage: str | None = None,
    to_stage: str | None = None,
    from_version: int | None = None,
    to_version: int | None = None,
    target_version: int | None = None,
    trace_id: str | None = None,
    identity_source: str | None = None,
    actor_trusted: bool | None = None,
    actor_auth_mode: str | None = None,
    legacy_actor_id: str | None = None,
    stage_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_actor = _normalize_audit_actor(actor, requested_by)
    normalized_applied_by = (applied_by or normalized_actor).strip() or normalized_actor
    event: dict[str, Any] = {
        "actor": normalized_actor,
        "requested_by": normalized_actor,
        "applied_by": normalized_applied_by,
        "action": action,
        "from_stage": from_stage,
        "to_stage": to_stage,
        "version": version,
        "created_at": _utc_now_iso(),
        "trace_id": (trace_id or "").strip() or str(uuid4()),
    }
    if identity_source:
        event["identity_source"] = identity_source
    if actor_trusted is not None:
        event["actor_trusted"] = actor_trusted
    if actor_auth_mode:
        event["actor_auth_mode"] = actor_auth_mode
    if legacy_actor_id:
        event["legacy_actor_id"] = legacy_actor_id
    if from_version is not None:
        event["from_version"] = from_version
    if to_version is not None:
        event["to_version"] = to_version
    if target_version is not None:
        event["target_version"] = target_version
    if stage_snapshot is not None:
        event["stage_snapshot"] = stage_snapshot
    return event


def _append_workflow_stage_history(
    history: dict[str, list[dict[str, Any]]],
    workflow_name: str,
    event: dict[str, Any],
    *,
    limit: int = 50,
) -> dict[str, list[dict[str, Any]]]:
    workflow_history = [item for item in history.get(workflow_name, []) if isinstance(item, dict)]
    workflow_history.append(event)
    history[workflow_name] = workflow_history[-limit:]
    return history


def _audit_without_snapshot(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    return {key: value for key, value in event.items() if key != "stage_snapshot"}


def _visible_stage_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in (_audit_without_snapshot(item) for item in history) if isinstance(event, dict)]


def _find_stage_snapshot_by_version(
    *,
    workflow_stages: dict[str, dict[str, Any]],
    history: list[dict[str, Any]],
    target_stage: str,
    target_version: int | None,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for stage_record in workflow_stages.values():
        if isinstance(stage_record, dict):
            candidates.append(stage_record)
    for event in history:
        snapshot = event.get("stage_snapshot") if isinstance(event, dict) else None
        if isinstance(snapshot, dict):
            candidates.append(snapshot)
    for candidate in reversed(candidates):
        if candidate.get("stage") != target_stage:
            continue
        if target_version is not None and candidate.get("version") != target_version:
            continue
        return candidate
    return None


def _build_workflow_stage_record(
    *,
    stage: str,
    version: int,
    steps: list[dict[str, Any]],
    board_layout: dict[str, Any],
    promoted_from: str | None = None,
    audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "stage": stage,
        "version": version,
        "steps": steps,
        "board_layout": board_layout,
        "requires_publish": stage != "active",
    }
    if promoted_from:
        record["promoted_from"] = promoted_from
    if audit:
        record["audit"] = {key: value for key, value in audit.items() if key != "stage_snapshot"}
    return record


def _infer_node_module_from_handler(handler: str) -> str:
    handler = str(handler or "").strip()
    if handler == "ingest.market":
        return "search_market"
    if handler == "ingest.data_api":
        return "search_data_api"
    if handler == "ingest.google_news":
        return "search_news"
    if handler == "ingest.reddit":
        return "search_reddit"
    return "custom"


def _build_default_graph_from_steps(steps: list[dict]) -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []
    for idx, step in enumerate(steps, start=1):
        node_id = f"n{idx}"
        nodes.append(
            {
                "id": node_id,
                "module_key": _infer_node_module_from_handler(step.get("handler") or ""),
                "title": step.get("name") or step.get("handler") or node_id,
                "data_type": "market_info",
                "params": step.get("params") if isinstance(step.get("params"), dict) else {},
            }
        )
        if idx > 1:
            edges.append(
                {
                    "id": f"e{idx - 1}",
                    "source": f"n{idx - 1}",
                    "target": node_id,
                    "mapping": {"count_rule": "", "field_map": []},
                }
            )
    return {"nodes": nodes, "edges": edges}


def _normalize_board_layout(board_layout: dict, steps: list[dict]) -> dict:
    layout = board_layout if isinstance(board_layout, dict) else {}
    design = layout.get("design")
    design = design if isinstance(design, dict) else {}
    graph = layout.get("graph")
    graph = graph if isinstance(graph, dict) else {}
    graph_nodes = graph.get("nodes")
    graph_edges = graph.get("edges")
    graph_nodes = graph_nodes if isinstance(graph_nodes, list) else []
    graph_edges = graph_edges if isinstance(graph_edges, list) else []
    if not graph_nodes:
        fallback = _build_default_graph_from_steps(steps)
        graph_nodes = fallback["nodes"]
        graph_edges = fallback["edges"] if not graph_edges else graph_edges

    edge_mappings = layout.get("edge_mappings")
    if not isinstance(edge_mappings, list):
        edge_mappings = []
    adapter_nodes = layout.get("adapter_nodes")
    if not isinstance(adapter_nodes, list):
        adapter_nodes = []
    data_flow = layout.get("data_flow")
    if not isinstance(data_flow, list):
        data_flow = ["documents", "extracted_data", "visualization"]

    normalized_design = {
        "global_data_type": str(design.get("global_data_type") or "market_info"),
        "node_overrides": design.get("node_overrides") if isinstance(design.get("node_overrides"), dict) else {},
        "llm_policy": str(design.get("llm_policy") or "auto"),
        "visualization_module": str(design.get("visualization_module") or layout.get("layout") or "trend"),
    }

    return {
        **layout,
        "layout": str(layout.get("layout") or "trend"),
        "auto_interface": bool(layout.get("auto_interface", True)),
        "data_flow": data_flow,
        "design": normalized_design,
        "graph": {"nodes": graph_nodes, "edges": graph_edges},
        "edge_mappings": [x for x in edge_mappings if isinstance(x, dict)],
        "adapter_nodes": [x for x in adapter_nodes if isinstance(x, dict)],
    }


def _read_workflow_config_version(project_key: str) -> int:
    record = get_config(project_key, WORKFLOW_PLATFORM_CONFIG_KEY) or {}
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    _, _, version = _coerce_workflow_payload(payload)
    return version


def _serialize_workflow_steps(steps: list[WorkflowStepPayload]) -> list[dict[str, Any]]:
    return [
        {
            "handler": step.handler,
            "params": step.params,
            "enabled": step.enabled,
            "name": step.name,
        }
        for step in steps
    ]


def _compact_step_for_diff(step: dict[str, Any] | None) -> dict[str, Any] | None:
    if step is None:
        return None
    return {
        "handler": step.get("handler"),
        "name": step.get("name"),
        "enabled": bool(step.get("enabled", True)),
        "params": step.get("params") if isinstance(step.get("params"), dict) else {},
    }


def _build_workflow_diff_contract(
    *,
    changed: bool,
    step_changes: list[dict[str, Any]],
    board_changed: bool,
    current_version: int,
) -> dict[str, Any]:
    removed_or_disabled = any(
        change.get("change_type") == "removed"
        or (
            isinstance(change.get("after"), dict)
            and isinstance(change.get("before"), dict)
            and bool(change["before"].get("enabled", True))
            and not bool(change["after"].get("enabled", True))
        )
        for change in step_changes
    )
    affected_areas: list[str] = []
    if step_changes:
        affected_areas.append("workflow_steps")
    if board_changed:
        affected_areas.append("graph_board_layout")
    if changed:
        affected_areas.append("publish_policy")
    if not affected_areas:
        affected_areas.append("none")

    if not changed:
        reason_code = "workflow_template_unchanged"
        risk_level = "low"
    elif step_changes and board_changed:
        reason_code = "workflow_template_steps_and_board_changed"
        risk_level = "high" if removed_or_disabled else "medium"
    elif step_changes:
        reason_code = "workflow_template_steps_changed"
        risk_level = "high" if removed_or_disabled else "medium"
    else:
        reason_code = "workflow_template_board_changed"
        risk_level = "medium"

    policy_change = {
        "changed": changed,
        "will_mutate": False,
        "requires_publish": changed,
        "stage": "draft_preview" if changed else "active_matches_draft",
        "active_version": current_version,
        "draft_version": current_version + 1 if changed else current_version,
    }
    impact_summary = {
        "mode": "template_diff",
        "reason_code": reason_code,
        "risk_level": risk_level,
        "affected_areas": affected_areas,
        "steps_changed": len(step_changes),
        "board_layout_changed": board_changed,
        "policy_change": policy_change,
        "will_mutate": False,
        "requires_publish": changed,
    }
    quick_actions = [
        {
            "kind": "publish_workflow_template",
            "message": "Review the diff, save a draft, then promote through staging before active execution.",
            "action_priority": "medium" if risk_level == "medium" else "high",
            "reason_code": reason_code,
        }
    ] if changed else [
        {
            "kind": "no_publish_required",
            "message": "No workflow template change is pending; keep the current active template.",
            "action_priority": "low",
            "reason_code": reason_code,
        }
    ]
    return {
        "reason_code": reason_code,
        "risk_level": risk_level,
        "affected_areas": affected_areas,
        "policy_change": policy_change,
        "impact_summary": impact_summary,
        "quick_actions": quick_actions,
    }


def _build_workflow_template_diff(
    *,
    workflow_name: str,
    payload: WorkflowTemplatePayload,
) -> dict[str, Any]:
    effective_project_key, normalized_workflow_name = _validate_workflow_template_payload(workflow_name, payload)

    try:
        _, current_steps, current_meta, current_board_layout = _read_workflow_template(
            effective_project_key,
            normalized_workflow_name,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        error = detail.get("error") if isinstance(detail.get("error"), dict) else {}
        if exc.status_code != 404 or error.get("code") != ErrorCode.NOT_FOUND.value:
            raise
        current_steps = []
        current_meta = {"source": "new"}
        current_board_layout = {}

    proposed_steps = _serialize_workflow_steps(payload.steps)
    proposed_board_layout = _normalize_board_layout(payload.board_layout, proposed_steps)
    current_version = _read_workflow_config_version(effective_project_key)

    max_len = max(len(current_steps), len(proposed_steps))
    step_changes: list[dict[str, Any]] = []
    for idx in range(max_len):
        before = _compact_step_for_diff(current_steps[idx] if idx < len(current_steps) else None)
        after = _compact_step_for_diff(proposed_steps[idx] if idx < len(proposed_steps) else None)
        if before == after:
            continue
        if before is None:
            change_type = "added"
        elif after is None:
            change_type = "removed"
        else:
            change_type = "modified"
        step_changes.append(
            {
                "index": idx + 1,
                "change_type": change_type,
                "before": before,
                "after": after,
            }
        )

    board_changed = current_board_layout != proposed_board_layout
    changed = bool(step_changes or board_changed or current_meta.get("source") == "new")
    contract = _build_workflow_diff_contract(
        changed=changed,
        step_changes=step_changes,
        board_changed=board_changed,
        current_version=current_version,
    )

    return {
        "project_key": effective_project_key,
        "workflow_name": normalized_workflow_name,
        "config_key": WORKFLOW_PLATFORM_CONFIG_KEY,
        "changed": changed,
        "reason_code": contract["reason_code"],
        "risk_level": contract["risk_level"],
        "affected_areas": contract["affected_areas"],
        "policy_change": contract["policy_change"],
        "impact_summary": contract["impact_summary"],
        "quick_actions": contract["quick_actions"],
        "current_version": current_version,
        "next_version": current_version + 1 if changed else current_version,
        "version_summary": {
            "active_version": current_version,
            "draft_version": current_version + 1 if changed else current_version,
            "staging_version": None,
            "stage": "draft_preview" if changed else "active_matches_draft",
            "source": current_meta.get("source"),
            "will_mutate": False,
            "requires_publish": changed,
        },
        "diff": {
            "steps": step_changes,
            "step_count_before": len(current_steps),
            "step_count_after": len(proposed_steps),
            "board_layout_changed": board_changed,
        },
        "current": {
            "meta": current_meta,
            "steps": current_steps,
            "board_layout": current_board_layout,
        },
        "proposed": {
            "steps": proposed_steps,
            "board_layout": proposed_board_layout,
        },
    }


def _build_workflow_dry_run_result(
    *,
    workflow_name: str,
    project_key: str,
    params: dict,
) -> dict[str, Any]:
    effective_project_key, steps, meta, board_layout = _read_workflow_template(project_key, workflow_name)
    normalized_workflow_name = workflow_name.strip()
    current_version = _read_workflow_config_version(effective_project_key)

    missing_dependencies: list[dict[str, Any]] = []
    step_preview: list[dict[str, Any]] = []
    enabled_count = 0
    disabled_count = 0
    for idx, step in enumerate(steps, start=1):
        enabled = bool(step.get("enabled", True))
        handler = str(step.get("handler") or "").strip()
        name = step.get("name") or handler or f"step-{idx}"
        if not enabled:
            disabled_count += 1
            step_preview.append(
                {
                    "index": idx,
                    "name": name,
                    "handler": handler,
                    "status": "skipped",
                    "reason": "disabled",
                    "readiness": "skipped",
                    "risk_level": "low",
                }
            )
            continue

        enabled_count += 1
        if handler not in _WORKFLOW_HANDLERS:
            dependency = {
                "index": idx,
                "name": name,
                "handler": handler,
                "kind": "workflow_handler",
                "message": f"workflow handler not found: {handler}",
            }
            missing_dependencies.append(dependency)
            step_preview.append({**dependency, "status": "blocked", "readiness": "blocked", "risk_level": "high"})
            continue

        step_preview.append(
            {
                "index": idx,
                "name": name,
                "handler": handler,
                "status": "ready",
                "readiness": "ready",
                "risk_level": "low",
            }
        )

    steps_by_status: dict[str, int] = {"ready": 0, "blocked": 0, "skipped": 0}
    for step in step_preview:
        status = str(step.get("status") or "unknown")
        steps_by_status[status] = steps_by_status.get(status, 0) + 1

    blocking_reasons = [
        {
            "kind": dependency["kind"],
            "message": dependency["message"],
            "step_index": dependency["index"],
            "handler": dependency["handler"],
        }
        for dependency in missing_dependencies
    ]
    readiness = "blocked" if blocking_reasons else "ready"
    risk_level = "high" if blocking_reasons else "low"
    reason_code = "missing_workflow_handler" if blocking_reasons else "workflow_ready"
    affected_areas = ["workflow_handlers", "runtime_execution"] if blocking_reasons else ["runtime_execution"]
    user_action_required = bool(blocking_reasons)
    readiness_summary = (
        "Dry-run is blocked because one or more enabled workflow handlers are missing."
        if blocking_reasons
        else "Dry-run found all enabled workflow handlers; workflow is ready to execute."
    )
    user_actions = [
        {
            "kind": "install_or_register_workflow_handler",
            "message": f"Register workflow handler before execution: {dependency['handler']}",
            "step_index": dependency["index"],
            "handler": dependency["handler"],
        }
        for dependency in missing_dependencies
    ]
    quick_actions = [
        {
            "kind": action["kind"],
            "message": action["message"],
            "action_priority": "high",
            "reason_code": reason_code,
            "step_index": action["step_index"],
            "handler": action["handler"],
        }
        for action in user_actions
    ] if user_actions else [
        {
            "kind": "execute_workflow",
            "message": "All enabled handlers are available; execute the workflow when ready.",
            "action_priority": "low",
            "reason_code": reason_code,
        }
    ]
    policy_change = {
        "changed": False,
        "will_mutate": False,
        "requires_publish": False,
        "stage": "dry_run",
        "summary": "Dry-run validates runtime readiness only and does not change workflow policy.",
    }

    impact_summary = {
        "mode": "dry_run",
        "reason_code": reason_code,
        "will_execute": False,
        "writes_blocked": True,
        "runtime_tasks_blocked": True,
        "steps_total": len(steps),
        "enabled_steps": enabled_count,
        "disabled_steps": disabled_count,
        "handlers": [str(step.get("handler") or "").strip() for step in steps],
        "workflow_source": meta.get("source"),
        "config_version": current_version,
        "current_version": current_version,
        "params_keys": sorted(str(key) for key in params.keys()),
        "risk_level": risk_level,
        "readiness": readiness,
        "affected_areas": affected_areas,
        "policy_change": policy_change,
        "blocking_reason_count": len(blocking_reasons),
        "user_action_required": user_action_required,
        "quick_actions_count": len(quick_actions),
    }
    governance = _build_workflow_governance(
        project_key=effective_project_key,
        workflow_name=normalized_workflow_name,
        operation="dry_run",
        stage="dry_run",
        dry_run=True,
        will_mutate=False,
        requires_publish=False,
        current_version=current_version,
        next_version=current_version,
        target_stage="dry_run",
        target_version=current_version,
        snapshot={"stage": "active", "version": current_version, "meta": meta},
        history=[],
    )

    return {
        "project_key": effective_project_key,
        "workflow_name": normalized_workflow_name,
        "governance": governance,
        "dry_run": True,
        "status": "blocked" if missing_dependencies else "ok",
        "reason_code": reason_code,
        "risk_level": risk_level,
        "readiness": readiness,
        "readiness_summary": readiness_summary,
        "affected_areas": affected_areas,
        "policy_change": policy_change,
        "blocking_reasons": blocking_reasons,
        "steps_by_status": steps_by_status,
        "user_action_required": user_action_required,
        "user_actions": user_actions,
        "quick_actions": quick_actions,
        "missing_dependencies": missing_dependencies,
        "impact_summary": impact_summary,
        "config_version": current_version,
        "current_version": current_version,
        "config_key": WORKFLOW_PLATFORM_CONFIG_KEY,
        "meta": meta,
        "board_layout": board_layout,
        "steps": step_preview,
    }


@router.get("/menu", response_model=ProjectCustomizationDictEnvelope)
def get_menu_config(project_key: str | None = Query(default=None)):
    customization = get_project_customization(project_key)
    return success_response(
        {
            "project_key": customization.project_key,
            "menu": customization.get_menu_config(),
        }
    )


@router.get("/workflows", response_model=ProjectCustomizationDictEnvelope)
def list_workflows(project_key: str | None = Query(default=None)):
    customization = get_project_customization(project_key)
    workflow_mapping = customization.get_workflow_mapping()
    custom_record = get_config(customization.project_key, WORKFLOW_PLATFORM_CONFIG_KEY) or {}
    custom_payload = custom_record.get("payload") if isinstance(custom_record.get("payload"), dict) else {}
    custom_workflows, _, _ = _coerce_workflow_payload(custom_payload)
    merged = set(workflow_mapping.keys()) | set(custom_workflows.keys())
    return success_response(
        {
            "project_key": customization.project_key,
            "items": sorted(merged),
        }
    )


def _read_workflow_template(project_key: str | None, workflow_name: str) -> tuple[str, list[dict], dict[str, str], dict]:
    customization = get_project_customization(project_key)
    effective_project_key = customization.project_key
    normalized_workflow_name = workflow_name.strip()
    if not normalized_workflow_name:
        _raise_invalid_input(
            "workflow_name is required.",
            details={"field": "workflow_name", "value": workflow_name},
        )

    custom_definition = load_custom_workflow_definition(effective_project_key, normalized_workflow_name)
    if custom_definition is not None:
        steps = dump_workflow_definition(custom_definition.steps)
        board_layout = _normalize_board_layout(
            load_custom_workflow_board_layout(effective_project_key, normalized_workflow_name),
            steps,
        )
        return (
            effective_project_key,
            steps,
            {"source": "custom"},
            board_layout,
        )

    workflow_mapping = customization.get_workflow_mapping()
    workflow = workflow_mapping.get(normalized_workflow_name)
    if workflow is None:
        _raise_not_found(
            f"workflow not found: {normalized_workflow_name}",
            details={"workflow_name": normalized_workflow_name},
        )
    steps = dump_workflow_definition(workflow.steps)
    board_layout = _normalize_board_layout(
        load_custom_workflow_board_layout(effective_project_key, normalized_workflow_name),
        steps,
    )
    return (
        effective_project_key,
        steps,
        {"source": "builtin"},
        board_layout,
    )


@router.get("/workflows/{workflow_name}/template", response_model=ProjectCustomizationDictEnvelope)
def get_workflow_template(workflow_name: str, project_key: str | None = Query(default=None)):
    effective_project_key, steps, meta, board_layout = _read_workflow_template(project_key, workflow_name)
    return success_response(
        {
            "project_key": effective_project_key,
            "workflow_name": workflow_name,
            "steps": steps,
            "board_layout": board_layout,
            "meta": meta,
        }
    )


@router.post("/workflows/{workflow_name}/template/diff", response_model=ProjectCustomizationDictEnvelope)
def diff_workflow_template(workflow_name: str, payload: WorkflowTemplatePayload):
    data = _build_workflow_template_diff(workflow_name=workflow_name, payload=payload)
    data["governance"] = _build_workflow_governance(
        project_key=data["project_key"],
        workflow_name=data["workflow_name"],
        operation="snapshot",
        stage=data["version_summary"]["stage"],
        dry_run=True,
        will_mutate=False,
        requires_publish=bool(data["version_summary"]["requires_publish"]),
        current_version=data["current_version"],
        next_version=data["next_version"],
        target_stage="draft",
        target_version=data["next_version"],
        snapshot={"current": data["current"], "proposed": data["proposed"], "diff": data["diff"]},
        history=[],
    )
    return success_response(data)


@router.get("/workflows/{workflow_name}/template/versions", response_model=ProjectCustomizationDictEnvelope)
def list_workflow_template_versions(workflow_name: str, project_key: str | None = Query(default=None)):
    effective_project_key = (project_key or "").strip() or get_project_customization().project_key
    if not effective_project_key:
        _raise_project_key_required()
    normalized_workflow_name = workflow_name.strip()
    if not normalized_workflow_name:
        _raise_invalid_input(
            "workflow_name is required.",
            details={"field": "workflow_name", "value": workflow_name},
        )

    _, workflows, boards, version, stages, history = _read_workflow_platform_payload(effective_project_key)
    workflow_stages = dict(stages.get(normalized_workflow_name) or {})
    workflow_history = history.get(normalized_workflow_name, [])
    active_workflow = workflows.get(normalized_workflow_name)
    if isinstance(active_workflow, dict):
        existing_active_record = workflow_stages.get("active") if isinstance(workflow_stages.get("active"), dict) else {}
        workflow_stages["active"] = _build_workflow_stage_record(
            stage="active",
            version=int(existing_active_record.get("version") or version),
            steps=active_workflow.get("steps") if isinstance(active_workflow.get("steps"), list) else [],
            board_layout=boards.get(normalized_workflow_name) if isinstance(boards.get(normalized_workflow_name), dict) else {},
            audit=existing_active_record.get("audit") if isinstance(existing_active_record.get("audit"), dict) else None,
        )
    items = [
        workflow_stages[stage]
        for stage in ("draft", "staging", "active")
        if isinstance(workflow_stages.get(stage), dict)
    ]
    visible_history = _visible_stage_history(workflow_history)
    latest_stage = workflow_stages.get("active") or workflow_stages.get("staging") or workflow_stages.get("draft") or {}
    return success_response(
        {
            "project_key": effective_project_key,
            "workflow_name": normalized_workflow_name,
            "config_key": WORKFLOW_PLATFORM_CONFIG_KEY,
            "current_version": version,
            "governance": _build_workflow_governance(
                project_key=effective_project_key,
                workflow_name=normalized_workflow_name,
                operation="history",
                stage="history",
                dry_run=True,
                will_mutate=False,
                requires_publish=False,
                current_version=version,
                next_version=version,
                target_stage=str(latest_stage.get("stage") or "history"),
                target_version=latest_stage.get("version") if isinstance(latest_stage, dict) else None,
                snapshot=latest_stage if isinstance(latest_stage, dict) else {},
                history=visible_history,
            ),
            "items": items,
            "history": visible_history,
            "stage_summary": {
                "has_draft": "draft" in workflow_stages,
                "has_staging": "staging" in workflow_stages,
                "has_active": "active" in workflow_stages,
                "active_version": version if "active" in workflow_stages else None,
                "draft_version": workflow_stages.get("draft", {}).get("version"),
                "staging_version": workflow_stages.get("staging", {}).get("version"),
                "latest_audit": _audit_without_snapshot(workflow_history[-1]) if workflow_history else None,
            },
        }
    )


@router.post("/workflows/{workflow_name}/template/stage", response_model=ProjectCustomizationDictEnvelope)
def save_workflow_template_stage(request: Request, workflow_name: str, payload: WorkflowTemplateStagePayload):
    effective_project_key, normalized_workflow_name = _validate_workflow_template_payload(workflow_name, payload)
    existing_payload, workflows, boards, version, stages, history = _read_workflow_platform_payload(effective_project_key)
    serialized_steps = _serialize_workflow_steps(payload.steps)
    normalized_board = _normalize_board_layout(payload.board_layout, serialized_steps)
    next_version = version + 1
    workflow_stage_map = dict(stages.get(normalized_workflow_name) or {})
    audit_identity = _resolve_audit_identity(request, actor=payload.actor, requested_by=payload.requested_by)
    audit = _build_stage_audit_event(
        action="save_stage",
        version=next_version,
        actor=audit_identity["actor"],
        requested_by=audit_identity["requested_by"],
        applied_by=audit_identity["applied_by"],
        from_stage=None,
        to_stage=payload.stage,
        trace_id=payload.trace_id,
        identity_source=audit_identity["identity_source"],
        actor_trusted=audit_identity["actor_trusted"],
        actor_auth_mode=audit_identity["actor_auth_mode"],
        legacy_actor_id=audit_identity["legacy_actor_id"],
    )
    stage_record = _build_workflow_stage_record(
        stage=payload.stage,
        version=next_version,
        steps=serialized_steps,
        board_layout=normalized_board,
        audit=audit,
    )
    audit["stage_snapshot"] = stage_record
    workflow_stage_map[payload.stage] = stage_record
    stages[normalized_workflow_name] = workflow_stage_map
    history = _append_workflow_stage_history(history, normalized_workflow_name, audit)
    visible_history = _visible_stage_history(history.get(normalized_workflow_name, []))
    governance = _build_workflow_governance(
        project_key=effective_project_key,
        workflow_name=normalized_workflow_name,
        operation="stage",
        stage=payload.stage,
        dry_run=False,
        will_mutate=True,
        requires_publish=payload.stage != "active",
        current_version=version,
        next_version=next_version,
        target_stage=payload.stage,
        target_version=next_version,
        audit=audit,
        snapshot=stage_record,
        history=visible_history,
    )

    if payload.stage == "active":
        workflows[normalized_workflow_name] = {"steps": serialized_steps}
        boards[normalized_workflow_name] = normalized_board

    data = upsert_config(
        project_key=effective_project_key,
        config_key=WORKFLOW_PLATFORM_CONFIG_KEY,
        config_type=WORKFLOW_PLATFORM_CONFIG_KEY,
        payload={
            **existing_payload,
            "version": next_version,
            "workflows": workflows,
            "boards": boards,
            "workflow_stages": stages,
            "workflow_stage_history": history,
        },
    )
    return success_response(
        {
            "project_key": data["project_key"],
            "workflow_name": normalized_workflow_name,
            "saved": True,
            "stage": payload.stage,
            "config_key": WORKFLOW_PLATFORM_CONFIG_KEY,
            "current_version": version,
            "next_version": next_version,
            "governance": governance,
            "audit": _audit_without_snapshot(audit),
            "history": visible_history,
            "version_summary": {
                "active_version": next_version if payload.stage == "active" else version,
                "draft_version": next_version if payload.stage == "draft" else workflow_stage_map.get("draft", {}).get("version"),
                "staging_version": next_version if payload.stage == "staging" else workflow_stage_map.get("staging", {}).get("version"),
                "stage": payload.stage,
                "will_mutate": True,
                "requires_publish": payload.stage != "active",
            },
            "stage_record": stage_record,
            "config": data["payload"],
        }
    )


@router.post("/workflows/{workflow_name}/template/promote", response_model=ProjectCustomizationDictEnvelope)
def promote_workflow_template_stage(request: Request, workflow_name: str, payload: WorkflowTemplatePromotePayload):
    effective_project_key = (payload.project_key or "").strip()
    if not effective_project_key:
        _raise_project_key_required()
    normalized_workflow_name = workflow_name.strip()
    if not normalized_workflow_name:
        _raise_invalid_input(
            "workflow_name is required.",
            details={"field": "workflow_name", "value": workflow_name},
        )
    if payload.from_stage == payload.to_stage:
        _raise_invalid_input(
            "from_stage and to_stage must be different.",
            details={"from_stage": payload.from_stage, "to_stage": payload.to_stage},
        )

    existing_payload, workflows, boards, version, stages, history = _read_workflow_platform_payload(effective_project_key)
    workflow_stage_map = dict(stages.get(normalized_workflow_name) or {})
    source_record = workflow_stage_map.get(payload.from_stage)
    if not isinstance(source_record, dict):
        _raise_not_found(
            f"workflow {payload.from_stage} stage not found: {normalized_workflow_name}",
            details={"workflow_name": normalized_workflow_name, "stage": payload.from_stage},
        )
    steps = source_record.get("steps") if isinstance(source_record.get("steps"), list) else []
    board_layout = source_record.get("board_layout") if isinstance(source_record.get("board_layout"), dict) else {}
    next_version = version + 1
    audit_identity = _resolve_audit_identity(request, actor=payload.actor, requested_by=payload.requested_by)
    audit = _build_stage_audit_event(
        action="promote_stage",
        version=next_version,
        actor=audit_identity["actor"],
        requested_by=audit_identity["requested_by"],
        applied_by=audit_identity["applied_by"],
        from_stage=payload.from_stage,
        to_stage=payload.to_stage,
        trace_id=payload.trace_id,
        identity_source=audit_identity["identity_source"],
        actor_trusted=audit_identity["actor_trusted"],
        actor_auth_mode=audit_identity["actor_auth_mode"],
        legacy_actor_id=audit_identity["legacy_actor_id"],
    )
    promoted_record = _build_workflow_stage_record(
        stage=payload.to_stage,
        version=next_version,
        steps=steps,
        board_layout=board_layout,
        promoted_from=payload.from_stage,
        audit=audit,
    )
    audit["stage_snapshot"] = promoted_record
    workflow_stage_map[payload.to_stage] = promoted_record
    stages[normalized_workflow_name] = workflow_stage_map
    history = _append_workflow_stage_history(history, normalized_workflow_name, audit)
    visible_history = _visible_stage_history(history.get(normalized_workflow_name, []))
    governance = _build_workflow_governance(
        project_key=effective_project_key,
        workflow_name=normalized_workflow_name,
        operation="publish" if payload.to_stage == "active" else "stage",
        stage=payload.to_stage,
        dry_run=False,
        will_mutate=True,
        requires_publish=payload.to_stage != "active",
        current_version=version,
        next_version=next_version,
        target_stage=payload.to_stage,
        target_version=next_version,
        audit=audit,
        snapshot=promoted_record,
        history=visible_history,
    )
    if payload.to_stage == "active":
        workflows[normalized_workflow_name] = {"steps": steps}
        boards[normalized_workflow_name] = board_layout

    data = upsert_config(
        project_key=effective_project_key,
        config_key=WORKFLOW_PLATFORM_CONFIG_KEY,
        config_type=WORKFLOW_PLATFORM_CONFIG_KEY,
        payload={
            **existing_payload,
            "version": next_version,
            "workflows": workflows,
            "boards": boards,
            "workflow_stages": stages,
            "workflow_stage_history": history,
        },
    )
    return success_response(
        {
            "project_key": data["project_key"],
            "workflow_name": normalized_workflow_name,
            "promoted": True,
            "from_stage": payload.from_stage,
            "to_stage": payload.to_stage,
            "config_key": WORKFLOW_PLATFORM_CONFIG_KEY,
            "current_version": version,
            "next_version": next_version,
            "governance": governance,
            "audit": _audit_without_snapshot(audit),
            "history": visible_history,
            "version_summary": {
                "active_version": next_version if payload.to_stage == "active" else version,
                "draft_version": workflow_stage_map.get("draft", {}).get("version"),
                "staging_version": next_version if payload.to_stage == "staging" else workflow_stage_map.get("staging", {}).get("version"),
                "stage": payload.to_stage,
                "will_mutate": True,
                "requires_publish": payload.to_stage != "active",
            },
            "stage_record": promoted_record,
            "config": data["payload"],
        }
    )


@router.post("/workflows/{workflow_name}/template/rollback/preview", response_model=ProjectCustomizationDictEnvelope)
def preview_workflow_template_rollback(request: Request, workflow_name: str, payload: WorkflowTemplateRollbackPreviewPayload):
    effective_project_key = (payload.project_key or "").strip()
    if not effective_project_key:
        _raise_project_key_required()
    normalized_workflow_name = workflow_name.strip()
    if not normalized_workflow_name:
        _raise_invalid_input(
            "workflow_name is required.",
            details={"field": "workflow_name", "value": workflow_name},
        )

    _, workflows, boards, version, stages, history = _read_workflow_platform_payload(effective_project_key)
    workflow_stage_map = dict(stages.get(normalized_workflow_name) or {})
    if normalized_workflow_name in workflows and "active" not in workflow_stage_map:
        workflow_stage_map["active"] = _build_workflow_stage_record(
            stage="active",
            version=version,
            steps=workflows[normalized_workflow_name].get("steps")
            if isinstance(workflows.get(normalized_workflow_name), dict)
            and isinstance(workflows[normalized_workflow_name].get("steps"), list)
            else [],
            board_layout=boards.get(normalized_workflow_name) if isinstance(boards.get(normalized_workflow_name), dict) else {},
        )
    workflow_history = history.get(normalized_workflow_name, [])
    target_snapshot = _find_stage_snapshot_by_version(
        workflow_stages=workflow_stage_map,
        history=workflow_history,
        target_stage=payload.target_stage,
        target_version=payload.target_version,
    )
    audit_identity = _resolve_audit_identity(request, actor=payload.actor, requested_by=payload.requested_by)
    audit = _build_stage_audit_event(
        action="rollback_preview",
        version=version,
        actor=audit_identity["actor"],
        requested_by=audit_identity["requested_by"],
        applied_by=audit_identity["applied_by"],
        from_stage="active",
        to_stage=payload.target_stage,
        trace_id=payload.trace_id,
        identity_source=audit_identity["identity_source"],
        actor_trusted=audit_identity["actor_trusted"],
        actor_auth_mode=audit_identity["actor_auth_mode"],
        legacy_actor_id=audit_identity["legacy_actor_id"],
    )
    can_execute = isinstance(target_snapshot, dict)
    rollback_reason = str(payload.reason or "").strip() or "rollback preview requested"
    audit["reason"] = rollback_reason
    audit["operator"] = _governance_operator_from_audit(audit)
    audit["target"] = {
        "object_type": WORKFLOW_GOVERNANCE_OBJECT_TYPE,
        "object_id": _workflow_governance_object_id(effective_project_key, normalized_workflow_name),
        "stage": payload.target_stage,
        "version": payload.target_version or (target_snapshot or {}).get("version"),
    }
    audit["snapshot"] = target_snapshot or {}
    rollback_plan = {
        "mode": "preview_only",
        "can_execute": can_execute,
        "executable": can_execute,
        "will_mutate": False,
        "reason": None if can_execute else "target stage/version snapshot is not available in workflow_stage_history",
        "from_stage": "active",
        "to_stage": payload.target_stage,
        "target_version": payload.target_version or (target_snapshot or {}).get("version"),
        "target_stage_record": target_snapshot,
        "apply_endpoint": f"/api/v1/project-customization/workflows/{normalized_workflow_name}/template/rollback",
        "requires_explicit_apply": True,
    }
    visible_history = _visible_stage_history(workflow_history)
    governance = _build_workflow_governance(
        project_key=effective_project_key,
        workflow_name=normalized_workflow_name,
        operation="rollback",
        stage="rollback_preview",
        dry_run=True,
        will_mutate=False,
        requires_publish=payload.target_stage != "active",
        current_version=version,
        next_version=version + 1 if can_execute else None,
        target_stage=payload.target_stage,
        target_version=rollback_plan["target_version"],
        reason=rollback_reason,
        audit=audit,
        snapshot=target_snapshot if isinstance(target_snapshot, dict) else {},
        history=visible_history,
    )
    return success_response(
        {
            "project_key": effective_project_key,
            "workflow_name": normalized_workflow_name,
            "config_key": WORKFLOW_PLATFORM_CONFIG_KEY,
            "current_version": version,
            "next_version": version + 1 if can_execute else None,
            "governance": governance,
            "rollback_preview": True,
            "audit": _audit_without_snapshot(audit),
            "history": visible_history,
            "rollback_plan": rollback_plan,
            "version_summary": {
                "stage": "rollback_preview",
                "will_mutate": False,
                "requires_publish": payload.target_stage != "active",
                "active_version": workflow_stage_map.get("active", {}).get("version") if "active" in workflow_stage_map else None,
                "staging_version": workflow_stage_map.get("staging", {}).get("version"),
                "draft_version": workflow_stage_map.get("draft", {}).get("version"),
                "target_version": rollback_plan["target_version"],
            },
        }
    )


@router.post("/workflows/{workflow_name}/template/rollback", response_model=ProjectCustomizationDictEnvelope)
def apply_workflow_template_rollback(request: Request, workflow_name: str, payload: WorkflowTemplateRollbackPreviewPayload):
    effective_project_key = (payload.project_key or "").strip()
    if not effective_project_key:
        _raise_project_key_required()
    normalized_workflow_name = workflow_name.strip()
    if not normalized_workflow_name:
        _raise_invalid_input(
            "workflow_name is required.",
            details={"field": "workflow_name", "value": workflow_name},
        )

    existing_payload, workflows, boards, version, stages, history = _read_workflow_platform_payload(effective_project_key)
    workflow_stage_map = dict(stages.get(normalized_workflow_name) or {})
    if normalized_workflow_name in workflows and "active" not in workflow_stage_map:
        workflow_stage_map["active"] = _build_workflow_stage_record(
            stage="active",
            version=version,
            steps=workflows[normalized_workflow_name].get("steps")
            if isinstance(workflows.get(normalized_workflow_name), dict)
            and isinstance(workflows[normalized_workflow_name].get("steps"), list)
            else [],
            board_layout=boards.get(normalized_workflow_name) if isinstance(boards.get(normalized_workflow_name), dict) else {},
        )
    workflow_history = history.get(normalized_workflow_name, [])
    target_snapshot = _find_stage_snapshot_by_version(
        workflow_stages=workflow_stage_map,
        history=workflow_history,
        target_stage=payload.target_stage,
        target_version=payload.target_version,
    )
    if not isinstance(target_snapshot, dict):
        _raise_not_found(
            "target stage/version snapshot is not available in workflow_stage_history",
            details={
                "workflow_name": normalized_workflow_name,
                "target_stage": payload.target_stage,
                "target_version": payload.target_version,
            },
        )

    steps = target_snapshot.get("steps") if isinstance(target_snapshot.get("steps"), list) else []
    board_layout = target_snapshot.get("board_layout") if isinstance(target_snapshot.get("board_layout"), dict) else {}
    source_stage_record = workflow_stage_map.get(payload.target_stage)
    source_version = source_stage_record.get("version") if isinstance(source_stage_record, dict) else None
    source_version = source_version if isinstance(source_version, int) else version
    restored_target_version = target_snapshot.get("version")
    next_version = version + 1
    audit_identity = _resolve_audit_identity(request, actor=payload.actor, requested_by=payload.requested_by)
    audit = _build_stage_audit_event(
        action="rollback_apply",
        version=next_version,
        actor=audit_identity["actor"],
        requested_by=audit_identity["requested_by"],
        applied_by=audit_identity["applied_by"],
        from_stage=payload.target_stage,
        to_stage=payload.target_stage,
        from_version=source_version,
        to_version=next_version,
        target_version=restored_target_version if isinstance(restored_target_version, int) else payload.target_version,
        trace_id=payload.trace_id,
        identity_source=audit_identity["identity_source"],
        actor_trusted=audit_identity["actor_trusted"],
        actor_auth_mode=audit_identity["actor_auth_mode"],
        legacy_actor_id=audit_identity["legacy_actor_id"],
    )
    rollback_reason = str(payload.reason or "").strip() or "rollback applied"
    rollback_record = _build_workflow_stage_record(
        stage=payload.target_stage,
        version=next_version,
        steps=steps,
        board_layout=board_layout,
        promoted_from=f"rollback:{payload.target_stage}",
        audit=audit,
    )
    rollback_record["rolled_back_from_version"] = source_version
    rollback_record["target_version"] = restored_target_version if isinstance(restored_target_version, int) else payload.target_version
    rollback_record["rollback_reason"] = rollback_reason
    audit["reason"] = rollback_reason
    audit["operator"] = _governance_operator_from_audit(audit)
    audit["target"] = {
        "object_type": WORKFLOW_GOVERNANCE_OBJECT_TYPE,
        "object_id": _workflow_governance_object_id(effective_project_key, normalized_workflow_name),
        "stage": payload.target_stage,
        "version": rollback_record["target_version"],
    }
    audit["snapshot"] = target_snapshot
    audit["stage_snapshot"] = rollback_record
    workflow_stage_map[payload.target_stage] = rollback_record
    stages[normalized_workflow_name] = workflow_stage_map
    history = _append_workflow_stage_history(history, normalized_workflow_name, audit)
    visible_history = _visible_stage_history(history.get(normalized_workflow_name, []))
    if payload.target_stage == "active":
        workflows[normalized_workflow_name] = {"steps": steps}
        boards[normalized_workflow_name] = board_layout

    rollback_plan = {
        "mode": "apply",
        "can_execute": True,
        "executable": True,
        "will_mutate": True,
        "reason": None,
        "from_stage": payload.target_stage,
        "to_stage": payload.target_stage,
        "from_version": source_version,
        "to_version": next_version,
        "target_version": rollback_record["target_version"],
        "target_stage_record": target_snapshot,
        "applied_stage_record": rollback_record,
        "requires_explicit_apply": False,
    }
    governance = _build_workflow_governance(
        project_key=effective_project_key,
        workflow_name=normalized_workflow_name,
        operation="rollback",
        stage=payload.target_stage,
        dry_run=False,
        will_mutate=True,
        requires_publish=payload.target_stage != "active",
        current_version=version,
        next_version=next_version,
        target_stage=payload.target_stage,
        target_version=rollback_record["target_version"],
        reason=rollback_reason,
        audit=audit,
        snapshot=target_snapshot,
        history=visible_history,
    )
    data = upsert_config(
        project_key=effective_project_key,
        config_key=WORKFLOW_PLATFORM_CONFIG_KEY,
        config_type=WORKFLOW_PLATFORM_CONFIG_KEY,
        payload={
            **existing_payload,
            "version": next_version,
            "workflows": workflows,
            "boards": boards,
            "workflow_stages": stages,
            "workflow_stage_history": history,
        },
    )
    return success_response(
        {
            "project_key": data["project_key"],
            "workflow_name": normalized_workflow_name,
            "config_key": WORKFLOW_PLATFORM_CONFIG_KEY,
            "current_version": version,
            "next_version": next_version,
            "governance": governance,
            "rollback_applied": True,
            "from_stage": payload.target_stage,
            "to_stage": payload.target_stage,
            "audit": _audit_without_snapshot(audit),
            "history": visible_history,
            "rollback_plan": rollback_plan,
            "version_summary": {
                "stage": payload.target_stage,
                "will_mutate": True,
                "requires_publish": payload.target_stage != "active",
                "active_version": next_version if payload.target_stage == "active" else workflow_stage_map.get("active", {}).get("version"),
                "staging_version": next_version if payload.target_stage == "staging" else workflow_stage_map.get("staging", {}).get("version"),
                "draft_version": workflow_stage_map.get("draft", {}).get("version"),
                "from_version": source_version,
                "to_version": next_version,
                "target_version": rollback_record["target_version"],
            },
            "stage_record": rollback_record,
            "config": data["payload"],
        }
    )


@router.post("/workflows/{workflow_name}/template", response_model=ProjectCustomizationDictEnvelope)
def upsert_workflow_template(workflow_name: str, payload: WorkflowTemplatePayload):
    effective_project_key, normalized_workflow_name = _validate_workflow_template_payload(workflow_name, payload)

    existing_payload, workflows, boards, version, stages, history = _read_workflow_platform_payload(effective_project_key)

    serialized_steps = _serialize_workflow_steps(payload.steps)

    workflows[normalized_workflow_name] = {
        "steps": [
            x for x in serialized_steps
        ],
    }
    boards[normalized_workflow_name] = _normalize_board_layout(payload.board_layout, serialized_steps)

    next_payload = {
        **existing_payload,
        "version": version + 1,
        "workflows": workflows,
        "boards": boards,
        "workflow_stages": stages,
        "workflow_stage_history": history,
    }
    data = upsert_config(
        project_key=effective_project_key,
        config_key=WORKFLOW_PLATFORM_CONFIG_KEY,
        config_type=WORKFLOW_PLATFORM_CONFIG_KEY,
        payload=next_payload,
    )
    next_version = version + 1

    return success_response(
        {
            "project_key": data["project_key"],
            "workflow_name": normalized_workflow_name,
            "saved": True,
            "config_key": WORKFLOW_PLATFORM_CONFIG_KEY,
            "governance": _build_workflow_governance(
                project_key=effective_project_key,
                workflow_name=normalized_workflow_name,
                operation="publish",
                stage="active",
                dry_run=False,
                will_mutate=True,
                requires_publish=False,
                current_version=version,
                next_version=next_version,
                target_stage="active",
                target_version=next_version,
                snapshot={
                    "stage": "active",
                    "version": next_version,
                    "steps": workflows[normalized_workflow_name]["steps"],
                    "board_layout": boards[normalized_workflow_name],
                },
                history=_visible_stage_history(history.get(normalized_workflow_name, [])),
            ),
            "config": data["payload"],
        }
    )


@router.delete("/workflows/{workflow_name}/template", response_model=ProjectCustomizationDictEnvelope)
def delete_workflow_template(workflow_name: str, project_key: str | None = Query(default=None)):
    effective_project_key = (project_key or "").strip() or get_project_customization().project_key
    if not effective_project_key:
        _raise_project_key_required()

    normalized_workflow_name = workflow_name.strip()
    if not normalized_workflow_name:
        _raise_invalid_input(
            "workflow_name is required.",
            details={"field": "workflow_name", "value": workflow_name},
        )

    record = get_config(effective_project_key, WORKFLOW_PLATFORM_CONFIG_KEY) or {}
    existing_payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    workflows, boards, version = _coerce_workflow_payload(existing_payload)
    if normalized_workflow_name not in workflows:
        _raise_not_found(
            f"custom workflow not found: {normalized_workflow_name}",
            details={"workflow_name": normalized_workflow_name},
        )

    workflows.pop(normalized_workflow_name, None)
    boards.pop(normalized_workflow_name, None)

    data = upsert_config(
        project_key=effective_project_key,
        config_key=WORKFLOW_PLATFORM_CONFIG_KEY,
        config_type=WORKFLOW_PLATFORM_CONFIG_KEY,
        payload={"version": version + 1, "workflows": workflows, "boards": boards},
    )

    return success_response(
        {
            "project_key": data["project_key"],
            "workflow_name": normalized_workflow_name,
            "deleted": True,
            "config_key": WORKFLOW_PLATFORM_CONFIG_KEY,
            "config": data["payload"],
        }
    )


@router.get("/llm-mapping", response_model=ProjectCustomizationDictEnvelope)
def get_llm_mapping(project_key: str | None = Query(default=None)):
    customization = get_project_customization(project_key)
    return success_response(
        {
            "project_key": customization.project_key,
            "llm_mapping": customization.get_llm_mapping(),
        }
    )


@router.get("/graph-config", response_model=ProjectCustomizationDictEnvelope)
def get_graph_config(project_key: str | None = Query(default=None)):
    customization = get_project_customization(project_key)
    return success_response(
        {
            "project_key": customization.project_key,
            "graph_doc_types": resolve_graph_doc_types(customization.project_key),
            "graph_type_labels": resolve_graph_type_labels(customization.project_key),
            "graph_node_types": resolve_graph_node_types(customization.project_key),
            "graph_node_labels": resolve_graph_node_labels(customization.project_key),
            "graph_field_labels": resolve_graph_field_labels(customization.project_key),
            "graph_edge_types": resolve_graph_edge_types(customization.project_key),
            "graph_relation_labels": resolve_graph_relation_labels(customization.project_key),
            "graph_edge_style_bindings": resolve_graph_edge_style_bindings(customization.project_key),
            "graph_projections": resolve_graph_projections(customization.project_key),
            "graph_topic_scope_entities": resolve_graph_topic_scope_entities(customization.project_key),
        }
    )


@router.post("/workflows/{workflow_name}/run", response_model=ProjectCustomizationDictEnvelope)
def run_workflow(workflow_name: str, payload: WorkflowRunPayload, dry_run: bool | None = Query(default=None)):
    try:
        project_key = (payload.project_key or "").strip()
        if not project_key:
            _raise_project_key_required()
        should_dry_run = bool(payload.dry_run if dry_run is None else dry_run)
        if should_dry_run:
            return success_response(
                _build_workflow_dry_run_result(
                    workflow_name=workflow_name,
                    params=payload.params or {},
                    project_key=project_key,
                )
            )
        result = execute_project_workflow(
            workflow_name=workflow_name,
            params=payload.params or {},
            project_key=project_key,
        )
        return success_response(result)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, ValueError):
            raise HTTPException(
                status_code=400,
                detail=error_response(
                    ErrorCode.INVALID_INPUT,
                    str(exc) or "Invalid workflow input.",
                    details={"exception_type": exc.__class__.__name__},
                ),
            ) from exc
        code, message, details = map_exception_to_error(exc)
        raise HTTPException(
            status_code=_status_code_for_error_code(code),
            detail=error_response(code, message, details=details),
        ) from exc
