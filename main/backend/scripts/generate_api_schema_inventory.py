from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DOC_PATH = (
    REPO_ROOT
    / "development"
    / "latest-dev-docs"
    / "backend-docs"
    / "B_API"
    / "API_SCHEMA_INVENTORY_2026-05-22.md"
)
HTTP_METHODS = ("DELETE", "GET", "PATCH", "POST", "PUT")


def _schema_label(schema: Any) -> str:
    if not isinstance(schema, dict) or not schema:
        return "untyped"
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return ref.rsplit("/", 1)[-1]
    schema_type = schema.get("type")
    if schema_type == "array":
        return f"array[{_schema_label(schema.get('items'))}]"
    if schema_type:
        return str(schema_type)
    for compound_key in ("allOf", "anyOf", "oneOf"):
        variants = schema.get(compound_key)
        if isinstance(variants, list) and variants:
            return f"{compound_key}[" + ",".join(_schema_label(item) for item in variants) + "]"
    title = schema.get("title")
    if isinstance(title, str) and title:
        return title
    return "inline"


def _type_label(type_: Any) -> str:
    if type_ is None:
        return "none"
    name = getattr(type_, "__name__", None)
    if isinstance(name, str) and name:
        return name
    text = str(type_)
    if text.startswith("<class '") and text.endswith("'>"):
        return text[len("<class '") : -2]
    return text.replace("typing.", "")


def _route_source_module(route: APIRoute | None) -> str:
    if route is None:
        return "unknown"
    module = getattr(route.endpoint, "__module__", "")
    if module.startswith("app.api."):
        return f"{module.removeprefix('app.api.')}.py"
    if module == "app.main":
        return "main.py"
    return module or "unknown"


def _route_index(app: Any) -> dict[tuple[str, str], APIRoute]:
    index: dict[tuple[str, str], APIRoute] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods or []):
            if method in HTTP_METHODS:
                index[(method, route.path)] = route
    return index


def _parameter_names(operation: dict[str, Any], location: str) -> str:
    values: list[str] = []
    for parameter in operation.get("parameters", []):
        if not isinstance(parameter, dict) or parameter.get("in") != location:
            continue
        name = str(parameter.get("name") or "")
        if not name:
            continue
        suffix = "" if bool(parameter.get("required")) else "?"
        values.append(f"{name}{suffix}")
    return ", ".join(values) if values else "-"


def _request_body(operation: dict[str, Any]) -> tuple[str, bool]:
    request_body = operation.get("requestBody")
    if not isinstance(request_body, dict):
        return "-", False
    content = request_body.get("content")
    if not isinstance(content, dict):
        return "untyped", bool(request_body.get("required"))
    json_media = content.get("application/json")
    if not isinstance(json_media, dict):
        return "non-json", bool(request_body.get("required"))
    return _schema_label(json_media.get("schema")), bool(request_body.get("required"))


def _response_200_schema(operation: dict[str, Any]) -> str:
    response = operation.get("responses", {}).get("200")
    if not isinstance(response, dict):
        return "missing"
    content = response.get("content")
    if not isinstance(content, dict):
        return "no-content"
    json_media = content.get("application/json")
    if not isinstance(json_media, dict):
        return "non-json"
    return _schema_label(json_media.get("schema"))


def _status_codes(operation: dict[str, Any]) -> str:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return "-"
    return ", ".join(sorted(str(code) for code in responses))


def build_inventory(app: Any) -> dict[str, Any]:
    schema = app.openapi()
    routes = _route_index(app)
    operations: list[dict[str, Any]] = []

    for path, path_item in schema.get("paths", {}).items():
        if not str(path).startswith("/api/v1/") or not isinstance(path_item, dict):
            continue
        for method in HTTP_METHODS:
            operation = path_item.get(method.lower())
            if not isinstance(operation, dict):
                continue
            route = routes.get((method, path))
            request_body, request_body_required = _request_body(operation)
            operations.append(
                {
                    "method": method,
                    "path": path,
                    "operation_id": operation.get("operationId") or "-",
                    "source_module": _route_source_module(route),
                    "handler": getattr(route, "name", "-") if route else "-",
                    "tag": ", ".join(operation.get("tags") or []) or "-",
                    "path_params": _parameter_names(operation, "path"),
                    "query_params": _parameter_names(operation, "query"),
                    "request_body": request_body,
                    "request_body_required": request_body_required,
                    "response_model": _type_label(getattr(route, "response_model", None) if route else None),
                    "response_200_schema": _response_200_schema(operation),
                    "status_codes": _status_codes(operation),
                }
            )

    method_counts = Counter(operation["method"] for operation in operations)
    response_schema_counts = Counter(operation["response_200_schema"] for operation in operations)
    source_counts = defaultdict(lambda: Counter())
    for operation in operations:
        bucket = source_counts[operation["source_module"]]
        bucket["operations"] += 1
        if operation["request_body"] != "-":
            bucket["request_bodies"] += 1
        if operation["response_model"] != "none":
            bucket["response_models"] += 1
        if operation["response_200_schema"] == "untyped":
            bucket["untyped_200"] += 1

    source_summary = [
        {
            "source_module": module,
            "operations": counts["operations"],
            "request_bodies": counts["request_bodies"],
            "response_models": counts["response_models"],
            "untyped_200": counts["untyped_200"],
        }
        for module, counts in sorted(source_counts.items())
    ]
    api_router_operations = sum(
        1
        for operation in operations
        if operation["source_module"].endswith(".py") and operation["source_module"] != "main.py"
    )
    summary = {
        "api_v1_operations": len(operations),
        "api_router_operations": api_router_operations,
        "app_level_operations": len(operations) - api_router_operations,
        "component_schemas": len(schema.get("components", {}).get("schemas", {})),
        "method_counts": {method: method_counts.get(method, 0) for method in HTTP_METHODS},
        "request_body_operations": sum(1 for operation in operations if operation["request_body"] != "-"),
        "explicit_response_model_operations": sum(
            1 for operation in operations if operation["response_model"] != "none"
        ),
        "untyped_openapi_200_operations": response_schema_counts.get("untyped", 0),
        "response_200_schema_counts": dict(sorted(response_schema_counts.items())),
    }
    return {"summary": summary, "source_summary": source_summary, "operations": operations}


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _render_source_summary(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Source Module | Operations | Request Bodies | Explicit Response Models | Untyped 200 Schemas |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {source_module} | {operations} | {request_bodies} | {response_models} | {untyped_200} |".format(
                **{key: _md(value) for key, value in row.items()}
            )
        )
    return "\n".join(lines)


