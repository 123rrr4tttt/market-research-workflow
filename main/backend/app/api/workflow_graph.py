from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from ..contracts import ApiEnvelope, ErrorCode, error_response, map_exception_to_error, success_response
from ..contracts.schemas.workflow_graph import (
    WorkflowGraphAuditListData,
    WorkflowGraphCuratedStateData,
    WorkflowGraphEvidencePackData,
    WorkflowGraphHandoffData,
    WorkflowGraphHandoffListData,
    WorkflowGraphHandoffReplayData,
)
from ..services.skill_runtime import invoke_skill
from ..services.workflow_graph.curated_service import WorkflowGraphObjectMissingError, WorkflowGraphSyncConflictError
from ..services.workflow_graph.handoff_store import handoff_store
from ..services.workflow_graph.observability import query_top_failure_reasons


router = APIRouter(prefix="/workflow-graph", tags=["workflow-graph"])
WorkflowGraphDynamicEnvelope = ApiEnvelope[dict[str, Any]]


def _error_status_code(code: ErrorCode) -> int:
    mapping = {
        ErrorCode.INVALID_INPUT: 400,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.CONFIG_ERROR: 500,
        ErrorCode.UPSTREAM_ERROR: 502,
        ErrorCode.PARSE_ERROR: 502,
        ErrorCode.RATE_LIMITED: 429,
        ErrorCode.INTERNAL_ERROR: 500,
    }
    return mapping.get(code, 500)


def _error_json(code: ErrorCode, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    payload = error_response(code, message, details=details)
    payload["detail"] = {"error": payload["error"], "message": payload["error"]["message"]}
    return JSONResponse(
        status_code=_error_status_code(code),
        content=payload,
        headers={"X-Error-Code": code.value},
    )


def _skill_context(*, operation: str, actor_role: str = "orchestration_runtime") -> dict[str, Any]:
    return {
        "actor_role": actor_role,
        "permissions": [operation],
        "trace_id": f"workflow-graph.{operation}",
        "consumer": "workflow_graph.api",
    }


def _invoke_compile(payload: dict[str, Any]) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.compile",
        payload=payload,
        context=_skill_context(operation="workflow_graph.compile"),
    ).get("result")


def _invoke_run(payload: dict[str, Any]) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.run",
        payload=payload,
        context=_skill_context(operation="workflow_graph.run"),
    ).get("result")


def _invoke_get_run(run_id: str) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.get_run",
        args=(run_id,),
        context=_skill_context(
            operation="workflow_graph.read",
            actor_role="business_capability_wrapper",
        ),
    ).get("result")


def _invoke_get_run_events(run_id: str) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.get_run_events",
        args=(run_id,),
        context=_skill_context(
            operation="workflow_graph.read",
            actor_role="business_capability_wrapper",
        ),
    ).get("result")


def _invoke_replay_run(run_id: str, replay_mode: str = "events_only") -> Any:
    return invoke_skill(
        skill_id="workflow_graph.replay_run",
        args=(run_id,),
        kwargs={"replay_mode": replay_mode},
        context=_skill_context(
            operation="workflow_graph.read",
            actor_role="business_capability_wrapper",
        ),
    ).get("result")


def _invoke_get_run_agent_session(run_id: str) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.get_run_agent_session",
        args=(run_id,),
        context=_skill_context(
            operation="workflow_graph.read",
            actor_role="business_capability_wrapper",
        ),
    ).get("result")


def _invoke_get_compiled(graph_id: str) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.get_compiled",
        args=(graph_id,),
        context=_skill_context(
            operation="workflow_graph.read",
            actor_role="business_capability_wrapper",
        ),
    ).get("result")


def _invoke_list_templates() -> Any:
    return invoke_skill(
        skill_id="workflow_graph.template.list",
        context=_skill_context(operation="workflow_graph.template"),
    ).get("result")


def _invoke_create_template(payload: dict[str, Any]) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.template.create",
        payload=payload,
        context=_skill_context(operation="workflow_graph.template"),
    ).get("result")


