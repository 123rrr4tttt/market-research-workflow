from __future__ import annotations

from typing import Any


def validate_tool_arguments(*, arguments: dict[str, Any], input_schema: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Small JSON-schema subset for model-produced tool arguments.

    AgentCore exposes schemas to the model, but the runtime must still own the
    final contract check before execution. This intentionally covers
    the subset used by CoreToolSpec inputs without adding another dependency.
    """

    schema = dict(input_schema or {})
    if not schema:
        return []
    return _validate_value(arguments, schema=schema, path="$")


def summarize_validation_errors(errors: list[dict[str, Any]]) -> str:
    if not errors:
        return ""
    first = errors[0]
    suffix = f" (+{len(errors) - 1} more)" if len(errors) > 1 else ""
    return f"{first.get('path')}: {first.get('message')}{suffix}"


def _validate_value(value: Any, *, schema: dict[str, Any], path: str) -> list[dict[str, Any]]:
    if not isinstance(schema, dict) or not schema:
        return []

    if "oneOf" in schema:
        options = [item for item in list(schema.get("oneOf") or []) if isinstance(item, dict)]
        if not options:
            return []
        if any(not _validate_value(value, schema=option, path=path) for option in options):
            return []
        return [_error(path, "one_of_mismatch", "value does not match any allowed schema")]

    errors: list[dict[str, Any]] = []
    expected_type = schema.get("type")
    if expected_type and not _matches_type(value, str(expected_type)):
        return [_error(path, "type_mismatch", f"expected {expected_type}")]

    if "enum" in schema:
        allowed = list(schema.get("enum") or [])
        if value not in allowed:
            errors.append(_error(path, "enum_mismatch", f"expected one of {allowed}"))

    if isinstance(value, dict):
        errors.extend(_validate_object(value, schema=schema, path=path))
    elif isinstance(value, list):
        errors.extend(_validate_array(value, schema=schema, path=path))
    elif isinstance(value, str):
        errors.extend(_validate_string(value, schema=schema, path=path))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        errors.extend(_validate_number(value, schema=schema, path=path))

    return errors


def _validate_object(value: dict[str, Any], *, schema: dict[str, Any], path: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}

    for key in list(schema.get("required") or []):
        if key not in value:
            errors.append(_error(f"{path}.{key}", "required", "required property is missing"))

    if schema.get("additionalProperties") is False:
        allowed = set(properties)
        for key in sorted(set(value) - allowed):
            errors.append(_error(f"{path}.{key}", "additional_property", "additional property is not allowed"))

    for key, child_schema in properties.items():
        if key in value and isinstance(child_schema, dict):
            errors.extend(_validate_value(value[key], schema=child_schema, path=f"{path}.{key}"))

    return errors


def _validate_array(value: list[Any], *, schema: dict[str, Any], path: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    min_items = schema.get("minItems")
    max_items = schema.get("maxItems")
    if isinstance(min_items, int) and len(value) < min_items:
        errors.append(_error(path, "min_items", f"expected at least {min_items} item(s)"))
    if isinstance(max_items, int) and len(value) > max_items:
        errors.append(_error(path, "max_items", f"expected at most {max_items} item(s)"))

    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        for index, item in enumerate(value):
            errors.extend(_validate_value(item, schema=item_schema, path=f"{path}[{index}]"))
    return errors


def _validate_string(value: str, *, schema: dict[str, Any], path: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    min_length = schema.get("minLength")
    max_length = schema.get("maxLength")
    if isinstance(min_length, int) and len(value) < min_length:
        errors.append(_error(path, "min_length", f"expected at least {min_length} character(s)"))
    if isinstance(max_length, int) and len(value) > max_length:
        errors.append(_error(path, "max_length", f"expected at most {max_length} character(s)"))
    return errors


def _validate_number(value: int | float, *, schema: dict[str, Any], path: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if isinstance(minimum, (int, float)) and value < minimum:
        errors.append(_error(path, "minimum", f"expected value >= {minimum}"))
    if isinstance(maximum, (int, float)) and value > maximum:
        errors.append(_error(path, "maximum", f"expected value <= {maximum}"))
    return errors


def _matches_type(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return True


def _error(path: str, code: str, message: str) -> dict[str, Any]:
    return {"path": path, "code": code, "message": message}
