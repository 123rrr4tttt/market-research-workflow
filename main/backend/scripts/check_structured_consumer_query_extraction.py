#!/usr/bin/env python3
"""Check Wave11 structured consumer query extraction boundary."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


DOCUMENT_QUERY_CONTRACT_VERSION = "document_queries.v1"
REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
PROMPT_TIME_DENSITY_PATH = BACKEND_ROOT / "app" / "services" / "stats" / "prompt_time_density.py"
POLICY_FILTERS_PATH = BACKEND_ROOT / "app" / "services" / "document_queries" / "policy_filters.py"


def _read_tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imports_prompt_time_density_query_boundary(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "document_queries" or node.level < 1:
            continue
        if any(alias.name == "prompt_time_density_time_expr" for alias in node.names):
            return True
    return False


def _function_names(tree: ast.AST) -> set[str]:
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def _function_calls_name(tree: ast.AST, *, function_name: str, called_name: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != function_name:
            continue
        return any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == called_name
            for child in ast.walk(node)
        )
    return False


def build_check() -> dict[str, Any]:
    prompt_tree = _read_tree(PROMPT_TIME_DENSITY_PATH)
    prompt_text = PROMPT_TIME_DENSITY_PATH.read_text(encoding="utf-8")
    policy_tree = _read_tree(POLICY_FILTERS_PATH)
    policy_text = POLICY_FILTERS_PATH.read_text(encoding="utf-8")
    prompt_function_names = _function_names(prompt_tree)
    policy_function_names = _function_names(policy_tree)
    checks = {
        "imports_document_query_boundary": _imports_prompt_time_density_query_boundary(prompt_tree),
        "query_function_uses_document_query_boundary": _function_calls_name(
            prompt_tree,
            function_name="query_prompt_time_density",
            called_name="prompt_time_density_time_expr",
        ),
        "local_json_iso_date_expr_removed": "_json_iso_date_expr" not in prompt_function_names,
        "local_effective_date_expr_removed": "_effective_date_expr" not in prompt_function_names,
        "no_local_document_extracted_data_sql_path": "Document.extracted_data[" not in prompt_text,
        "document_json_iso_date_expr_exported": "document_json_iso_date_expr" in policy_function_names,
        "prompt_time_density_time_expr_exported": "prompt_time_density_time_expr" in policy_function_names,
        "prompt_time_density_time_expr_uses_policy_time_expr": _function_calls_name(
            policy_tree,
            function_name="prompt_time_density_time_expr",
            called_name="policy_time_expr",
        ),
        "query_boundary_has_effective_time": "effective_time" in policy_text,
        "query_boundary_has_source_time": "source_time" in policy_text,
        "query_boundary_has_policy_effective_date": "effective_date" in policy_text,
    }
    passed = all(checks.values())
    return {
        "status": "passed" if passed else "failed",
        "contract_version": DOCUMENT_QUERY_CONTRACT_VERSION,
        "topic_ids": [
            "2026-03-12-data-structured-service-modularization",
            "2026-03-14-consumer-side-modularization",
        ],
        "query_boundary": "main/backend/app/services/document_queries.prompt_time_density_time_expr",
        "consumer_surface": str(PROMPT_TIME_DENSITY_PATH.relative_to(REPO_ROOT)),
        "checks": checks,
    }


def main() -> int:
    result = build_check()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
