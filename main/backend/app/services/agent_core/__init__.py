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
    core_tool_call_contract_shape,
)
from .core import AgentCore
from .fake_provider import FakeCoreProvider
from .json_provider import JsonCoreProvider
from .native_provider import NativeToolCallingCoreProvider
from .platform_contract import build_agent_core_platform_contract, build_provider_capability_matrix
from .provider_trace import build_agent_core_provider_trace_readback_contract
from .provider_readiness import build_agent_core_provider_live_readiness_contract
from .project_tools import build_project_core_tool_registry
from .registry import CoreToolRegistry
from .tool_window import CoreToolWindow, select_core_tool_window
from .tool_calling_quality import build_agent_core_tool_calling_quality_contract

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
    "core_tool_call_contract_shape",
    "build_agent_core_platform_contract",
    "build_provider_capability_matrix",
    "build_agent_core_provider_live_readiness_contract",
    "build_agent_core_provider_trace_readback_contract",
    "build_agent_core_tool_calling_quality_contract",
    "build_project_core_tool_registry",
    "select_core_tool_window",
]
