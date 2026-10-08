"""Focused authority metadata for the W08-C PostgreSQL substrate shard."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, get_args, get_origin, get_type_hints

from functorial_kit.arch.gates import scan_project
from functorial_kit.arch.scan import ratchet, violation_key

from app.successor_runtime.substrate.postgres.delivery_runtime import (
    build_delivery_runtime_assignment,
)
from app.successor_runtime.substrate.postgres.research_admission import (
    build_first_specimen_admission_registry,
)
from app.successor_runtime.runtime.admission_coordinator import (
    ExactAdmissionRegistry,
)
from app.successor_runtime.runtime.assignments import RuntimeAssignment

_POSTGRES_PATHS = (
    "main/backend/app/successor_runtime/substrate/postgres/",
)
_EXACT_BASELINE_KEYS = {
    "derived-marked|"
    "main/backend/app/successor_runtime/substrate/postgres/delivery_runtime.py|"
    "build_delivery_runtime_assignment returns an unmarked derived value",
    "derived-marked|"
    "main/backend/app/successor_runtime/substrate/postgres/research_admission.py|"
    "build_first_specimen_admission_registry returns an unmarked derived value",
}


def test_w08c_postgres_builder_metadata_preserves_return_types() -> None:
    prepared_command = "kit:prepared-command"
    metadata = {
        build_delivery_runtime_assignment: (
            RuntimeAssignment,
            prepared_command,
        ),
        build_first_specimen_admission_registry: (
            ExactAdmissionRegistry,
            prepared_command,
        ),
    }

    assert len(_EXACT_BASELINE_KEYS) == 2
    for function, (expected_return_type, expected_prefix) in metadata.items():
        return_type = get_type_hints(function, include_extras=True)["return"]
        assert get_origin(return_type) is Annotated
        value, annotation = get_args(return_type)
        assert value is expected_return_type
        assert isinstance(annotation, str)
        assert annotation.startswith(expected_prefix)
        if expected_prefix == prepared_command:
            assert "effect_boundary=postgres." in annotation
        assert annotation.endswith(
            "witness=test:test_w08c_postgres_builder_metadata_preserves_return_types"
        )


def test_w08c_exact_keys_are_removed_without_new_postgres_findings() -> None:
    scan = scan_project(Path(__file__).resolve().parents[4])
    result = ratchet(scan.violations, scan.baseline)
    raw_owned_derived = {
        violation_key(violation)
        for violation in scan.violations
        if violation.gate == "derived-marked"
        and violation.file.startswith(_POSTGRES_PATHS)
    }
    owned_new = {
        violation_key(violation)
        for violation in result.new_violations
        if violation.gate == "derived-marked"
        and violation.file.startswith(_POSTGRES_PATHS)
    }
    assert raw_owned_derived == set()
    assert owned_new == set()
    assert _EXACT_BASELINE_KEYS.isdisjoint(scan.baseline)
