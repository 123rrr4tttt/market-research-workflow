"""Shared workflow identities and typed failures for compile and observation."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal, NoReturn, TypeAlias, TypeGuard, Union, get_args

from functorial_kit import Failure, define_failure_family

WorkflowJsonAtom: TypeAlias = str | int | float | bool | None
WorkflowJsonValue: TypeAlias = Union[
    WorkflowJsonAtom,
    list["WorkflowJsonValue"],
    dict[str, "WorkflowJsonValue"],
]
WorkflowJsonObject: TypeAlias = dict[str, WorkflowJsonValue]


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _workflow_json_failure(message: str, *, path: str) -> Failure:
    return WORKFLOW_DEFINITION_FAILURES.fail(
        WORKFLOW_DSL_MALFORMED_PAYLOAD,
        message,
        {
            "owner": "workflow_common.json_normalizer",
            "operation": "normalize_workflow_json",
            "site": path,
            "public_exception": "TypeError",
            "public_message": message,
            "witness": "test:test_workflow_json_normalizer_uses_typed_failure_lift_for_public_type_error",
            "path": path,
        },
    )


def _raise_workflow_json_failure(failure: Failure) -> NoReturn:
    message = str((failure.context or {}).get("public_message") or failure.message)
    # kit:boundary owner=workflow_common.json_normalizer class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=workflow.definition.failure witness=test:test_workflow_json_normalizer_uses_typed_failure_lift_for_public_type_error
    raise TypeError(message)


def try_normalize_workflow_json_value(
    value: object,
    *,
    path: str = "value",
) -> WorkflowJsonValue | Failure:
    """Validate and copy one raw value into the shared workflow JSON domain."""

    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return _workflow_json_failure(
                f"{path} contains a non-finite JSON number",
                path=path,
            )
        return value
    if _is_object_mapping(value):
        normalized: WorkflowJsonObject = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str):
                return _workflow_json_failure(
                    f"{path} contains a non-string JSON object key",
                    path=path,
                )
            parsed = try_normalize_workflow_json_value(
                raw_value,
                path=f"{path}.{raw_key}",
            )
            if isinstance(parsed, Failure):
                return parsed
            normalized[raw_key] = parsed
        return normalized
    if _is_object_list(value):
        normalized_items: list[WorkflowJsonValue] = []
        for index, item in enumerate(value):
            parsed = try_normalize_workflow_json_value(item, path=f"{path}[{index}]")
            if isinstance(parsed, Failure):
                return parsed
            normalized_items.append(parsed)
        return normalized_items
    return _workflow_json_failure(
        f"{path} contains a non-JSON value of type {type(value).__name__}",
        path=path,
    )


def normalize_workflow_json_value(
    value: object,
    *,
    path: str = "value",
) -> WorkflowJsonValue:
    normalized = try_normalize_workflow_json_value(value, path=path)
    if isinstance(normalized, Failure):
        _raise_workflow_json_failure(normalized)
    return normalized


def try_normalize_workflow_json_object(
    value: object,
    *,
    path: str = "value",
) -> WorkflowJsonObject | Failure:
    normalized = try_normalize_workflow_json_value(value, path=path)
    if isinstance(normalized, Failure):
        return normalized
    if not isinstance(normalized, dict):
        return _workflow_json_failure(f"{path} must be a JSON object", path=path)
    return normalized


def normalize_workflow_json_object(
    value: object,
    *,
    path: str = "value",
) -> WorkflowJsonObject:
    normalized = try_normalize_workflow_json_object(value, path=path)
    if isinstance(normalized, Failure):
        _raise_workflow_json_failure(normalized)
    return normalized

WORKFLOW_DSL_MALFORMED_PAYLOAD = "WORKFLOW_DSL_MALFORMED_PAYLOAD"
WORKFLOW_DSL_DUPLICATE_NODE_ID = "WORKFLOW_DSL_DUPLICATE_NODE_ID"
WORKFLOW_DSL_UNSUPPORTED_NODE_TYPE = "WORKFLOW_DSL_UNSUPPORTED_NODE_TYPE"
WORKFLOW_DSL_MISSING_ENDPOINT = "WORKFLOW_DSL_MISSING_ENDPOINT"
WORKFLOW_DSL_CYCLE = "WORKFLOW_DSL_CYCLE"
WORKFLOW_DSL_COMPILE_FAILURE = "WORKFLOW_DSL_COMPILE_FAILURE"
WORKFLOW_CONTRACT_KIND_UNSUPPORTED = "WORKFLOW_CONTRACT_KIND_UNSUPPORTED"
WORKFLOW_OBSERVATION_SHAPE_INVALID = "WORKFLOW_OBSERVATION_SHAPE_INVALID"
WORKFLOW_PROGRAM_PLAN_BINDING_INVALID = "WORKFLOW_PROGRAM_PLAN_BINDING_INVALID"
WORKFLOW_ROLLBACK_BINDING_INVALID = "WORKFLOW_ROLLBACK_BINDING_INVALID"
WORKFLOW_SLICE_SHAPE_INVALID = "WORKFLOW_SLICE_SHAPE_INVALID"

WorkflowDefinitionFailureCode = Literal[
    "WORKFLOW_CONTRACT_KIND_UNSUPPORTED",
    "WORKFLOW_DSL_COMPILE_FAILURE",
    "WORKFLOW_DSL_CYCLE",
    "WORKFLOW_DSL_DUPLICATE_NODE_ID",
    "WORKFLOW_DSL_MALFORMED_PAYLOAD",
    "WORKFLOW_DSL_MISSING_ENDPOINT",
    "WORKFLOW_DSL_UNSUPPORTED_NODE_TYPE",
    "WORKFLOW_OBSERVATION_SHAPE_INVALID",
    "WORKFLOW_PROGRAM_PLAN_BINDING_INVALID",
    "WORKFLOW_ROLLBACK_BINDING_INVALID",
    "WORKFLOW_SLICE_SHAPE_INVALID",
]

WORKFLOW_DEFINITION_FAILURES = define_failure_family(
    "workflow.definition.failure",
    get_args(WorkflowDefinitionFailureCode),
)


__all__ = [
    "WORKFLOW_CONTRACT_KIND_UNSUPPORTED",
    "WORKFLOW_DEFINITION_FAILURES",
    "WorkflowDefinitionFailureCode",
    "WORKFLOW_DSL_COMPILE_FAILURE",
    "WORKFLOW_DSL_CYCLE",
    "WORKFLOW_DSL_DUPLICATE_NODE_ID",
    "WORKFLOW_DSL_MALFORMED_PAYLOAD",
    "WORKFLOW_DSL_MISSING_ENDPOINT",
    "WORKFLOW_DSL_UNSUPPORTED_NODE_TYPE",
    "WorkflowJsonAtom",
    "WorkflowJsonObject",
    "WorkflowJsonValue",
    "WORKFLOW_OBSERVATION_SHAPE_INVALID",
    "WORKFLOW_PROGRAM_PLAN_BINDING_INVALID",
    "WORKFLOW_ROLLBACK_BINDING_INVALID",
    "WORKFLOW_SLICE_SHAPE_INVALID",
    "normalize_workflow_json_object",
    "normalize_workflow_json_value",
    "try_normalize_workflow_json_object",
    "try_normalize_workflow_json_value",
]
