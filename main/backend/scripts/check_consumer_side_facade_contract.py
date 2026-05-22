#!/usr/bin/env python3
"""Wave9 consumer-side facade/query boundary gate."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "consumer.facade_boundary.wave9.v1"
BOUNDARY_RULE = (
    "Python consumer surfaces read structured document fields through document_views; "
    "SQL JSON predicates and sort expressions stay in document_queries or documented query-only bridges."
)
TOPIC_ID = "2026-03-14-consumer-side-modularization"

PYTHON_READ_SURFACES = (
    "main/backend/app/services/graph/adapters/__init__.py",
    "main/backend/app/services/graph/adapters/generic.py",
    "main/backend/app/services/graph/adapters/market.py",
    "main/backend/app/services/graph/adapters/policy.py",
    "main/backend/app/services/graph/adapters/reddit.py",
    "main/backend/app/services/writing/keyword_card_service.py",
    "main/backend/app/services/writing/search_suggest_service.py",
    "main/backend/app/services/writing/document_service.py",
    "main/backend/app/services/writing/citation_service.py",
    "main/backend/app/api/search.py",
    "main/backend/app/api/writing.py",
)

BOUNDARY_IMPORT_REQUIREMENTS = {
    "main/backend/app/services/graph/adapters/__init__.py": ("document_views",),
    "main/backend/app/services/graph/adapters/generic.py": ("document_views",),
    "main/backend/app/services/graph/adapters/market.py": ("document_views",),
    "main/backend/app/services/graph/adapters/policy.py": ("document_views",),
    "main/backend/app/services/graph/adapters/reddit.py": ("document_views",),
    "main/backend/app/services/writing/keyword_card_service.py": ("document_queries", "document_views"),
    "main/backend/app/services/writing/search_suggest_service.py": ("document_queries",),
    "main/backend/app/services/writing/document_service.py": ("document_queries", "document_views"),
    "main/backend/app/services/writing/citation_service.py": ("document_queries", "document_views"),
}

PROHIBITED_IMPORT_TOKENS = {
    "main/backend/app/services/writing/search_suggest_service.py": ("source_library.resolver",),
}

DEFERRED_QUERY_SURFACES = (
    "main/backend/app/api/admin.py",
    "main/backend/app/api/dashboard.py",
)

EXTRACTED_QUERY_SURFACES = (
    "main/backend/app/services/stats/prompt_time_density.py",
)


def get_consumer_boundary_snapshot() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "boundary_rule": BOUNDARY_RULE,
        "python_read_facade": "main/backend/app/services/document_views",
        "sql_json_query_boundary": "main/backend/app/services/document_queries",
        "worker5_scope": [
            "graph.adapters_python_read_boundary",
            "writing.suggest_material_query_boundary",
            "search.api_no_document_json_read",
        ],
        "worker4_boundary": "does_not_modify_document_queries_core",
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


def _direct_extracted_data_reads(tree: ast.AST) -> list[DirectRead]:
    reads: list[DirectRead] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "extracted_data":
            reads.append(
                DirectRead(
                    line=getattr(node, "lineno", 0),
                    column=getattr(node, "col_offset", 0),
                    expression=ast.unparse(node),
                )
            )
    return reads


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


def _surface_result(root: Path, rel_path: str) -> dict[str, Any]:
    path = root / rel_path
    exists = path.is_file()
    tree = _parse(path) if exists else None
    reads = _direct_extracted_data_reads(tree) if tree is not None else []
    imports = _import_tokens(tree) if tree is not None else set()
    required = BOUNDARY_IMPORT_REQUIREMENTS.get(rel_path, ())
    prohibited = PROHIBITED_IMPORT_TOKENS.get(rel_path, ())
    missing_required = [token for token in required if token not in imports]
    prohibited_hits = [token for token in prohibited if token in imports]
    passed = exists and not reads and not missing_required and not prohibited_hits
    return {
        "path": rel_path,
        "exists": exists,
        "direct_extracted_data_reads": [read.__dict__ for read in reads],
        "required_boundary_imports": list(required),
        "missing_boundary_imports": missing_required,
        "prohibited_query_bypass_imports": prohibited_hits,
        "passed": passed,
    }


def build_check(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _repo_root()
    root = root.resolve()
    surfaces = [_surface_result(root, rel_path) for rel_path in PYTHON_READ_SURFACES]
    all_passed = all(item["passed"] for item in surfaces)
    return {
        "contract_version": CONTRACT_VERSION,
        "topic_id": TOPIC_ID,
        "status": "passed" if all_passed else "failed",
        "boundary": get_consumer_boundary_snapshot(),
        "surfaces": surfaces,
        "validation": {
            "passed": all_passed,
            "checked_python_read_surface_count": len(surfaces),
            "direct_extracted_data_read_count": sum(len(item["direct_extracted_data_reads"]) for item in surfaces),
            "deferred_query_surfaces": list(DEFERRED_QUERY_SURFACES),
            "extracted_query_surfaces": list(EXTRACTED_QUERY_SURFACES),
            "deferred_query_scope": (
                "Remaining admin/dashboard SQL JSON predicates are outside worker5 and are left for later "
                "worker/integration slices; prompt_time_density query-time extraction is now guarded separately."
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Wave9 consumer-side facade/query boundary evidence.")
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
