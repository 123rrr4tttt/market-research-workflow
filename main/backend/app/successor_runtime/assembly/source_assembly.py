"""C2 family assembly: installed store-rehydrated handlers plus projector.

Digests are never invented here.  Each installed handler uses the exact
binding builder already used by the family canaries, the bundle/catalog
contract digest, and the existing C2 deployment catalog digest function.
C2.4 additionally registers the exact per-run projector source key when the
run owner supplies it; without a per-run source key it stays
``PROJECTOR_WIRING_DECLARED``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Annotated

from app.successor_runtime.assembly.base import (
    PROJECTOR_REGISTRY_INCARNATION,
    CellBinding,
    FamilyAssembly,
    ProjectorSourceKey,
    ProjectorWiring,
    RollbackBindingDeclaration,
    successor_binding,
)
from app.successor_runtime.capabilities import single_source_guard_port as provider_guard
from app.successor_runtime.capabilities import source_resolution as resolution
from app.successor_runtime.capabilities import source_planning as planning
from app.successor_runtime.capabilities import source_provider_acquisition as provider_acquisition
from app.successor_runtime.capabilities import (
    source_provider_worker as provider_worker,
)
from app.successor_runtime.capabilities import (
    source_provider_test_interpreters as provider_fixtures,
)
from app.successor_runtime.capabilities.source_resolution_interpreters import (
    authority_requirement_digest,
    successor_interpreter_profile_digest,
)
from app.successor_runtime.capabilities.source_terminal_projection import (
    DECLARED_LOSS_PROFILE_REF,
    SOURCE_TERMINAL_PROJECTION_PROJECTOR_ID,
    SOURCE_TERMINAL_PROJECTION_PROJECTOR_VERSION,
    SOURCE_TERMINAL_PROJECTION_TERMINAL_SCHEMA,
)
from app.successor_runtime.capabilities.source_native_contribution import (
    ASSEMBLY_CELL_IDS,
    SOURCE_FAMILY_ID as _SOURCE_FAMILY_ID,
)
from app.successor_runtime.substrate.postgres.source_library_c2_1_handler import (
    SourceLibraryC2_1StoreRehydratedHandler,
)
from app.successor_runtime.substrate.postgres.source_library_c2_23_canary import (
    C2_2StoreRehydratedHandler,
    C2_3StoreRehydratedHandler,
    build_successor_c2_2_binding,
    build_successor_c2_3_binding,
)
from app.successor_runtime.substrate.projections.registry import (
    ProjectorRegistry,
    validate_projector_contract,
)
from app.successor_runtime.substrate.projections.source_library_terminal import (
    PostgresSourceLibraryTerminalProjector,
)

SOURCE_FAMILY_ID = _SOURCE_FAMILY_ID

SOURCE_RESOLUTION_CELL_ID = ASSEMBLY_CELL_IDS[0]
SOURCE_PLANNING_CELL_ID = ASSEMBLY_CELL_IDS[1]
SOURCE_PROVIDER_ACQUISITION_CELL_ID = ASSEMBLY_CELL_IDS[2]
SOURCE_TERMINAL_PROJECTION_CELL_ID = ASSEMBLY_CELL_IDS[3]

SOURCE_ROLLBACK_PATHS = {
    SOURCE_RESOLUTION_CELL_ID: ("main/backend/app/successor_migration/legacy_source_library.py",),
    SOURCE_PLANNING_CELL_ID: (
        (
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/p3-fragments/C2.json"
        ),
        "main/backend/app/successor_migration/legacy_source_library_c2_2.py",
    ),
    SOURCE_PROVIDER_ACQUISITION_CELL_ID: (
        (
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/p3-fragments/C2.json"
        ),
        "main/backend/app/successor_migration/legacy_source_library_c2_3.py",
    ),
    SOURCE_TERMINAL_PROJECTION_CELL_ID: (
        (
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/p3-fragments/C2.json"
        ),
        ("main/backend/app/successor_runtime/substrate/projections/source_library_terminal.py"),
        "main/backend/app/successor_migration/legacy_source_library_c2_4.py",
    ),
}


def _source_resolution_contract_ref() -> object:
    catalog = resolution.build_source_resolution_catalog(resolution.build_source_resolution_bundle())
    ref = catalog.lookup(resolution.SOURCE_RESOLUTION_KIND)
    if ref is None:
        raise RuntimeError("source resolve contract missing from existing bundle catalog")
    return ref


def _source_planning_contract_ref(kind: str) -> object:
    catalog = planning.build_source_planning_catalog(planning.build_source_planning_bundle())
    ref = catalog.lookup(kind)
    if ref is None:
        raise RuntimeError(f"source planning contract {kind!r} missing from existing catalog")
    return ref


def _source_provider_acquisition_contract_ref() -> object:
    catalog = provider_acquisition.build_source_provider_acquisition_catalog(
        provider_acquisition.build_source_provider_acquisition_bundle()
    )
    ref = catalog.lookup(provider_acquisition.SOURCE_PROVIDER_ACQUISITION_KIND)
    if ref is None:
        raise RuntimeError("provider acquisition contract missing from existing bundle catalog")
    return ref


def _source_provider_acquisition_gateway(
    provider_gateway: object | None,
) -> tuple[object, str]:
    """Choose the C2.3 gateway without invoking any provider."""

    if provider_gateway is not None:
        delegate = provider_gateway
        note = (
            "LIVE_PROVIDER_DIMENSION_RESOLVED_SERPER_EXPLICIT: "
            "caller supplied the live Serper gateway; no provider invocation "
            "occurs during assembly construction"
        )
    else:
        live_gateway = provider_worker.build_serper_live_gateway()
        if live_gateway is not None:
            delegate = live_gateway
            note = (
                "LIVE_PROVIDER_DIMENSION_RESOLVED_SERPER: "
                "C2_3StoreRehydratedHandler uses the env-backed live Serper "
                "gateway; no provider invocation occurs during assembly "
                "construction and receipts stay redacted"
            )
        else:
            delegate = provider_fixtures.FixtureProviderEffectGateway(
                credentials=provider_fixtures.FixtureCredentialResolverPort(),
                effect=provider_fixtures.FixtureProviderEffectPort(),
                readback=provider_fixtures.FixtureProviderReadbackPort(),
            )
            note = (
                "LIVE_PROVIDER_DIMENSION_UNRESOLVED: "
                "C2_3StoreRehydratedHandler uses the existing deterministic "
                "FixtureProviderEffectGateway; the fixture path does not "
                "constitute production provider wiring"
            )
    return (
        delegate,
        note + "; SINGLE_SOURCE_GUARD_PORT_CONSUMED_BEFORE_DISPATCH; no provider "
        "invocation occurs during assembly construction",
    )


def _source_native_definition(native: object | None) -> object:
    """Resolve the default C2 typed contribution definition lazily."""

    from app.successor_runtime.capabilities.source_native_contribution import (
        DEFAULT_SOURCE_NATIVE_SOURCE,
        SourceNativeDefinition,
        compile_source_native_contribution,
    )

    if native is None:
        native = compile_source_native_contribution(DEFAULT_SOURCE_NATIVE_SOURCE)
        if not isinstance(native, SourceNativeDefinition) and not hasattr(native, "definition"):
            raise ValueError("default C2 native contribution failed")
    definition = getattr(native, "definition", native)
    if not isinstance(definition, SourceNativeDefinition):
        raise ValueError("C2 native handle drift")
    return definition


def build_source_assembly(
    *,
    uow_factory: Callable[[], object],
    project_scope_digest: str,
    projector_source_keys: Mapping[str, ProjectorSourceKey] | None = None,
    provider_gateway: object | None = None,
    native: object | None = None,
) -> Annotated[
    FamilyAssembly,
    "kit:prepared-command effect_boundary=successor_runtime.c2_assembly "
    "witness=test:test_c2_assembly_installs_one_exact_handler_per_installed_cell",
]:
    """Return the C2 family assembly with exact installed handlers.

    C2.4 stays ``PROJECTOR_WIRING_DECLARED`` until the run owner supplies a
    per-run source key; with a key it registers one read-only projector
    contract in the family registry and becomes ``INSTALLED``.
    """

    deployment_catalog_digest = resolution.deployment_catalog_digest()
    native_definition = _source_native_definition(native)
    stages = {stage.name: stage for stage in native_definition.source.stages}
    if tuple(stage.cell_id for stage in native_definition.source.stages) != ASSEMBLY_CELL_IDS:
        raise ValueError("source native cell order drift")

    c2_1_ref = _source_resolution_contract_ref()
    c2_1_binding = successor_binding(
        operation_contract_digest=c2_1_ref.contract_digest,
        interpreter_profile_digest=successor_interpreter_profile_digest(),
        deployment_catalog_digest=deployment_catalog_digest,
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=authority_requirement_digest(),
        runtime_protocol_version="1",
    )
    c2_1_handler = SourceLibraryC2_1StoreRehydratedHandler(
        uow_factory=uow_factory,
        handler_binding_digest=c2_1_binding.binding_digest,
        interpreter_profile_digest=c2_1_binding.interpreter_profile_digest,
        operation_contract_digest=c2_1_ref.contract_digest,
        deployment_catalog_digest=deployment_catalog_digest,
    )

    c2_2_contracts = tuple(_source_planning_contract_ref(kind) for kind in stages["plan"].kinds)
    c2_2_bindings = tuple(
        build_successor_c2_2_binding(
            contract_digest=contract_ref.contract_digest,
            deployment_catalog_digest=deployment_catalog_digest,
            project_scope_digest=project_scope_digest,
            runtime_protocol_version="1",
        )
        for contract_ref in c2_2_contracts
    )
    c2_2_handlers = tuple(
        C2_2StoreRehydratedHandler(
            uow_factory=uow_factory,
            handler_binding_digest=binding.binding_digest,
            interpreter_profile_digest=binding.interpreter_profile_digest,
            operation_contract_digest=contract_ref.contract_digest,
            deployment_catalog_digest=deployment_catalog_digest,
        )
        for contract_ref, binding in zip(
            c2_2_contracts,
            c2_2_bindings,
            strict=True,
        )
    )
    if not c2_2_handlers:
        raise ValueError("source native plan stage installs no operation handlers")

    c2_3_ref = _source_provider_acquisition_contract_ref()
    c2_3_binding = build_successor_c2_3_binding(
        contract_digest=c2_3_ref.contract_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        project_scope_digest=project_scope_digest,
        runtime_protocol_version="1",
    )
    c2_3_gateway, c2_3_gateway_note = _source_provider_acquisition_gateway(provider_gateway)
    c2_3_guard_port = provider_guard.DefaultSingleSourceGuardPort()
    c2_3_handler = C2_3StoreRehydratedHandler(
        uow_factory=uow_factory,
        handler_binding_digest=c2_3_binding.binding_digest,
        interpreter_profile_digest=c2_3_binding.interpreter_profile_digest,
        operation_contract_digest=c2_3_ref.contract_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        gateway=c2_3_gateway,
        single_source_guard_port=c2_3_guard_port,
    )

    c2_4_wiring = ProjectorWiring(
        cell_id=SOURCE_TERMINAL_PROJECTION_CELL_ID,
        projector_id=SOURCE_TERMINAL_PROJECTION_PROJECTOR_ID,
        projector_version=SOURCE_TERMINAL_PROJECTION_PROJECTOR_VERSION,
        source_kind=PostgresSourceLibraryTerminalProjector.source_kind,
        projection_id=SOURCE_TERMINAL_PROJECTION_TERMINAL_SCHEMA,
        projection_schema_ref=SOURCE_TERMINAL_PROJECTION_TERMINAL_SCHEMA,
        declared_loss=(DECLARED_LOSS_PROFILE_REF,),
        note=("ProjectorRegistry registration is run-bound; the per-run source key is never synthesized here"),
    )
    c2_4_source_key = (projector_source_keys or {}).get(SOURCE_TERMINAL_PROJECTION_CELL_ID)
    if c2_4_source_key is None:
        c2_4_status = "PROJECTOR_WIRING_DECLARED"
        c2_4_binding_digest = None
        c2_4_required_wiring: tuple[str, ...] = ()
        c2_4_note = (
            "projector identity declared from existing constants; missing "
            "per-run source key (source_ref/source_incarnation), which the "
            "run owner must supply before registry registration"
        )
        c2_4_registry = None
    else:
        c2_4_contract = c2_4_wiring.to_contract(c2_4_source_key)
        c2_4_validation = validate_projector_contract(c2_4_contract)
        if not c2_4_validation.valid:
            raise ValueError(
                "terminal projection contract invalid: "
                + "; ".join(item.message for item in c2_4_validation.violations)
            )
        c2_4_binding_digest = c2_4_wiring.registration_digest(c2_4_contract)
        c2_4_registry = ProjectorRegistry(
            revision=0,
            incarnation=PROJECTOR_REGISTRY_INCARNATION,
            projectors=(c2_4_contract,),
        )
        c2_4_status = "INSTALLED"
        c2_4_required_wiring = ()
        c2_4_note = (
            "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED: "
            "per-run source_ref/source_incarnation bound; no PostgreSQL write "
            "adopted"
        )

    cells = (
        CellBinding(
            cell_id=SOURCE_RESOLUTION_CELL_ID,
            family_id=SOURCE_FAMILY_ID,
            status="INSTALLED",
            operation_contract_refs=stages["resolve"].kinds,
            handler_binding_digest=c2_1_handler.handler_binding_digest,
            recovery_binding_ref="mrw.source.resolve-execution-request.recovery.v2",
            rollback_binding_refs=SOURCE_ROLLBACK_PATHS[SOURCE_RESOLUTION_CELL_ID],
            note=(
                "store-rehydrated successor handler installed from native "
                f"{native_definition.contribution_id}; exact persisted "
                "project scope supplied by the caller"
            ),
        ),
        CellBinding(
            cell_id=SOURCE_PLANNING_CELL_ID,
            family_id=SOURCE_FAMILY_ID,
            status="INSTALLED",
            operation_contract_refs=stages["plan"].kinds,
            handler_binding_digest=c2_2_handlers[0].handler_binding_digest,
            recovery_binding_ref="mrw.source.plan-source-mode.recovery.v2",
            rollback_binding_refs=SOURCE_ROLLBACK_PATHS[SOURCE_PLANNING_CELL_ID],
            note=(
                "one store-rehydrated planner handler is installed for each "
                "native plan operation kind with its exact contract binding; "
                "no provider effect is performed"
            ),
        ),
        CellBinding(
            cell_id=SOURCE_PROVIDER_ACQUISITION_CELL_ID,
            family_id=SOURCE_FAMILY_ID,
            status="INSTALLED",
            operation_contract_refs=stages["provider_effect"].kinds,
            handler_binding_digest=c2_3_handler.handler_binding_digest,
            recovery_binding_ref="mrw.source.provider-acquisition.recovery.v2",
            rollback_binding_refs=SOURCE_ROLLBACK_PATHS[SOURCE_PROVIDER_ACQUISITION_CELL_ID],
            note=c2_3_gateway_note,
        ),
        CellBinding(
            cell_id=SOURCE_TERMINAL_PROJECTION_CELL_ID,
            family_id=SOURCE_FAMILY_ID,
            status=c2_4_status,
            operation_contract_refs=stages["terminal_projection"].kinds,
            handler_binding_digest=c2_4_binding_digest,
            recovery_binding_ref="mrw.source.project-terminal-result.recovery.v2",
            rollback_binding_refs=SOURCE_ROLLBACK_PATHS[SOURCE_TERMINAL_PROJECTION_CELL_ID],
            required_wiring=c2_4_required_wiring,
            note=c2_4_note,
        ),
    )
    c2_4_wiring_tuple = (c2_4_wiring,)
    rollback_bindings = tuple(
        RollbackBindingDeclaration(
            cell_id=cell_id,
            status="PRESENT",
            binding_refs=SOURCE_ROLLBACK_PATHS[cell_id],
            note="spec rollback binding present",
        )
        for cell_id in ASSEMBLY_CELL_IDS
    )
    return FamilyAssembly(
        family_id=SOURCE_FAMILY_ID,
        cells=cells,
        handlers=(c2_1_handler, *c2_2_handlers, c2_3_handler),
        projector_wiring=c2_4_wiring_tuple,
        projector_registry=c2_4_registry,
        rollback_bindings=rollback_bindings,
    )


__all__ = [
    "SOURCE_FAMILY_ID",
    "SOURCE_ROLLBACK_PATHS",
    "build_source_assembly",
]
