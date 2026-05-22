#!/usr/bin/env python3
"""Wave13 admin/dashboard consumer read boundary gate."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "consumer.admin_dashboard_boundary.wave13.v1"
TOPIC_ID = "2026-03-14-consumer-side-modularization"
BOUNDARY_RULE = (
    "Selected admin/dashboard Python consumer reads must route through document_views; "
    "Document.extracted_data SQL JSON predicates are checked by the Wave15 document_queries facade gate."
)

CHECKED_FUNCTIONS = {
    "main/backend/app/api/dashboard.py": (
        "get_sentiment_analysis",
        "get_sentiment_sources",
    ),
    "main/backend/app/api/admin.py": (
        "_augment_market_graph_with_topic_structured",
        "list_social_data",
        "get_content_graph",
        "get_market_graph",
        "get_policy_graph",
    ),
}

REQUIRED_BOUNDARY_IMPORTS = {
    "main/backend/app/api/dashboard.py": ("document_views",),
    "main/backend/app/api/admin.py": ("document_views",),
}

REQUIRED_BOUNDARY_CALLS = {
    "get_sentiment_analysis": ("get_social_sentiment_orientation", "get_social_platform_label", "get_social_sentiment_terms"),
    "get_sentiment_sources": ("get_social_sentiment_orientation", "get_social_platform_label"),
    "_augment_market_graph_with_topic_structured": ("get_extracted_data",),
    "list_social_data": ("build_social_data_item",),
    "get_content_graph": ("get_social_platform_label", "get_social_sentiment"),
    "get_market_graph": ("get_market_data",),
    "get_policy_graph": ("get_policy_data",),
}


@dataclass(frozen=True)
class DirectRead:
    line: int
    column: int
    expression: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _parse(path: Path) -> ast.AST:
    return ast.parse(_read_text(path), filename=str(path))


def _expression(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001
        return node.__class__.__name__


def _import_tokens(tree: ast.AST) -> set[str]:
    tokens: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                tokens.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            tokens.add(module)
            if module:
                parts = module.split(".")
                for index in range(len(parts)):
                    tokens.add(".".join(parts[index:]))
            for alias in node.names:
                tokens.add(alias.name)
    return tokens


def _function_map(tree: ast.AST) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _is_sql_model_extracted_data(node: ast.Attribute) -> bool:
    return isinstance(node.value, ast.Name) and node.value.id == "Document"


def _direct_instance_reads(func: ast.AST) -> list[DirectRead]:
    reads: list[DirectRead] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Attribute) and node.attr == "extracted_data":
            if _is_sql_model_extracted_data(node):
                continue
            reads.append(
                DirectRead(
                    line=getattr(node, "lineno", 0),
                    column=getattr(node, "col_offset", 0),
                    expression=_expression(node),
                )
            )
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "extracted_data"
        ):
            reads.append(
                DirectRead(
                    line=getattr(node, "lineno", 0),
                    column=getattr(node, "col_offset", 0),
                    expression=_expression(node),
                )
            )
    return reads


def _sql_model_read_count(func: ast.AST) -> int:
    return sum(
        1
        for node in ast.walk(func)
        if isinstance(node, ast.Attribute)
        and node.attr == "extracted_data"
        and _is_sql_model_extracted_data(node)
    )


def _called_names(func: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def _surface_result(root: Path, rel_path: str, function_names: tuple[str, ...]) -> dict[str, Any]:
    path = root / rel_path
    exists = path.is_file()
    tree = _parse(path) if exists else None
    functions = _function_map(tree) if tree is not None else {}
    imports = _import_tokens(tree) if tree is not None else set()
    required_imports = REQUIRED_BOUNDARY_IMPORTS.get(rel_path, ())
    missing_imports = [token for token in required_imports if token not in imports]

    function_results: list[dict[str, Any]] = []
    for name in function_names:
        func = functions.get(name)
        required_calls = REQUIRED_BOUNDARY_CALLS.get(name, ())
        if func is None:
            function_results.append(
                {
                    "name": name,
                    "exists": False,
                    "direct_instance_extracted_data_reads": [],
                    "required_boundary_calls": list(required_calls),
                    "missing_boundary_calls": list(required_calls),
                    "sql_json_expression_count": 0,
                    "passed": False,
                }
            )
            continue

        direct_reads = _direct_instance_reads(func)
        called_names = _called_names(func)
        missing_calls = [call for call in required_calls if call not in called_names]
        function_results.append(
            {
                "name": name,
                "exists": True,
                "direct_instance_extracted_data_reads": [read.__dict__ for read in direct_reads],
                "required_boundary_calls": list(required_calls),
                "missing_boundary_calls": missing_calls,
                "sql_json_expression_count": _sql_model_read_count(func),
                "passed": not direct_reads and not missing_calls,
            }
        )

    passed = exists and not missing_imports and all(item["passed"] for item in function_results)
    return {
        "path": rel_path,
        "exists": exists,
        "required_boundary_imports": list(required_imports),
        "missing_boundary_imports": missing_imports,
        "functions": function_results,
        "passed": passed,
    }


def build_check(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _repo_root()
    root = root.resolve()
    surfaces = [
        _surface_result(root, rel_path, function_names)
        for rel_path, function_names in CHECKED_FUNCTIONS.items()
    ]
    all_passed = all(item["passed"] for item in surfaces)
    direct_read_count = sum(
        len(function["direct_instance_extracted_data_reads"])
        for surface in surfaces
        for function in surface["functions"]
    )
    sql_json_count = sum(
        int(function["sql_json_expression_count"])
        for surface in surfaces
        for function in surface["functions"]
    )
    checked_functions = sum(len(surface["functions"]) for surface in surfaces)
    return {
        "contract_version": CONTRACT_VERSION,
        "topic_id": TOPIC_ID,
        "status": "passed" if all_passed else "failed",
        "boundary_rule": BOUNDARY_RULE,
        "python_read_facade": "main/backend/app/services/document_views",
        "checked_surfaces": surfaces,
        "validation": {
            "passed": all_passed,
            "checked_python_consumer_function_count": checked_functions,
            "direct_instance_extracted_data_read_count": direct_read_count,
            "allowed_sql_json_expression_count": sql_json_count,
            "query_layer_deferred_scope": (
                "Wave13 only guards Python instance reads. Wave15 owns the admin/dashboard SQL JSON predicate "
                "facade gate and should keep this count at zero for selected functions."
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Wave13 admin/dashboard consumer read boundary evidence.")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build_check()
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
