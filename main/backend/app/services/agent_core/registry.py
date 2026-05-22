from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .contracts import AgentCoreRequest, CoreEvent, CoreToolCall, CoreToolExecutor, CoreToolResult, CoreToolSpec


ToolHandler = Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]
TOOL_SCHEMA_INVENTORY_CONTRACT_VERSION = "agent_core.tool_schema_inventory.v1"


class CoreToolRegistry(CoreToolExecutor):
    """In-process tool registry used by AgentCore.

    It intentionally stores model-visible tool specs and execution handlers in
    one place so old capability routing can be replaced by provider-owned tool
    calls against explicit schemas.
    """

    def __init__(self) -> None:
        self._specs: dict[str, CoreToolSpec] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, spec: CoreToolSpec, handler: ToolHandler) -> None:
        name = str(spec.name or "").strip()
        if not name:
            raise ValueError("tool spec name is required")
        self._specs[name] = spec
        self._handlers[name] = handler

    def get(self, tool_name: str) -> CoreToolSpec | None:
        return self._specs.get(str(tool_name or "").strip())

    def list_specs(self) -> list[CoreToolSpec]:
        return [self._specs[name] for name in sorted(self._specs)]

    def schema_inventory(self) -> dict[str, Any]:
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
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        handler = self._handlers.get(tool_call.tool_name)
        if handler is None:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Tool {tool_call.tool_name} is not registered.",
                error={"code": "tool_not_registered", "message": f"Tool {tool_call.tool_name} is not registered."},
            )
        return handler(tool_call, tool_spec, request, emit)

    @staticmethod
    def simple_result(
        *,
        call: CoreToolCall,
        status: str = "completed",
        model_summary: str,
        structured_content: dict[str, Any] | None = None,
    ) -> CoreToolResult:
        if status not in {"completed", "failed", "canceled", "needs_approval", "deferred"}:
            raise ValueError(f"unsupported tool status: {status}")
        return CoreToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status=status,  # type: ignore[arg-type]
            model_summary=model_summary,
            structured_content=dict(structured_content or {}),
        )


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown").strip() or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return {name: counts[name] for name in sorted(counts)}
