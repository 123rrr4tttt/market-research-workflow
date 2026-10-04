"""Native C2 catalog derives projections, verification, and bindings from one source."""

from __future__ import annotations

import dataclasses

from app.successor_runtime.assembly.base import ProjectorSourceKey
from app.successor_runtime.capabilities import (
    source_resolution as resolution,
)
from app.successor_runtime.capabilities import (
    source_provider_acquisition as provider_acquisition,
)
from app.successor_runtime.capabilities import (
    source_provider_worker as provider_worker,
)
from app.successor_runtime.capabilities.source_native_contribution import (
    ASSEMBLY_CELL_IDS,
    SOURCE_NATIVE_RULE_ID,
    DEFAULT_SOURCE_NATIVE_SOURCE,
    SourceAssemblyContext,
    SourceNativeSource,
    compile_source_native_contribution,
)
from app.successor_runtime.substrate.postgres.source_library_c2_23_canary import (
    C2_3StoreRehydratedHandler,
)
from functorial_kit.core.failure import Failure

from mrw_functorial_kit.contributions import source as source_catalog_module


def _inert_context() -> SourceAssemblyContext:
    return SourceAssemblyContext(
        uow_factory=lambda: None,
        project_scope_digest="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )


def _compile(source: SourceNativeSource):
    native = compile_source_native_contribution(source)
    assert not isinstance(native, Failure)
    return native


def test_default_source_compiles_and_keeps_pipeline_order() -> None:
    native = source_catalog_module.source_native_contribution
    capabilities = [obj.id for obj in native.projection.objects if obj.kind == "Capability"]
    assert native.projection.id == DEFAULT_SOURCE_NATIVE_SOURCE.contribution_id
    assert native.projection.owner == DEFAULT_SOURCE_NATIVE_SOURCE.owner
    assert native.verification is not None
    assert native.verification.rule_id == SOURCE_NATIVE_RULE_ID
    assert native.verification.complete is True
    # Resolve, plan, provider effect then terminal projection; capabilities are
    # declared in bundle operation order inside the plan stage.
    assert capabilities[:1] == ["source.resolve_execution_request.v2"]
    assert capabilities[-1] == "source.execute_provider_acquisition.v2"
    projections = [obj for obj in native.projection.objects if obj.kind == "ReadOnlyProjection"]
    assert [obj.id for obj in projections] == ["source.project_terminal_result.v2"]


def test_native_definition_keeps_exact_c2_1_and_c2_3_codec_identities() -> None:
    b21 = resolution.build_source_resolution_bundle()
    b23 = provider_acquisition.build_source_provider_acquisition_bundle()
    assert b21.payload_codec().codec_id == resolution.SOURCE_RESOLUTION_PAYLOAD_CODEC_ID
    assert b23.payload_codec().codec_id == provider_acquisition.SOURCE_PROVIDER_ACQUISITION_PAYLOAD_CODEC_ID
    assert len(b21.payload_codec().codec_digest) == 64
    assert len(b23.payload_codec().codec_digest) == 64


def test_invalid_stage_shape_fails_instead_of_indexing() -> None:
    changed = dataclasses.replace(
        DEFAULT_SOURCE_NATIVE_SOURCE,
        stages=DEFAULT_SOURCE_NATIVE_SOURCE.stages[:3],
    )
    result = compile_source_native_contribution(changed)
    assert isinstance(result, Failure)
    assert any(item["path"] == "$.source.stages" for item in result.context["issues"])


def test_external_effect_and_projection_boundaries_are_separate() -> None:
    stages = DEFAULT_SOURCE_NATIVE_SOURCE.stages
    assert [stage.name for stage in stages] == [
        "resolve",
        "plan",
        "provider_effect",
        "terminal_projection",
    ]
    assert [stage.external_effect for stage in stages] == [False, False, True, False]
    assert [stage.read_only_projection for stage in stages] == [False, False, False, True]


def test_non_default_source_updates_projection_id_from_one_declaration() -> None:
    changed = dataclasses.replace(
        DEFAULT_SOURCE_NATIVE_SOURCE,
        contribution_id="test.mrw.c2.native.alt.v1",
    )
    native = _compile(changed)
    assert native.projection.id == changed.contribution_id
    binding = native.assemble(_inert_context())
    assert not isinstance(binding, Failure)
    assert tuple(cell.cell_id for cell in binding.family_assembly.cells) == (ASSEMBLY_CELL_IDS)


def test_non_default_source_preserves_explicit_effect_and_projector_bindings() -> None:
    changed = dataclasses.replace(
        DEFAULT_SOURCE_NATIVE_SOURCE,
        contribution_id="test.mrw.c2.native.explicit-boundaries.v1",
    )
    native = _compile(changed)
    gateway = provider_worker.build_serper_live_gateway(
        api_key_provider=lambda: "test-key-not-a-real-credential",
        transport=lambda *args: (200, {"organic": []}),
    )
    assert gateway is not None
    binding = native.assemble(
        SourceAssemblyContext(
            uow_factory=lambda: None,
            project_scope_digest="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            provider_gateway=gateway,
            projector_source_keys={
                ASSEMBLY_CELL_IDS[-1]: ProjectorSourceKey(
                    source_ref="postgres://fixture/source",
                    source_incarnation="fixture-incarnation",
                )
            },
        )
    )
    assert not isinstance(binding, Failure)
    provider_handler = next(
        handler for handler in binding.family_assembly.handlers if isinstance(handler, C2_3StoreRehydratedHandler)
    )
    assert provider_handler.gateway is gateway
    assert binding.family_assembly.cell(ASSEMBLY_CELL_IDS[-1]).status == "INSTALLED"
    assert binding.family_assembly.projector_registry is not None


def test_default_catalog_law_and_verification_plan_are_inert_until_run() -> None:
    catalog = source_catalog_module.source_native_catalog
    assert [native.definition.contribution_id for native in catalog] == [DEFAULT_SOURCE_NATIVE_SOURCE.contribution_id]
    plan = source_catalog_module.source_verification_plan_for()
    assert plan.selection.contribution_ids == (DEFAULT_SOURCE_NATIVE_SOURCE.contribution_id,)
    for witness in source_catalog_module.source_verification_law_witnesses:
        witness.run()
    source_catalog_module.source_law_witnesses[0].run()


def test_inert_binding_preserves_assembly_statuses_and_effect_note() -> None:
    native = source_catalog_module.source_native_contribution
    binding = native.assemble(_inert_context())
    assert not isinstance(binding, Failure)
    statuses = tuple(cell.status for cell in binding.family_assembly.cells)
    # The provider-effect handler is installed inertly; the terminal projector
    # stays declared until the run owner supplies its per-run source key.
    assert statuses == ("INSTALLED", "INSTALLED", "INSTALLED", "PROJECTOR_WIRING_DECLARED")
    assert binding.family_assembly.family_id == "mrw.source"


def _reject_tampered_c2_assembly(native, mutate) -> None:
    from dataclasses import replace as dc_replace

    from app.successor_runtime.capabilities.source_native_contribution import (
        validate_source_native_binding,
    )
    from functorial_kit.native_contribution import BindingAccepted

    binding = native.assemble(_inert_context())
    assert not isinstance(binding, Failure)
    tampered_assembly = mutate(binding.family_assembly)
    rejected = validate_source_native_binding(
        native.definition,
        dc_replace(binding, family_assembly=tampered_assembly),
    )
    assert not isinstance(rejected, BindingAccepted)
    return rejected


def test_c2_validator_rejects_installed_ref_handler_projector_tampering() -> None:
    from dataclasses import replace as dc_replace

    native = _compile(dataclasses.replace(DEFAULT_SOURCE_NATIVE_SOURCE))
    assembly = native.assemble(_inert_context())
    assert not isinstance(assembly, Failure)

    cells = list(assembly.family_assembly.cells)
    tampered_cell = dc_replace(cells[0], operation_contract_refs=("tampered.ref.v1",))
    rejected = _reject_tampered_c2_assembly(
        native,
        lambda family: dc_replace(family, cells=(tampered_cell, *cells[1:])),
    )
    assert any(issue.path == "$.binding.family_assembly.cells.operation_contract_refs" for issue in rejected.issues)

    handlers = tuple(assembly.family_assembly.handlers)
    rejected = _reject_tampered_c2_assembly(
        native,
        lambda family: dc_replace(
            family,
            handlers=(handlers[1], handlers[0], *handlers[2:]),
        ),
    )
    assert any(issue.path == "$.binding.family_assembly.handlers" for issue in rejected.issues)

    wiring = assembly.family_assembly.projector_wiring
    tampered_wiring = dc_replace(wiring[0], projector_id="tampered.projector.v1")
    rejected = _reject_tampered_c2_assembly(
        native,
        lambda family: dc_replace(family, projector_wiring=(tampered_wiring,)),
    )
    assert any(issue.path == "$.binding.family_assembly.projector_wiring" for issue in rejected.issues)
