"""Focused ABI metadata witnesses for the W10 CLI/report generator batch."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Annotated, Any, get_args, get_origin, get_type_hints


BACKEND_ROOT = Path(__file__).resolve().parents[2] / "main" / "backend"
SCRIPTS_ROOT = BACKEND_ROOT / "scripts"
WITNESS = "test:test_w10_cli_generator_derived_metadata_preserves_abi"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from generate_successor_p3_aggregate import AggregateBuild


def _metadata(fact_source: str) -> str:
    return (
        "kit:non-authoritative derived_as=generated_evidence "
        f"fact_source={fact_source} witness={WITNESS}"
    )


CASES: list[tuple[str, str, object, str]] = [
    (
        "generate_api_schema_inventory",
        "build_inventory",
        dict,
        _metadata("fastapi.openapi.routes"),
    ),
    (
        "generate_c1_slice_acceptance",
        "build_slice",
        dict,
        _metadata(
            "successor_program_specs+legacy_oracle_receipt+pg_gate_bindings"
        ),
    ),
    (
        "generate_c1_slice_acceptance",
        "build_evidence",
        tuple,
        _metadata(
            "successor_program_specs+legacy_oracle_receipt+pg_gate_bindings"
        ),
    ),
    (
        "generate_c1_slice_acceptance",
        "build_aggregate_from_disk",
        dict,
        _metadata("three_exact_c1_slice_artifacts+P1P3_movement_matrix"),
    ),
    (
        "generate_capability_spec_route_decision",
        "build_documents",
        tuple,
        _metadata("frozen_development_contract+P3_aggregate+P4_fragments"),
    ),
    (
        "generate_prompt_time_density_gonogo",
        "build_gonogo_report",
        dict,
        _metadata("realcase+perf+ope+policy_health_inputs"),
    ),
    (
        "generate_runtime_kernel_abi_pilot",
        "build_bytes",
        bytes,
        _metadata("runtime_kernel_abi_contract"),
    ),
    (
        "generate_successor_p1_p3_semantic_movement",
        "build_matrix",
        dict,
        _metadata("P1P3_movement_spec+inline_movement_rows+C7_design_rows"),
    ),
    (
        "generate_successor_p1_p3_semantic_movement",
        "build_fragments",
        dict,
        _metadata("P1P3_movement_matrix"),
    ),
    (
        "generate_successor_p1_p3_semantic_movement",
        "build_inventory",
        dict,
        _metadata("P1P3_movement_matrix"),
    ),
    (
        "generate_successor_p1_p3_semantic_movement",
        "build_gate",
        dict,
        _metadata("P1P3_movement_spec+matrix+inventory"),
    ),
    (
        "generate_successor_p1_p3_semantic_movement",
        "build_documents",
        dict,
        _metadata("P1P3_movement_spec+C7_design_inventory_matrix_trace"),
    ),
    (
        "generate_successor_p3_aggregate",
        "build_p3_aggregate",
        AggregateBuild,
        _metadata("migration_ledger+P1_selection+P2_packet+P3_fragments"),
    ),
    (
        "generate_successor_p3_c2_fragment",
        "build_fragment",
        dict,
        _metadata(
            "C2.1_resolution+C2.2_program+C2.3_fixture_receipt+C2.4_projection"
        ),
    ),
    (
        "generate_successor_p3_c3_fragment",
        "build_fragment",
        dict,
        _metadata("C3.1_C3.2_fixtures+current_repo_bindings"),
    ),
    (
        "generate_successor_p3_c4_fragment",
        "build_fragment",
        dict,
        _metadata("C4.1_plan+C4.2_retry+C4.3_submission+repo_bindings"),
    ),
    (
        "generate_successor_p3_c5_fragment",
        "build_fragment",
        dict,
        _metadata("C5.1-C5.4_observations+repo_bindings"),
    ),
    (
        "generate_successor_p3_c6_fragment",
        "build_fragment",
        dict,
        _metadata("C6.1-C6.3_closures+repo_bindings"),
    ),
    (
        "generate_successor_p3_c6_fragment",
        "build_digested_fragment",
        dict,
        _metadata("C6_fragment_build"),
    ),
    (
        "generate_successor_p4_c7_fragment",
        "build_fragment",
        dict,
        _metadata("C7.1-C7.4_observations+repo_bindings"),
    ),
    (
        "generate_successor_p4_c8_fragment",
        "build_fragment",
        dict,
        _metadata("C8.1-C8.4_observations+repo_bindings"),
    ),
    (
        "generate_successor_p4_c9_fragment",
        "build_fragment",
        dict,
        _metadata("C9.1-C9.3_contracts+repo_bindings"),
    ),
]


def test_w10_cli_generator_derived_metadata_preserves_abi() -> None:
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    if str(SCRIPTS_ROOT) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_ROOT))

    for module_name, function_name, base_type, expected in CASES:
        module = importlib.import_module(module_name)
        function = getattr(module, function_name)
        hints = get_type_hints(function, include_extras=True)
        return_type = hints["return"]

        assert get_origin(return_type) is Annotated
        value, metadata = get_args(return_type)
        assert (get_origin(value) or value) is base_type
        assert isinstance(metadata, str)
        assert metadata == expected
