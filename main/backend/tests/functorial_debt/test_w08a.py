"""Focused authority annotations for the W08-A remaining assembly keys."""

from __future__ import annotations

import ast
from pathlib import Path


ASSEMBLY_ROOT = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "successor_runtime"
    / "assembly"
)
WITNESS = "test:test_w08a_remaining_assembly_bindings_are_prepared_commands"

EXPECTED_ANNOTATIONS: tuple[tuple[str, str, str], ...] = (
    (
        "c5_assembly.py",
        "build_deterministic_reconciliation_binding",
        "C5_2ReconcileRouteBinding",
    ),
    ("c5_assembly.py", "build_c5_assembly", "FamilyAssembly"),
    ("c6_assembly.py", "build_deterministic_fixtures", "dict[str, Any]"),
    (
        "c6_assembly.py",
        "build_openai_live_fixture_options",
        "C6AssemblyOptions | None",
    ),
    ("c6_assembly.py", "build_c6_assembly", "FamilyAssembly"),
    ("c7_assembly.py", "build_c7_assembly", "FamilyAssembly"),
    (
        "c7_assembly.py",
        "build_deterministic_c7_rollback_options",
        "C7AssemblyOptions",
    ),
    (
        "c8_assembly.py",
        "build_deterministic_c8_delivery_closure",
        "dict[str, Any]",
    ),
    (
        "c8_assembly.py",
        "build_deterministic_c8_payloads",
        "dict[str, Any]",
    ),
    ("c8_assembly.py", "build_c8_assembly", "FamilyAssembly"),
    (
        "c9_assembly.py",
        "build_deterministic_facade_validation_query",
        "FacadeQueryV2",
    ),
    (
        "c9_assembly.py",
        "build_deterministic_facade_closure",
        "SuccessorRuntimeFacade",
    ),
    (
        "c9_assembly.py",
        "build_deterministic_command_submission_port",
        "CommandSubmissionPort",
    ),
    ("c9_assembly.py", "build_c9_assembly", "FamilyAssembly"),
    (
        "s1_horizontal_port_assembly.py",
        "build_s1_horizontal_port_registry",
        "tuple[S1HorizontalPortContract, ...]",
    ),
    (
        "s2c_ops_domain_surface_assembly.py",
        "build_s2c_ops_domain_surface_registry",
        "tuple[S2cOpsDomainSurfaceContract, ...]",
    ),
    (
        "successor_assembly.py",
        "build_local_offline_fixture_options",
        "FamilyAssemblyOptions",
    ),
)


def _return_annotation(path: Path, function_name: str) -> ast.Subscript:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    )
    annotation = function.returns
    assert isinstance(annotation, ast.Subscript)
    assert isinstance(annotation.value, ast.Name)
    assert annotation.value.id == "Annotated"
    assert isinstance(annotation.slice, ast.Tuple)
    return annotation


def test_w08a_remaining_assembly_bindings_are_prepared_commands() -> None:
    seen: set[tuple[str, str]] = set()
    for filename, function_name, expected_return_type in EXPECTED_ANNOTATIONS:
        path = ASSEMBLY_ROOT / filename
        seen.add((filename, function_name))
        annotation = _return_annotation(path, function_name)
        slice_items = annotation.slice.elts
        assert len(slice_items) == 2
        assert ast.unparse(slice_items[0]) == expected_return_type
        metadata = ast.literal_eval(slice_items[1])
        assert metadata.startswith("kit:prepared-command effect_boundary=")
        assert WITNESS in metadata

    assert seen == {
        (filename, function_name) for filename, function_name, _ in EXPECTED_ANNOTATIONS
    }