def _invoke_get_template(template_id: str) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.template.get",
        args=(template_id,),
        context=_skill_context(operation="workflow_graph.template"),
    ).get("result")


def _invoke_patch_template(template_id: str, payload: dict[str, Any]) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.template.patch",
        args=(template_id, payload),
        context=_skill_context(operation="workflow_graph.template"),
    ).get("result")


def _invoke_delete_template(template_id: str, payload: dict[str, Any]) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.template.delete",
        args=(template_id, payload),
        context=_skill_context(operation="workflow_graph.template"),
    ).get("result")


def _invoke_list_template_versions(template_id: str) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.template.version.list",
        args=(template_id,),
        context=_skill_context(operation="workflow_graph.template"),
    ).get("result")


def _invoke_create_template_version(template_id: str, payload: dict[str, Any]) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.template.version.create",
        args=(template_id, payload),
        context=_skill_context(operation="workflow_graph.template"),
    ).get("result")


def _invoke_get_template_version(template_id: str, version_id: str) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.template.version.get",
        args=(template_id, version_id),
        context=_skill_context(operation="workflow_graph.template"),
    ).get("result")


def _invoke_activate_template_version(template_id: str, version_id: str, payload: dict[str, Any]) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.template.version.activate",
        args=(template_id, version_id, payload),
        context=_skill_context(operation="workflow_graph.template"),
    ).get("result")


def _invoke_get_curated_graph(graph_id: str) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.curated.get",
        args=(graph_id,),
        context=_skill_context(operation="workflow_graph.curated"),
    ).get("result")


def _invoke_save_curated_draft(graph_id: str, payload: dict[str, Any]) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.curated.save_draft",
        args=(graph_id, payload),
        context=_skill_context(operation="workflow_graph.curated"),
    ).get("result")


def _invoke_submit_curated_draft(graph_id: str, payload: dict[str, Any]) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.curated.submit",
        args=(graph_id, payload),
        context=_skill_context(operation="workflow_graph.curated"),
    ).get("result")


def _invoke_sync_curated_graph(graph_id: str, payload: dict[str, Any]) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.curated.sync",
        args=(graph_id, payload),
        context=_skill_context(operation="workflow_graph.curated"),
    ).get("result")


def _invoke_rollback_curated_graph(graph_id: str, payload: dict[str, Any]) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.curated.rollback",
        args=(graph_id, payload),
        context=_skill_context(operation="workflow_graph.curated"),
    ).get("result")


def _invoke_list_curated_audits(graph_id: str, limit: int) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.curated.list_audits",
        args=(graph_id,),
        kwargs={"limit": limit},
        context=_skill_context(operation="workflow_graph.curated"),
    ).get("result")


def _invoke_build_evidence_pack(graph_id: str, payload: dict[str, Any]) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.curated.evidence_pack",
        args=(graph_id, payload),
        context=_skill_context(operation="workflow_graph.curated"),
    ).get("result")


def _invoke_reporting_handoff(graph_id: str, payload: dict[str, Any]) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.curated.handoff.reporting",
        args=(graph_id, payload),
        context=_skill_context(operation="workflow_graph.handoff"),
    ).get("result")


def _invoke_writing_handoff(graph_id: str, payload: dict[str, Any]) -> Any:
    return invoke_skill(
        skill_id="workflow_graph.curated.handoff.writing",
        args=(graph_id, payload),
        context=_skill_context(operation="workflow_graph.handoff"),
    ).get("result")


def _ok_workflow_graph(payload: dict[str, Any]) -> dict[str, Any]:
    return success_response(payload, meta={"deprecated": "workflow_graph.contract.v2"})


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_compile(value: Any) -> dict[str, Any]:
    data = _as_dict(value)
    normalized = {
        "graph_id": data.get("graph_id"),
        "version": data.get("version"),
        "checksum": data.get("checksum"),
        "topo_order": data.get("topo_order") or [],
        "warnings": data.get("warnings") or [],
        "contract_version": "workflow_graph.v2",
    }
    if data.get("template_id") is not None:
        normalized["template_id"] = data.get("template_id")
    if data.get("version_id") is not None:
        normalized["version_id"] = data.get("version_id")
    return normalized


