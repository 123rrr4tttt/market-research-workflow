"""Model-owned agent core contracts and execution loop."""

from .contracts import (
    AgentCoreRequest,
    AgentCoreRunResult,
    CoreApprovalResume,
    CoreEvent,
    CoreModelStep,
    CorePermissionRequest,
    CoreToolCall,
    CoreToolResult,
    CoreToolSpec,
)
from .core import AgentCore
from .fake_provider import FakeCoreProvider
from .json_provider import JsonCoreProvider
from .native_provider import NativeToolCallingCoreProvider
from .platform_contract import build_agent_core_platform_contract
from .project_tools import build_project_core_tool_registry
from .registry import CoreToolRegistry
from .tool_window import CoreToolWindow, select_core_tool_window

__all__ = [
    "AgentCore",
    "AgentCoreRequest",
    "AgentCoreRunResult",
    "CoreApprovalResume",
    "CoreEvent",
    "CoreModelStep",
    "CorePermissionRequest",
    "CoreToolCall",
    "CoreToolRegistry",
    "CoreToolResult",
    "CoreToolSpec",
    "FakeCoreProvider",
    "JsonCoreProvider",
    "NativeToolCallingCoreProvider",
    "CoreToolWindow",
    "build_agent_core_platform_contract",
    "build_project_core_tool_registry",
    "select_core_tool_window",
]
