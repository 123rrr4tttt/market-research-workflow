"""Explicit kit contribution catalog for the native MRW C2 family."""

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
from app.successor_runtime.capabilities.source_native_contribution import (
    SourceAssemblyContext,
    SourceNativeSource,
    DEFAULT_SOURCE_NATIVE_SOURCE,
    compile_source_native_contribution,
)


def source_verification_plan_for(
    changes: object | None = None,
) -> VerificationPlan:
    """Derive an inert verification plan from the same native C2 catalog."""

    plan = plan_contribution_verification(
        tuple(
            VerificationSource(native.projection, native.verification)
            for native in source_native_catalog
        ),
        changes,
    )
    if isinstance(plan, Failure):
        raise RuntimeError(f"invalid C2 verification plan: {plan.message}")
    return plan


def _run_source_native_catalog_law() -> None:
    """Exercise the default native definition and its inert assembly law."""

    native = compile_source_native_contribution(DEFAULT_SOURCE_NATIVE_SOURCE)
    if isinstance(native, Failure):
        raise AssertionError(native.message)
    expected_projection_ids = tuple(
        compile_source_native_contribution(source).projection.id  # type: ignore[union-attr]
        for source in (DEFAULT_SOURCE_NATIVE_SOURCE,)
    )
    if (native.projection.id,) != expected_projection_ids:
        raise AssertionError("C2 native catalog order drifted from definition order")
    binding = native.assemble(
        SourceAssemblyContext(
            uow_factory=lambda: None,
            project_scope_digest="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        )
    )
    if isinstance(binding, Failure):
        raise AssertionError(binding.message)


_catalog_law = define_law_witness(
    "test_source_native_catalog_law",
    _run_source_native_catalog_law,
)
if isinstance(_catalog_law, Failure):
    raise RuntimeError(f"invalid C2 native catalog law: {_catalog_law.message}")

# This tuple is the sole native C2 contribution catalog.  Runtime consumers and
# the factory-free generated projections both derive from it.
source_native_contribution = compile_source_native_contribution(DEFAULT_SOURCE_NATIVE_SOURCE)
if isinstance(source_native_contribution, Failure):
    raise RuntimeError(f"invalid default C2 native contribution: {source_native_contribution.message}")
source_native_catalog = (source_native_contribution,)


source_verification_plan = source_verification_plan_for()
_registered_verification_callbacks: dict[str, Callable[[], object]] = {}


def _register_verification_runner(name: str, run: Callable[[], object]) -> None:
    """Existing verification runner target: collect plan callbacks without running them."""

    _registered_verification_callbacks[name] = run


_registration = register_verification_plan(source_verification_plan, _register_verification_runner)
if isinstance(_registration, Failure):
    raise RuntimeError(f"invalid C2 verification registration: {_registration.message}")
source_verification_registration: VerificationRegistration | None = _registration

_verification_plan_witness_ids = (
    *(item.id for item in source_verification_plan.prerequisites),
    *(item.witness.id for item in source_verification_plan.checks),
)
source_verification_law_witnesses: tuple[LawWitness, ...] = tuple(
    LawWitness(
        witness_id,
        _registered_verification_callbacks[f"test:{witness_id}"],
    )
    for witness_id in _verification_plan_witness_ids
)
source_law_witnesses: tuple[LawWitness, ...] = (_catalog_law, *source_verification_law_witnesses)
source_law_witness_references = tuple(
    law_witness_reference(witness) for witness in source_law_witnesses
)

source_contribution_catalog = tuple(native.projection for native in source_native_catalog)
source_native_catalog = source_native_catalog
source_contribution_catalog = source_contribution_catalog
source_law_witnesses = source_law_witnesses
source_law_witness_references = source_law_witness_references
source_verification_law_witnesses = source_verification_law_witnesses
source_verification_plan = source_verification_plan
source_verification_plan_for = source_verification_plan_for
source_verification_registration = source_verification_registration

contribution_catalog = ContributionCatalog(
    contributions=source_contribution_catalog,
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = [
    "source_contribution_catalog",
    "source_law_witness_references",
    "source_law_witnesses",
    "source_native_catalog",
    "source_native_contribution",
    "source_verification_law_witnesses",
    "source_verification_plan",
    "source_verification_plan_for",
    "source_verification_registration",
    "contribution_catalog",
    "source_contribution_catalog",
    "source_law_witness_references",
    "source_law_witnesses",
    "source_native_catalog",
    "source_verification_law_witnesses",
    "source_verification_plan",
    "source_verification_plan_for",
    "source_verification_registration",
]