def _normalize_run(value: Any) -> dict[str, Any]:
    data = _as_dict(value)
    node_statuses = data.get("node_statuses") if isinstance(data.get("node_statuses"), dict) else {}
    normalized = {
        "run_id": data.get("run_id"),
        "status": data.get("status"),
        "node_statuses": node_statuses,
        "nodes": node_statuses,
        "contract_version": "workflow_graph.v2",
    }
    for field in ("session_id", "current_phase", "root_task_id", "compat_mode"):
        if field in data:
            normalized[field] = data.get(field)
    return normalized


def _normalize_run_detail(value: Any) -> dict[str, Any]:
    data = _as_dict(value)
    node_statuses = data.get("node_statuses") if isinstance(data.get("node_statuses"), dict) else {}
    return {
        **data,
        "node_statuses": node_statuses,
        "nodes": node_statuses,
        "contract_version": "workflow_graph.v2",
    }


def _normalize_run_events(value: Any) -> dict[str, Any]:
    data = _as_dict(value)
    items = data.get("items") if isinstance(data.get("items"), list) else []
    normalized = {
        "items": items,
        "total": len(items),
        "contract_version": "workflow_graph.v2",
    }
    if data.get("session_id") is not None:
        normalized["session_id"] = data.get("session_id")
    return normalized


def _workflow_sync_error_json(exc: Exception, *, fallback_message: str) -> JSONResponse:
    if isinstance(exc, WorkflowGraphSyncConflictError):
        return _error_json(
            ErrorCode.INVALID_INPUT,
            str(exc) or fallback_message,
            details=exc.to_details(),
        )
    if isinstance(exc, WorkflowGraphObjectMissingError):
        return _error_json(
            ErrorCode.NOT_FOUND,
            str(exc) or "graph object missing",
            details={"category": "object_missing"},
        )
    if isinstance(exc, ValueError):
        return _error_json(
            ErrorCode.INVALID_INPUT,
            str(exc) or fallback_message,
            details={"category": "validation_failure"},
        )
    code, message, details = map_exception_to_error(exc)
    return _error_json(code, message, details)


