#!/usr/bin/env python3
"""Wave15 admin/dashboard SQL JSON predicate facade gate."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "consumer.sql_predicate_facade.wave15.v1"
TOPIC_ID = "2026-03-14-consumer-side-modularization"
QUERY_FACADE = "main/backend/app/services/document_queries/consumer_predicates.py"
QUERY_BOUNDARY = "main/backend/app/services/document_queries"
BOUNDARY_RULE = (
    "admin.py and dashboard.py consumer SQL JSON predicates must call document_queries; "
    "Document.extracted_data[...] expressions are owned by the query facade."
)

CHECKED_SURFACES = (
    "main/backend/app/api/admin.py",
    "main/backend/app/api/dashboard.py",
)

REQUIRED_FACADE_FUNCTIONS = (
    "content_graph_structured_condition",
    "document_extracted_data_present_case",
    "document_has_extracted_data_condition",
    "document_missing_extracted_data_condition",
    "document_publish_or_created_on_or_after_condition",
    "document_publish_or_created_on_or_before_condition",
    "market_game_condition",
    "market_graph_structured_condition",
    "market_publish_created_or_report_on_or_after_condition",
    "market_publish_created_or_report_on_or_before_condition",
    "market_report_date_expr",
    "market_state_condition",
    "policy_graph_has_data_condition",
    "policy_graph_state_condition",
    "policy_graph_type_ilike_condition",
    "social_document_base_conditions",
    "social_platform_condition",
    "social_sentiment_orientation_condition",
)

REQUIRED_CALLS = {
    "main/backend/app/api/admin.py": {
        "list_documents": (
            "document_has_extracted_data_condition",
            "document_missing_extracted_data_condition",
        ),
        "list_social_data": (
            "social_platform_condition",
            "social_sentiment_orientation_condition",
        ),
        "get_content_graph": ("content_graph_structured_condition",),
        "get_market_graph": (
            "market_graph_structured_condition",
            "market_state_condition",
            "market_game_condition",
            "market_publish_created_or_report_on_or_after_condition",
            "market_publish_created_or_report_on_or_before_condition",
        ),
        "get_policy_graph": (
            "policy_graph_has_data_condition",
            "policy_graph_state_condition",
            "policy_graph_type_ilike_condition",
        ),
    },
    "main/backend/app/api/dashboard.py": {
        "get_dashboard_stats": ("document_has_extracted_data_condition",),
        "get_document_analysis": ("document_extracted_data_present_case",),
        "get_sentiment_analysis": ("social_document_base_conditions",),
        "get_sentiment_sources": ("social_document_base_conditions",),
    },
}


@dataclass(frozen=True)
class SqlJsonRead:
    line: int
    column: int
    expression: str
    function: str | None = None


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


def _function_names(tree: ast.AST) -> set[str]:
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _called_names(func: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def _is_document_extracted_data(node: ast.Attribute) -> bool:
    return (
        node.attr == "extracted_data"
        and isinstance(node.value, ast.Name)
        and node.value.id == "Document"
    )


def _sql_json_reads(tree: ast.AST, *, function_name: str | None = None) -> list[SqlJsonRead]:
    reads: list[SqlJsonRead] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and _is_document_extracted_data(node):
            reads.append(
                SqlJsonRead(
                    line=getattr(node, "lineno", 0),
                    column=getattr(node, "col_offset", 0),
                    expression=_expression(node),
                    function=function_name,
                )
            )
    return reads


def _surface_result(root: Path, rel_path: str) -> dict[str, Any]:
    path = root / rel_path
    exists = path.is_file()
    tree = _parse(path) if exists else None
    imports = _import_tokens(tree) if tree is not None else set()
    functions = _function_map(tree) if tree is not None else {}
    direct_reads = _sql_json_reads(tree) if tree is not None else []
    missing_imports = [] if "document_queries" in imports else ["document_queries"]

    function_results: list[dict[str, Any]] = []
    for name, required_calls in REQUIRED_CALLS.get(rel_path, {}).items():
        func = functions.get(name)
        if func is None:
            function_results.append(
                {
                    "name": name,
                    "exists": False,
                    "required_facade_calls": list(required_calls),
                    "missing_facade_calls": list(required_calls),
                    "direct_document_extracted_data_reads": [],
                    "passed": False,
                }
            )
            continue

        called_names = _called_names(func)
        missing_calls = [call for call in required_calls if call not in called_names]
        function_direct_reads = _sql_json_reads(func, function_name=name)
        function_results.append(
            {
                "name": name,
                "exists": True,
                "required_facade_calls": list(required_calls),
                "missing_facade_calls": missing_calls,
                "direct_document_extracted_data_reads": [read.__dict__ for read in function_direct_reads],
                "passed": not missing_calls and not function_direct_reads,
            }
        )

    passed = exists and not missing_imports and not direct_reads and all(item["passed"] for item in function_results)
    return {
        "path": rel_path,
        "exists": exists,
        "required_imports": ["document_queries"],
        "missing_imports": missing_imports,
        "direct_document_extracted_data_reads": [read.__dict__ for read in direct_reads],
        "functions": function_results,
        "passed": passed,
    }


def _facade_result(root: Path) -> dict[str, Any]:
    path = root / QUERY_FACADE
    exists = path.is_file()
    tree = _parse(path) if exists else None
    function_names = _function_names(tree) if tree is not None else set()
    missing_functions = [name for name in REQUIRED_FACADE_FUNCTIONS if name not in function_names]
    direct_reads = _sql_json_reads(tree) if tree is not None else []
    return {
        "path": QUERY_FACADE,
        "exists": exists,
        "required_functions": list(REQUIRED_FACADE_FUNCTIONS),
        "missing_functions": missing_functions,
        "owned_document_extracted_data_expression_count": len(direct_reads),
        "passed": exists and not missing_functions and bool(direct_reads),
    }


def _export_result(root: Path) -> dict[str, Any]:
    init_path = root / QUERY_BOUNDARY / "__init__.py"
    exists = init_path.is_file()
    text = _read_text(init_path) if exists else ""
    missing_exports = [name for name in REQUIRED_FACADE_FUNCTIONS if name not in text]
    return {
        "path": f"{QUERY_BOUNDARY}/__init__.py",
        "exists": exists,
        "missing_exports": missing_exports,
        "passed": exists and not missing_exports,
    }


def build_check(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _repo_root()
    root = root.resolve()
    facade = _facade_result(root)
    exports = _export_result(root)
    surfaces = [_surface_result(root, rel_path) for rel_path in CHECKED_SURFACES]
    direct_api_reads = sum(len(surface["direct_document_extracted_data_reads"]) for surface in surfaces)
    checked_functions = sum(len(surface["functions"]) for surface in surfaces)
    all_passed = facade["passed"] and exports["passed"] and all(surface["passed"] for surface in surfaces)
    return {
        "contract_version": CONTRACT_VERSION,
        "topic_id": TOPIC_ID,
        "status": "passed" if all_passed else "failed",
        "boundary_rule": BOUNDARY_RULE,
        "sql_json_query_boundary": QUERY_BOUNDARY,
        "facade": facade,
        "exports": exports,
        "checked_surfaces": surfaces,
        "validation": {
            "passed": all_passed,
            "checked_api_surface_count": len(surfaces),
            "checked_consumer_query_function_count": checked_functions,
            "direct_admin_dashboard_document_extracted_data_read_count": direct_api_reads,
            "covered_scope": (
                "admin.py and dashboard.py no longer own Document.extracted_data SQL JSON predicates; "
                "selected document-view consumer queries call document_queries helpers."
            ),
            "remaining_boundary": (
                "Document.extracted_data SQL JSON paths remain inside document_queries helper modules. "
                "This gate does not claim non-admin/dashboard consumers or Python instance-level writer/governance paths."
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Wave15 admin/dashboard SQL JSON predicate facade.")
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
