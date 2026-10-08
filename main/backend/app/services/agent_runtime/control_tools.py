from __future__ import annotations
from collections.abc import Mapping, Sequence
from functools import partial
from functorial_kit import Failure
from sqlalchemy.engine import Engine
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_core.contracts import (
    AgentCoreRequest,
    CoreToolCall,
    CoreToolResult,
    CoreToolSpec,
    JSONObject,
    ToolStatus,
)
from app.services.agent_core.tool_contribution import (
    ProjectToolAuthorSource,
    ProjectToolOperation,
    bind_project_tool_operation,
)
from app.services.agent_core.tool_support import (
    compact_json_value,
    concurrency_from_class,
    json_object,
    normalize_string_list,
    permission_from_approval,
    risk_from_metadata,
    safe_int,
)
from .tool_contract import build_tool_definition


def _as_text(value: object) -> str:
    return str(value or "").strip()


def _runtime_engine(runtime_engine: Engine | None) -> Engine:
    if runtime_engine is not None:
        return runtime_engine
    from app.models.base import engine

    return engine


def _control_result(
    call: CoreToolCall, *, status: ToolStatus, summary: str, result: JSONObject, error: JSONObject | None = None
) -> CoreToolResult:
    return CoreToolResult(
        call_id=call.call_id,
        tool_name=call.tool_name,
        status=status,
        model_summary=summary,
        ui_summary=summary,
        structured_content={"result": json_object(compact_json_value(result, max_items=20, max_depth=4))},
        error=error,
    )


def _control_failure(call: CoreToolCall, *, summary: str, session_id: str, failure: Failure) -> CoreToolResult:
    return _control_result(
        call,
        status="failed",
        summary=summary,
        result={"session_id": session_id},
        error={
            "type": "Failure",
            "code": failure.code,
            "message": failure.message,
            "context": json_object(failure.context),
        },
    )


def project_tool_spec(tool_value: Mapping[str, object]) -> CoreToolSpec:
    tool = json_object(tool_value)
    approval_level = str(tool.get("approval_level") or "none").strip()
    concurrency_class = str(tool.get("concurrency_class") or "read_only").strip()
    name = str(tool.get("name") or tool.get("tool_name") or tool.get("capability_id") or "").strip()
    return CoreToolSpec(
        name=name,
        title=str(tool.get("title") or tool.get("name") or name),
        description_for_model=str(tool.get("description") or name),
        input_schema=json_object(tool.get("input_schema") or {"type": "object", "properties": {}}),
        output_schema=json_object(tool.get("output_schema") or {"type": "object", "additionalProperties": True}),
        source="project",
        risk=risk_from_metadata(
            approval_level=approval_level,
            concurrency_class=concurrency_class,
            risks=normalize_string_list(tool.get("risks")),
        ),
        permission=permission_from_approval(approval_level),
        concurrency=concurrency_from_class(concurrency_class),
        timeout_seconds=safe_int(tool.get("timeout_seconds")) or 10,
        result_budget=safe_int(tool.get("result_budget")) or 4000,
        project_service_id=str(tool.get("capability_id") or name),
        metadata={"legacy_tool_definition": dict(tool)},
    )


def project_tool_sources(
    declarations: Sequence[tuple[JSONObject, ProjectToolOperation]],
    *,
    scope_source: str,
    permission_source: str,
    failure_family: str,
    readback_semantics: str,
) -> tuple[ProjectToolAuthorSource, ...]:
    return tuple(
        (
            ProjectToolAuthorSource(
                binding_id=f"facility.{spec.name}",
                version="1",
                tool_spec=spec,
                handler=bind_project_tool_operation(handler),
                executor_ref=spec.name,
                scope_source=scope_source,
                permission_source=permission_source,
                failure_family=failure_family,
                readback_semantics=readback_semantics,
            )
            for definition, handler in declarations
            for spec in (project_tool_spec(definition),)
        )
    )


