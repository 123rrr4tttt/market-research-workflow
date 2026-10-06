from __future__ import annotations

from collections.abc import Callable

from functorial_kit import Failure
from app.services.agent_sessions.service import AgentSessionService
from mrw_functorial_kit.core.agent_service_semantics import agent_runtime_failures

from .contracts import (
    AgentCoreRequest,
    compact_json_value,
    CoreEvent,
    CoreToolCall,
    CoreToolResult,
    CoreToolSpec,
    JSONObject,
    ToolStatus,
)
from .host_authorization import (
    TrustedHostContext,
    authorize_tool_call,
    canonical_arguments_sha256,
    VerifiedHostAuthorization,
    validate_execution_scope,
    verified_host_authorization_channel,
)


ToolHandler = Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]
TOOL_SCHEMA_INVENTORY_CONTRACT_VERSION = "agent_core.tool_schema_inventory.v1"


class CoreToolRegistry:
    """In-process tool registry used by AgentCore.

    It intentionally stores model-visible tool specs and execution handlers in
    one place so old capability routing can be replaced by provider-owned tool
    calls against explicit schemas.
    """

    def __init__(self) -> None:
        self._specs: dict[str, CoreToolSpec] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, spec: CoreToolSpec, handler: ToolHandler) -> Failure | None:
        name = _validate_tool_name(spec.name)
        if isinstance(name, Failure):
            return name
        self._specs[name] = spec
        self._handlers[name] = handler
        return None

    def get(self, tool_name: str) -> CoreToolSpec | None:
        return self._specs.get(str(tool_name or "").strip())

    def list_specs(self) -> list[CoreToolSpec]:
        return [self._specs[name] for name in sorted(self._specs)]

    def schema_inventory(self) -> JSONObject:
        specs = self.list_specs()
        tools = [spec.to_dict() for spec in specs]
        return {
            "contract_version": TOOL_SCHEMA_INVENTORY_CONTRACT_VERSION,
            "tool_count": len(tools),
            "summary": {
                "by_source": _count_by(tools, "source"),
                "by_risk": _count_by(tools, "risk"),
                "by_permission": _count_by(tools, "permission"),
                "by_concurrency": _count_by(tools, "concurrency"),
            },
            "tools": tools,
        }

    def execute_tool(
        self,
        *,
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec | None = None,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
        trusted_context: TrustedHostContext | None = None,
        authorization_service: AgentSessionService | None = None,
        host_authorization: VerifiedHostAuthorization | None = None,
        package_digest: str | None = None,
    ) -> CoreToolResult:
        registered_spec = self.get(tool_call.tool_name)
        handler = self._handlers.get(tool_call.tool_name)
        if registered_spec is None or handler is None:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Tool {tool_call.tool_name} is not registered.",
                error={"code": "tool_not_registered", "message": f"Tool {tool_call.tool_name} is not registered."},
            )
        if tool_spec is not None and tool_spec != registered_spec:
            return _authorization_result(
                tool_call,
                "tool_spec_mismatch",
                "caller tool spec does not match the registered tool spec",
            )
        if handler is None:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Tool {tool_call.tool_name} is not registered.",
                error={"code": "tool_not_registered", "message": f"Tool {tool_call.tool_name} is not registered."},
            )

        if trusted_context is None:
            if host_authorization is not None:
                return _authorization_result(
                    tool_call,
                    "host_context_required",
                    "host authorization requires its trusted host context",
                )
            if registered_spec.permission == "allow":
                return handler(tool_call, registered_spec, request, emit)
            if registered_spec.permission in {"ask", "explicit_user_request"}:
                return _needs_approval_result(tool_call, approval_id=None)
            return _authorization_result(
                tool_call,
                "tool_permission_denied",
                f"Tool {tool_call.tool_name} is denied by CoreToolSpec.permission.",
            )

        scope_failure = validate_execution_scope(trusted_context, request, tool_call)
        if isinstance(scope_failure, Failure):
            return _failure_result(tool_call, scope_failure)

        if host_authorization is None:
            if authorization_service is None:
                return _authorization_result(
                    tool_call,
                    "authorization_service_required",
                    "trusted host execution requires AgentSessionService authorization",
                )
            arguments_sha256 = canonical_arguments_sha256(tool_call.arguments)
            if isinstance(arguments_sha256, Failure):
                return _failure_result(tool_call, arguments_sha256)
            decision = authorize_tool_call(
                authorization_service,
                trusted_context,
                registered_spec,
                tool_call.arguments,
                package_digest=package_digest,
                originating_call_id=tool_call.call_id,
            )
            if isinstance(decision, Failure):
                return _failure_result(tool_call, decision)
            if decision.status == "needs_approval":
                return _needs_approval_result(
                    tool_call,
                    approval_id=str((decision.approval or {}).get("approval_id") or "") or None,
                )
            host_authorization = decision.authorization

        if host_authorization is None:
            return _authorization_result(tool_call, "host_authorization_missing", "host authorization is missing")
        if host_authorization.context != trusted_context:
            return _authorization_result(
                tool_call,
                "host_authorization_context_mismatch",
                "host authorization was issued for a different trusted context",
            )
        arguments_sha256 = canonical_arguments_sha256(tool_call.arguments)
        if isinstance(arguments_sha256, Failure):
            return _failure_result(tool_call, arguments_sha256)
        execution_call_id = host_authorization.execution_call_id or host_authorization.origin_call_id
        if (
            host_authorization.tool_name != registered_spec.name
            or host_authorization.arguments_sha256 != arguments_sha256
            or host_authorization.permission != registered_spec.permission
            or execution_call_id != tool_call.call_id
            or host_authorization.package_digest != (str(package_digest).strip() or None if package_digest else None)
        ):
            return _authorization_result(
                tool_call,
                "host_authorization_action_mismatch",
                "host authorization does not match the registered tool action",
            )
        with verified_host_authorization_channel(host_authorization):
            return handler(tool_call, registered_spec, request, emit)

    @staticmethod
    def simple_result(
        *,
        call: CoreToolCall,
        status: str = "completed",
        model_summary: str,
        structured_content: JSONObject | None = None,
    ) -> CoreToolResult | Failure:
        normalized_status = _validate_tool_status(status)
        if isinstance(normalized_status, Failure):
            return normalized_status
        return CoreToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status=normalized_status,
            model_summary=model_summary,
            structured_content=dict(structured_content or {}),
        )


