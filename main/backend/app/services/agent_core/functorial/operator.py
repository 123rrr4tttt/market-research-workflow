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
from typing import TypeGuard

from app.contracts.json import JSONObject, JSONValue

from ..contracts import CoreToolSpec

from app.services.agent_core.project_tools import build_project_core_tool_registry

from .contracts import OPERATOR_RISKS, OperatorRisk, OperatorValidationError


def _object_schema(
    properties: dict[str, JSONObject],
    required: tuple[str, ...] = (),
) -> JSONObject:
    schema: JSONObject = {"type": "object", "properties": properties}
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


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _is_object_mapping(value: object) -> TypeGuard[dict[str, object]]:
    return _is_object_dict(value) and all(isinstance(key, str) for key in value)


def _is_object_sequence(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _json_schema_value(value: object) -> JSONValue:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if _is_object_sequence(value):
        return [_json_schema_value(item) for item in value]
    if _is_object_mapping(value):
        return {key: _json_schema_value(item) for key, item in value.items()}
    raise OperatorValidationError("operator schema is not JSON")


def _normalize_open_schema(schema: object, *, default: JSONObject | None = None) -> JSONObject:
    normalized = _json_schema_value(schema) if _is_object_mapping(schema) and schema else default or {}
    if not isinstance(normalized, dict):
        raise OperatorValidationError("operator schema root must be an object")
    return copy.deepcopy(normalized)


def _normalize_input_schema(schema: object) -> JSONObject:
    normalized = _normalize_open_schema(schema)
    properties = normalized.get("properties")
    if not isinstance(properties, dict) or not properties:
        normalized["type"] = "object"
        normalized["properties"] = {"query": {"type": "string"}}
    return normalized


def _normalize_output_schema(schema: object, name: str) -> JSONObject:
    del name
    normalized = _normalize_open_schema(schema, default=copy.deepcopy(_DEFAULT_OUTPUT_SCHEMA))
    if not normalized:
        return copy.deepcopy(_DEFAULT_OUTPUT_SCHEMA)
    return normalized


@dataclass(frozen=True)
class OperatorSpec:
    operator_id: str
    name: str
    input_schema: JSONObject
    output_schema: JSONObject
    impl_ref: str
    risk: OperatorRisk

    def to_dict(self) -> JSONObject:
        return {
            "operator_id": self.operator_id,
            "name": self.name,
            "input_schema": dict(self.input_schema or {}),
            "output_schema": dict(self.output_schema or {}),
            "impl_ref": self.impl_ref,
            "risk": self.risk,
        }


def _normalize_risk(risk: object) -> OperatorRisk:
    value = str(risk or "").strip().lower()
    if value == "privileged":
        return "write_external"
    if value in OPERATOR_RISKS:
        return value
    # kit:boundary — reject malformed external tool metadata before projection.
    raise OperatorValidationError(
        f"unsupported operator risk {value!r}; expected one of {OPERATOR_RISKS}"
    )


def _operator_from_core_spec(spec: CoreToolSpec) -> OperatorSpec:
    name = str(spec.name or "").strip()
    return OperatorSpec(
        operator_id=name,
        name=str(spec.title or name),
        input_schema=_normalize_input_schema(spec.input_schema),
        output_schema=_normalize_output_schema(spec.output_schema, name),
        impl_ref=f"agent_runtime:{name}",
        risk=_normalize_risk(spec.risk),
    )


def project_process_operators() -> list[OperatorSpec]:
    """Project the registered Core tool interfaces into OperatorSpecs."""
    projected: dict[str, OperatorSpec] = {}

    core_registry = build_project_core_tool_registry(service=None)
    for tool in core_registry.list_specs():
        spec = _operator_from_core_spec(tool)
        projected[spec.operator_id] = spec

    return [projected[key] for key in sorted(projected)]
