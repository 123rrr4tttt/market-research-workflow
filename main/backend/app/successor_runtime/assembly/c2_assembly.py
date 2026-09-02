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

from app.successor_runtime.assembly.base import (
    PROJECTOR_REGISTRY_INCARNATION,
    CellBinding,
    FamilyAssembly,
    ProjectorSourceKey,
    ProjectorWiring,
    RollbackBindingDeclaration,
    successor_binding,
)
from app.successor_runtime.capabilities import single_source_guard_port as c23_guard
from app.successor_runtime.capabilities import source_library_c2_1 as c21
from app.successor_runtime.capabilities import source_library_c2_2 as c22
from app.successor_runtime.capabilities import source_library_c2_3 as c23
from app.successor_runtime.capabilities import (
    source_library_c2_3_live_provider as c23_live,
)
from app.successor_runtime.capabilities import (
    source_library_c2_3_test_interpreters as c23_fixtures,
)
from app.successor_runtime.capabilities.source_library_c2_1_interpreters import (
    authority_requirement_digest,
    successor_interpreter_profile_digest,
)
from app.successor_runtime.capabilities.source_library_c2_4_projection import (
    DECLARED_LOSS_PROFILE_REF,
    SOURCE_LIBRARY_C2_4_PROJECTOR_ID,
    SOURCE_LIBRARY_C2_4_PROJECTOR_VERSION,
    SOURCE_LIBRARY_C2_4_TERMINAL_SCHEMA,
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

C2_FAMILY_ID = "C2"

C2_ROLLBACK_PATHS = {
    "C2.1": ("main/backend/app/successor_migration/legacy_source_library.py",),
    "C2.2": (
        (
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/p3-fragments/C2.json"
        ),
        "main/backend/app/successor_migration/legacy_source_library_c2_2.py",
    ),
    "C2.3": (
        (
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/p3-fragments/C2.json"
        ),
        "main/backend/app/successor_migration/legacy_source_library_c2_3.py",
    ),
    "C2.4": (
        (
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/p3-fragments/C2.json"
        ),
        (
            "main/backend/app/successor_runtime/substrate/projections/"
            "source_library_terminal.py"
        ),
        "main/backend/app/successor_migration/legacy_source_library_c2_4.py",
    ),
}

C2_2_PLANNER_KIND = c22.SOURCE_LIBRARY_C2_2_PROTOCOL_SEARCH_KIND


def _c2_1_contract_ref() -> object:
    catalog = c21.build_source_library_c2_1_catalog(
        c21.build_source_library_c2_1_bundle()
    )
    ref = catalog.lookup(c21.SOURCE_LIBRARY_C2_1_KIND)
    if ref is None:
        raise RuntimeError("C2.1 contract missing from existing bundle catalog")
    return ref


def _c2_2_contract_ref() -> object:
    catalog = c22.build_source_library_c2_2_catalog(
        c22.build_source_library_c2_2_bundle()
    )
    ref = catalog.lookup(C2_2_PLANNER_KIND)
    if ref is None:
        raise RuntimeError("C2.2 planner contract missing from existing catalog")
    return ref


def _c2_3_contract_ref() -> object:
    catalog = c23.build_source_library_c2_3_catalog(
        c23.build_source_library_c2_3_bundle()
    )
    ref = catalog.lookup(c23.SOURCE_LIBRARY_C2_3_KIND)
    if ref is None:
        raise RuntimeError("C2.3 contract missing from existing bundle catalog")
    return ref


def _c2_3_gateway(
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
        live_gateway = c23_live.build_serper_live_gateway()
        if live_gateway is not None:
            delegate = live_gateway
            note = (
                "LIVE_PROVIDER_DIMENSION_RESOLVED_SERPER: "
                "C2_3StoreRehydratedHandler uses the env-backed live Serper "
                "gateway; no provider invocation occurs during assembly "
                "construction and receipts stay redacted"
            )
        else:
            delegate = c23_fixtures.FixtureProviderEffectGateway(
                credentials=c23_fixtures.FixtureCredentialResolverPort(),
                effect=c23_fixtures.FixtureProviderEffectPort(),
                readback=c23_fixtures.FixtureProviderReadbackPort(),
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


def build_c2_assembly(
    *,
    uow_factory: Callable[[], object],
    project_scope_digest: str,
    projector_source_keys: Mapping[str, ProjectorSourceKey] | None = None,
    provider_gateway: object | None = None,
) -> FamilyAssembly:
    """Return the C2 family assembly with exact installed handlers.

    C2.4 stays ``PROJECTOR_WIRING_DECLARED`` until the run owner supplies a
    per-run source key; with a key it registers one read-only projector
    contract in the family registry and becomes ``INSTALLED``.
    """

    deployment_catalog_digest = c21.deployment_catalog_digest()

    c2_1_ref = _c2_1_contract_ref()
    c2_1_binding = successor_binding(
        operation_contract_digest=c2_1_ref.contract_digest,
        interpreter_profile_digest=successor_interpreter_profile_digest(),
        deployment_catalog_digest=deployment_catalog_digest,
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=authority_requirement_digest(),
    )
    c2_1_handler = SourceLibraryC2_1StoreRehydratedHandler(
        uow_factory=uow_factory,
        handler_binding_digest=c2_1_binding.binding_digest,
        interpreter_profile_digest=c2_1_binding.interpreter_profile_digest,
        operation_contract_digest=c2_1_ref.contract_digest,
        deployment_catalog_digest=deployment_catalog_digest,
    )

    c2_2_ref = _c2_2_contract_ref()
    c2_2_binding = build_successor_c2_2_binding(
        contract_digest=c2_2_ref.contract_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        project_scope_digest=project_scope_digest,
    )
    c2_2_handler = C2_2StoreRehydratedHandler(
        uow_factory=uow_factory,
        handler_binding_digest=c2_2_binding.binding_digest,
        interpreter_profile_digest=c2_2_binding.interpreter_profile_digest,
        operation_contract_digest=c2_2_ref.contract_digest,
        deployment_catalog_digest=deployment_catalog_digest,
    )

    c2_3_ref = _c2_3_contract_ref()
    c2_3_binding = build_successor_c2_3_binding(
        contract_digest=c2_3_ref.contract_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        project_scope_digest=project_scope_digest,
    )
    c2_3_gateway, c2_3_gateway_note = _c2_3_gateway(provider_gateway)
    c2_3_guard_port = c23_guard.DefaultSingleSourceGuardPort()
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
        cell_id="C2.4",
        projector_id=SOURCE_LIBRARY_C2_4_PROJECTOR_ID,
        projector_version=SOURCE_LIBRARY_C2_4_PROJECTOR_VERSION,
        source_kind=PostgresSourceLibraryTerminalProjector.source_kind,
        projection_id=SOURCE_LIBRARY_C2_4_TERMINAL_SCHEMA,
        projection_schema_ref=SOURCE_LIBRARY_C2_4_TERMINAL_SCHEMA,
        declared_loss=(DECLARED_LOSS_PROFILE_REF,),
        note=(
            "ProjectorRegistry registration is run-bound; the per-run source "
            "key is never synthesized here"
        ),
    )
    c2_4_source_key = (projector_source_keys or {}).get("C2.4")
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
                "C2.4 projector contract invalid: "
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
            cell_id="C2.1",
            family_id=C2_FAMILY_ID,
            status="INSTALLED",
            operation_contract_refs=("source_library.resolve_execution_request.v1",),
            handler_binding_digest=c2_1_handler.handler_binding_digest,
            recovery_binding_ref="mrw.successor.source-library.c2-1.recovery.v1",
            rollback_binding_refs=C2_ROLLBACK_PATHS["C2.1"],
            note=(
                "store-rehydrated successor handler installed; exact persisted "
                "project scope supplied by the caller"
            ),
        ),
        CellBinding(
            cell_id="C2.2",
            family_id=C2_FAMILY_ID,
            status="INSTALLED",
            operation_contract_refs=(
                "source_library.protocol_search.v1",
                "source_library.provider_harvest.v1",
                "source_library.site_search.v1",
                "source_library.url_execution.v1",
            ),
            handler_binding_digest=c2_2_handler.handler_binding_digest,
            recovery_binding_ref="mrw.successor.source-library.c2-2.recovery.v1",
            rollback_binding_refs=C2_ROLLBACK_PATHS["C2.2"],
            note=(
                "store-rehydrated planner handler installed; binding pins the "
                "existing protocol_search contract digest from the family "
                "bundle/catalog, matching the canary binding"
            ),
        ),
        CellBinding(
            cell_id="C2.3",
            family_id=C2_FAMILY_ID,
            status="INSTALLED",
            operation_contract_refs=("source_library.execute_provider_effect.v1",),
            handler_binding_digest=c2_3_handler.handler_binding_digest,
            recovery_binding_ref="mrw.successor.source-library.c2-3.recovery.v1",
            rollback_binding_refs=C2_ROLLBACK_PATHS["C2.3"],
            note=c2_3_gateway_note,
        ),
        CellBinding(
            cell_id="C2.4",
            family_id=C2_FAMILY_ID,
            status=c2_4_status,
            operation_contract_refs=("source_library.project_terminal_compat.v1",),
            handler_binding_digest=c2_4_binding_digest,
            recovery_binding_ref="mrw.successor.source-library.c2-4.recovery.v1",
            rollback_binding_refs=C2_ROLLBACK_PATHS["C2.4"],
            required_wiring=c2_4_required_wiring,
            note=c2_4_note,
        ),
    )
    c2_4_wiring_tuple = (c2_4_wiring,)
    rollback_bindings = tuple(
        RollbackBindingDeclaration(
            cell_id=cell_id,
            status="PRESENT",
            binding_refs=C2_ROLLBACK_PATHS[cell_id],
            note="spec rollback binding present",
        )
        for cell_id in ("C2.1", "C2.2", "C2.3", "C2.4")
    )
    return FamilyAssembly(
        family_id=C2_FAMILY_ID,
        cells=cells,
        handlers=(c2_1_handler, c2_2_handler, c2_3_handler),
        projector_wiring=c2_4_wiring_tuple,
        projector_registry=c2_4_registry,
        rollback_bindings=rollback_bindings,
    )


__all__ = [
    "C2_2_PLANNER_KIND",
    "C2_FAMILY_ID",
    "C2_ROLLBACK_PATHS",
    "build_c2_assembly",
]
