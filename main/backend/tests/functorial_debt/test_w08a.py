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
        "task_observation_assembly.py",
        "build_deterministic_reconciliation_binding",
        "TaskEffectReconcileRouteBinding",
    ),
    ("task_observation_assembly.py", "build_task_observation_assembly", "FamilyAssembly"),
    ("material_ingest_assembly.py", "build_material_ingest_assembly", "FamilyAssembly"),
    (
        "material_ingest_assembly.py",
        "build_deterministic_material_ingest_rollback_options",
        "MaterialIngestAssemblyOptions",
    ),
    (
        "knowledge_assembly.py",
        "build_deterministic_knowledge_delivery_closure",
        "dict[str, Any]",
    ),
    (
        "knowledge_assembly.py",
        "build_deterministic_knowledge_payloads",
        "dict[str, Any]",
    ),
    ("knowledge_assembly.py", "build_knowledge_assembly", "FamilyAssembly"),
    (
        "projection_assembly.py",
        "build_deterministic_facade_validation_query",
        "FacadeQueryV2",
    ),
    (
        "projection_assembly.py",
        "build_deterministic_facade_closure",
        "SuccessorRuntimeFacade",
    ),
    (
        "projection_assembly.py",
        "build_deterministic_command_submission_port",
        "CommandSubmissionPort",
    ),
    ("projection_assembly.py", "build_projection_assembly", "FamilyAssembly"),
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
