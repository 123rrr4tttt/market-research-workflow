#!/usr/bin/env python3
"""Wave20 prompt-time-density consumer facade boundary gate."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "prompt-time-density-consumer-facade.wave20.v1"
TOPIC_ID = "2026-03-14-consumer-side-modularization"
SURFACE_PATH = "main/backend/app/services/stats/prompt_time_density.py"
FACADE_PATH = "main/backend/app/services/document_views/stats_view.py"
REQUIRED_FACADE_CALLS = {
    "resolve_document_effective_time_provenance": ("get_prompt_time_density_fields",),
    "_prompt_group_of": ("get_prompt_time_density_group",),
    "_source_domain_of": ("get_prompt_time_density_source_domain",),
}


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


def _called_names(node: ast.AST) -> set[str]:
    calls: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                calls.add(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                calls.add(child.func.attr)
    return calls


def _import_tokens(tree: ast.AST) -> set[str]:
    tokens: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                tokens.add(alias.asname or alias.name)
                tokens.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                tokens.add(module)
                parts = module.split(".")
                for index in range(len(parts)):
                    tokens.add(".".join(parts[index:]))
            for alias in node.names:
                tokens.add(alias.asname or alias.name)
                tokens.add(alias.name)
    return tokens


def _direct_extracted_data_reads(tree: ast.AST) -> list[dict[str, Any]]:
    reads: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "extracted_data":
            reads.append(
                {
                    "line": getattr(node, "lineno", 0),
                    "column": getattr(node, "col_offset", 0),
                    "expression": ast.unparse(node),
                }
            )
    return reads


def build_check(root: Path | None = None) -> dict[str, Any]:
    repo_root = root or _repo_root()
    surface = repo_root / SURFACE_PATH
    facade = repo_root / FACADE_PATH
    problems: list[str] = []

    surface_tree = _parse(surface) if surface.is_file() else None
    facade_tree = _parse(facade) if facade.is_file() else None
    if surface_tree is None:
        problems.append(f"missing surface: {SURFACE_PATH}")
    if facade_tree is None:
        problems.append(f"missing facade: {FACADE_PATH}")

    surface_imports = _import_tokens(surface_tree) if surface_tree is not None else set()
    required_imports = sorted({name for calls in REQUIRED_FACADE_CALLS.values() for name in calls})
    missing_imports = [name for name in required_imports if name not in surface_imports]
    if missing_imports:
        problems.append(f"missing document_views imports: {missing_imports}")

    direct_reads = _direct_extracted_data_reads(surface_tree) if surface_tree is not None else []
    if direct_reads:
        problems.append(f"{SURFACE_PATH} still reads extracted_data directly")

    facade_functions = set(_function_map(facade_tree)) if facade_tree is not None else set()
    missing_facade_defs = [name for name in required_imports if name not in facade_functions]
    if missing_facade_defs:
        problems.append(f"missing facade definitions: {missing_facade_defs}")

    surface_functions = _function_map(surface_tree) if surface_tree is not None else {}
    function_results: list[dict[str, Any]] = []
    for function_name, required_calls in REQUIRED_FACADE_CALLS.items():
        func = surface_functions.get(function_name)
        if func is None:
            missing_calls = list(required_calls)
            function_problems = [f"missing function {function_name}"]
        else:
            calls = _called_names(func)
            missing_calls = [name for name in required_calls if name not in calls]
            function_problems = []
        if missing_calls:
            function_problems.append(f"missing facade calls: {missing_calls}")
        problems.extend(f"{function_name}: {problem}" for problem in function_problems)
        function_results.append(
            {
                "name": function_name,
                "exists": func is not None,
                "required_facade_calls": list(required_calls),
                "missing_facade_calls": missing_calls,
                "passed": func is not None and not missing_calls,
            }
        )

    return {
        "contract_version": CONTRACT_VERSION,
        "topic_id": TOPIC_ID,
        "status": "passed" if not problems else "failed",
        "surface": {
            "path": SURFACE_PATH,
            "required_document_view_imports": required_imports,
            "missing_document_view_imports": missing_imports,
            "direct_extracted_data_reads": direct_reads,
            "functions": function_results,
        },
        "facade": {
            "path": FACADE_PATH,
            "missing_definitions": missing_facade_defs,
        },
        "validation": {
            "passed": not problems,
            "problem_count": len(problems),
            "problems": problems,
            "covered_scope": (
                "prompt_time_density Python-level structured field reads use document_views; "
                "SQL date predicates remain in document_queries."
            ),
            "remaining_boundary": (
                "No live DB/API smoke is claimed. This does not cover admin governance writes or other consumer slices."
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check prompt-time-density consumer facade boundary.")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build_check()
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
