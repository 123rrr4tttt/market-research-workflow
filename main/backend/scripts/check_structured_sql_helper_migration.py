#!/usr/bin/env python3
"""Wave15 structured SQL/query helper migration inventory gate."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "structured-sql-helper-migration.wave15.v1"
TOPIC_ID = "2026-03-12-data-structured-service-modularization"
DOCUMENT_QUERY_CONTRACT_VERSION = "document_queries.v1"


@dataclass(frozen=True)
class CoveredSurface:
    surface_id: str
    path: str
    role: str
    required_definitions: tuple[str, ...] = ()
    required_imports: tuple[str, ...] = ()
    required_text: tuple[str, ...] = ()
    required_calls: tuple[tuple[str, tuple[str, ...]], ...] = ()
    endpoint: str | None = None


@dataclass(frozen=True)
class DeferredBoundary:
    boundary_id: str
    path: str
    function_name: str
    boundary_type: str
    reason: str
    endpoint: str | None = None


COVERED_SURFACES: tuple[CoveredSurface, ...] = (
    CoveredSurface(
        surface_id="document_query_contract",
        path="main/backend/app/services/document_queries/contracts.py",
        role="query_object_and_result_envelope",
        required_definitions=(
            "DocumentQuery",
            "DocumentQueryFilter",
            "DocumentQuerySort",
            "build_document_query",
            "build_document_query_result_envelope",
            "rows_for_document_views",
            "validate_document_query_result_envelope",
        ),
        required_text=(f'DOCUMENT_QUERY_CONTRACT_VERSION = "{DOCUMENT_QUERY_CONTRACT_VERSION}"',),
    ),
    CoveredSurface(
        surface_id="document_query_statement_builder",
        path="main/backend/app/services/document_queries/statement_builder.py",
        role="generic_document_query_to_sqlalchemy_statement_builder",
        required_definitions=(
            "apply_document_query_to_statement",
            "build_document_query_statement",
            "compile_document_query_statement",
            "document_query_to_statement",
        ),
        required_imports=("Document", "DocumentQuery", "select"),
        required_text=('DOCUMENT_QUERY_STATEMENT_BUILDER_VERSION = "document_query_statement_builder.v1"',),
        required_calls=(
            ("build_document_query_statement", ("apply_document_query_to_statement",)),
            ("document_query_to_statement", ("build_document_query_statement",)),
            ("compile_document_query_statement", ("build_document_query_statement",)),
        ),
    ),
    CoveredSurface(
        surface_id="policy_sql_expression_helpers",
        path="main/backend/app/services/document_queries/policy_filters.py",
        role="sqlalchemy_json_predicate_helper",
        required_definitions=(
            "document_json_iso_date_expr",
            "policy_effective_date_expr",
            "policy_has_data_condition",
            "policy_state_condition",
            "policy_time_expr",
            "policy_type_condition",
            "policy_type_order_expr",
            "prompt_time_density_time_expr",
        ),
        required_calls=(("prompt_time_density_time_expr", ("policy_time_expr",)),),
    ),
    CoveredSurface(
        surface_id="writing_material_query_helpers",
        path="main/backend/app/services/document_queries/writing_material_queries.py",
        role="document_query_envelope_before_legacy_rows",
        required_definitions=(
            "query_hybrid_document_envelope",
            "query_report_source_envelope",
            "query_source_library_material_envelope",
            "query_hybrid_document_rows",
            "query_report_source_rows",
            "query_source_library_material_rows",
        ),
        required_imports=("build_document_query", "build_document_query_result_envelope", "rows_for_document_views"),
        required_calls=(
            ("query_hybrid_document_envelope", ("build_document_query", "build_document_query_result_envelope")),
            ("query_report_source_envelope", ("build_document_query", "build_document_query_result_envelope")),
            ("query_source_library_material_envelope", ("build_document_query", "build_document_query_result_envelope")),
            ("query_hybrid_document_rows", ("rows_for_document_views",)),
            ("query_report_source_rows", ("rows_for_document_views",)),
            ("query_source_library_material_rows", ("rows_for_document_views",)),
        ),
    ),
    CoveredSurface(
        surface_id="prompt_time_density_sql_helper_consumer",
        path="main/backend/app/services/stats/prompt_time_density.py",
        role="consumer_uses_document_query_sql_time_helper",
        required_imports=("prompt_time_density_time_expr",),
        required_calls=(("query_prompt_time_density", ("prompt_time_density_time_expr",)),),
    ),
    CoveredSurface(
        surface_id="search_endpoint_document_query_projection",
        path="main/backend/app/services/document_queries/search_endpoint.py",
        role="api_search_document_query_projection_helper",
        endpoint="/api/v1/search",
        required_definitions=(
            "build_search_endpoint_document_query",
            "build_search_endpoint_document_query_envelope",
        ),
        required_imports=("build_document_query", "build_document_query_result_envelope"),
        required_text=(
            'SEARCH_ENDPOINT_CONSUMER = "api.search"',
            'SEARCH_ENDPOINT_SOURCE = "api.search.hybrid"',
        ),
        required_calls=(
            ("build_search_endpoint_document_query", ("build_document_query",)),
            ("build_search_endpoint_document_query_envelope", ("build_search_endpoint_document_query",)),
            ("build_search_endpoint_document_query_envelope", ("build_document_query_result_envelope",)),
            ("build_search_endpoint_document_query_envelope", ("validate_document_query_result_envelope",)),
        ),
    ),
    CoveredSurface(
        surface_id="api_search_endpoint_uses_projection",
        path="main/backend/app/api/search.py",
        role="endpoint_emits_document_query_v1_projection",
        endpoint="/api/v1/search",
        required_imports=("DOCUMENT_QUERY_CONTRACT_VERSION", "build_search_endpoint_document_query_envelope"),
        required_text=(
            "document_query_contract_version",
            "document_query_results",
            "document_query_pagination",
            "document_query_meta",
        ),
        required_calls=(("search", ("build_search_endpoint_document_query_envelope",)),),
    ),
)


DEFERRED_BOUNDARIES: tuple[DeferredBoundary, ...] = (
    DeferredBoundary(
        boundary_id="admin_documents_list_has_extracted_data_filter",
        path="main/backend/app/api/admin.py",
        function_name="list_documents",
        endpoint="/api/v1/admin/documents/list",
        boundary_type="admin_endpoint_sql_json_predicate",
        reason="has_extracted_data filters still build Document.extracted_data predicates inline.",
    ),
    DeferredBoundary(
        boundary_id="admin_social_data_structured_filters",
        path="main/backend/app/api/admin.py",
        function_name="list_social_data",
        endpoint="/api/v1/admin/social-data/list",
        boundary_type="admin_endpoint_sql_json_predicate",
        reason="platform and sentiment filters still read structured JSON fields inline.",
    ),
    DeferredBoundary(
        boundary_id="admin_content_graph_structured_filters",
        path="main/backend/app/api/admin.py",
        function_name="get_content_graph",
        endpoint="/api/v1/admin/content-graph",
        boundary_type="admin_endpoint_sql_json_predicate",
        reason="content graph SQL filters still check sentiment/entities structured JSON keys inline.",
    ),
    DeferredBoundary(
        boundary_id="admin_market_graph_structured_filters",
        path="main/backend/app/api/admin.py",
        function_name="get_market_graph",
        endpoint="/api/v1/admin/market-graph",
        boundary_type="admin_endpoint_sql_json_predicate",
        reason="market graph SQL filters still check market/company/product/operation JSON keys inline.",
    ),
    DeferredBoundary(
        boundary_id="admin_policy_graph_structured_filters",
        path="main/backend/app/api/admin.py",
        function_name="get_policy_graph",
        endpoint="/api/v1/admin/policy-graph",
        boundary_type="admin_endpoint_sql_json_predicate",
        reason="policy graph state/type SQL predicates still read policy JSON fields inline.",
    ),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _parse(path: Path) -> ast.AST:
    return ast.parse(_read_text(path), filename=str(path))


def _definition_names(tree: ast.AST) -> set[str]:
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _function_map(tree: ast.AST) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _import_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                names.add(module)
                parts = module.split(".")
                for index in range(len(parts)):
                    names.add(".".join(parts[index:]))
            for alias in node.names:
                names.add(alias.asname or alias.name)
                names.add(alias.name)
    return names


def _called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            names.add(child.func.id)
        elif isinstance(child.func, ast.Attribute):
            names.add(child.func.attr)
    return names


def _is_document_extracted_data_attr(node: ast.Attribute) -> bool:
    return (
        node.attr == "extracted_data"
        and isinstance(node.value, ast.Name)
        and node.value.id == "Document"
    )


def _document_extracted_data_count(node: ast.AST) -> int:
    return sum(
        1
        for child in ast.walk(node)
        if isinstance(child, ast.Attribute) and _is_document_extracted_data_attr(child)
    )


def _check_covered_surface(root: Path, surface: CoveredSurface) -> dict[str, Any]:
    path = root / surface.path
    exists = path.is_file()
    text = _read_text(path) if exists else ""
    tree = _parse(path) if exists else None
    definitions = _definition_names(tree) if tree is not None else set()
    imports = _import_names(tree) if tree is not None else set()
    functions = _function_map(tree) if tree is not None else {}

    missing_definitions = [name for name in surface.required_definitions if name not in definitions]
    missing_imports = [name for name in surface.required_imports if name not in imports]
    missing_text = [snippet for snippet in surface.required_text if snippet not in text]
    call_results: list[dict[str, Any]] = []
    for function_name, required_calls in surface.required_calls:
        function = functions.get(function_name)
        calls = _called_names(function) if function is not None else set()
        missing_calls = [name for name in required_calls if name not in calls]
        call_results.append(
            {
                "function": function_name,
                "exists": function is not None,
                "required_calls": list(required_calls),
                "missing_calls": missing_calls,
                "passed": function is not None and not missing_calls,
            }
        )

    passed = (
        exists
        and not missing_definitions
        and not missing_imports
        and not missing_text
        and all(item["passed"] for item in call_results)
    )
    return {
        "surface_id": surface.surface_id,
        "path": surface.path,
        "role": surface.role,
        "endpoint": surface.endpoint,
        "status": "covered" if passed else "gap",
        "exists": exists,
        "missing_definitions": missing_definitions,
        "missing_imports": missing_imports,
        "missing_text_markers": missing_text,
        "required_calls": call_results,
        "passed": passed,
    }


def _check_deferred_boundary(root: Path, boundary: DeferredBoundary) -> dict[str, Any]:
    path = root / boundary.path
    exists = path.is_file()
    tree = _parse(path) if exists else None
    functions = _function_map(tree) if tree is not None else {}
    function = functions.get(boundary.function_name)
    count = _document_extracted_data_count(function) if function is not None else 0
    return {
        "boundary_id": boundary.boundary_id,
        "path": boundary.path,
        "function": boundary.function_name,
        "endpoint": boundary.endpoint,
        "boundary_type": boundary.boundary_type,
        "reason": boundary.reason,
        "exists": exists,
        "function_exists": function is not None,
        "direct_sql_json_expression_count": count,
        "migration_status": "deferred" if count > 0 else "covered_or_removed",
    }


def build_check(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root is not None else _repo_root().resolve()
    covered = [_check_covered_surface(root, surface) for surface in COVERED_SURFACES]
    deferred = [_check_deferred_boundary(root, boundary) for boundary in DEFERRED_BOUNDARIES]
    covered_passed = all(item["passed"] for item in covered)
    missing_deferred_targets = [
        f"{item['path']}::{item['function']}"
        for item in deferred
        if not item["exists"] or not item["function_exists"]
    ]
    active_deferred = [item for item in deferred if item["migration_status"] == "deferred"]
    status_passed = covered_passed and not missing_deferred_targets
    return {
        "contract_version": CONTRACT_VERSION,
        "topic_id": TOPIC_ID,
        "document_query_contract_version": DOCUMENT_QUERY_CONTRACT_VERSION,
        "status": "passed" if status_passed else "failed",
        "migration_boundary": {
            "covered_scope": (
                "DocumentQuery envelope helpers, generic DocumentQuery-to-SQLAlchemy statement builder, "
                "policy SQL expression helpers, prompt-time-density SQL time helper consumption, writing "
                "material query helpers, and /api/v1/search projection."
            ),
            "deferred_scope": (
                "Admin/dashboard structured JSON SQL predicates remain inventory items until the "
                "consumer predicate facade checker confirms they are covered or removed."
            ),
        },
        "covered_query_helpers": covered,
        "remaining_migration_boundaries": deferred,
        "validation": {
            "passed": status_passed,
            "covered_surface_count": len(covered),
            "covered_surface_gap_count": sum(1 for item in covered if not item["passed"]),
            "deferred_boundary_count": len(active_deferred),
            "missing_deferred_targets": missing_deferred_targets,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Wave15 structured SQL/query helper migration inventory.")
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
