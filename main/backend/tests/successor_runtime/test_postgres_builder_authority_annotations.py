"""PostgreSQL builders declare which effects they prepare."""

from __future__ import annotations

from typing import Annotated, get_args, get_origin, get_type_hints

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

def test_postgres_builder_metadata_preserves_return_types() -> None:
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
            "witness=test:test_postgres_builder_metadata_preserves_return_types"
        )
