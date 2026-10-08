"""S2b C7 cell-extension wiring tests for the retained registry handler."""

from __future__ import annotations

import pytest
from app.successor_runtime.assembly.base import (
    MaterialIngestAssemblyOptions,
    local_assembly_scope_digest,
)
from app.successor_runtime.assembly.material_ingest_assembly import build_material_ingest_assembly
from app.successor_runtime.capabilities.material_ingest_registry import (
    MaterialIngestRegistryReserveCommand,
    LocalSuccessorMaterialIngestRegistryStore,
    derive_registry_identity,
)
from app.successor_runtime.capabilities.material_native_contribution import (
    MATERIAL_COMMIT_READBACK_CELL_ID,
)
from app.successor_runtime.substrate.postgres.ingest_c7_registry_handler import (
    C7IngestRegistryRuntimeHandler,
)

pytestmark = pytest.mark.unit

_PROJECT_KEY = "s2b-local"


def _c7_options() -> MaterialIngestAssemblyOptions:
    identity = derive_registry_identity(
        project_key=_PROJECT_KEY,
        trigger_type="ingest.url.single",
        idempotency_key="idem:s2b-cell-extension:001",
        request_payload={"url": "https://example.com/article", "kind": "url"},
    )
    return MaterialIngestAssemblyOptions(
        registry_store=LocalSuccessorMaterialIngestRegistryStore(),
        registry_command=MaterialIngestRegistryReserveCommand(
            identity=identity,
            subject_payload={"url": "https://example.com/article"},
            request_payload={"url": "https://example.com/article", "kind": "url"},
        ),
    )


def test_s2b_c7_2_ingest_registry_handler_wired_in_c7_assembly() -> None:
    assembly = build_material_ingest_assembly(
        options=_c7_options(),
        project_scope_digest=local_assembly_scope_digest(),
    )

    registry_handlers = [
        handler
        for handler in assembly.handlers
        if isinstance(handler, C7IngestRegistryRuntimeHandler)
    ]
    assert len(registry_handlers) == 1
    assert assembly.cell(MATERIAL_COMMIT_READBACK_CELL_ID).status == "INSTALLED"
    assert "ingest-submission registry typed route handler installed" in (
        assembly.cell(MATERIAL_COMMIT_READBACK_CELL_ID).note
    )
    assert registry_handlers[0].execute_calls == 0


def test_s2b_assembly_requires_pairwise_store_and_command() -> None:
    scope = local_assembly_scope_digest()
    with pytest.raises(ValueError, match="registry_store"):
        build_material_ingest_assembly(
            options=MaterialIngestAssemblyOptions(
                registry_store=LocalSuccessorMaterialIngestRegistryStore()
            ),
            project_scope_digest=scope,
        )


def test_s2b_cell_extension_handlers_keep_authority_false_until_execute() -> None:
    scope = local_assembly_scope_digest()
    c7_assembly = build_material_ingest_assembly(options=_c7_options(), project_scope_digest=scope)
    c7_handler = next(
        handler
        for handler in c7_assembly.handlers
        if isinstance(handler, C7IngestRegistryRuntimeHandler)
    )
    assert c7_handler.command.authority is None
