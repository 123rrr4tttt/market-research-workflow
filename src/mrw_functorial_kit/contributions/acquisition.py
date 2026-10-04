"""Explicit kit contribution catalog for the native MRW C3 family."""

from __future__ import annotations

from collections.abc import Callable

from functorial_kit.contribution_verification import (
    VerificationPlan,
    VerificationRegistration,
    VerificationSource,
    plan_contribution_verification,
    register_verification_plan,
)
from functorial_kit.contributions import ContributionCatalog
from functorial_kit.core.failure import Failure
from functorial_kit.law_witness import (
    LawWitness,
    define_law_witness,
    law_witness_reference,
)
from app.successor_runtime.assembly.base import AcquisitionAssemblyOptions
from app.successor_runtime.capabilities.acquisition_native_contribution import AcquisitionAssemblyContext, AcquisitionNativeSource, DEFAULT_ACQUISITION_NATIVE_SOURCE, compile_acquisition_native_contribution


def acquisition_verification_plan_for(
    changes: object | None = None,
) -> VerificationPlan:
    """Derive an inert verification plan from the same native C3 catalog."""

    plan = plan_contribution_verification(
        tuple(
            VerificationSource(native.projection, native.verification)
            for native in acquisition_native_catalog
        ),
        changes,
    )
    if isinstance(plan, Failure):
        raise RuntimeError(f"invalid C3 verification plan: {plan.message}")
    return plan


def _run_acquisition_native_catalog_law() -> None:
    """Exercise the default native definition and its inert assembly law."""

    native = compile_acquisition_native_contribution(DEFAULT_ACQUISITION_NATIVE_SOURCE)
    if isinstance(native, Failure):
        raise AssertionError(native.message)
    expected_projection_ids = tuple(
        compile_acquisition_native_contribution(source).projection.id  # type: ignore[union-attr]
        for source in (DEFAULT_ACQUISITION_NATIVE_SOURCE,)
    )
    if (native.projection.id,) != expected_projection_ids:
        raise AssertionError("C3 native catalog order drifted from definition order")
    binding = native.assemble(
        AcquisitionAssemblyContext(
            uow_factory=lambda: None,
            project_scope_digest="digest:c3-native-catalog",
            options=AcquisitionAssemblyOptions(),
        )
    )
    if isinstance(binding, Failure):
        raise AssertionError(binding.message)


_catalog_law = define_law_witness(
    "test_acquisition_native_catalog_law",
    _run_acquisition_native_catalog_law,
)
if isinstance(_catalog_law, Failure):
    raise RuntimeError(f"invalid C3 native catalog law: {_catalog_law.message}")

# This tuple is the sole native C3 contribution catalog.  Runtime consumers and
# the factory-free generated projections both derive from it.
acquisition_native_contribution = compile_acquisition_native_contribution(DEFAULT_ACQUISITION_NATIVE_SOURCE)
if isinstance(acquisition_native_contribution, Failure):
    raise RuntimeError(f"invalid default C3 native contribution: {acquisition_native_contribution.message}")
acquisition_native_catalog = (acquisition_native_contribution,)


acquisition_verification_plan = acquisition_verification_plan_for()
_registered_verification_callbacks: dict[str, Callable[[], object]] = {}


def _register_verification_runner(name: str, run: Callable[[], object]) -> None:
    """Existing verification runner target: collect plan callbacks without running them."""

    _registered_verification_callbacks[name] = run


_registration = register_verification_plan(acquisition_verification_plan, _register_verification_runner)
if isinstance(_registration, Failure):
    raise RuntimeError(f"invalid C3 verification registration: {_registration.message}")
acquisition_verification_registration: VerificationRegistration | None = _registration

_verification_plan_witness_ids = (
    *(item.id for item in acquisition_verification_plan.prerequisites),
    *(item.witness.id for item in acquisition_verification_plan.checks),
)
acquisition_verification_law_witnesses: tuple[LawWitness, ...] = tuple(
    LawWitness(
        witness_id,
        _registered_verification_callbacks[f"test:{witness_id}"],
    )
    for witness_id in _verification_plan_witness_ids
)
acquisition_law_witnesses: tuple[LawWitness, ...] = (_catalog_law, *acquisition_verification_law_witnesses)
acquisition_law_witness_references = tuple(
    law_witness_reference(witness) for witness in acquisition_law_witnesses
)

acquisition_contribution_catalog = tuple(native.projection for native in acquisition_native_catalog)
acquisition_native_catalog = acquisition_native_catalog
acquisition_contribution_catalog = acquisition_contribution_catalog
acquisition_law_witnesses = acquisition_law_witnesses
acquisition_law_witness_references = acquisition_law_witness_references
acquisition_verification_law_witnesses = acquisition_verification_law_witnesses
acquisition_verification_plan = acquisition_verification_plan
acquisition_verification_plan_for = acquisition_verification_plan_for
acquisition_verification_registration = acquisition_verification_registration

contribution_catalog = ContributionCatalog(
    contributions=acquisition_contribution_catalog,
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = [
    "acquisition_contribution_catalog",
    "acquisition_law_witness_references",
    "acquisition_law_witnesses",
    "acquisition_native_catalog",
    "acquisition_native_contribution",
    "acquisition_verification_law_witnesses",
    "acquisition_verification_plan",
    "acquisition_verification_plan_for",
    "acquisition_verification_registration",
    "contribution_catalog",
    "acquisition_contribution_catalog",
    "acquisition_law_witness_references",
    "acquisition_law_witnesses",
    "acquisition_native_catalog",
    "acquisition_verification_law_witnesses",
    "acquisition_verification_plan",
    "acquisition_verification_plan_for",
    "acquisition_verification_registration",
]