def _render_operations(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Method | Path | Handler | Source | Path Params | Query Params | Request Body | Response Model | 200 Schema | Statuses |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        request_body = row["request_body"]
        if request_body != "-" and not row["request_body_required"]:
            request_body = f"{request_body} (optional)"
        lines.append(
            "| {method} | `{path}` | `{handler}` | `{source_module}` | {path_params} | {query_params} | `{request_body}` | `{response_model}` | `{response_200_schema}` | {status_codes} |".format(
                method=_md(row["method"]),
                path=_md(row["path"]),
                handler=_md(row["handler"]),
                source_module=_md(row["source_module"]),
                path_params=_md(row["path_params"]),
                query_params=_md(row["query_params"]),
                request_body=_md(request_body),
                response_model=_md(row["response_model"]),
                response_200_schema=_md(row["response_200_schema"]),
                status_codes=_md(row["status_codes"]),
            )
        )
    return "\n".join(lines)


def render_markdown(inventory: dict[str, Any]) -> str:
    summary = inventory["summary"]
    method_counts = ", ".join(
        f"`{method}` {count}" for method, count in summary["method_counts"].items() if count
    )
    response_counts = ", ".join(
        f"`{name}` {count}" for name, count in summary["response_200_schema_counts"].items()
    )
    return f"""# Backend API Schema Inventory (Current)

> Status: CURRENT as of 2026-05-22. Generated from the running FastAPI app OpenAPI surface by `main/backend/scripts/generate_api_schema_inventory.py`.
>
> Scope: every `/api/v1` OpenAPI operation exposed by `app.main.app`, including the {summary["api_router_operations"]} router operations covered by `API_ROUTE_MAP_2026-05-22.md` plus {summary["app_level_operations"]} non-`app.api` operations (`/api/v1/health`, `/api/v1/health/deep`, `/api/v1/maps/usa`).
>
> Drift guard: `main/backend/tests/contract/test_api_schema_inventory_contract_unittest.py` regenerates this document from the current FastAPI OpenAPI schema and compares it byte-for-byte.

## Summary

- OpenAPI `/api/v1` operations: **{summary["api_v1_operations"]}**.
- API router operations also covered by `API_ROUTE_MAP_2026-05-22.md`: **{summary["api_router_operations"]}**.
- App-level `/api/v1` operations outside `main/backend/app/api/*.py`: **{summary["app_level_operations"]}**.
- Component schemas advertised by OpenAPI: **{summary["component_schemas"]}**.
- Method distribution: {method_counts}.
- Operations with JSON request bodies: **{summary["request_body_operations"]}**.
- Operations with explicit FastAPI `response_model`: **{summary["explicit_response_model_operations"]}**.
- Operations whose OpenAPI 200 response schema is still untyped: **{summary["untyped_openapi_200_operations"]}**.
- 200 response schema distribution: {response_counts}.

## Contract Meaning

This inventory records the request-body models, visible response models, OpenAPI 200-response schema labels, parameters, operation IDs, and response status-code sets that clients can infer from the current FastAPI application.

It does not prove runtime envelope conformance for every handler. A typed OpenAPI surface can still use conservative `dict[str, Any]`, `Any`, `object`, `non-json`, or `missing` response labels where handlers return legacy payloads, redirects, static/non-JSON content, or status-code-specific responses. Tightening those internals needs per-route runtime envelope tests beyond this schema-surface inventory.

## Source Summary

{_render_source_summary(inventory["source_summary"])}

## Operation Inventory

{_render_operations(inventory["operations"])}
"""


def main() -> None:
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from app.main import app

    inventory = build_inventory(app)
    DEFAULT_DOC_PATH.write_text(render_markdown(inventory), encoding="utf-8")
    print(f"wrote {DEFAULT_DOC_PATH}")


if __name__ == "__main__":
    main()
