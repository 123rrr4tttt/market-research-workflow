#!/usr/bin/env python3
"""MRW AgentCore tool registry -> MCP bridge (stdio).

The AgentCore tool registry is the single truth source. This bridge projects the
registered tool surface for MCP clients, deriving each tool's read/write
annotation from ``CoreToolSpec.risk``. ``permission`` is never used as the
read-only signal because ``allow`` also covers write/privileged tools such as
``writing.document.create``.

Without an authenticated host binding this stdio surface is fail-closed.
``initialize`` and ``tools/list`` still answer so a client can recover the
protocol, but any scoped or write call is rejected with an explicit
``scope_required`` / ``authorization_required`` code and has zero side effect.
Only the public no-scope read tools (``skill.search`` and ``skill.load``) execute
directly. Functorial composition is not exposed by this bridge and is never
scheduled here.

Env:
  MRW_BACKEND : backend package root (default ../backend)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _repo_src_root() -> Path:
    return Path(__file__).resolve().parents[3] / "src"


REPO_SRC = _repo_src_root()
if not REPO_SRC.is_dir():
    print(
        f"MRW MCP server bootstrap: repository source directory not found: {REPO_SRC}",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _backend_root() -> Path:
    env = os.environ.get("MRW_BACKEND")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[1]


ROOT = _backend_root()
sys.path.insert(0, str(REPO_SRC))
sys.path.insert(0, str(ROOT))

from app.services.agent_core.contracts import (
    AgentCoreRequest,
    CoreToolCall,
)
from app.services.agent_core.project_tools import (
    build_project_core_tool_registry,
)
from app.services.agent_sessions.service import AgentSessionService

_SERVICE = AgentSessionService()
_REGISTRY = build_project_core_tool_registry(service=_SERVICE)


HOST_AUTHORIZATION_STATUS = {
    "status": "unbound",
    "reason": "trusted_host_binding_unavailable",
}


PUBLIC_NO_SCOPE_TOOLS = {"skill.load", "skill.search"}


_FUNCTORIAL_TOOL_NAMES = {"create_motif", "create_workflow", "run_workflow"}


def _mcp_tool(spec) -> dict:
    schema = dict(spec.input_schema or {"type": "object", "properties": {}})
    return {
        "name": spec.name,
        "description": spec.description_for_model or "",
        "inputSchema": schema,
        "outputSchema": spec.output_schema
        or {"type": "object", "additionalProperties": True},
        "annotations": {
            "readOnlyHint": spec.risk == "read_only",
            "openWorldHint": False,
        },
    }


def _handle_tools_list() -> dict:
    return {"tools": [_mcp_tool(s) for s in _REGISTRY.list_specs()]}


def _is_public_no_scope_tool(spec) -> bool:
    properties = dict((spec.input_schema or {}).get("properties") or {})
    has_scope_parameter = bool({"project_key", "session_id"} & properties.keys())
    return (
        spec.name in PUBLIC_NO_SCOPE_TOOLS
        and spec.risk == "read_only"
        and spec.permission == "allow"
        and not has_scope_parameter
    )


def _requires_host_authorization(spec) -> bool:
    return spec.risk != "read_only" or spec.permission != "allow"


def _unbound_result(*, code: str, message: str) -> dict:
    return {
        "content": [{"type": "text", "text": message}],
        "structuredContent": {
            "code": code,
            "message": message,
            "host_authorization": HOST_AUTHORIZATION_STATUS,
            "approval_required": True,
        },
        "isError": True,
    }


def _unsupported_result(message: str) -> dict:
    return {
        "content": [{"type": "text", "text": message}],
        "structuredContent": {"code": "unsupported", "message": message},
        "isError": True,
    }


def _execute_public_read(name: str, arguments: dict, spec) -> dict:
    call = CoreToolCall(
        tool_name=name,
        arguments=arguments,
        reason="stdio-public-registry-read",
    )
    request = AgentCoreRequest(
        message="",
        session_id="",
        project_key=None,
        turn_id="stdio-unbound",
    )
    result = _REGISTRY.execute_tool(
        tool_call=call,
        tool_spec=spec,
        request=request,
        emit=lambda _e: None,
    )
    if result.status == "needs_approval":
        return {
            "content": [{"type": "text", "text": result.model_summary}],
            "structuredContent": {
                **dict(result.structured_content or {}),
                "code": "approval_required",
                "host_authorization": HOST_AUTHORIZATION_STATUS,
                "approval_required": True,
            },
            "isError": True,
        }
    if result.status != "completed":
        return {
            "content": [{"type": "text", "text": result.model_summary}],
            "structuredContent": dict(result.structured_content or {}),
            "isError": True,
        }
    text = result.model_summary or json.dumps(
        result.structured_content or {}, ensure_ascii=False
    )[:4000]
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": dict(result.structured_content or {}),
        "isError": False,
    }


def _handle_tools_call(params: dict) -> dict:
    name = str((params or {}).get("name") or "").strip()
    arguments = (
        dict((params or {}).get("arguments") or {})
        if isinstance((params or {}).get("arguments"), dict)
        else {}
    )
    if name in _FUNCTORIAL_TOOL_NAMES:
        return _unsupported_result(
            f"{name} is not exposed through the stdio MCP surface; "
            "functorial composition requires the unified host authorization boundary"
        )
    spec = _REGISTRY.get(name)
    if spec is None:
        return {
            "content": [{"type": "text", "text": f"unknown tool: {name}"}],
            "isError": True,
        }
    supplied_scope = sorted(
        key
        for key in ("project_key", "session_id")
        if arguments.get(key) is not None
    )
    if supplied_scope:
        return _unbound_result(
            code="scope_required",
            message=(
                f"{', '.join(supplied_scope)} must be bound by a trusted host; "
                "model-supplied scope is not accepted"
            ),
        )
    if _is_public_no_scope_tool(spec):
        return _execute_public_read(name, arguments, spec)
    if _requires_host_authorization(spec):
        return _unbound_result(
            code="authorization_required",
            message=(
                f"{name} requires a trusted host authorization binding "
                "before it can run"
            ),
        )
    return _unbound_result(
        code="scope_required",
        message=f"{name} requires a trusted host project/session binding",
    )


def _send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params") or {}
        if method == "initialize":
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": params.get("protocolVersion")
                        or "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "mrw-agent-core", "version": "0.1.0"},
                        "hostAuthorization": HOST_AUTHORIZATION_STATUS,
                    },
                }
            )
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": msg_id, "result": _handle_tools_list()})
        elif method == "tools/call":
            _send(
                {"jsonrpc": "2.0", "id": msg_id, "result": _handle_tools_call(params)}
            )
        elif method.startswith("notifications/"):
            continue
        elif msg_id is not None:
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"method not found: {method}",
                    },
                }
            )


if __name__ == "__main__":
    main()