@router.post("/compile", response_model=WorkflowGraphDynamicEnvelope)
def compile_workflow_graph(payload: dict[str, Any]) -> Any:
    try:
        return _ok_workflow_graph(_normalize_compile(_invoke_compile(payload)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "compiled graph not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.post("/run", response_model=WorkflowGraphDynamicEnvelope)
def run_workflow_graph(payload: dict[str, Any]) -> Any:
    try:
        return _ok_workflow_graph(_normalize_run(_invoke_run(payload)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "run not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.get("/runs/{run_id}", response_model=WorkflowGraphDynamicEnvelope)
def get_workflow_graph_run(run_id: str) -> Any:
    try:
        return _ok_workflow_graph(_normalize_run_detail(_invoke_get_run(run_id)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "run not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.get("/runs/{run_id}/events", response_model=WorkflowGraphDynamicEnvelope)
def get_workflow_graph_run_events(run_id: str) -> Any:
    try:
        return _ok_workflow_graph(_normalize_run_events(_invoke_get_run_events(run_id)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "run not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.get("/runs/{run_id}/agent-session", response_model=WorkflowGraphDynamicEnvelope)
def get_workflow_graph_run_agent_session(run_id: str) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_get_run_agent_session(run_id)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "run agent session not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.get("/compiled/{graph_id}", response_model=WorkflowGraphDynamicEnvelope)
def get_workflow_graph_compiled(graph_id: str) -> Any:
    try:
        return _ok_workflow_graph(_normalize_compile(_invoke_get_compiled(graph_id)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "compiled graph not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.get("/runs/{run_id}/replay", response_model=WorkflowGraphDynamicEnvelope)
def replay_workflow_graph_run(run_id: str, replay_mode: str = "events_only") -> Any:
    try:
        return _ok_workflow_graph(_normalize_run_detail(_invoke_replay_run(run_id, replay_mode)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "run not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.get("/templates", response_model=WorkflowGraphDynamicEnvelope)
def list_workflow_graph_templates() -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_list_templates()))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.post("/templates", response_model=WorkflowGraphDynamicEnvelope)
def create_workflow_graph_template(payload: dict[str, Any]) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_create_template(payload)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "template not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.get("/templates/{template_id}", response_model=WorkflowGraphDynamicEnvelope)
def get_workflow_graph_template(template_id: str) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_get_template(template_id)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "template not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.patch("/templates/{template_id}", response_model=WorkflowGraphDynamicEnvelope)
def patch_workflow_graph_template(template_id: str, payload: dict[str, Any]) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_patch_template(template_id, payload)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "template not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.delete("/templates/{template_id}", response_model=WorkflowGraphDynamicEnvelope)
def delete_workflow_graph_template(template_id: str, payload: dict[str, Any] | None = Body(default=None)) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_delete_template(template_id, payload or {})))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "template not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.get("/templates/{template_id}/versions", response_model=WorkflowGraphDynamicEnvelope)
def list_workflow_graph_template_versions(template_id: str) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_list_template_versions(template_id)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "template not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.post("/templates/{template_id}/versions", response_model=WorkflowGraphDynamicEnvelope)
def create_workflow_graph_template_version(template_id: str, payload: dict[str, Any]) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_create_template_version(template_id, payload)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "template/version not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.get("/templates/{template_id}/versions/{version_id}", response_model=WorkflowGraphDynamicEnvelope)
def get_workflow_graph_template_version(template_id: str, version_id: str) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_get_template_version(template_id, version_id)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "template/version not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.post("/templates/{template_id}/versions/{version_id}/activate", response_model=WorkflowGraphDynamicEnvelope)
def activate_workflow_graph_template_version(
    template_id: str,
    version_id: str,
    payload: dict[str, Any] | None = Body(default=None),
) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_activate_template_version(template_id, version_id, payload or {})))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "template/version not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.get(
    "/curated/{graph_id}",
    response_model=ApiEnvelope[WorkflowGraphCuratedStateData],
    response_model_exclude_unset=True,
)
def get_workflow_graph_curated_state(graph_id: str) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_get_curated_graph(graph_id)))
    except Exception as exc:  # noqa: BLE001
        return _workflow_sync_error_json(exc, fallback_message="failed to fetch curated graph")


@router.post(
    "/curated/{graph_id}/draft",
    response_model=ApiEnvelope[WorkflowGraphCuratedStateData],
    response_model_exclude_unset=True,
)
def save_workflow_graph_curated_draft(graph_id: str, payload: dict[str, Any]) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_save_curated_draft(graph_id, payload)))
    except Exception as exc:  # noqa: BLE001
        return _workflow_sync_error_json(exc, fallback_message="failed to save draft")


@router.post(
    "/curated/{graph_id}/submit",
    response_model=ApiEnvelope[WorkflowGraphCuratedStateData],
    response_model_exclude_unset=True,
)
def submit_workflow_graph_curated_draft(graph_id: str, payload: dict[str, Any] | None = Body(default=None)) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_submit_curated_draft(graph_id, payload or {})))
    except Exception as exc:  # noqa: BLE001
        return _workflow_sync_error_json(exc, fallback_message="failed to submit draft")


@router.post(
    "/curated/{graph_id}/sync",
    response_model=ApiEnvelope[WorkflowGraphCuratedStateData],
    response_model_exclude_unset=True,
)
def sync_workflow_graph_curated_state(graph_id: str, payload: dict[str, Any] | None = Body(default=None)) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_sync_curated_graph(graph_id, payload or {})))
    except Exception as exc:  # noqa: BLE001
        return _workflow_sync_error_json(exc, fallback_message="failed to sync graph state")


