from __future__ import annotations

from typing import Annotated, get_args, get_origin, get_type_hints

from app.successor_runtime.substrate.projections.c8_handler_bindings import (
    build_c8_delivery_activation_catalog,
    build_c8_interpreter_binding,
    build_c8_recovery_binding,
)
from app.successor_runtime.substrate.projections.projection_sources import (
    build_task_view,
    build_knowledge_view,
    build_material_view,
)
from app.successor_runtime.substrate.projections.source_library_terminal import (
    build_source_library_terminal_table,
)

W08E_EXACT_KEYS = (
    "derived-marked|main/backend/app/successor_runtime/substrate/projections/c8_handler_bindings.py|"
    "build_c8_delivery_activation_catalog returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_runtime/substrate/projections/c8_handler_bindings.py|"
    "build_c8_interpreter_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_runtime/substrate/projections/c8_handler_bindings.py|"
    "build_c8_recovery_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_runtime/substrate/projections/c9_sources.py|"
    "build_agent_session_payload returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_runtime/substrate/projections/c9_sources.py|"
    "build_research_graph_payload returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_runtime/substrate/projections/c9_sources.py|"
    "build_search_payload returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_runtime/substrate/projections/source_library_terminal.py|"
    "build_source_library_terminal_table returns an unmarked derived value",
)


def test_w08e_projection_authority_metadata_is_exact() -> None:
    assert len(W08E_EXACT_KEYS) == len(set(W08E_EXACT_KEYS)) == 7

    metadata = {
        build_c8_delivery_activation_catalog: "kit:prepared-command",
        build_c8_interpreter_binding: "kit:prepared-command",
        build_c8_recovery_binding: "kit:prepared-command",
        build_task_view: "kit:non-authoritative derived_as=view",
        build_knowledge_view: "kit:non-authoritative derived_as=view",
        build_material_view: "kit:non-authoritative derived_as=view",
        build_source_library_terminal_table: "kit:prepared-command",
    }
    for function, expected_prefix in metadata.items():
        return_type = get_type_hints(function, include_extras=True)["return"]
        assert get_origin(return_type) is Annotated
        value, annotation = get_args(return_type)
        assert value is not None
        assert isinstance(annotation, str)
        assert annotation.startswith(expected_prefix)
        assert "witness=test:test_w08e_projection_authority_metadata_is_exact" in annotation
