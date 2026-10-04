"""Acquisition batch assembly delegated to its native contribution rule.

The deterministic bundle/catalog/registry/program/handler wiring lives in the
native rule.  Without deterministic element payloads the acquisition cells remain
``FIXTURE_CLOSURE_REQUIRED`` and no handler is installed.
"""

from __future__ import annotations
from collections.abc import Callable
from typing import Annotated
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import NativeContribution
from app.successor_runtime.assembly.base import AcquisitionAssemblyOptions, FamilyAssembly
from app.successor_runtime.capabilities.acquisition_native_contribution import (
    ASSEMBLY_CELL_IDS,
    AcquisitionAssemblyContext,
    AcquisitionNativeBinding,
    AcquisitionNativeSource,
    DEFAULT_ACQUISITION_NATIVE_SOURCE,
    compile_acquisition_native_contribution,
)

ACQUISITION_BATCH_FAMILY_ID = "acquisition.batch"
LOCAL_ONLY_REGISTRY_REVISION = 0
ACQUISITION_BATCH_ROLLBACK_PATHS = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/p3-fragments/C3.json",
    "main/backend/app/successor_migration/legacy_collect_runtime.py",
)
_DEFAULT_ACQUISITION_NATIVE: NativeContribution | None = None


def default_acquisition_native_contribution() -> NativeContribution:
    """Compile the default authored acquisition source once for assembly."""
    global _DEFAULT_ACQUISITION_NATIVE
    if _DEFAULT_ACQUISITION_NATIVE is None:
        native = compile_acquisition_native_contribution(DEFAULT_ACQUISITION_NATIVE_SOURCE)
        if isinstance(native, Failure):
            raise RuntimeError(f"invalid default C3 native contribution: {native.message}")
        _DEFAULT_ACQUISITION_NATIVE = native
    return _DEFAULT_ACQUISITION_NATIVE


def build_deterministic_element_payloads(
    project_key: str = "project:c3-i1-local",
) -> Annotated[
    tuple[object, ...],
    "kit:prepared-command effect_boundary=successor_runtime.acquisition_batch_assembly witness=test:test_c3_assembly_installs_with_production_fixture_builder",
]:
    """Build deterministic acquisition element payloads from the collect API."""
    from app.successor_runtime.capabilities import acquisition_batch as acquisition

    request_ref = acquisition.build_collect_request_ref(
        request_id="request:c3-i1-local", project_key=project_key, channel="search.market"
    )
    snapshot = acquisition.CollectLegacyRequestSnapshot(
        schema_version=acquisition.COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
        flow="collect",
        channel="search.market",
        project_key=project_key,
        query_terms=("机器人", "市场"),
        urls=(),
        limit=80,
        options=acquisition.freeze_json_object({}),
        source_context=acquisition.freeze_json_object({}),
        snapshot_digest="",
    )
    policy = acquisition.CollectResourcePolicy(
        schema_ref=acquisition.COLLECT_RESOURCE_POLICY_SCHEMA_REF,
        max_parallelism=2,
        deadline_seconds=60,
        cancellation="COORDINATED",
        backpressure=True,
        provider_concurrency_key="search.market",
        policy_digest="",
    )
    plan = acquisition.build_collect_batch_plan(
        request_ref=request_ref,
        snapshot=snapshot,
        plan_id="plan:c3-i1-local",
        resource_policy=policy,
        authority_scope_ref=project_key,
    )
    return tuple(
        (
            acquisition.collect_batch_element_payload_from_dicts(
                request_ref=request_ref,
                request_snapshot=snapshot,
                element=plan.elements[index],
                resource_policy=policy,
                authority_scope_ref=project_key,
            )
            for index in range(len(plan.elements))
        )
    )


def build_acquisition_batch_assembly(
    *,
    uow_factory: Callable[[], object],
    project_scope_digest: str,
    options: AcquisitionAssemblyOptions | None = None,
    native: NativeContribution | None = None,
    source: AcquisitionNativeSource | None = None,
) -> Annotated[
    FamilyAssembly,
    "kit:prepared-command effect_boundary=successor_runtime.acquisition_batch_assembly witness=test:test_c3_assembly_installs_with_production_fixture_builder",
]:
    """Return the acquisition assembly through one compiled native binding."""
    compiled_native = native
    if compiled_native is None and source is not None:
        compiled = compile_acquisition_native_contribution(source)
        if isinstance(compiled, Failure):
            raise RuntimeError(f"invalid C3 native source {source.contribution_id}: {compiled.message}")
        compiled_native = compiled
    if compiled_native is None:
        compiled_native = default_acquisition_native_contribution()
    binding = compiled_native.assemble(
        AcquisitionAssemblyContext(
            uow_factory=uow_factory,
            project_scope_digest=project_scope_digest,
            options=options or AcquisitionAssemblyOptions(),
        )
    )
    if isinstance(binding, Failure):
        raise RuntimeError(f"C3 native assembly failed: {binding.message}")
    assert isinstance(binding, AcquisitionNativeBinding)
    if tuple((cell.cell_id for cell in binding.family_assembly.cells)) != ASSEMBLY_CELL_IDS:
        raise ValueError("C3 assembly cell identity drifted from native source")
    return binding.family_assembly


__all__ = [
    "ASSEMBLY_CELL_IDS",
    "ACQUISITION_BATCH_FAMILY_ID",
    "ACQUISITION_BATCH_ROLLBACK_PATHS",
    "LOCAL_ONLY_REGISTRY_REVISION",
    "build_acquisition_batch_assembly",
    "build_deterministic_element_payloads",
    "default_acquisition_native_contribution",
]
