#!/usr/bin/env python3
"""MRW AgentCore retrieval functor -> MCP bridge (stdio).

Functorial design: the AgentCore tool registry is the single truth source. This
bridge projects only the *retrieval* morphisms (read-only, project-parameterised)
that compose to answer "what is happening in my project". It deliberately does
NOT dump the full 83-tool pool; write/control/agent-batch tools stay out of the
assistant surface. Same interface serves any project (project_key parameterised).

Env:
  MRW_BACKEND                        : backend package root (default ../backend)
  MRW_BUSINESS_CHAIN_PROJECT_KEY     : default project_key for calls
  MRW_ACTIVE_PROJECT_KEY             : optional fallback after MRW_BUSINESS_CHAIN_PROJECT_KEY
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from pathlib import Path


def _backend_root() -> Path:
    env = os.environ.get("MRW_BACKEND")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[1]


ROOT = _backend_root()
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

from app.services.agent_core.functorial.motif import compose_motif
from app.services.agent_core.functorial.registry import (
    catalog as _fcatalog,
)
from app.services.agent_core.functorial.workflow import (
    build_workflow_program,
)


def _ftool(name, description, schema):
    return {
        "name": name,
        "description": description,
        "inputSchema": schema,
        "outputSchema": {"type": "object", "additionalProperties": True},
        "annotations": {"readOnlyHint": False, "openWorldHint": False},
    }


FUNCTORIAL_TOOLS = [
    _ftool(
        "create_motif",
        "Compose existing operators into a named reusable motif (basic ordered composition).",
        {
            "type": "object",
            "properties": {
                "motif_id": {"type": "string"},
                "name": {"type": "string"},
                "composition": {"type": "array", "items": {"type": "string"}},
                "input_schema": {"type": "object", "additionalProperties": True},
                "output_schema": {"type": "object", "additionalProperties": True},
            },
            "required": ["motif_id", "name", "composition"],
        },
    ),
    _ftool(
        "create_workflow",
        "Compose operators/motifs into a fixed long workflow (linear DAG) and register it by name.",
        {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "name": {"type": "string"},
                "steps": {"type": "array", "items": {"type": "string"}},
                "laws": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["workflow_id", "name", "steps"],
        },
    ),
    _ftool(
        "run_workflow",
        "Run a registered workflow by name: execute its operators in order and return results.",
        {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "inputs": {"type": "object", "additionalProperties": True},
                "project_key": {"type": "string"},
            },
            "required": ["workflow_id"],
        },
    ),
]


def _configured_project_key() -> str:
    """Resolve a default project without embedding a checkout-specific key."""

    for name in ("MRW_BUSINESS_CHAIN_PROJECT_KEY", "MRW_ACTIVE_PROJECT_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    try:
        from app.settings.config import settings

        return str(getattr(settings, "active_project_key", "") or "").strip()
    except Exception as exc:  # noqa: BLE001
        _logger.debug("failed to resolve active project key: %s", exc)
        return ""


DEFAULT_PROJECT_KEY = _configured_project_key()
_logger = logging.getLogger(__name__)

# Read-only retrieval morphisms the assistant composes to answer project questions.
CURATED = {
    # writing workbench: read + write (assistant composes retrieval AND native report write)
    "writing.document.create",
    "writing.document.insert_paragraph",
    "writing.document.citations.upsert",
    "writing.document.list",
    "writing.document.read",
    "writing.document.section.read",
    "project.context.bundle",
    "project.summary.read",
    "project.structured_data.search",
    "project.structured_data.item.read",
    "project.structured_data.items.read",
    "project.graph.search",
    "project.structured_graph.query",
    "agent_artifact.search",
    "agent_artifact.read",
    "agent_investigation.trace.read",
    "source_library.item.search",
    "source_library.item.list",
    "ingest.status.read",
    "agent_runtime.tool_pool.list",
    "agent_runtime.tool.search",
}


def _resolve_session_id(project_key: str) -> str:
    """Pick a real agent-session id for the project (tools reject unknown ids)."""
    try:
        sessions = _SERVICE.store.list_sessions(limit=200) or []
        ok = lambda s: str(s.get("project_key") or "") == project_key
        actives = [
            s
            for s in sessions
            if ok(s) and str(s.get("status") or "") in ("active", "pending")
        ]
        if actives:
            return str(actives[0].get("session_id") or "")
        for s in sessions:
            if ok(s):
                return str(s.get("session_id") or "")
    except Exception as exc:  # noqa: BLE001
        _logger.debug("failed to list sessions for project %s: %s", project_key, exc)
    try:
        created = _SERVICE.store.create_session(
            {
                "session_id": None,
                "project_key": project_key,
                "status": "active",
                "title": "MRW assistant retrieval context",
            }
        )
        return str((created or {}).get("session_id") or "")
    except Exception as exc:  # noqa: BLE001
        _logger.debug(
            "failed to create retrieval session for project %s: %s", project_key, exc
        )
        return f"mcp-{uuid.uuid4().hex[:16]}"


def _mcp_tool(spec) -> dict:
    schema = dict(spec.input_schema or {"type": "object", "properties": {}})
    props = dict(schema.get("properties") or {})
    if not DEFAULT_PROJECT_KEY:
        props.setdefault("project_key", {"type": "string"})
        required = list(schema.get("required") or [])
        if "project_key" not in required:
            required.append("project_key")
        schema["required"] = required
    # symmetric: every tool accepts an optional project_key (default env)
    props.setdefault(
        "project_key",
        {
            "type": "string",
            "description": f"MRW project_key (default {DEFAULT_PROJECT_KEY})",
        },
    )
    schema = {**schema, "properties": props}
    return {
        "name": spec.name,
        "description": spec.description_for_model or "",
        "inputSchema": schema,
        "outputSchema": spec.output_schema
        or {"type": "object", "additionalProperties": True},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    }


def _handle_tools_list() -> dict:
    # Full exposure: project every registered AgentCore operator (retrieval,
    # writing/commit, ingest, runtime, control) plus the functorial tools.
    # The previous CURATED whitelist hid ~60 tools from the built-in agent and
    # made discovery tools report writes as "deferred/approval-required",
    # which the agent then echoed back as "I am read-only".
    tools = [_mcp_tool(s) for s in _REGISTRY.list_specs()]
    tools += [dict(t) for t in FUNCTORIAL_TOOLS]
    return {"tools": tools}


def _exec_operator(tool_name: str, arguments: dict, project_key: str) -> dict:
    spec = _REGISTRY.get(tool_name)
    if spec is None:
        return {"ok": False, "tool": tool_name, "error": "not registered"}
    call = CoreToolCall(
        call_id=f"mcp-{uuid.uuid4().hex[:16]}",
        tool_name=tool_name,
        arguments=arguments,
        reason="workflow-run",
    )
    request = AgentCoreRequest(
        message="",
        session_id=_resolve_session_id(project_key),
        project_key=project_key,
        turn_id=f"turn-{uuid.uuid4().hex[:16]}",
    )
    result = _REGISTRY.execute_tool(
        tool_call=call, tool_spec=spec, request=request, emit=lambda _e: None
    )
    return {
        "ok": result.status not in ("failed", "canceled"),
        "tool": tool_name,
        "summary": result.model_summary or "",
        "data": (result.structured_content or {})
        if isinstance(result.structured_content, dict)
        else {},
    }


def _resolve_step_operators(step: str) -> list[str]:
    """Resolve a workflow step (operator:<id> or motif:<id>) to operator ids."""
    if not step.startswith("motif:"):
        return [step.split(":", 1)[1] if ":" in step else step]
    motif = _fcatalog.get("motifs", step.split(":", 1)[1]) or {}
    return [
        c.split(":", 1)[1] if ":" in c else c for c in (motif.get("composition") or [])
    ]


def _handle_functorial_tool(name: str, arguments: dict) -> dict | None:
    if name == "create_motif":
        m = compose_motif(
            arguments["motif_id"],
            arguments.get("name") or arguments["motif_id"],
            arguments.get("composition") or [],
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"motif created: {getattr(m, 'motif_id', None)}",
                }
            ],
            "isError": False,
        }
    if name == "create_workflow":
        w = build_workflow_program(
            arguments["workflow_id"],
            arguments.get("name") or arguments["workflow_id"],
            arguments.get("steps") or [],
            arguments.get("laws"),
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"workflow created: {getattr(w, 'workflow_id', None)}",
                }
            ],
            "isError": False,
        }
    if name == "run_workflow":
        wf = _fcatalog.get("workflows", arguments.get("workflow_id") or "")
        if not wf:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"unknown workflow: {arguments.get('workflow_id')}",
                    }
                ],
                "isError": True,
            }
        project_key = str(arguments.get("project_key") or DEFAULT_PROJECT_KEY).strip()
        inputs = (
            arguments.get("inputs") if isinstance(arguments.get("inputs"), dict) else {}
        )
        results = []
        for step in wf.get("steps") or []:
            for op in _resolve_step_operators(str(step)):
                results.append(_exec_operator(op, inputs, project_key))
        text = json.dumps(results, ensure_ascii=False)[:4000]
        return {"content": [{"type": "text", "text": text}], "isError": False}
    return None


def _handle_tools_call(params: dict) -> dict:
    name = str((params or {}).get("name") or "").strip()
    arguments = (
        dict((params or {}).get("arguments") or {})
        if isinstance((params or {}).get("arguments"), dict)
        else {}
    )
    functor = _handle_functorial_tool(name, arguments)
    if functor is not None:
        return functor
    spec = _REGISTRY.get(name)
    if spec is None:
        return {
            "content": [{"type": "text", "text": f"unknown tool: {name}"}],
            "isError": True,
        }
    project_key = str(arguments.pop("project_key", "") or DEFAULT_PROJECT_KEY).strip()
    call = CoreToolCall(
        call_id=f"mcp-{uuid.uuid4().hex[:16]}",
        tool_name=name,
        arguments=arguments,
        reason="mcp-bridge",
    )
    request = AgentCoreRequest(
        message="",
        session_id=_resolve_session_id(project_key),
        project_key=project_key,
        turn_id=f"turn-{uuid.uuid4().hex[:16]}",
    )
    result = _REGISTRY.execute_tool(
        tool_call=call, tool_spec=spec, request=request, emit=lambda _e: None
    )
    text = (
        result.model_summary
        or json.dumps(result.structured_content or {}, ensure_ascii=False)[:4000]
    )
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": (result.structured_content or {})
        if isinstance(result.structured_content, dict)
        else {},
        "isError": result.status in ("failed", "canceled"),
    }


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
                        "serverInfo": {"name": "mrw-retrieval", "version": "0.1.0"},
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