def _validate_tool_name(value: object) -> str | Failure:
    name = str(value or "").strip()
    if not name:
        return agent_runtime_failures.fail(
            "tool_name_required",
            "tool spec name is required",
            {"field": "name"},
        )
    return name


def _needs_approval_result(tool_call: CoreToolCall, *, approval_id: str | None) -> CoreToolResult:
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="needs_approval",
        model_summary=f"Tool {tool_call.tool_name} requires explicit host approval.",
        structured_content={"approval_id": approval_id} if approval_id else {},
    )


def _authorization_result(tool_call: CoreToolCall, code: str, message: str) -> CoreToolResult:
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="failed",
        model_summary=message,
        error={"code": code, "message": message},
    )


def _failure_result(tool_call: CoreToolCall, failure: Failure) -> CoreToolResult:
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="failed",
        model_summary=failure.message,
        error={"code": failure.code, "message": failure.message, "context": compact_json_value(failure.context)},
    )


def _validate_tool_status(value: object) -> ToolStatus | Failure:
    status = str(value or "").strip()
    statuses: dict[str, ToolStatus] = {
        "completed": "completed",
        "failed": "failed",
        "canceled": "canceled",
        "needs_approval": "needs_approval",
        "deferred": "deferred",
    }
    normalized = statuses.get(status)
    if normalized is None:
        return agent_runtime_failures.fail(
            "tool_status_unsupported",
            f"unsupported tool status: {status}",
            {"field": "status", "value": value},
        )
    return normalized


def _count_by(items: list[JSONObject], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown").strip() or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return {name: counts[name] for name in sorted(counts)}
