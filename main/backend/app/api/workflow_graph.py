from __future__ import annotations

from importlib import import_module
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from ..contracts import ErrorCode, error_response, map_exception_to_error, success_response


router = APIRouter(prefix="/workflow-graph", tags=["workflow-graph"])


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
    return JSONResponse(
        status_code=_error_status_code(code),
        content=error_response(code, message, details=details),
    )


def _load_workflow_graph_services() -> tuple[Any, Any]:
    module = import_module("app.services.workflow_graph")
    compiler = getattr(module, "compiler", None)
    runtime = getattr(module, "runtime", None)
    if compiler is None or runtime is None:
        raise RuntimeError("services.workflow_graph must define compiler and runtime")
    return compiler, runtime


def _call_first(target: Any, method_names: tuple[str, ...], *args: Any) -> Any:
    for name in method_names:
        method = getattr(target, name, None)
        if callable(method):
            return method(*args)
    raise AttributeError(f"no supported method found: {', '.join(method_names)}")


def _invoke_compile(payload: dict[str, Any]) -> Any:
    compiler, _ = _load_workflow_graph_services()
    return _call_first(compiler, ("compile", "compile_graph"), payload)


def _invoke_run(payload: dict[str, Any]) -> Any:
    _, runtime = _load_workflow_graph_services()
    return _call_first(runtime, ("run", "run_graph", "start_run"), payload)


def _invoke_get_run(run_id: str) -> Any:
    _, runtime = _load_workflow_graph_services()
    return _call_first(runtime, ("get_run", "fetch_run"), run_id)


def _invoke_get_run_events(run_id: str) -> Any:
    _, runtime = _load_workflow_graph_services()
    return _call_first(runtime, ("get_run_events", "list_run_events", "events"), run_id)


def _invoke_replay_run(run_id: str) -> Any:
    _, runtime = _load_workflow_graph_services()
    return _call_first(runtime, ("replay_run", "replay"), run_id)


def _invoke_get_compiled(graph_id: str) -> Any:
    compiler, _ = _load_workflow_graph_services()
    return _call_first(compiler, ("get_compiled", "get_graph", "fetch_compiled"), graph_id)


def _invoke_list_templates() -> Any:
    compiler, _ = _load_workflow_graph_services()
    return _call_first(compiler, ("list_templates",))


def _invoke_create_template(payload: dict[str, Any]) -> Any:
    compiler, _ = _load_workflow_graph_services()
    return _call_first(compiler, ("create_template",), payload)


def _invoke_get_template(template_id: str) -> Any:
    compiler, _ = _load_workflow_graph_services()
    return _call_first(compiler, ("get_template",), template_id)


def _invoke_patch_template(template_id: str, payload: dict[str, Any]) -> Any:
    compiler, _ = _load_workflow_graph_services()
    return _call_first(compiler, ("patch_template",), template_id, payload)


def _invoke_delete_template(template_id: str, payload: dict[str, Any]) -> Any:
    compiler, _ = _load_workflow_graph_services()
    return _call_first(compiler, ("delete_template",), template_id, payload)


def _invoke_list_template_versions(template_id: str) -> Any:
    compiler, _ = _load_workflow_graph_services()
    return _call_first(compiler, ("list_template_versions",), template_id)


def _invoke_create_template_version(template_id: str, payload: dict[str, Any]) -> Any:
    compiler, _ = _load_workflow_graph_services()
    return _call_first(compiler, ("create_template_version",), template_id, payload)


def _invoke_get_template_version(template_id: str, version_id: str) -> Any:
    compiler, _ = _load_workflow_graph_services()
    return _call_first(compiler, ("get_template_version",), template_id, version_id)


def _invoke_activate_template_version(template_id: str, version_id: str, payload: dict[str, Any]) -> Any:
    compiler, _ = _load_workflow_graph_services()
    return _call_first(compiler, ("activate_template_version",), template_id, version_id, payload)


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
    return {
        "run_id": data.get("run_id"),
        "status": data.get("status"),
        "node_statuses": node_statuses,
        "nodes": node_statuses,
        "contract_version": "workflow_graph.v2",
    }


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
    return {
        "items": items,
        "total": len(items),
        "contract_version": "workflow_graph.v2",
    }


@router.post("/compile", response_model=None)
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


@router.post("/run", response_model=None)
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


@router.get("/runs/{run_id}", response_model=None)
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


@router.get("/runs/{run_id}/events", response_model=None)
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


@router.get("/compiled/{graph_id}", response_model=None)
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


@router.get("/runs/{run_id}/replay", response_model=None)
def replay_workflow_graph_run(run_id: str) -> Any:
    try:
        return _ok_workflow_graph(_normalize_run_detail(_invoke_replay_run(run_id)))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "run not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.get("/templates", response_model=None)
def list_workflow_graph_templates() -> Any:
    try:
        return _ok_workflow_graph(_as_dict(_invoke_list_templates()))
    except ValueError as exc:
        return _error_json(ErrorCode.INVALID_INPUT, str(exc) or "invalid input")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.post("/templates", response_model=None)
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


@router.get("/templates/{template_id}", response_model=None)
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


@router.patch("/templates/{template_id}", response_model=None)
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


@router.delete("/templates/{template_id}", response_model=None)
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


@router.get("/templates/{template_id}/versions", response_model=None)
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


@router.post("/templates/{template_id}/versions", response_model=None)
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


@router.get("/templates/{template_id}/versions/{version_id}", response_model=None)
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


@router.post("/templates/{template_id}/versions/{version_id}/activate", response_model=None)
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
