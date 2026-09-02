"""C3 family assembly: composed handler only when element payloads exist.

The composed TraverseOrdered -> FoldAtom handler is the existing canary
realization.  Without deterministic element payloads the C3 cells are
``FIXTURE_CLOSURE_REQUIRED`` and no handler is installed.
"""

from __future__ import annotations

from collections.abc import Callable

from app.successor_runtime.assembly.base import (
    C3AssemblyOptions,
    CellBinding,
    FamilyAssembly,
    RollbackBindingDeclaration,
    successor_binding,
)
from app.successor_runtime.capabilities import collect_c3 as c3
from app.successor_runtime.capabilities import collect_c3_program as c3p
from app.successor_runtime.capabilities.collect_c3_interpreters import (
    authority_requirement_digest,
    successor_interpreter_profile_digest_c3_2,
)
from app.successor_runtime.substrate.postgres.collect_c3_canary import (
    C3CollectComposedRuntimeHandler,
)

C3_FAMILY_ID = "C3"

LOCAL_ONLY_REGISTRY_REVISION = 0

C3_ROLLBACK_PATHS = (
    (
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/p3-fragments/C3.json"
    ),
    "main/backend/app/successor_migration/legacy_collect_runtime.py",
)


def build_deterministic_element_payloads(
    project_key: str = "project:c3-i1-local",
) -> tuple[object, ...]:
    """Build the deterministic I1 C3 element payloads from the collect API."""

    request_ref = c3.build_collect_request_ref(
        request_id="request:c3-i1-local",
        project_key=project_key,
        channel="search.market",
    )
    snapshot = c3.CollectLegacyRequestSnapshot(
        schema_version=c3.COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
        flow="collect",
        channel="search.market",
        project_key=project_key,
        query_terms=("机器人", "市场"),
        urls=(),
        limit=80,
        options=c3.freeze_json_object({}),
        source_context=c3.freeze_json_object({}),
        snapshot_digest="",
    )
    policy = c3.CollectResourcePolicy(
        schema_ref=c3.COLLECT_RESOURCE_POLICY_SCHEMA_REF,
        max_parallelism=2,
        deadline_seconds=60,
        cancellation="COORDINATED",
        backpressure=True,
        provider_concurrency_key="search.market",
        policy_digest="",
    )
    plan = c3.build_collect_batch_plan(
        request_ref=request_ref,
        snapshot=snapshot,
        plan_id="plan:c3-i1-local",
        resource_policy=policy,
        authority_scope_ref=project_key,
    )
    return tuple(
        c3.collect_batch_element_payload_from_dicts(
            request_ref=request_ref,
            request_snapshot=snapshot,
            element=plan.elements[index],
            resource_policy=policy,
            authority_scope_ref=project_key,
        )
        for index in range(len(plan.elements))
    )


def _build_composed_handler(
    *,
    uow_factory: Callable[[], object],
    project_scope_digest: str,
    element_payloads: tuple[object, ...],
) -> C3CollectComposedRuntimeHandler:
    bundle = c3.build_collect_c3_bundle()
    catalog = c3.build_collect_c3_catalog(bundle)
    registry = c3.build_collect_c3_registry(bundle)
    fold_contract_ref = bundle.operation_c3_2.ref
    project_key = element_payloads[0].parent_request_ref.project_key
    for payload in element_payloads:
        if payload.parent_request_ref.project_key != project_key:
            raise ValueError("C3 element payloads must share one project_key")
    program = c3p.build_collect_c3_composed_program(
        element_payloads=element_payloads,
        catalog=catalog,
        program_id=f"program:c3-assembly:{project_key}",
        project_key=project_key,
        project_registry_revision=LOCAL_ONLY_REGISTRY_REVISION,
        project_scope_digest=project_scope_digest,
    )
    plan = c3p.compile_collect_c3_program(
        program,
        catalog,
        operation_contracts=registry,
        transform_registry=c3p.build_collect_c3_transform_registry(),
    )
    deployment_catalog_digest = c3.deployment_catalog_digest()
    binding = successor_binding(
        operation_contract_digest=fold_contract_ref.contract_digest,
        interpreter_profile_digest=successor_interpreter_profile_digest_c3_2(),
        deployment_catalog_digest=deployment_catalog_digest,
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=authority_requirement_digest(),
        resource_policy_epoch=1,
        runtime_protocol_version="1",
    )
    return C3CollectComposedRuntimeHandler(
        composed_program=program,
        composed_plan=plan,
        catalog=catalog,
        binding=binding,
        deployment_catalog_digest=deployment_catalog_digest,
        uow_factory=uow_factory,
    )


def build_c3_assembly(
    *,
    uow_factory: Callable[[], object],
    project_scope_digest: str,
    options: C3AssemblyOptions | None = None,
) -> FamilyAssembly:
    """Return the C3 family assembly for one fixture closure or declared gap."""

    opts = options or C3AssemblyOptions()
    if opts.element_payloads:
        handler = _build_composed_handler(
            uow_factory=uow_factory,
            project_scope_digest=project_scope_digest,
            element_payloads=tuple(opts.element_payloads),
        )
        handler_digest = handler.handler_binding_digest
        status = "INSTALLED"
        installed_note = (
            "LOCAL_OFFLINE deterministic no-provider fixture closure; "
            "C3.1/C3.2 share the composed TraverseOrdered->FoldAtom handler; "
            "exact persisted registry revision/scope must be supplied by the run"
        )
    else:
        handler = None
        handler_digest = None
        status = "FIXTURE_CLOSURE_REQUIRED"
        installed_note = (
            "FIXTURE_CLOSURE_REQUIRED: no deterministic element payloads "
            "supplied; missing element_payloads"
        )

    cells = (
        CellBinding(
            cell_id="C3.1",
            family_id=C3_FAMILY_ID,
            status=status,
            operation_contract_refs=(
                "collect.execute_batch_element.v1",
                "mrw.traverse_ordered.materialize",
            ),
            handler_binding_digest=handler_digest,
            recovery_binding_ref="mrw.successor.collect.c3-1.recovery.v1",
            rollback_binding_refs=C3_ROLLBACK_PATHS,
            note=installed_note,
        ),
        CellBinding(
            cell_id="C3.2",
            family_id=C3_FAMILY_ID,
            status=status,
            operation_contract_refs=("collect.fold_ordered_results.v1",),
            handler_binding_digest=handler_digest,
            recovery_binding_ref="mrw.successor.collect.c3-2.recovery.v1",
            rollback_binding_refs=C3_ROLLBACK_PATHS,
            note=installed_note,
        ),
    )
    rollback_bindings = (
        RollbackBindingDeclaration(
            cell_id="C3.1",
            status="PRESENT",
            binding_refs=C3_ROLLBACK_PATHS,
            note="spec rollback binding present",
        ),
        RollbackBindingDeclaration(
            cell_id="C3.2",
            status="PRESENT",
            binding_refs=C3_ROLLBACK_PATHS,
            note="spec rollback binding present",
        ),
    )
    return FamilyAssembly(
        family_id=C3_FAMILY_ID,
        cells=cells,
        handlers=() if handler is None else (handler,),
        rollback_bindings=rollback_bindings,
    )


__all__ = [
    "C3_FAMILY_ID",
    "C3_ROLLBACK_PATHS",
    "LOCAL_ONLY_REGISTRY_REVISION",
    "build_c3_assembly",
    "build_deterministic_element_payloads",
]