@router.post(
    "/curated/{graph_id}/rollback",
    response_model=ApiEnvelope[WorkflowGraphCuratedStateData],
    response_model_exclude_unset=True,
)
def rollback_workflow_graph_curated_state(graph_id: str, payload: dict[str, Any]) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_rollback_curated_graph(graph_id, payload)))
    except Exception as exc:  # noqa: BLE001
        return _workflow_sync_error_json(exc, fallback_message="failed to rollback graph state")


@router.get(
    "/curated/{graph_id}/audit",
    response_model=ApiEnvelope[WorkflowGraphAuditListData],
    response_model_exclude_unset=True,
)
def list_workflow_graph_curated_audits(graph_id: str, limit: int = 50) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_list_curated_audits(graph_id, limit)))
    except Exception as exc:  # noqa: BLE001
        return _workflow_sync_error_json(exc, fallback_message="failed to list audits")


@router.post(
    "/curated/{graph_id}/evidence-pack",
    response_model=ApiEnvelope[WorkflowGraphEvidencePackData],
    response_model_exclude_unset=True,
)
def build_workflow_graph_evidence_pack(graph_id: str, payload: dict[str, Any] | None = Body(default=None)) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_build_evidence_pack(graph_id, payload or {})))
    except Exception as exc:  # noqa: BLE001
        return _workflow_sync_error_json(exc, fallback_message="failed to build evidence pack")


@router.post(
    "/curated/{graph_id}/handoff/reporting",
    response_model=ApiEnvelope[WorkflowGraphHandoffData],
    response_model_exclude_unset=True,
)
def build_workflow_graph_reporting_handoff(graph_id: str, payload: dict[str, Any]) -> Any:
    try:
        handoff_payload = _as_dict(_invoke_reporting_handoff(graph_id, payload))
        persist = handoff_store.persist(graph_id=graph_id, payload=handoff_payload)
        handoff_payload["persistence"] = persist
        return _ok_workflow_graph(handoff_payload)
    except Exception as exc:  # noqa: BLE001
        return _workflow_sync_error_json(exc, fallback_message="failed to build reporting handoff")


@router.post(
    "/curated/{graph_id}/handoff/writing",
    response_model=ApiEnvelope[WorkflowGraphHandoffData],
    response_model_exclude_unset=True,
)
def build_workflow_graph_writing_handoff(graph_id: str, payload: dict[str, Any]) -> Any:
    try:
        handoff_payload = _as_dict(_invoke_writing_handoff(graph_id, payload))
        persist = handoff_store.persist(graph_id=graph_id, payload=handoff_payload)
        handoff_payload["persistence"] = persist
        return _ok_workflow_graph(handoff_payload)
    except Exception as exc:  # noqa: BLE001
        return _workflow_sync_error_json(exc, fallback_message="failed to build writing handoff")


@router.get(
    "/runs/{run_id}/handoff",
    response_model=ApiEnvelope[WorkflowGraphHandoffListData],
    response_model_exclude_unset=True,
)
def list_workflow_graph_run_handoffs(run_id: str, handoff_mode: str | None = None) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(handoff_store.list_handoffs(run_id=run_id, handoff_mode=handoff_mode)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "run not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.get(
    "/runs/{run_id}/handoff/{handoff_id}/replay",
    response_model=ApiEnvelope[WorkflowGraphHandoffReplayData],
    response_model_exclude_unset=True,
)
def replay_workflow_graph_handoff(run_id: str, handoff_id: str) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(handoff_store.replay_handoff(run_id=run_id, handoff_id=handoff_id)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "handoff not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.get("/observability/failure-reasons", response_model=WorkflowGraphDynamicEnvelope)
def get_workflow_graph_failure_reasons(limit: int = 20) -> Any:
    try:
        return _ok_workflow_graph(_as_dict(query_top_failure_reasons(limit=limit)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)
