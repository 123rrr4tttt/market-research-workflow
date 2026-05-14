from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


ToolExecutionHook = Callable[[dict[str, Any]], None]


def is_abort_requested(abort_signal: Any | None) -> bool:
    if abort_signal is None:
        return False
    if isinstance(abort_signal, bool):
        return abort_signal
    if callable(abort_signal):
        try:
            return bool(abort_signal())
        except TypeError:
            return False
    for attr in ("aborted", "cancelled", "canceled", "is_aborted", "is_cancelled", "is_canceled"):
        value = getattr(abort_signal, attr, None)
        if value is None:
            continue
        if callable(value):
            try:
                if bool(value()):
                    return True
            except TypeError:
                continue
        elif bool(value):
            return True
    return False


@dataclass(frozen=True)
class ToolExecutionHooks:
    pre_tool: tuple[ToolExecutionHook, ...] = ()
    post_tool: tuple[ToolExecutionHook, ...] = ()
    on_error: tuple[ToolExecutionHook, ...] = ()
    on_approval: tuple[ToolExecutionHook, ...] = ()
    on_cancel: tuple[ToolExecutionHook, ...] = ()

    def emit(self, hook_name: str, payload: dict[str, Any]) -> None:
        callbacks = getattr(self, hook_name, ())
        for callback in callbacks:
            callback(dict(payload))


@dataclass(frozen=True)
class ToolExecutionPolicy:
    parallel_read_only: bool = True
    approval_required_classes: tuple[str, ...] = ("write_external", "privileged")
    serial_classes: tuple[str, ...] = ("write_shared", "write_external", "privileged")

    def requires_approval(self, tool_definition: dict[str, Any] | None) -> bool:
        tool = dict(tool_definition or {})
        approval_level = str(tool.get("approval_level") or "none").lower()
        concurrency_class = str(tool.get("concurrency_class") or "read_only").lower()
        return approval_level in {"high", "explicit_user_request"} or concurrency_class in self.approval_required_classes

    def can_run_parallel(self, tool_definitions: list[dict[str, Any]]) -> bool:
        if not self.parallel_read_only:
            return False
        if not tool_definitions:
            return False
        for tool in tool_definitions:
            if str(tool.get("concurrency_class") or "read_only").lower() != "read_only":
                return False
            if str(tool.get("approval_level") or "none").lower() != "none":
                return False
        return True

    def build_concurrency_plan(self, tool_definitions: list[dict[str, Any]]) -> dict[str, Any]:
        read_only_parallel: list[str] = []
        serial: list[str] = []
        approval_required: list[str] = []
        for tool in tool_definitions:
            name = str(tool.get("name") or tool.get("tool_name") or tool.get("capability_id") or "")
            concurrency_class = str(tool.get("concurrency_class") or "read_only").lower()
            if self.requires_approval(tool):
                approval_required.append(name)
            if concurrency_class == "read_only" and str(tool.get("approval_level") or "none").lower() == "none":
                read_only_parallel.append(name)
            else:
                serial.append(name)
        return {
            "parallel_read_only": bool(self.parallel_read_only),
            "read_only_parallelizable": read_only_parallel,
            "serial": serial,
            "approval_required": approval_required,
        }


@dataclass
class ToolCallExecutionRecord:
    tool_name: str
    call_id: str
    input_payload: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    tool_definition: dict[str, Any] = field(default_factory=dict)
