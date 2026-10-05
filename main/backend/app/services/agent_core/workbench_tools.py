"""Agent facilities for the original local Concept Workbench CLI."""

from __future__ import annotations

from typing import Any

from functorial_kit import Failure

from app.services.crawlers_mgmt.workbench import (
    METHOD_DEFINITIONS,
    OPERATION_DEFINITIONS,
    read_workbench_method,
    run_workbench,
    workbench_module,
)

from .contracts import AgentCoreRequest, CoreToolCall, CoreToolResult, CoreToolSpec
from .host_authorization import current_verified_host_authorization, validate_verified_host_authorization
from .macro_tools import FacilityBinding
from .tool_contribution import ProjectToolAuthorSource, compile_project_tool_native, ProjectToolAssemblyContext


WORKBENCH_SKILL_ID = "concept-workbench-project-wiring"
WORKBENCH_TOOL_PREFIX = "concept_workbench."
_HOST_AUTHORITY = "agent_core.host_authorization"
_TEXT = {"type": "string", "minLength": 1, "maxLength": 2048}


def _operation_schema(operation: str) -> dict[str, Any]:
    properties: dict[str, Any] = {"target_id": _TEXT}
    required = ["target_id"]
    if operation in {"scan", "materials"}:
        properties["paths"] = {"type": "array", "items": _TEXT, "minItems": 1, "maxItems": 100}
        required.append("paths")
    if operation in {"scan", "shapes", "inspect", "check", "sync", "verify"}:
        properties["catalog"] = _TEXT
    if operation == "scan":
        properties["shape"] = {**_TEXT, "default": "python.sync-function.v1"}
    if operation == "inspect":
        properties["id"] = _TEXT
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def _handler(operation: str):
    def dispatch(call: CoreToolCall, spec: CoreToolSpec, request: AgentCoreRequest, _emit: Any) -> CoreToolResult:
        authorization = current_verified_host_authorization()
        if authorization is None or (
            authorization.context.project_key != request.project_key
            or authorization.context.session_id != request.session_id
            or authorization.context.turn_id != request.turn_id
        ):
            return CoreToolResult(
                call_id=call.call_id, tool_name=call.tool_name, status="failed",
                model_summary="A verified project-bound host request is required.",
                error={"code": "workbench_host_required", "message": "A verified project-bound host request is required."},
            )
        checked = validate_verified_host_authorization(
            authorization, authorization.context, spec, dict(call.arguments),
            package_digest=authorization.package_digest,
        )
        if isinstance(checked, Failure):
            return CoreToolResult(
                call_id=call.call_id, tool_name=call.tool_name, status="failed",
                model_summary=checked.message,
                error={"code": checked.code, "message": checked.message, "context": dict(checked.context or {})},
            )
        try:
            if operation == "module":
                if call.arguments:
                    raise ValueError("Module read takes no arguments.")
                result = workbench_module(str(request.project_key))
            elif operation == "method":
                if set(call.arguments) - {"method_id", "relative_path"}:
                    raise ValueError("Unknown method read arguments.")
                result = read_workbench_method(**dict(call.arguments))
            else:
                result = run_workbench(operation, dict(call.arguments), str(request.project_key))
        except (ValueError, OSError) as exc:
            return CoreToolResult(
                call_id=call.call_id, tool_name=call.tool_name, status="failed",
                model_summary=str(exc), error={"code": "workbench_input_invalid", "message": str(exc)},
            )
        exit_code = result.get("exit_code", 0)
        success = exit_code == 0
        return CoreToolResult(
            call_id=call.call_id, tool_name=call.tool_name,
            status="completed" if success else "failed",
            model_summary=f"Concept Workbench {operation}: exit_code={exit_code}.",
            structured_content=result,
            error=None if success else {
                "code": "workbench_cli_failed", "message": str(result.get("stderr") or "Original CLI returned a non-zero exit code."),
            },
        )
    return dispatch


def workbench_tool_sources() -> tuple[ProjectToolAuthorSource, ...]:
    """Derive tool bindings from the original adapter's one operation catalog."""
    declarations = [
        (f"concept_workbench.project.{item['id']}", item["id"], item["title"], _operation_schema(item["id"]), "write_shared")
        for item in OPERATION_DEFINITIONS
    ]
    declarations.extend((
        ("concept_workbench.module.read", "module", "Read Concept Workbench Module", {"type": "object", "properties": {}, "additionalProperties": False}, "read_only"),
        ("concept_workbench.method.read", "method", "Read Workbench and Functorial Methods", {
            "type": "object", "properties": {
                "method_id": {"type": "string", "enum": [item["id"] for item in METHOD_DEFINITIONS]},
                "relative_path": {**_TEXT, "default": "SKILL.md"},
            }, "required": ["method_id"], "additionalProperties": False,
        }, "read_only"),
    ))
    return tuple(ProjectToolAuthorSource(
        binding_id=f"facility.{name}", version="1",
        tool_spec=CoreToolSpec(
            name=name, title=title,
            description_for_model=(
                f"{title}. Use concept_workbench.module.read to discover project-bound targets and "
                "concept_workbench.method.read for the original workbench/functorial instructions. "
                "Only explicitly configured local project roots are permitted. Catalogs and witnesses "
                "may execute code; sync/init write project files. Preserve original CLI reports and exit codes."
            ),
            input_schema=schema, output_schema={"type": "object", "additionalProperties": True},
            source="project", risk=risk, permission="allow", concurrency="serial", timeout_seconds=310,
            project_service_id=name, metadata={
                "contract_version": "concept_workbench.agent_facility.v1",
                "uses_existing_frontdoor": _HOST_AUTHORITY,
            },
        ),
        handler=_handler(operation), executor_ref=name,
        scope_source="Trusted MRW project plus operator-configured local target roots",
        permission_source="Verified host policy plus original Concept Workbench CLI boundaries",
        failure_family="Original CLI exit code, stdout, stderr, report and transport failure",
        readback_semantics="Original CLI observation; no crawler deployment or business completion claim",
        governed_dispatch_ref=_HOST_AUTHORITY,
    ) for name, operation, title, schema, risk in declarations)


def workbench_facilities() -> tuple[FacilityBinding, ...]:
    bindings = []
    for source in workbench_tool_sources():
        native = compile_project_tool_native(source)
        if isinstance(native, Failure):
            raise ValueError(native.message)
        binding = native.assemble(ProjectToolAssemblyContext())
        if isinstance(binding, Failure):
            raise ValueError(binding.message)
        bindings.append(binding.definition)
    return tuple(bindings)