def task_cancel(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, service: AgentSessionService, engine: Engine | None = None
) -> CoreToolResult:
    session_id = _as_text(tool_call.arguments.get("session_id")) or request.session_id
    try:
        from app.services.agent_core.host_authorization import current_verified_host_authorization

        authorization = current_verified_host_authorization()
        if authorization is None:
            return _control_result(
                tool_call,
                status="failed",
                summary="task cancel requires a verified host authorization",
                result={"session_id": session_id},
                error={
                    "type": "Failure",
                    "code": "host_authorization_missing",
                    "message": "no verified host authorization for task cancel",
                },
            )
        context = authorization.context
        if context.session_id != session_id:
            return _control_result(
                tool_call,
                status="failed",
                summary="trusted host context does not match the cancel target",
                result={"session_id": session_id},
                error={
                    "type": "Failure",
                    "code": "host_context_session_mismatch",
                    "message": "verified host session differs from cancel target",
                },
            )
        session = service.get_session(session_id)
        if isinstance(session, Failure):
            return _control_failure(
                tool_call, summary=f"cancel failed for session {session_id}", session_id=session_id, failure=session
            )
        run_id = _as_text(session.get("compat_job_id"))
        if not run_id:
            return _control_result(
                tool_call,
                status="failed",
                summary="session has no platform run to cancel",
                result={"session_id": session_id},
                error={"type": "Failure", "code": "run_id_missing", "message": "session compat_job_id is absent"},
            )
        actor_context = authorization.actor_context
        if actor_context is None or not actor_context.actor_trusted or (not actor_context.actor_id):
            return _control_result(
                tool_call,
                status="failed",
                summary="task cancel requires an authenticated request actor",
                result={"session_id": session_id},
                error={
                    "type": "Failure",
                    "code": "trusted_actor_missing",
                    "message": "verified host authorization has no authenticated request actor",
                },
            )
        result = service.cancel_run(
            run_id, actor_id=actor_context.actor_id, project_key=context.project_key, engine=_runtime_engine(engine)
        )
        if isinstance(result, Failure):
            return _control_failure(
                tool_call, summary=f"cancel failed for run {run_id}", session_id=session_id, failure=result
            )
        return _control_result(
            tool_call,
            status="completed",
            summary=f"cancel requested for run {run_id}",
            result={"session_id": session_id, "run_id": run_id, "state": result["state"]},
        )
    except Exception as exc:
        return _control_result(
            tool_call,
            status="failed",
            summary=f"cancel failed for session {session_id}: {exc}",
            result={"session_id": session_id},
            error={"type": exc.__class__.__name__, "message": str(exc)},
        )


def task_summary(tool_call: CoreToolCall, request: AgentCoreRequest, *, service: AgentSessionService) -> CoreToolResult:
    session_id = str(tool_call.arguments.get("session_id") or "").strip() or request.session_id
    result: JSONObject = {"session_id": session_id}
    error: JSONObject | None = None
    status: ToolStatus = "failed"
    try:
        summary = service.get_session_summary(session_id)
        if isinstance(summary, Failure):
            message = f"summary failed for session {session_id}"
            error = {
                "type": "Failure",
                "code": summary.code,
                "message": summary.message,
                "context": json_object(summary.context),
            }
        else:
            status = "completed"
            message = f"read session summary {session_id}"
            result["summary"] = json_object(summary)
    except Exception as exc:
        message = f"summary failed for session {session_id}: {exc}"
        error = {"type": exc.__class__.__name__, "message": str(exc)}
    return _control_result(tool_call, status=status, summary=message, result=result, error=error)


def project_tool_declaration(
    *,
    name: str,
    description: str,
    input_schema: JSONObject,
    operation: ProjectToolOperation,
    output_schema: JSONObject | None = None,
    risk_level: str = "low",
    concurrency_class: str = "read_only",
    approval_level: str = "none",
    timeout_seconds: int = 10,
    result_budget: int = 4000,
) -> tuple[JSONObject, ProjectToolOperation]:
    return (
        json_object(
            build_tool_definition(
                name=name,
                description=description,
                input_schema=input_schema,
                output_schema=output_schema,
                risk_level=risk_level,
                concurrency_class=concurrency_class,
                approval_level=approval_level,
                timeout_seconds=timeout_seconds,
                result_budget=result_budget,
            )
        ),
        operation,
    )


def _control_tool_declarations(
    service: AgentSessionService, engine: Engine | None
) -> tuple[tuple[JSONObject, ProjectToolOperation], ...]:
    return (
        project_tool_declaration(
            name="task.cancel",
            description="Request cancellation of the canonical runtime run associated with this session.",
            input_schema={
                "type": "object",
                "properties": {"session_id": {"type": "string"}, "reason": {"type": "string"}},
                "additionalProperties": False,
            },
            output_schema={"type": "object", "additionalProperties": True},
            risk_level="medium",
            concurrency_class="write_shared",
            approval_level="explicit_user_request",
            timeout_seconds=10,
            result_budget=4000,
            operation=partial(task_cancel, service=service, engine=engine),
        ),
        project_tool_declaration(
            name="task.summary",
            description="Read the current session summary without dispatching work or changing task state.",
            input_schema={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "additionalProperties": False,
            },
            output_schema={"type": "object", "additionalProperties": True},
            risk_level="low",
            concurrency_class="read_only",
            approval_level="none",
            timeout_seconds=10,
            result_budget=4000,
            operation=partial(task_summary, service=service),
        ),
    )


def control_project_tool_sources(
    *, service: AgentSessionService, engine: Engine | None = None
) -> tuple[ProjectToolAuthorSource, ...]:
    return project_tool_sources(
        _control_tool_declarations(service, engine),
        scope_source="session_id argument or AgentCoreRequest.session_id; verified host target for cancellation",
        permission_source="CoreToolSpec.permission and verified host actor for canonical cancellation",
        failure_family="original session owner Failure, authorization rejection and control exceptions",
        readback_semantics="session summary projection or original canonical cancel_run request; no session coordinator",
    )
