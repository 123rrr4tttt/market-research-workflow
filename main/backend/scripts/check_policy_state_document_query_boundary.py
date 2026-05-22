#!/usr/bin/env python3
"""Wave17 policy state endpoint document-query boundary gate."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "policy-state-document-query-boundary.wave17.v1"
TOPIC_ID = "2026-03-14-consumer-side-modularization"
STRUCTURED_TOPIC_ID = "2026-03-12-data-structured-service-modularization"
SURFACE_PATH = "main/backend/app/api/policies.py"
FUNCTION_NAME = "get_state_policies"
QUERY_HELPER = "main/backend/app/services/document_queries/policy_filters.py"
REQUIRED_HELPER_CALLS = ("policy_state_condition", "policy_time_expr")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse(path: Path) -> ast.AST:
    return ast.parse(_read_text(path), filename=str(path))


def _function_map(tree: ast.AST) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


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


def _direct_document_extracted_data_reads(func: ast.AST) -> list[dict[str, Any]]:
    reads: list[dict[str, Any]] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Attribute) and _is_document_extracted_data(node):
            reads.append(
                {
                    "line": getattr(node, "lineno", 0),
                    "column": getattr(node, "col_offset", 0),
                    "expression": "Document.extracted_data",
                }
            )
    return reads


def _import_tokens(tree: ast.AST) -> set[str]:
    tokens: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                tokens.add(module)
            for alias in node.names:
                tokens.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                tokens.add(alias.asname or alias.name)
    return tokens


def build_check(root: Path | None = None) -> dict[str, Any]:
    repo_root = root or _repo_root()
    surface = repo_root / SURFACE_PATH
    helper = repo_root / QUERY_HELPER
    problems: list[str] = []

    surface_tree = _parse(surface)
    helper_tree = _parse(helper)
    functions = _function_map(surface_tree)
    target = functions.get(FUNCTION_NAME)
    if target is None:
        problems.append(f"missing function {FUNCTION_NAME}")
        calls: set[str] = set()
        direct_reads: list[dict[str, Any]] = []
    else:
        calls = _called_names(target)
        direct_reads = _direct_document_extracted_data_reads(target)

    imports = _import_tokens(surface_tree)
    helper_functions = set(_function_map(helper_tree))
    missing_imports = [name for name in REQUIRED_HELPER_CALLS if name not in imports]
    missing_calls = [name for name in REQUIRED_HELPER_CALLS if name not in calls]
    missing_helper_defs = [name for name in REQUIRED_HELPER_CALLS if name not in helper_functions]

    if missing_imports:
        problems.append(f"missing document_queries imports: {missing_imports}")
    if missing_calls:
        problems.append(f"{FUNCTION_NAME} missing helper calls: {missing_calls}")
    if missing_helper_defs:
        problems.append(f"missing helper definitions: {missing_helper_defs}")
    if direct_reads:
        problems.append(f"{FUNCTION_NAME} still reads Document.extracted_data directly")

    return {
        "contract_version": CONTRACT_VERSION,
        "topic_id": TOPIC_ID,
        "structured_topic_id": STRUCTURED_TOPIC_ID,
        "status": "passed" if not problems else "failed",
        "surface": {
            "path": SURFACE_PATH,
            "function": FUNCTION_NAME,
            "endpoint": "/api/v1/policies/state/{state}",
            "required_helper_calls": list(REQUIRED_HELPER_CALLS),
            "missing_imports": missing_imports,
            "missing_calls": missing_calls,
            "direct_document_extracted_data_reads": direct_reads,
        },
        "helper": {
            "path": QUERY_HELPER,
            "missing_definitions": missing_helper_defs,
        },
        "validation": {
            "passed": not problems,
            "problem_count": len(problems),
            "problems": problems,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print the full JSON report")
    args = parser.parse_args()

    result = build_check()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"{result['status'].upper()} {CONTRACT_VERSION} "
            f"surface={SURFACE_PATH}:{FUNCTION_NAME} "
            f"problems={result['validation']['problem_count']}"
        )
    return 0 if result["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
