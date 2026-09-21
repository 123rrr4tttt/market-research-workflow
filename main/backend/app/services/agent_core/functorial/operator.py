"""Functorial operator projection.

Projects MRW's existing process interfaces onto a single :class:`OperatorSpec`
catalog without rewriting any tool implementation.

An operator is a typed morphism ``operator_id -> (input_schema, output_schema)``
that internally references an existing project process interface via
``impl_ref``. The projection only re-labels existing surfaces; it never calls
them, so a live service/DB is not required.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from app.services.agent_core.project_tools import build_project_core_tool_registry
from app.services.agent_runtime.control_tools import AgentControlToolRuntime
from app.services.agent_runtime.read_only_tools import ReadOnlyAgentToolRuntime

from .contracts import OPERATOR_RISKS, OperatorRisk, OperatorValidationError


def _object_schema(
    properties: dict[str, dict[str, Any]],
    required: tuple[str, ...] = (),
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = list(required)
    return schema


_SEARCH_OUTPUT_SCHEMA = _object_schema(
    {
        "items": {"type": "array"},
        "total": {"type": "number"},
        "query": {"type": "string"},
    },
    ("items", "total"),
)
_READ_OUTPUT_SCHEMA = _object_schema(
    {
        "item": {"type": "object"},
        "content": {"type": "string"},
    }
)
_WRITE_OUTPUT_SCHEMA = _object_schema(
    {
        "document_id": {"type": "string"},
        "id": {"type": "string"},
        "title": {"type": "string"},
        "content": {"type": "string"},
        "accepted": {"type": "boolean"},
    }
)
_STATUS_OUTPUT_SCHEMA = _object_schema(
    {
        "status": {"type": "string"},
        "counts": {"type": "object"},
        "available": {"type": "boolean"},
    }
)
_FALLBACK_OUTPUT_SCHEMA = _object_schema({"result": {"type": "object"}})


_DEFAULT_OUTPUT_SCHEMA = _FALLBACK_OUTPUT_SCHEMA


def _normalize_input_schema(schema: Any) -> dict[str, Any]:
    normalized = copy.deepcopy(schema or {})
    if not isinstance(normalized, dict):
        normalized = {}
    properties = normalized.get("properties")
    if not isinstance(properties, dict) or not properties:
        normalized["type"] = "object"
        normalized["properties"] = {"query": {"type": "string"}}
    return normalized


def _normalize_output_schema(schema: Any, name: str) -> dict[str, Any]:
    normalized = copy.deepcopy(schema or {})
    if not isinstance(normalized, dict) or not normalized:
        return copy.deepcopy(_DEFAULT_OUTPUT_SCHEMA)
    return normalized


@dataclass(frozen=True)
class OperatorSpec:
    operator_id: str
    name: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    impl_ref: str
    risk: OperatorRisk

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "name": self.name,
            "input_schema": dict(self.input_schema or {}),
            "output_schema": dict(self.output_schema or {}),
            "impl_ref": self.impl_ref,
            "risk": self.risk,
        }


def _normalize_risk(risk: Any) -> str:
    value = str(risk or "").strip().lower()
    if value == "privileged":
        return "write_external"
    if value in OPERATOR_RISKS:
        return value
    # kit:boundary — reject malformed external tool metadata before projection.
    raise OperatorValidationError(
        f"unsupported operator risk {value!r}; expected one of {OPERATOR_RISKS}"
    )


def _risk_from_tool_definition(tool: dict[str, Any]) -> str:
    concurrency = str(tool.get("concurrency_class") or "read_only").strip().lower()
    risk = "read_only" if concurrency == "read_only" else concurrency
    return _normalize_risk(risk)


def _operator_from_tool_definition(tool: dict[str, Any]) -> OperatorSpec:
    name = str(
        tool.get("name") or tool.get("tool_name") or tool.get("capability_id") or ""
    ).strip()
    return OperatorSpec(
        operator_id=name,
        name=name,
        input_schema=_normalize_input_schema(tool.get("input_schema")),
        output_schema=_normalize_output_schema(tool.get("output_schema"), name),
        impl_ref=f"agent_runtime:{name}",
        risk=_risk_from_tool_definition(tool),
    )


def _operator_from_core_spec(spec: Any) -> OperatorSpec:
    name = str(getattr(spec, "name", "") or "").strip()
    return OperatorSpec(
        operator_id=name,
        name=str(getattr(spec, "title", None) or name),
        input_schema=_normalize_input_schema(getattr(spec, "input_schema", None)),
        output_schema=_normalize_output_schema(getattr(spec, "output_schema", None), name),
        impl_ref=f"agent_runtime:{name}",
        risk=_normalize_risk(getattr(spec, "risk", None)),
    )


def project_process_operators() -> list[OperatorSpec]:
    """Project existing process interfaces into a deduplicated OperatorSpec list.

    Sources (all already live in the repository):

    1. ``read_only_tools.ReadOnlyAgentToolRuntime.list_tool_definitions()``
    2. ``control_tools.AgentControlToolRuntime.list_tool_definitions()``
    3. ``project_tools.build_project_core_tool_registry(...).list_specs()``

    The three sources overlap (the core registry already adapts the read-only and
    control runtimes), so projection is keyed by ``operator_id`` and deduplicated.
    """
    projected: dict[str, OperatorSpec] = {}

    read_only_runtime = ReadOnlyAgentToolRuntime(service=None)  # type: ignore[arg-type]
    for tool in read_only_runtime.list_tool_definitions():
        spec = _operator_from_tool_definition(tool)
        projected[spec.operator_id] = spec

    control_runtime = AgentControlToolRuntime(service=None)  # type: ignore[arg-type]
    for tool in control_runtime.list_tool_definitions():
        spec = _operator_from_tool_definition(tool)
        projected[spec.operator_id] = spec

    core_registry = build_project_core_tool_registry(service=None)  # type: ignore[arg-type]
    for tool in core_registry.list_specs():
        spec = _operator_from_core_spec(tool)
        projected[spec.operator_id] = spec

    return [projected[key] for key in sorted(projected)]
