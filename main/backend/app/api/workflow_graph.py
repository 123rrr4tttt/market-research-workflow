from __future__ import annotations

from importlib import import_module
from typing import Any

from fastapi import APIRouter
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


def _invoke_get_compiled(graph_id: str) -> Any:
    compiler, _ = _load_workflow_graph_services()
    return _call_first(compiler, ("get_compiled", "get_graph", "fetch_compiled"), graph_id)


@router.post("/compile", response_model=None)
def compile_workflow_graph(payload: dict[str, Any]) -> Any:
    try:
        return success_response(_invoke_compile(payload))
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "compiled graph not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.post("/run", response_model=None)
def run_workflow_graph(payload: dict[str, Any]) -> Any:
    try:
        return success_response(_invoke_run(payload))
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "run not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.get("/runs/{run_id}", response_model=None)
def get_workflow_graph_run(run_id: str) -> Any:
    try:
        return success_response(_invoke_get_run(run_id))
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "run not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.get("/runs/{run_id}/events", response_model=None)
def get_workflow_graph_run_events(run_id: str) -> Any:
    try:
        return success_response(_invoke_get_run_events(run_id))
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "run not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)


@router.get("/compiled/{graph_id}", response_model=None)
def get_workflow_graph_compiled(graph_id: str) -> Any:
    try:
        return success_response(_invoke_get_compiled(graph_id))
    except KeyError as exc:
        return _error_json(ErrorCode.NOT_FOUND, str(exc) or "compiled graph not found")
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(code, message, details)
